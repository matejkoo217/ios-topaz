#!/usr/bin/env python3
"""Independent validator and round-trip verification for fuxi Apple Device Tree (.adt).

Reads raw ADT bytes from disk, unpacks them independently of mkadt.py, and asserts
that all required fuxi hardware constants are present in the actual serialized bytes:
  - GICD: 0x17100000 (distributor)
  - GICR: 0x17180000 (redistributor base)
  - GICR stride: 0x40000 (256 KiB redistributor stride)
  - Timer: 0x17420000 (arch_mem_timer frame)
  - Timer PPIs: 27 (virtual) and 30 (physical)
  - 8 CPUs: cores 0..7 with MPIDR Aff1 = core << 8 (0x000..0x700)
  - Memory ranges: /chosen dram-base/dram-size, sweet-fbcon, sweet-ufs

Exit code: 0 on complete pass, 1 on any assertion failure.
"""
import struct, sys


class AdtParser:
    def __init__(self, data):
        self.data = data

    def parse_node(self, off=0):
        nprops, nchildren = struct.unpack_from('<II', self.data, off)
        off += 8
        props = {}
        for _ in range(nprops):
            raw_name = self.data[off:off + 32].split(b'\0')[0].decode('latin1')
            size, = struct.unpack_from('<I', self.data, off + 32)
            flags = size >> 31
            val_len = size & 0x7fffffff
            val = self.data[off + 36:off + 36 + val_len]
            props[raw_name] = (flags, val)
            off += 36 + ((val_len + 3) & ~3)
        children = {}
        for _ in range(nchildren):
            child, off = self.parse_node(off)
            name = child['props'].get('name', (0, b'?\0'))[1].split(b'\0')[0].decode('latin1')
            children[name] = child
        return {'props': props, 'children': children}, off


def u32(val_bytes):
    return struct.unpack('<I', val_bytes)[0]


def u64(val_bytes):
    return struct.unpack('<Q', val_bytes)[0]


def u64_list(val_bytes):
    count = len(val_bytes) // 8
    return list(struct.unpack(f'<{count}Q', val_bytes))


def main():
    adt_path = sys.argv[1] if len(sys.argv) > 1 else 'xnu/out/fuxi.adt'
    print(f'=== Verifying ADT: {adt_path} ===')
    with open(adt_path, 'rb') as f:
        raw_bytes = f.read()
    print(f'Total file size: {len(raw_bytes)} bytes')

    parser = AdtParser(raw_bytes)
    root, end_off = parser.parse_node(0)
    assert end_off == len(raw_bytes), f'Trailing bytes in ADT: {end_off} != {len(raw_bytes)}'

    checks = []

    def check(desc, passed, detail=''):
        status = 'PASS' if passed else 'FAIL'
        checks.append((desc, status, detail))
        print(f'[{status}] {desc}: {detail}')
        if not passed:
            raise AssertionError(f'Check failed: {desc} -> {detail}')

    # 1. Root compatible string
    compat_flags, compat_raw = root['props']['compatible']
    compat_str = compat_raw.decode('latin1')
    check('Root compatible contains xiaomi,fuxi', 'xiaomi,fuxi' in compat_str, compat_str)
    check('Root compatible contains qcom,kalama', 'qcom,kalama' in compat_str, compat_str)
    check('Root compatible contains AppleARM', 'AppleARM' in compat_str, compat_str)

    # 2. Chosen node and memory ranges
    chosen = root['children']['chosen']
    dram_base = u64(chosen['props']['dram-base'][1])
    dram_size = u64(chosen['props']['dram-size'][1])
    check('DRAM base is valid high bank (0x880000000 or 0x8c0000000)',
          dram_base in (0x880000000, 0x8c0000000), f'0x{dram_base:x}')
    check('DRAM size >= 768 MiB (0x30000000)',
          dram_size >= 0x30000000, f'0x{dram_size:x} ({dram_size // (1024*1024)} MiB)')
    chip_id = u32(chosen['props']['chip-id'][1])
    check('A11 chip-id for iOS 16 userland is 0x8015', chip_id == 0x8015, f'0x{chip_id:x}')

    # 3. CPUs node: 8 cores with MPIDRs
    cpus = root['children']['cpus']
    check('cpus node contains 8 CPU children', len(cpus['children']) == 8, f'{len(cpus["children"])} CPUs')
    for core in range(8):
        cname = f'cpu{core}'
        check(f'{cname} child exists', cname in cpus['children'], cname)
        cpu_node = cpus['children'][cname]
        reg = u32(cpu_node['props']['reg'][1])
        expected_mpidr = core << 8
        check(f'{cname} MPIDR reg == 0x{expected_mpidr:03x}', reg == expected_mpidr, f'0x{reg:03x}')
        cluster_id = u32(cpu_node['props']['cluster-id'][1])
        check(f'{cname} cluster-id == {core}', cluster_id == core, f'{cluster_id}')

    # 4. arm-io bus and GIC
    arm_io = root['children']['arm-io']
    ranges = u64_list(arm_io['props']['ranges'][1])
    check('arm-io ranges has 3 u64 cells (child, parent, size)', len(ranges) == 3, f'{[hex(x) for x in ranges]}')
    child_base, soc_base, window_size = ranges
    check('arm-io parent SOC_BASE == 0x01000000', soc_base == 0x01000000, f'0x{soc_base:x}')

    gic = arm_io['children']['gic']
    gic_reg = u64_list(gic['props']['reg'][1])
    check('gic reg has 4 u64 cells (gicd_rel, gicd_len, gicr_rel, gicr_len)', len(gic_reg) == 4, f'{[hex(x) for x in gic_reg]}')
    gicd_phys = soc_base + gic_reg[0]
    gicd_len = gic_reg[1]
    gicr_phys = soc_base + gic_reg[2]
    gicr_len = gic_reg[3]

    check('GICD distributor address == 0x17100000', gicd_phys == 0x17100000, f'0x{gicd_phys:x}')
    check('GICD distributor size == 0x10000', gicd_len == 0x10000, f'0x{gicd_len:x}')
    check('GICR redistributor base == 0x17180000', gicr_phys == 0x17180000, f'0x{gicr_phys:x}')
    check('GICR redistributor size == 0x200000', gicr_len == 0x200000, f'0x{gicr_len:x}')

    gic_dist_prop = u64(gic['props']['distributor-base'][1])
    gic_rdist_prop = u64(gic['props']['redistributor-base'][1])
    check('GIC distributor-base property == 0x17100000', gic_dist_prop == 0x17100000, f'0x{gic_dist_prop:x}')
    check('GIC redistributor-base property == 0x17180000', gic_rdist_prop == 0x17180000, f'0x{gic_rdist_prop:x}')

    stride_prop = u32(gic['props']['redistributor-stride'][1])
    check('GIC redistributor-stride == 0x40000 (256 KiB)', stride_prop == 0x40000, f'0x{stride_prop:x}')
    stride_short = u32(gic['props']['stride'][1])
    check('GIC stride property == 0x40000', stride_short == 0x40000, f'0x{stride_short:x}')

    vtimer_intid = u32(gic['props']['virtual-timer-intid'][1])
    check('GIC virtual-timer-intid == 27 (GIC_PPI 11)', vtimer_intid == 27, f'{vtimer_intid}')
    ptimer_intid = u32(gic['props']['physical-timer-intid'][1])
    check('GIC physical-timer-intid == 30 (GIC_PPI 14)', ptimer_intid == 30, f'{ptimer_intid}')

    # 5. Timer frame nodes (both in arm-io and root sweet-timer)
    timer_armio = arm_io['children']['timer']
    timer_reg = u64_list(timer_armio['props']['reg'][1])
    timer_phys = soc_base + timer_reg[0]
    check('arm-io/timer frame address == 0x17420000', timer_phys == 0x17420000, f'0x{timer_phys:x}')
    check('arm-io/timer phys-addr property == 0x17420000', u64(timer_armio['props']['phys-addr'][1]) == 0x17420000, '0x17420000')

    fuxi_timer = root['children']['sweet-timer']
    fuxi_timer_reg = u64_list(fuxi_timer['props']['reg'][1])
    check('sweet-timer root node reg == 0x17420000', fuxi_timer_reg[0] == 0x17420000, f'0x{fuxi_timer_reg[0]:x}')
    check('sweet-timer vtimer-intid == 27', u32(fuxi_timer['props']['virtual-timer-intid'][1]) == 27, '27')
    check('sweet-timer ptimer-intid == 30', u32(fuxi_timer['props']['physical-timer-intid'][1]) == 30, '30')
    check('sweet-timer stride == 0x40000', u32(fuxi_timer['props']['stride'][1]) == 0x40000, '0x40000')

    # 6. Continuous splash framebuffer (sweet-fbcon)
    fbcon = root['children']['sweet-fbcon']
    fb_reg = u64_list(fbcon['props']['reg'][1])
    check('sweet-fbcon splash address == 0xb8000000', fb_reg[0] == 0xb8000000, f'0x{fb_reg[0]:x}')
    check('sweet-fbcon splash size == 0x2b00000 (43.0 MiB)', fb_reg[1] == 0x2b00000, f'0x{fb_reg[1]:x}')
    fb_w = u32(fbcon['props']['width'][1])
    fb_h = u32(fbcon['props']['height'][1])
    fb_stride = u32(fbcon['props']['stride'][1])
    check('sweet-fbcon geometry 1080x2400', fb_w == 1080 and fb_h == 2400, f'{fb_w}x{fb_h}')
    check('sweet-fbcon stride == 4320 (1080*4)', fb_stride == 4320, f'{fb_stride}')

    # 7. Internal UFS host controller
    ufs = root['children']['sweet-ufs']
    ufs_reg = u64_list(ufs['props']['reg'][1])
    check('sweet-ufs host address == 0x01d84000', ufs_reg[0] == 0x01d84000, f'0x{ufs_reg[0]:x}')
    check('sweet-ufs register window size == 0x3000', ufs_reg[1] == 0x3000, f'0x{ufs_reg[1]:x}')

    print(f'\n=== ALL {len(checks)} ADT ASSERTIONS PASSED! ===')
    return 0


if __name__ == '__main__':
    sys.exit(main())

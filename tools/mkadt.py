#!/usr/bin/env python3
"""Build the minimal Apple Device Tree that xnu needs to boot on Qualcomm SoCs.

Supports both:
  - fuxi (Xiaomi 13, SM8550 "kalama") [DEFAULT]
  - topaz (Redmi Note 12 4G, SM6225 "khaje") [reference]

Usage:
  mkadt.py [OUT.adt] [--machine {fuxi,topaz}] [--dump] [--qemu] [--highmem] [--native]
"""
import argparse, hashlib, os, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adt  # noqa: E402

# ==============================================================================
# Helper functions for ADT construction
# ==============================================================================
u32 = lambda *v: struct.pack('<%dI' % len(v), *v)
u64 = lambda *v: struct.pack('<%dQ' % len(v), *v)
cstr = lambda s: s.encode() + b'\0'


def node(name, props=(), children=()):
    n = adt.Node()
    n.props = [('name', 0, cstr(name))] + [(k, 0, v) for k, v in props]
    n.children = list(children)
    return n


# The iOS userland is the iPhone X (iPhone10,3 / D22AP) IPSW. MobileGestalt
# derives product type, device class, home-button-less UI, artwork etc. from
# the root identity and /product of the real D22AP device tree.
D22AP_ADT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '../research/ipsw-x/d22ap.adt')


def d22ap_product(path=D22AP_ADT):
    """/product properties of the real D22AP tree, without the syscfg
    placeholders iBoot would fill in (flag bit set) and the node bookkeeping."""
    if not os.path.exists(path):
        return None
    try:
        root, _ = adt.parse(open(path, 'rb').read())
        for c in root.children:
            if dict((k, v) for k, f, v in c.props).get('name') == b'product\0':
                return [(k, v) for k, v in c.props if not f and k not in ('name', 'AAPL,phandle')]
    except Exception as e:
        print(f'warning: failed to parse {path}: {e}', file=sys.stderr)
        return None
    return None


# ==============================================================================
# QEMU virt constants (-M virt,gic-version=3 -cpu cortex-a76)
# ==============================================================================
QEMU_GICD = 0x08000000
QEMU_GICR = 0x080a0000
QEMU_TIMEBASE = 62500000
QEMU_VTIMER_INTID = 27

# ==============================================================================
# Machine Configurations
# ==============================================================================

MACHINES = {
    'topaz': {
        'name': 'topaz',
        'soc_name': 'khaje',
        'compat_root': [
            'D22AP', 'iPhone10,3', 'xiaomi,topaz', 'xiaomi,sweet', 'qcom,khaje', 'AppleARM'
        ],
        'phys_base': 0xb0000000,
        'mem_size': 0x4d000000,
        'high_phys_base': 0x140000000,
        'high_mem_size': 0x100000000,
        'soc_base': 0x01000000,
        'gicd': 0x0f200000,
        'gicd_size': 0x10000,
        'gicr': 0x0f300000,
        'gicr_size': 0x100000,
        'gicr_stride': 0x20000,
        'timer_base': 0,
        'timer_size': 0,
        'vtimer_intid': 19,
        'ptimer_intid': 18,
        'fb': 0x5c000000,
        'fb_size': 0xf00000,
        'fb_w': 1080,
        'fb_h': 2400,
        'fb_stride': 1080 * 4,
        'ufs': 0x04804000,
        'ufs_size': 0x3000,
        'timebase': 19200000,
        'ecid': 0x544f50415a000001,  # 'TOPAZ' + 1
        'boot_manifest_hash': hashlib.sha384(b'topaz boot manifest').digest(),
        'firmware_version': 'topaz-shim',
        'nr_cpus': 4,
        'cpu_reg': lambda i: 0x100 | i,
        'cpu_compat': lambda i: cstr('qcom,kryo260') + cstr('qcom,kryo470') + cstr('ARM,v8'),
        'cpu_freq': lambda i: 2803200000,
        'has_ufs': True,
    },
    'fuxi': {
        'name': 'fuxi',
        'soc_name': 'kalama',
        'compat_root': [
            'D22AP', 'iPhone10,3', 'xiaomi,fuxi', 'xiaomi,sweet', 'qcom,kalama', 'qcom,sm8550', 'AppleARM'
        ],
        # Kernel-managed RAM: High DDR bank (SM8550_FACTS.md §8 lines 506-508, iomem.txt:289)
        # 0x8_80000000 – 0x8_BB2FFFFF is 947 MiB of contiguous uncarved System RAM.
        # [VERIFIED: iomem.txt line 289, SM8550_FACTS.md §8 line 506]
        'phys_base': 0x880000000,
        'mem_size': 0x3b000000,       # 944 MiB (fits inside 947 MiB 0x880000000-0x8bb2fffff)
        # Highmem: 0x8c0000000 – 0x9ffffffff (5120 MiB System RAM; carve-outs start at 0x9ef990000)
        # [VERIFIED: iomem.txt line 291, SM8550_FACTS.md §8 line 508]
        'high_phys_base': 0x8c0000000,
        'high_mem_size': 0xb0000000,  # 2816 MiB = 2.75 GiB (clear of 0x9ef990000 carve-out)
        'soc_base': 0x01000000,       # /arm-io ranges base (must be non-zero for serial_init)
        # GICD: Distributor @ 0x17100000, size 0x10000
        # [VERIFIED: SM8550_FACTS.md §1 line 62, DT-kalama:803, ML-sm8550, PORT_FUXI.md §6 line 82]
        'gicd': 0x17100000,
        'gicd_size': 0x10000,
        # GICR: Redistributors @ 0x17180000, size 0x200000 (8 cores * 0x40000 stride)
        # [VERIFIED: SM8550_FACTS.md §1 line 63, DT-kalama:804, ML-sm8550, PORT_FUXI.md §6 line 82]
        'gicr': 0x17180000,
        'gicr_size': 0x200000,
        'gicr_stride': 0x40000,
        # GIC ITS: @ 0x17140000, size 0x40000
        # [VERIFIED: SM8550_FACTS.md §1 line 64, DT-kalama:812, ML-sm8550]
        'gic_its': 0x17140000,
        'gic_its_size': 0x40000,
        # Architected memory-mapped timer frame0 @ 0x17420000, size 0x1000
        # [VERIFIED: SM8550_FACTS.md §3 line 200, iomem.txt:243, DT-kalama:984, PORT_FUXI.md §6 line 83]
        'timer_base': 0x17420000,
        'timer_size': 0x1000,
        # Timer PPIs: standard ARM numbering (GIC_PPI 11 -> INTID 27, GIC_PPI 14 -> INTID 30)
        # [VERIFIED: SM8550_FACTS.md §3 lines 203, 213, DT-kalama:861, PORT_FUXI.md §6 line 83]
        'vtimer_intid': 27,
        'ptimer_intid': 30,
        # Continuous splash framebuffer @ 0xb8000000, size 0x2b00000 (43.0 MiB)
        # [VERIFIED: SM8550_FACTS.md §6 line 386, reserved-memory.txt:33, iomem.txt:279, PORT_FUXI.md §6 line 78]
        'fb': 0xb8000000,
        'fb_size': 0x2b00000,
        'fb_w': 1080,
        'fb_h': 2400,
        'fb_stride': 1080 * 4,        # 4320 bytes [INFERRED: standard 1080x4bpp, SM8550_FACTS.md §6 line 407]
        # Internal UFS host controller @ 0x01d84000, size 0x3000 ("ufshc@1d84000")
        # [VERIFIED: SM8550_FACTS.md §2 line 113, iomem.txt:10, DT-kalama:1932, PORT_FUXI.md §6 line 81]
        'ufs': 0x01d84000,
        'ufs_size': 0x3000,
        'timebase': 19200000,         # 19.2 MHz [VERIFIED: SM8550_FACTS.md §3 line 202]
        'ecid': 0x4655584900000001,   # 'FUXI' + 1 (synthetic ECID)
        'boot_manifest_hash': hashlib.sha384(b'fuxi boot manifest').digest(),
        'firmware_version': 'fuxi-shim',
        # 8 cores: 1x Cortex-X3 + 2x Cortex-A715 + 2x Cortex-A710 + 3x Cortex-A510
        # MPIDR: reg = core << 8 (0x000, 0x100, ..., 0x700)
        # [VERIFIED: SM8550_FACTS.md §4 line 234, dt-cpus.txt, DT-kalama:67, PORT_FUXI.md §6 line 85, D2 line 170]
        'nr_cpus': 8,
        'cpu_reg': lambda i: i << 8,
        'cpu_compat': lambda i: (
            cstr('arm,cortex-a510') if i in (0, 1, 2) else
            cstr('arm,cortex-a715') if i in (3, 4) else
            cstr('arm,cortex-a710') if i in (5, 6) else
            cstr('arm,cortex-x3')
        ) + cstr('qcom,kalama') + cstr('qcom,kryo470') + cstr('ARM,v9') + cstr('ARM,v8'),
        'cpu_freq': lambda i: (
            2000000000 if i in (0, 1, 2) else
            2800000000 if i in (3, 4, 5, 6) else
            3187200000
        ),
        'has_ufs': True,
    }
}


def build(machine='fuxi', seed=None, qemu=False, highmem=False, native=False):
    """Build the minimal Apple Device Tree for machine ('fuxi' or 'topaz')."""
    mach = MACHINES[machine]
    phys_base, mem_size = (mach['high_phys_base'], mach['high_mem_size']) if highmem else (mach['phys_base'], mach['mem_size'])
    gicd, gicr = (QEMU_GICD, QEMU_GICR) if qemu else (mach['gicd'], mach['gicr'])
    gicd_size, gicr_size = mach['gicd_size'], mach['gicr_size']
    timebase = QEMU_TIMEBASE if qemu else mach['timebase']
    vtimer_intid = QEMU_VTIMER_INTID if qemu else mach['vtimer_intid']
    ptimer_intid = mach['ptimer_intid']
    soc_base = mach['soc_base']

    seed = seed if seed is not None else os.urandom(64)
    phandle = iter(range(1, 1000))
    ph = lambda: ('AAPL,phandle', u32(next(phandle)))

    chosen = node('chosen', [
        ph(),
        ('dram-base', u64(phys_base)),
        ('dram-size', u64(mem_size)),
        ('random-seed', seed),
        ('debug-enabled', u32(1)),
        ('firmware-version', cstr(mach['firmware_version'])),
        ('system-firmware-version', cstr(mach['firmware_version'])),
        # iBoot's SHA-384 of the boot manifest; /sbin/mount -P 1 exits unless
        # it exists (bind mounts /private/preboot/<hex>/usr/standalone/firmware,
        # tolerating a missing directory). Fixed stand-in value.
        ('boot-manifest-hash', mach['boot_manifest_hash']),
        # libimg4 (cryptexd) aborts "failed to get crypto algorithm" without
        # it; real A11+ device trees say sha2-384.
        ('crypto-hash-method', cstr('sha2-384')),
        # MobileGestalt's screen class: display-scale (u32, default 0) comes
        # from /chosen, the pixel size from IOMobileFramebuffer. Scale 0 makes
        # SpringBoard's FBSDisplayMode "infxinf@0x" invalid. 1080x2400 @3x =
        # 360x800 points (like iPhone X class devices).
        ('display-scale', u32(3)),
        # XNU derives IOPlatformUUID (gethostuuid) from these on arm; without
        # them CFPreferences cannot use kCFPreferencesCurrentHost (no ByHost
        # files), so e.g. DataMigration never records LastSystemVersion and
        # migrates on every boot. Synthetic ECID (not the phone's); chip-id
        # of the A11 that the iPhone X userland expects.
        ('unique-chip-id', struct.pack('<Q', mach['ecid'])),
        ('chip-id', u32(0x8015)),
        # Security status as on a dev-fused, undemoted board (tuple 0,0,1,1):
        # MobileGestalt reads these from /chosen, and mobileactivationd's
        # DeviceType then takes its native "Hactivation" branch (state
        # Activated without an activation record; no SEP, no baseband here).
        ('certificate-production-status', u32(0)),
        ('effective-production-status-ap', u32(0)),
        ('certificate-security-mode', u32(1)),
        ('effective-security-mode-sep', u32(1)),
    ], [node('memory-map', [ph()]),
        # Local boot policy (kern_csr.c): SIP relaxed like `csrutil disable`
        # (lp-sip0: untrusted kexts, unrestricted FS, task_for_pid, kernel
        # debugger, dtrace, nvram), lp-sip1: unauthenticated (unsealed) root.
        # The iOS shared cache is in no trust cache, so dyld can only map it
        # with CSR_ALLOW_UNRESTRICTED_FS (vm_unix.c shared region checks).
        node('asmb', [ph(), ('lp-sip0', u64(0x6f)), ('lp-sip1', u32(1))])])

    # CPUs
    nr_cpus = 1 if qemu else mach['nr_cpus']
    cpu_nodes = []
    for core in range(nr_cpus):
        mpidr = core if qemu else mach['cpu_reg'](core)
        # In fuxi, each core has its own Aff1 cluster ID: MPIDR_CLUSTER_ID = core (0..7).
        # In topaz, all 4 Gold cores share cluster 0.
        cluster_id = core if (mach['name'] == 'fuxi' and not qemu) else 0
        cpu_nodes.append(node(f'cpu{core}', [
            ph(),
            ('device_type', cstr('cpu')),
            ('compatible', mach['cpu_compat'](core)),
            ('reg', u32(mpidr)),  # actual MPIDR Aff1:Aff0, NOT logical ID
            ('cpu-id', u32(core)),   # descriptive: XNU assigns IDs by DT order
            ('cluster-id', u32(cluster_id)),
            ('cluster-type', u32(0)),  # homogeneous CLUSTER_TYPE_SMP, not AMP
            ('die-cluster-id', u32(cluster_id)),
            ('cluster-core-id', u32(0 if mach['name'] == 'fuxi' else core)),
            ('l2-cache-id', u32(cluster_id)),
            ('l3-cache-id', u32(0)),
            ('state', cstr('running' if core == 0 else 'stopped')),
            ('timebase-frequency', u32(timebase)),
            ('clock-frequency', u32(mach['cpu_freq'](core))),
            ('bus-frequency', u32(100000000)),
            ('memory-frequency', u32(1866000000)),
            ('peripheral-frequency', u32(timebase)),
            ('fixed-frequency', u32(timebase)),
        ]))
    cpus = node('cpus', [ph(), ('#address-cells', u32(1)),
                         ('#size-cells', u32(0))], cpu_nodes)

    # GIC
    gic_props = [
        ph(),
        ('compatible', cstr('arm,gic-v3')),
        ('interrupt-controller', b''),
        ('virtual-timer-intid', u32(vtimer_intid)),
        ('physical-timer-intid', u32(ptimer_intid)),
        ('redistributor-stride', u32(mach['gicr_stride'])),
        ('stride', u32(mach['gicr_stride'])),
        ('distributor-base', u64(gicd)),
        ('redistributor-base', u64(gicr)),
        ('reg', u64(gicd - soc_base, gicd_size, gicr - soc_base, gicr_size)),
    ]
    if mach.get('timer_base'):
        gic_props.append(('timer-base', u64(mach['timer_base'])))
    if mach.get('gic_its'):
        gic_props.append(('its-base', u64(mach['gic_its'])))
    gic = node('gic', gic_props)

    arm_io_children = [
        gic,
        # No hardware: watchdogd checks IODeviceTree:/arm-io/wdt for no-pmu and
        # otherwise crashes trying to set the PMU boot stage (customer builds
        # ignore the -wdt_no_pmu boot-arg).
        node('wdt', [ph(), ('no-pmu', u32(1))]),
        # Main display: IOMobileFramebuffer.framework counts /arm-io children
        # with this device_type and reads the canvas size from the node
        # (the presented iPhone X size, see SweetFramebuffer.cpp);
        # the kernel's AppleCLCD matches the compatible string.
        node('disp0', [
            ph(),
            ('device_type', cstr('display-subsystem')),
            ('compatible', cstr('sweet,display')),
            # --native: present the real 1080x2400 panel (needed for direct MDP scanout,
            # which must match the canvas: sweetfb_native=1 with a 1125x2436 canvas makes
            # backboardd ask for a hardware scaler that does not exist)
            ('canvas-width', u32(1080 if native else 1125)),
            ('canvas-height', u32(2400 if native else 2436)),
        ]),
    ]

    # Timer frame node (SM8550 arch_mem_timer @ 0x17420000)
    if mach.get('timer_base') and not qemu:
        timer = node('timer', [
            ph(),
            ('compatible', cstr('arm,armv8-timer-mem') + cstr('qcom,arch-mem-timer')),
            ('reg', u64(mach['timer_base'] - soc_base, mach['timer_size'])),
            ('phys-addr', u64(mach['timer_base'])),
            ('virtual-timer-intid', u32(vtimer_intid)),
            ('physical-timer-intid', u32(ptimer_intid)),
            ('clock-frequency', u32(timebase)),
        ])
        arm_io_children.append(timer)

    arm_io = node('arm-io', [
        ph(),
        ('device_type', cstr('sweet-io')),
        ('compatible', cstr('sweet-io') + cstr('arm-io')),
        ('#address-cells', u32(2)),
        ('#size-cells', u32(2)),
        ('ranges', u64(0, soc_base, 0x100000000 - soc_base)),
    ], arm_io_children)

    fbcon = node('sweet-fbcon', [
        ph(),
        ('reg', u64(mach['fb'], mach['fb_size'])),
        ('width', u32(mach['fb_w'])),
        ('height', u32(mach['fb_h'])),
        ('stride', u32(mach['fb_stride'])),
    ])

    # bsd/dev/sweet_ufs.c: the UFS host ABL leaves running (absolute physical reg).
    ufs = node('sweet-ufs', [
        ph(),
        ('compatible', cstr('qcom,ufshc')),
        ('reg', u64(mach['ufs'], mach['ufs_size'])),
    ])

    # Direct sweet-timer root node for hardware timer frame reference
    sweet_timer_nodes = []
    if mach.get('timer_base') and not qemu:
        sweet_timer_nodes.append(node('sweet-timer', [
            ph(),
            ('compatible', cstr('qcom,arch-mem-timer')),
            ('reg', u64(mach['timer_base'], mach['timer_size'])),
            ('virtual-timer-intid', u32(vtimer_intid)),
            ('physical-timer-intid', u32(ptimer_intid)),
            ('stride', u32(mach['gicr_stride'])),
        ]))

    # pmap_compute_max_asids requires the node even when no overrides are set.
    # An absent pmap-max-asids property selects XNU's own MAX_ASIDS default.
    # No effaceable storage: keybagd then reads /private/var/keybags/systembag.kb
    # as a plain plist instead of decrypting it with the effaceable key.
    defaults = node('defaults', [ph(), ('no-effaceable-storage', u32(1))])

    # MobileGestalt HomeButtonType = IODeviceTree:/buttons home-button-type
    # (D22AP: 2, no Home button; absent = 0 = Home-button device).
    buttons = node('buttons', [
        ph(),
        ('button-names', cstr('volup') + cstr('voldown') + cstr('hold')),
        ('home-button-type', u32(2)),
        ('opposed-power-vol-buttons', u32(1)),
    ])

    product_props = d22ap_product()
    product = [node('product', [ph()] + product_props)] if product_props else []

    compat_root_str = b''.join(cstr(c) for c in mach['compat_root'])

    root_children = [chosen, defaults, cpus, arm_io, fbcon, buttons] + product + sweet_timer_nodes
    if not qemu and mach['has_ufs']:
        root_children.append(ufs)

    # Identity of the iPhone X whose userland runs here: compatible[0] is
    # hw.model/hw.target (D22AP), model is hw.machine/hw.product
    # (iPhone10,3). 'xiaomi,sweet' and qcom,kryo470 stay because the
    # SweetPlatformExpert and CPU IONameMatch still use them.
    return node('device-tree', [
        ph(),
        ('compatible', compat_root_str),
        ('model', cstr('iPhone10,3')),
        ('target-type', cstr('D22')),
        ('target-sub-type', cstr('D22AP')),
        ('manufacturer', cstr('Apple Inc.')),
        ('#address-cells', u32(2)),
        ('#size-cells', u32(2)),
    ], root_children)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('out', nargs='?', default=None, help='Output ADT file path (default: stdout dump or xnu/out/fuxi.adt)')
    ap.add_argument('--machine', choices=['fuxi', 'topaz'], default=None,
                    help='Machine target (default: fuxi, or topaz if "topaz" in out path)')
    ap.add_argument('--dump', action='store_true', help='Dump parsed tree to stdout')
    ap.add_argument('--qemu', action='store_true', help='Build for QEMU virt')
    ap.add_argument('--highmem', action='store_true', help='Use high DDR bank')
    ap.add_argument('--native', action='store_true', help='Present native 1080x2400 panel resolution')
    a = ap.parse_args()

    # Determine machine
    machine = a.machine
    if not machine:
        if a.out and 'topaz' in a.out.lower():
            machine = 'topaz'
        else:
            machine = 'fuxi'

    root = build(machine=machine, qemu=a.qemu, highmem=a.highmem, native=a.native)
    blob = adt.serialize(root)

    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with open(a.out, 'wb') as f:
            f.write(blob)
        print(f'{a.out}: {len(blob)} bytes ({machine})', file=sys.stderr)

    if a.dump or not a.out:
        parsed_root, _ = adt.parse(blob)
        adt.dump(parsed_root)

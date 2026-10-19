# ADT_FUXI — Apple Device Tree Generator Retargeting for Xiaomi 13 (fuxi, SM8550)

This report documents the retargeting of the Apple Device Tree (ADT) generator `tools/mkadt.py`
from the topaz (SM6225 "khaje") reference SoC to the Xiaomi 13 (`fuxi`, Qualcomm SM8550 "kalama"),
the generation of `xnu/out/fuxi.adt`, the generation and validation of `xnu/out/fuxi.payload`,
and the production of the bootable Android boot image v4 `shim/out/shim-boot.img`.

---

## 1. Hardware Constants & Authoritative Citations

Every address and constant emitted into `xnu/out/fuxi.adt` derives from primary device dumps
or vendor device trees, cross-checked against `device-dumps/SM8550_FACTS.md` and `PORT_FUXI.md` §6.

| Item | Value | Source Citation | Status | Purpose / Architecture Note |
|---|---|---|---|---|
| **Distributor (GICD)** | `0x17100000` (size `0x10000`) | `SM8550_FACTS.md` §1 line 62, `[DT-kalama]:803`, `[ML-sm8550]`, `PORT_FUXI.md` §6 line 82 | **VERIFIED** | GICv3 Distributor base. Relative to `arm-io` parent `0x01000000`, emitted as `0x16100000`. |
| **Redistributor (GICR)** | `0x17180000` (size `0x200000`) | `SM8550_FACTS.md` §1 line 63, `[DT-kalama]:804`, `[ML-sm8550]`, `PORT_FUXI.md` §6 line 82 | **VERIFIED** | GICv3 Redistributor base covering 8 cores. Relative to `arm-io`, emitted as `0x16180000`. |
| **GICR Stride** | `0x40000` (256 KiB) | `SM8550_FACTS.md` §1 line 63, `PORT_FUXI.md` §6 line 82, `FUXI.h` line 283 | **VERIFIED** | Redistributor stride for SM8550 (GIC-600 with ITS). Contrast with topaz's `0x20000`. |
| **GIC ITS / MSI** | `0x17140000` (size `0x40000`) | `SM8550_FACTS.md` §1 line 64, `[DT-kalama]:812`, `[ML-sm8550]` | **VERIFIED** | GICv3 Interrupt Translation Service (PCIe/Wi-Fi MSI frame). |
| **Virtual Timer PPI** | `27` (`GIC_PPI 11`) | `SM8550_FACTS.md` §3 line 203, 213, `[DT-kalama]:861`, `PORT_FUXI.md` §6 line 83 | **VERIFIED** | Non-secure view of `CNTV` per standard ARM architected timer mapping. Contrast with topaz's `19`. |
| **Physical Timer PPI** | `30` (`GIC_PPI 14`) | `SM8550_FACTS.md` §3 line 203, 213, `[DT-kalama]:861`, `PORT_FUXI.md` §6 line 83 | **VERIFIED** | Non-secure view of `CNTP`. Contrast with topaz's `18`. |
| **Timer Memory Frame** | `0x17420000` (size `0x1000`) | `SM8550_FACTS.md` §3 line 200, `device-dumps/iomem.txt`:243 (`arch_mem_timer`) | **VERIFIED** | Architected memory-mapped timer frame0 (`timer@17420000`). Relative to `arm-io`, emitted as `0x16420000`. |
| **Timer Frequency** | `19200000` Hz (19.2 MHz) | `SM8550_FACTS.md` §3 line 202, `[DT-kalama]:867,990`, `[ML-sm8550]` | **VERIFIED** | Counter frequency (`cntfrq_el0`) across all 8 cores. |
| **DRAM Base (`dram-base`)** | `0x880000000` (34.0 GiB) | `SM8550_FACTS.md` §8 line 506, `device-dumps/iomem.txt`:289, `PORT_FUXI.md` line 31 | **VERIFIED** | High DDR bank base. Contains 947 MiB (`0x880000000`–`0x8bb2fffff`) of completely uncarved contiguous System RAM. |
| **DRAM Size (`dram-size`)** | `0x3b000000` (944 MiB) | `device-dumps/iomem.txt`:289, `PORT_FUXI.md` line 31 | **VERIFIED** | Managed memory pool fitting safely within the 947 MiB high bank chunk, leaving 3 MiB headroom. |
| **Highmem DRAM Base** | `0x8c0000000` (35.0 GiB) | `SM8550_FACTS.md` §8 line 508, `device-dumps/iomem.txt`:291 | **VERIFIED** | Upper high DDR bank pool (`--highmem` flag). |
| **Highmem DRAM Size** | `0xb0000000` (2816 MiB) | `SM8550_FACTS.md` §8 line 508, `device-dumps/iomem.txt`:291 | **VERIFIED** | 2.75 GiB uncarved contiguous System RAM before `0x9ef990000` carve-out. |
| **Continuous Splash FB** | `0xb8000000` (size `0x2b00000`) | `SM8550_FACTS.md` §6 line 386, `device-dumps/reserved-memory.txt`:33, `iomem.txt`:279 | **VERIFIED** | 43.0 MiB `splash_region` reserved by ABL to maintain display pipeline scanout. |
| **Panel Geometry** | `1080 × 2400`, 32 bpp | `SM8550_FACTS.md` §6 line 362, `device-dumps/dmesg-hints.txt`:3 | **VERIFIED** | OLED panel geometry. Presentation canvas defaults to iPhone X `1125 × 2436` (or `1080 × 2400` with `--native`). |
| **Panel Stride** | `4320` bytes (`1080 * 4`) | `SM8550_FACTS.md` §6 line 407, `[ML-q5q]` | **INFERRED** | Linear 32bpp framebuffer stride. Standard 4-byte packed RGB/BGR line. |
| **UFS Host Controller** | `0x01d84000` (size `0x3000`) | `SM8550_FACTS.md` §2 line 113, `device-dumps/iomem.txt`:10, `[DT-kalama]:1932` | **VERIFIED** | `ufshc@1d84000` register window (`ufs_mem`). Internal UFS 4.0 host controller left initialized by ABL. |
| **IMEM Restart Reason** | `0x146aa65c` | `SM8550_FACTS.md` §8 line 623-625, `[DT-kalama]:1332`, `PORT_FUXI.md` §6 line 84 | **VERIFIED** | `qcom,msm-imem@146aa000` + `restart_reason@65c`. |
| **Core Count** | 8 cores (`cpu0`..`cpu7`) | `SM8550_FACTS.md` §4 line 234, `device-dumps/dt-cpus.txt`, `[DT-kalama]:67` | **VERIFIED** | 1x Cortex-X3 + 2x Cortex-A715 + 2x Cortex-A710 + 3x Cortex-A510. |
| **Core MPIDRs** | `core << 8` (`0x000`..`0x700`) | `SM8550_FACTS.md` §4 line 234, `device-dumps/dt-cpus.txt`, `PORT_FUXI.md` D2 line 170 | **VERIFIED** | Each core occupies its own Aff1 slice: `0x000, 0x100, 0x200, 0x300, 0x400, 0x500, 0x600, 0x700`. |
| **Core Frequencies** | 2.0 GHz (A510), 2.8 GHz (A715/A710), 3.19 GHz (X3) | `SM8550_FACTS.md` §4 lines 243-249 | **VERIFIED** | Nominal maximum clock frequencies per CPU partition. |
| **Root Compatibility** | `D22AP`, `iPhone10,3`, `xiaomi,fuxi`, `xiaomi,sweet`, `qcom,kalama`, `qcom,sm8550`, `AppleARM` | `PORT_FUXI.md` D1 line 169, `RETARGET_CHECKLIST.md` line 142 | **VERIFIED** | Bridges iPhone X iOS 16 userland identity with platform expert matching (`xiaomi,sweet` retained for SweetPlatformExpert and SweetCPU). |
| **Synthetic ECID** | `0x4655584900000001` (`FUXI\1`) | `RETARGET_CHECKLIST.md` line 124 | **SYNTHETIC** | Stable chip identity used by `IOPlatformExpertDevice::generatePlatformUUID`. |
| **Boot Manifest Hash** | `sha384(b'fuxi boot manifest')` | `tools/mkadt.py` line 118 | **SYNTHETIC** | Stand-in hash satisfying `/sbin/mount -P 1` boot manifest lookup. |

---

## 2. Generator Implementation (`tools/mkadt.py`)

The ADT generator was retargeted to support both machines via a `--machine {fuxi,topaz}` argument,
defaulting to `fuxi` while preserving full backwards compatibility with the topaz reference pipeline:

1. **Dual Machine Support**:
   - `python3 tools/mkadt.py xnu/out/fuxi.adt` -> builds the `fuxi` ADT by default.
   - `python3 tools/mkadt.py xnu/out/topaz.adt --machine topaz` -> preserves the known-good `topaz` reference tree.
   - Automatic heuristic: if output filename contains `"topaz"`, machine switches to `topaz` automatically unless explicitly overridden.
2. **Flexible Invocation**:
   - `python3 tools/mkadt.py --dump` generates in-memory and renders the parsed tree to stdout without requiring an output file path.
   - `--highmem` selects the 2.75 GiB upper high DDR bank (`0x8c0000000`).
   - `--native` presents the native 1080×2400 display canvas.
   - `--qemu` produces QEMU virt timer and GIC addresses for host emulation tests.
3. **Hardware Node Structure**:
   - `/arm-io/gic`: contains `reg` mapping GICD (`0x16100000` relative to `0x01000000` = `0x17100000`) and GICR (`0x16180000` relative = `0x17180000`, size `0x200000`), `redistributor-stride = 0x40000`, `stride = 0x40000`, `virtual-timer-intid = 27`, `physical-timer-intid = 30`, `distributor-base = 0x17100000`, `redistributor-base = 0x17180000`.
   - `/arm-io/timer`: contains `reg` (`0x16420000` relative = `0x17420000`, size `0x1000`), `phys-addr = 0x17420000`, `virtual-timer-intid = 27`, `physical-timer-intid = 30`.
   - `/sweet-timer`: top-level root node referencing absolute physical base `0x17420000`, size `0x1000`, PPIs 27/30, and stride `0x40000`.
   - `/sweet-fbcon`: references absolute physical splash address `0xb8000000`, size `0x2b00000` (43 MiB), geometry 1080×2400, stride 4320.
   - `/sweet-ufs`: references internal UFS host controller `0x01d84000`, size `0x3000`.
   - `/cpus`: 8 cores (`cpu0`..`cpu7`) with `reg = core << 8`, `cluster-id = core`, individual frequencies, and ARMv9 compatible strings.

---

## 3. Independent Binary Verification (`tools/verify_fuxi_adt.py`)

To ensure that the generator not only prints the right strings but writes the exact expected
byte structures, an independent binary parser `tools/verify_fuxi_adt.py` was created. It unpacks
`xnu/out/fuxi.adt` from disk using raw binary struct reads and performs 56 explicit assertions.

### Verification Results Summary

```
=== Verifying ADT: xnu/out/fuxi.adt ===
Total file size: 11220 bytes
[PASS] Root compatible contains xiaomi,fuxi: D22AP iPhone10,3 xiaomi,fuxi xiaomi,sweet qcom,kalama qcom,sm8550 AppleARM 
[PASS] Root compatible contains qcom,kalama: D22AP iPhone10,3 xiaomi,fuxi xiaomi,sweet qcom,kalama qcom,sm8550 AppleARM 
[PASS] Root compatible contains AppleARM: D22AP iPhone10,3 xiaomi,fuxi xiaomi,sweet qcom,kalama qcom,sm8550 AppleARM 
[PASS] DRAM base is valid high bank (0x880000000 or 0x8c0000000): 0x880000000
[PASS] DRAM size >= 768 MiB (0x30000000): 0x3b000000 (944 MiB)
[PASS] A11 chip-id for iOS 16 userland is 0x8015: 0x8015
[PASS] cpus node contains 8 CPU children: 8 CPUs
[PASS] cpu0 child exists: cpu0
[PASS] cpu0 MPIDR reg == 0x000: 0x000
[PASS] cpu0 cluster-id == 0: 0
[PASS] cpu1 child exists: cpu1
[PASS] cpu1 MPIDR reg == 0x100: 0x100
[PASS] cpu1 cluster-id == 1: 1
[PASS] cpu2 child exists: cpu2
[PASS] cpu2 MPIDR reg == 0x200: 0x200
[PASS] cpu2 cluster-id == 2: 2
[PASS] cpu3 child exists: cpu3
[PASS] cpu3 MPIDR reg == 0x300: 0x300
[PASS] cpu3 cluster-id == 3: 3
[PASS] cpu4 child exists: cpu4
[PASS] cpu4 MPIDR reg == 0x400: 0x400
[PASS] cpu4 cluster-id == 4: 4
[PASS] cpu5 child exists: cpu5
[PASS] cpu5 MPIDR reg == 0x500: 0x500
[PASS] cpu5 cluster-id == 5: 5
[PASS] cpu6 child exists: cpu6
[PASS] cpu6 MPIDR reg == 0x600: 0x600
[PASS] cpu6 cluster-id == 6: 6
[PASS] cpu7 child exists: cpu7
[PASS] cpu7 MPIDR reg == 0x700: 0x700
[PASS] cpu7 cluster-id == 7: 7
[PASS] arm-io ranges has 3 u64 cells (child, parent, size): ['0x0', '0x1000000', '0xff000000']
[PASS] arm-io parent SOC_BASE == 0x01000000: 0x1000000
[PASS] gic reg has 4 u64 cells (gicd_rel, gicd_len, gicr_rel, gicr_len): ['0x16100000', '0x10000', '0x16180000', '0x200000']
[PASS] GICD distributor address == 0x17100000: 0x17100000
[PASS] GICD distributor size == 0x10000: 0x10000
[PASS] GICR redistributor base == 0x17180000: 0x17180000
[PASS] GICR redistributor size == 0x200000: 0x200000
[PASS] GIC distributor-base property == 0x17100000: 0x17100000
[PASS] GIC redistributor-base property == 0x17180000: 0x17180000
[PASS] GIC redistributor-stride == 0x40000 (256 KiB): 0x40000
[PASS] GIC stride property == 0x40000: 0x40000
[PASS] GIC virtual-timer-intid == 27 (GIC_PPI 11): 27
[PASS] GIC physical-timer-intid == 30 (GIC_PPI 14): 30
[PASS] arm-io/timer frame address == 0x17420000: 0x17420000
[PASS] arm-io/timer phys-addr property == 0x17420000: 0x17420000
[PASS] sweet-timer root node reg == 0x17420000: 0x17420000
[PASS] sweet-timer vtimer-intid == 27: 27
[PASS] sweet-timer ptimer-intid == 30: 30
[PASS] sweet-timer stride == 0x40000: 0x40000
[PASS] sweet-fbcon splash address == 0xb8000000: 0xb8000000
[PASS] sweet-fbcon splash size == 0x2b00000 (43.0 MiB): 0x2b00000
[PASS] sweet-fbcon geometry 1080x2400: 1080x2400
[PASS] sweet-fbcon stride == 4320 (1080*4): 4320
[PASS] sweet-ufs host address == 0x01d84000: 0x1d84000
[PASS] sweet-ufs register window size == 0x3000: 0x3000

=== ALL 56 ADT ASSERTIONS PASSED! ===
```

Full log saved to: `/mnt/hdd/Bomb/macos-vm/evidence/adt-verify.txt`.

---

## 4. Payload & Boot Image Assembly

### 4.1 Payload Build (`xnu/out/fuxi.payload`)

The payload was constructed using `tools/mkpayload.py`:

```bash
python3 tools/mkpayload.py xnu/out/kernel.development.fuxi xnu/out/fuxi.adt xnu/out/fuxi.payload \
    --cmdline "debug=0xc serial=3 cpus=1 keepsyms=1 -enable_kprintf_spam -noprogress"
```

**Output:**
```
cputype: 0x100000c
cpusub: 0
fixups: 0
virt_base: 0xfffffe0006000000
entry: 0xfffffe000748c488
kernel_end: 0xfffffe00084c8000
ramdisk: None
size: 16613504
   __TEXT 0xfffffe0007004000 0x160000
   __DATA_CONST 0xfffffe0007164000 0x180000
   __TEXT_EXEC 0xfffffe00072e4000 0x854000
   __KLD 0xfffffe0007b38000 0x4000
   __LASTDATA_CONST 0xfffffe0007b3c000 0x4000
   __KLDDATA 0xfffffe0007b40000 0x4000
   __DATA 0xfffffe0007b44000 0x534000
   __BOOTDATA 0xfffffe0008078000 0x4c000
   __LINKINFO 0xfffffe00080c4000 0x4c000
   __LINKEDIT 0xfffffe0008110000 0x3b50b0
```

- **File size**: 16,613,504 bytes (15.84 MiB)
- **Magic**: `b'SWEETXNU'` (verified at offset `0x000`)
- **Version**: `1`
- **Segment count**: `10`
- **Virtual base**: `0xfffffe0006000000`
- **Entry point**: `0xfffffe000748c488`
- **Kernel end VA**: `0xfffffe00084c8000`
- **ADT offset / size**: `0xfd54a0` / `11220` bytes
- **Physical base**: `0x880000000`
- **Managed memory size**: `0x3b000000` (944 MiB)
- **Cmdline**: `debug=0xc serial=3 cpus=1 keepsyms=1 -enable_kprintf_spam -noprogress`

### 4.2 Chained Fixups Status

Inspection of `xnu/out/kernel.development.fuxi`'s Mach-O load commands revealed that command `0x80000034` (`LC_DYLD_CHAINED_FIXUPS`) is not present in this Mach-O build (the kernel was statically linked/rebased at `__TEXT vmaddr 0xfffffe0007004000`). Consequently:
```
fixups: 0
```
`tools/mkpayload.py`'s `apply_chained_fixups()` exited cleanly with `nfix = 0`. Captured in `/mnt/hdd/Bomb/macos-vm/evidence/adt-fixups.txt`.

### 4.3 Shim Retargeting & Boot Image Generation (`shim/out/shim-boot.img`)

To support booting the payload while keeping the M1 diagnostic path available:
1. `shim/shim.c`: wrapped `#define FUXI_M1_DIAG 1` in `#ifndef FUXI_M1_DIAG ... #endif`.
2. `shim/build.sh`: added dynamic switching:
   - When `$1` (payload) is passed: defaults `FUXI_M1_DIAG=0` so that `shim_main` calls `loader_boot(dtb)`.
   - When no argument is passed: defaults `FUXI_M1_DIAG=1` to preserve telemetry diagnostic reset.

Executing:
```bash
cd shim && ./build.sh ../xnu/out/fuxi.payload
```
Generated:
- **`shim/out/Image`**: `16,797,824` bytes (shim binary `184,320` bytes padded to 4KB boundary `0x2d000`, followed by `16,613,504` bytes of `fuxi.payload`).
- **`shim/out/shim-boot.img`**: `16,809,984` bytes.
- **`file shim/out/shim-boot.img`**:
  ```
  shim/out/shim-boot.img: Android bootimg, kernel (0x60), ramdisk (0x630)
  ```
- **Unpacked header inspection (`unpack_bootimg.py`)**:
  ```
  boot magic: ANDROID!
  kernel_size: 16797824
  ramdisk size: 94
  os version: 13.0.0
  os patch level: 2025-01
  boot image header version: 4
  command line args: console=null
  ```

---

## 5. Artifact Inventory & Captured Evidence

| Artifact Path | Description | Checksum / Evidence URI |
|---|---|---|
| `xnu/out/fuxi.adt` | Serialized fuxi Apple Device Tree (11,220 bytes) | `sha256: 1dbf3ab795585c5e7f13089389a18d1dadd2e656a7eeb6940b760a2a740c1155` |
| `xnu/out/fuxi.payload` | SWEETXNU payload with kernel + ADT + boot_args (16,613,504 bytes) | `sha256: 0dc991ce3615ce29a8f39af0291ca29709290c0909655bcff60f9e75fa249380` |
| `shim/out/shim-boot.img` | Android boot image v4 containing shim + payload (16,809,984 bytes) | `sha256: c43d7a2165f5b0f2261de07785cf5ecca637f9afd72a28d6135079696cd9be11` |
| `/mnt/hdd/Bomb/macos-vm/evidence/adt-dump.txt` | Human-readable ADT dump rendered by `mkadt.py --dump` | Captured |
| `/mnt/hdd/Bomb/macos-vm/evidence/adt-verify.txt` | Output of `tools/verify_fuxi_adt.py` (56 passed assertions) | Captured |
| `/mnt/hdd/Bomb/macos-vm/evidence/adt-payload.txt` | `tools/mkpayload.py` run log | Captured |
| `/mnt/hdd/Bomb/macos-vm/evidence/adt-bootimg.txt` | `shim/build.sh` build output and `file` command verification | Captured |
| `/mnt/hdd/Bomb/macos-vm/evidence/adt-fixups.txt` | Mach-O load command analysis confirming 0 chained fixups | Captured |

---

## 6. Gaps

The following hardware-dependent facts cannot be verified without running on physical hardware:

1. **Splash Framebuffer Scanout Persistence (`0xb8000000`)**:
   - `splash_region` base (`0xb8000000`) and size (`43.0 MiB`) are VERIFIED from `[D-rmem]:33` and `[D-iomem]:279`.
   - Stride is INFERRED as `4320` (`1080 * 4`).
   - Whether ABL's continuous splash scanout remains active after ABL hands off to EL1 on fuxi or whether the panel is already in command-mode LP1/LP2 standby requires physical visual observation on the phone during boot.
2. **Command-Mode Panel Low-Power State Machine**:
   - The panel is a Samsung command-mode panel (`qcom,mdss_dsi_m3_38_0c_0a_dsc_cmd`), which latches frames in panel GRAM.
   - If ABL quiesces the display clock before hand-off, updates written to `0xb8000000` will not refresh on-screen until an MDP/DSI commit kicks the panel.
3. **UFS Hardware Key Manager (HWKM) State**:
   - The UFS host controller window `0x01d84000` is VERIFIED.
   - On SM8550, UFS 4.0 includes an ICE HWKM block at `0x1d90000`. If ABL enabled HWKM before booting, the simple legacy UFS driver must either leave ICE in bypass mode or quiesce HWKM properly.
4. **Secondaries PSCI Wakeup Response**:
   - PSCI `CPU_ON` target MPIDRs are VERIFIED as `0x100..0x700`.
   - Secondary core redistributor initialization in `pe_fiq.c` uses `GICR_PE_SIZE = 0x40000`. Successful wakeup of all 7 secondaries depends on Qualcomm TrustZone accepting `PSCI_CPU_ON` SMC calls for the Cortex-A715, A710, and X3 cores from EL1 NS.

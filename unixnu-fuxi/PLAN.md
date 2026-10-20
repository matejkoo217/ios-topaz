# FUXI on UniXNU — plan and gates

Separate project. Nothing here touches the working port in `/mnt/hdd/Bomb/ios-fuxi-mt`;
that port stays alive and bootable while this is developed.

## Verdict: adopt as the base, but it is a firmware project first

UniXNU is genuinely ahead of our port. Verified in source, not from the README:

- `drivers/NativeAdreno` — GMU cold start, CP ring, native 4 KiB SMMU contexts,
  BOs, fences, scanout copy. `kits/AdrenoFirmware`, `AdrenoPM4`.
- `docs/devices/sheng.md` — the reference board is **sheng = Xiaomi Pad 6S Pro =
  SM8550**, the same SoC as fuxi. UFS root, display, touch, GPU compositing and
  per-process Metal devices are listed as working there.
- Real Apple userland: it boots an unmodified iPadOS restore image (APFS +
  Cryptex + trust cache + prelinked kernel), not an HFS+ approximation.
- `patches/` carries `xnu`, `mesa`, `libpthread` patch sets, including the
  4 KiB page-table work (`docs/xnu/four-k-page-tables`).

Our port's advantage is only that it already boots on *this* phone. Everything
else in UniXNU is further along.

## The gates, in the order they block

### Gate 1 — fuxi has no UEFI port (the real project)

UniXNU boots through Mu-Silicium UEFI: stock ABL → BootShim → UEFI firmware →
UniXNU → DarwinBoot → XNU. There is **no `uefi-fuxi`**. There is
`uefi-sheng`, and it is the template:

- 18 files / 1225 lines total for the whole device package
  (`Platforms/Xiaomi/shengPkg`) — memory map, configuration map, display DEPEX,
  GOP log, boot memory, dsc/fdf. Everything else is shared SM8550 silicon.
- `shengPkg/PORTING.md` says plainly: **"not hardware validated and is not a
  ready-to-flash image"**, and the **53 vendor UEFI drivers are not distributed**
  — they are imported from the device's own stock firmware image (the ABL, which
  is an EDK2 UEFI app).

So the fuxi work is: copy shengPkg → fuxiPkg, rebuild its memory map from
**fuxi's own** reserved-memory/DT data, and import fuxi's vendor DXE modules from
the stock `abl_a` image. sheng's numbers must not be reused: different panel
(1080x2400 vs 3048x2032), different RAM size, different PMIC rails.

### Gate 2 — the build driver is macOS-only for the kernel step

`./unixnu` prints: `developed and tested on macOS only; the kernel step needs
Xcode and --skip-setup needs hdiutil`.

Measured on this host (Debian, and Alfa is Linux too — `uname -sm` = `Linux
x86_64` on both):

- `defconfig` **works** on Linux
- `status` **works** on Linux
- firmware/EDK II build works on Linux (EDK II is a Linux-native build)
- the **kernel step needs Xcode** — there is no Mac in this setup

Options, in order of preference:

1. Keep their kernel config/patches but drive the build with this project's
   existing Linux XNU harness (`tools/build-kernel-local.sh` in the other repo
   already cross-builds XNU on Linux, and CI does it too). Highest value: no Mac.
2. Borrow a Mac (or a macOS VM) for `build kernel` / `build payload` only, and
   keep everything else on Linux.

### Gate 3 — device inputs that do not exist yet

`[payload]` needs a trust cache bundle, a Data seed ramdisk and a `--unique-chip-id`
platform seed; `[payload.adt]` needs fuxi's own ADT (chip id, owned memory,
root volume UUID). None are produced for fuxi. `owned_memory_size` depends on
whether this is an 8/12/16 GiB unit and must be read from the device.

## What was done in this repository

- `board.toml` — fuxi board file in their schema. Real values where known
  (userdata LBAs derived from this port's own UFS report: first `0x4b7840`,
  217.1 GiB), TODO where not.
- `configs/fuxi_defconfig` — sheng's feature set minus the sheng-only PMGR and
  with the Adreno driver off until the display path is proven. Includes a
  **placeholder** `CONFIG_XNU_OWNER_DATA_VOLUME_UUID` (build-time only; fuxi has
  no APFS Data volume yet).
- `../UniXNU` — umbrella checkout, submodules initialised, feeds fetched.
- `../uefi-sheng` — the firmware template (3.3 GB with submodules).
- `../uefi-fuxi` — hardlinked copy of the firmware tree with `fuxiPkg` derived
  from `shengPkg`, plus `Resources/Configs/fuxi.toml`.

### Firmware result (Linux, 2026-10-20)

`uefi-fuxi/Build/fuxiPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd` builds:
3,145,728 bytes (exactly `[uefi_fd] size = 0x300000`), 174 modules compiled,
`0055 Images Verified`, EDK II reports `Success`, `_FVH` present at 0x28, and
the main FV is `FVMAIN_COMPACT` (LZMA) — which is why `strings` finds no module
names in the image. Module inclusion is confirmed from the build log instead:
UniXNU, DarwinBoot, FuxiBootMemoryDxe, FuxiDisplayDepexDxe, FuxiGopLogDxe.

Three fixes were needed to get there (all in the copied tree, not upstream):

1. `Include/APRIORI.inc` imported `DevicePathDxe` from `Binaries/fuxi/…`
   **unguarded**, while `DXE.inc` used the edk2 source module. Switched to the
   source module; without this no build is possible without the stock import.
2. `Include/RAW.inc` pulled `Binaries/fuxi/RawFiles/SecParti.cfg` unguarded —
   commented out with a TODO (the Mu-only path does not need it).
3. Driver directories were renamed to `Fuxi*` but the files inside were not;
   the DSC therefore resolved to non-existent paths.

The remaining build complaint is benign for the FD: `The Device DTB is Missing
in "Resources/DTBs"` — that input is only needed for `unixnu bootimg`.

### Boot image result (Linux)

Stage-1 image packed and verified:

`unixnu-fuxi/build/fuxi/boot/boot.img` — 630,784 bytes, sha256
`39ba34dce7bbfc6843f5fd53ebe8f7a9…`

- `ANDROID!` v0 header, page size 4096, kernel_addr `0x8000`, tags `0x1e00000`
- kernel field = gzip(192-byte BootShim + 3,145,728-byte FD) — decompresses to
  exactly **3,145,920 bytes**, which proves the shim-to-FD handoff size
- BootShim carries FD base `0xa7100000` and size `0x300000` as immediates
- `_FVH` present in the payload; the FV is `FVMAIN_COMPACT` (LZMA)
- trailing **1,614 bytes** = `Resources/DTBs/fuxi.dtb`, compiled from
  `scripts/fuxi.dts`, containing `/reserved-memory/splash_region@b8000000`
  (the name the ABL requires) and `model = "Xiaomi 13 (fuxi)"`

`scripts/make-fuxi-adt.py` (ported from sheng) produces a 12,280-byte ADT that
parses byte-exact: `xiaomi,fuxi` + `qcom,sm8550`, 8 CPUs `0x0..0x700`, PSCI smc,
GICv3, NVRAM proxy, sha2-384. DRAM size currently `0x80000000` (first bank only
— the 8 GB unit also has 6 GiB at `0x880000000`).

**Not yet booted:** no device was visible on USB (`fastboot devices` and `adb`
both empty), so the image has never run on hardware.

### Kernel result (Mac, Ventura 13.7.8 / Xcode 15.2)

The pipeline runs (local Python 3.12.15, local cmake 3.31.6 + ninja 1.12.1, no
system installs) and compiles most of XNU, but two Xcode-version problems block
it:

1. **Fixed:** `makedefs/MakeInc.def` passes `-mach_msg2` to MIG; Xcode 15.2's
   `mig` does not know it and forwards it to clang, killing
   `GENERATE device_server.h`. Removed in the work tree (original kept at
   `/tmp/MakeInc.def.orig` on the Mac).
2. **Open:** `DriverKit/OSObject.iig.cpp` fails with `use of undeclared
   identifier 'IORPCMessageFromMach'`. The declaration exists in
   `iokit/DriverKit/IORPC.h:200`, so the generated file is resolving a different
   (SDK) DriverKit include path. This smells like the same version skew; it has
   not been chased yet.


## First milestone (Stage 1 in their bring-up order)

**A UEFI menu on the fuxi panel via `fastboot boot`, no flashing.**

Steps:
1. Build `uefi-sheng` unchanged on Linux and confirm EDK II + BaseTools produce a
   firmware volume here (validates the toolchain, not the board).
2. Clone shengPkg → `fuxiPkg`; rewrite `MemoryMapLib` from fuxi's reserved-memory
   and `iomem` dumps (already on disk in the other repo's `device-dumps/`).
3. Add the `splash_region` DT node (we already know fuxi's ABL powers the panel
   off without it) and get a GOP on the framebuffer.
4. Package with BootShim and `fastboot boot` it.

Only after the menu appears does the payload/kernel stage make sense.

## Hard rules inherited from the working port

- `fastboot boot` only. **Never flash or erase**, never touch userdata (`sda32`).
- fuxi is currently in fastboot and can be booted on request; a bad image should
  fall back to Android on a cold boot.

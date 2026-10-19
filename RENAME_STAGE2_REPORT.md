# Rename stage 2 — sweet/topaz → fuxi beyond the strings pass

Branch `fuxi-rename2`, based on `fuxi-rename` (stage 1) with `fuxi-offsets`
(0098/0099) merged in. Pushed to `fork` only. Every stage below was applied to
the local patch-application harness and then built by GitHub Actions before the
next stage started.

| stage | commit | CI run | conclusion |
|---|---|---|---|
| 0099 hunk context repair | `6a7239b` | (covered by next) | — |
| A — source filenames | `dd8e597` | 39309997671 | success |
| B — identifiers / symbols | `ca9befc` | 39311352650 | success |
| C — build gate + retire dual define | `4535117` | 39312596462 | success |
| D — vendored trees | `08ccd68` | 39313966886 | success |
| E — on-media magics | `c0f2448` | 39315464694 | success |
| F — patch/tool filenames | `1d9fa69` | 39316520748 | success |
| G — report + 0101 filename | `548fe97` | 39317473357 | success (kernel.development.fuxi, 17,223,312 bytes) |

Workflow: `.github/workflows/xnu.yml`, dispatched with `machine_config=FUXI`
(ref `fuxi-rename2`).

## Numbers

Occurrences of `sweet|topaz` (case-insensitive, git-tracked files):

| | files | occurrences |
|---|---|---|
| baseline (`fuxi-rename` tip `e67746c`) | 124 | 2582 |
| after stage 2 (this branch) | 111 | 704 |
| after stage 2, excluding `NOTES.md` | 110 | 534 |
| **code only** (patches + tools + shim), baseline | — | **2328** |
| **code only**, after | — | **455** |

The brief quoted 4782/154 files; that census covered the working tree including
untracked build artifacts (`logs/`, `xnu/out/`, `shim/out/`), which are not in
git and are not renamed here.

## Stage A — XNU source filenames (`dd8e597`, 60 files, 274+/274-)

308 token matches. Patches are the source of truth, so the paths were renamed
inside the series: `diff --git`, `---`/`+++`, the file-list entries and every
include/caller path.

- `bsd/dev/sweet_{ufs,touch,keys,usb,spmi,rpmh,sample,i2c1}.c`, `sweet_spmi.h`
  → `fuxi_*`; `bsd/kern/sweet_amfi.c` → `fuxi_amfi.c`
- `osfmk/arm64/sweet_early.{c,h}` → `fuxi_early.{c,h}`
- `iokit/Kernel/arm/Sweet{CPU,Battery,Entitlements,Framebuffer,KeyStore,PlatformExpert,Surface,Watchdog}.cpp`,
  `SweetSurface.h`, `hid/SweetHID.cpp` → `Fuxi*`
- file lists touched: `bsd/conf/files`, `iokit/conf/files.arm64`, `osfmk/conf/files`
- `tools/mkadt.py` comment references

## Stage B — identifiers and symbols (`ca9befc`, 69 files, 1691 replacements)

Token-exact: a name is renamed at every use *and* at its definition, never one
without the other (that is exactly what broke stage 1:
`SWEET_AKS_LOCK_STATE` renamed at one use while the `#define` stayed).

- functions/globals `sweet_*` → `fuxi_*` (ufs, touch, keys, log, prng, amfi,
  surface, early, i2c1, sample, usb, spmi, rpmh, crash, sandbox, pthread…)
- C++ classes `SweetCPU`, `SweetPlatformExpert`, `SweetBattery`,
  `SweetFramebuffer`, `SweetSurface(+Ref)`, `SweetHID(Touch|Buttons)`,
  `SweetKeyStore`, `SweetEntitlements`, `SweetWatchdog` → `Fuxi*`
- macros `SWEET_*` → `FUXI_*` (LOG_SIZE, SMP_MAX_CPUS, TOUCH_FINGERS,
  VTIMER_INTID, IPI_SGI, SURFACE_*, FB_*, AKS_*, include guards …)
- asm labels `_sweet_lse_{b,h,w,x}`, `Lsweet_secondary_el1`, `Lsweet_mark_*`
- IORegistry property keys `"SweetBattery*"` → `"FuxiBattery*"`, member
  function `SweetBattery::pollTopaz` → `FuxiBattery::pollFuxi`
- `MACHINE_FLAGS_ARM64_SWEET` → `MACHINE_FLAGS_ARM64_FUXI`

Also folded the duplicate defines the rename produced in `FUXI.h`
(`SWEET_VTIMER_INTID`/`FUXI_VTIMER_INTID` and the IPI SGI pair collapsed onto
one name each) and rewrote the comment that called them aliases.

## Stage C — the build gate (`4535117`, 57 files, 198 gate rewrites + new 0101)

- `ARM64_BOARD_CONFIG_SWEET` → `ARM64_BOARD_CONFIG_FUXI` at every use (167
  C-level checks), and `-DARM64_BOARD_CONFIG_SWEET` removed from
  `MACHINE_FLAGS_ARM64_FUXI`.
- gate idioms only: `#if defined(SWEET)`, `#ifdef SWEET`, `#if SWEET`,
  `#endif /* SWEET */`, `ifneq ($(CURRENT_MACHINE_CONFIG),SWEET)`.
  Prose stays: "sweet's Cortex-A76/A55", "SWEET uses 16K pages" are true
  statements about the inherited SM7150 code.
- `0101-fuxi-retire-sweet-board.patch` (new) retires the dual define and the
  SM7150 reference board:
  - `#define SWEET 1` removed from `FUXI.h` — while it existed, a missed
    driver guard would still have evaluated true and the build would not say so;
  - `pexpert/pexpert/arm64/SWEET.h` and `config/MASTER.arm64.sweet` deleted,
    `MACHINE_FLAGS_ARM64_SWEET` removed, the dead
    `#if defined(FUXI) && !defined(FUXI)` block removed from `board_config.h`;
  - consequence: `MACHINE_CONFIG=SWEET` now fails loudly instead of building a
    kernel with the SM7150 GIC base and 19/1 PPI numbering. **The SM7150
    reference configuration is intentionally gone from this fork.**
- the three stage scripts accept `MACHINE_CONFIG=FUXI` only.

## Stage D — vendored trees (`08ccd68`, 16 files, 334 replacements)

Directory, include path, make variable, object name and the config option that
selects them moved together — renaming one of them silently drops a source tree
from the build.

- `bsd/sweet_hfs` → `bsd/fuxi_hfs`, `options SWEET_HFS` → `options FUXI_HFS`,
  `optional sweet_hfs` → `optional fuxi_hfs` (40 entries in `bsd/conf/files`),
  `SWEET_HFS_ROOT`/`SWEET_HFS_OBJS`, compat guard
- `libkern/crypto/sweet_bearssl` → `fuxi_bearssl`, `SWEET_AES_INC/ROOT` →
  `FUXI_AES_INC/ROOT`, the 15 BearSSL-derived `libkern/crypto/sweet_*.c`
- `bsd/pthread/sweet_libpthread` → `fuxi_libpthread`, `SWEET_PTHREAD_INC/ROOT`,
  the staged-source path in the 0019 script

Checked on the patched tree: all 40 `bsd/fuxi_hfs/*.c` listed exist and every
file in the directory is listed; all 15 `libkern/crypto/fuxi_*.c` entries exist.

## Stage E — on-media magics (`c0f2448`, 8 files)

Both are written by one component and read by another; both sides moved:

- payload header `"SWEETXNU"` → `"FUXI-XNU"` (still 8 bytes, so the
  `char magic[8]`, mkpayload's `'<8sII'` pack and loader.c's 8-byte compare
  stay in step): `tools/mkpayload.py`, `shim/loader.c`, `shim/loader.h`,
  `tools/qemu-fuxi.py`
- persistent-log ring `"SWEETLOG"` → `"FUXI-LOG"`: `xnu/patches/0047`
  (`.magic = {'F','U','X','I','-','L','O','G'}`), `0069` (the same line as hunk
  context), `tools/fuxi-log.py`

Both changes are incompatible on purpose: an old payload now fails loudly
("no FUXI-XNU payload") instead of being half-parsed, and a log area written by
the previous kernel is rejected instead of decoded as garbage. Existing
`xnu/out/*.payload` and the flashed log area must be regenerated.

## Stage F — patch and tool filenames (`1d9fa69`, 87 files, 85 renames)

- 78 `NNNN-sweet-*.patch` → `NNNN-fuxi-*.patch` (numeric prefixes untouched, so
  the application order build.sh relies on is unchanged)
- 7 tools: `sweet-{crash.py,init.S,log-pull.sh,log.py,root-tweaks.py,usbnet.sh}`,
  `qemu-sweet.py` → `fuxi-*` / `qemu-fuxi.py`, references updated

## What broke, and what was already broken

1. **0099 did not apply on `fuxi-rename2`.** The merge of `fuxi-offsets` was
   textually clean, but 0099's hunk context contained
   `panic("SWEET CPU: invalid topology")`, which stage 1 had renamed. Git saw no
   conflict; `git apply --check` failed. darwin-xnu-build *silently skips*
   patches that do not apply (build.sh 473-478), so the fuxi 8-core topology fix
   would have been dropped and CI would still have been green. Fixed in
   `6a7239b` by regenerating the hunk against the current `FuxiCPU.cpp`; the
   change itself is unchanged. This is the second time in this port that a
   patch was silently skipped — the local harness prints skips and counts them.
2. **Stage 1's lesson is real.** No renames were done by substitution over
   prose or by hand-editing individual uses: every identifier was renamed from
   a token map, so definition and uses cannot diverge, and the checker below
   verifies it.
3. **Shared worktree race.** While this work was in progress the main worktree
   `/mnt/hdd/Bomb/ios-fuxi` was switched to another branch (`fuxi-ufs-fast`,
   adding `0100-fuxi-ufs-command-wait.patch`) by the other workstream. The
   rename is therefore done in a separate worktree (`/mnt/hdd/Bomb/ios-fuxi-r2`)
   and the main worktree was restored to exactly the files it had before (its
   own uncommitted edits to `xnu.yml`, `NOTES.md`, `ADT_FUXI.md`, `shim/*.c|h`
   were never touched, and `0100` was reverted to its committed content there).

## How this was verified (not by patch-apply success alone)

`tools/build-kernel-local.sh --dry-run` against a pristine `xnu-8796.141.3`
worktree: it runs the three stage scripts, applies every patch and **counts**
skips. Final state: `staged=3 applied=100 skipped=0`.

On the resulting tree:

- every `FUXI_*` macro used has exactly one `#define`
  (`FUXI_LSE` is an assembler `.macro`, not a preprocessor name);
- no macro is defined twice with different values;
- zero `ARM64_BOARD_CONFIG_SWEET`, zero `#define SWEET`, zero `#if … SWEET`;
- every listed `bsd/fuxi_hfs/*.c`, `libkern/crypto/fuxi_*.c` exists;
- `python3 -m py_compile` on every edited tool, `bash -n` on every edited
  script;
- CI (`xnu.yml`, FUXI, macOS 14) green after each stage. Note that green CI
  alone does **not** prove patches applied — hence the skip counter above.

## Deliberately left alone

| what | ~count | why |
|---|---|---|
| 20 boot arguments `sweetusb=`, `sweettouch=`, `sweetfb_*`, `sweethw=`, `sweetkeys=`, `sweetlog=`, `sweetnull=`, `sweetscan=`, `sweetsample=`, `sweetbattery=`, `sweetiolog=`, `sweetusblog=`, `sweethidtest=`, `sweet_amfi_debug=` | 94 | user-typed ABI. Renaming them would silently disable drivers for anyone booting with an existing cmdline; the printfs that document them still print the old spelling. |
| device-tree node names / compatible strings `sweet-ufs`, `sweet-fbcon`, `sweet-timer`, `sweet-io`, `xiaomi,sweet`, `sweet,display` | 31 | the ADT contract `tools/mkadt.py` generates; `xiaomi,sweet` is deliberately kept in the root compatible list for platform-expert matching. Changing a node name is a hardware-identity decision, not a rename. |
| `topaz`/`Topaz*`/`TOPAZ` provenance (104) | 104 | comments and file names that cite the SM6225 origin (`MakrSas/topaz-woa TopazBattery`, `TopazTouch hwio.c`, `topaz (SM6225) MPDIR Aff1…`), plus the `'TOPAZ'+1` ECID constant in mkadt.py. These are facts about where the code came from and about the device identity; rewriting them would make the comments lie. |
| prose `SWEET`/`sweet` in comments | 175 | e.g. "sweet's Cortex-A76/A55 have no PAC", "SWEET uses 16K pages", "the inherited sweet filesystem stack". True statements about the SM7150 code; not names the kernel resolves. |
| `SWEET.h` / `MASTER.arm64.sweet` mentions in patch text | ~56 | the retired board header and master config are still *created* by earlier patches (0004, 0006) and deleted by 0101. Removing the creations would mean rewriting seven later patches that edit those files; the built tree is the same either way. 0101 says explicitly why they are retired. |
| remaining string literals: `"Sweet"` HID manufacturer, `org.sweet.init` launchd label, `com.apple.private.sweet.test-*` entitlements, `ios-sweet` upstream URL in `tools/xnu-cc.py` | ~10 | strings, not symbols; the entitlement names and the launchd label are matched by generated plists, and the URL is history. |
| `tools/mkiosroot.sh`, `ipsw/`, `backups/`, `tools/populate-iosroot.sh`, `tools/mkiosroot-7z.sh`, `tools/extract-apfs.sh`, `tools/rebuild-image.sh`, `shim/out/`, the dyld-cache briefs | — | other in-flight workstream, untouched. |
| `NOTES.md` | 170 | dated changelog; it names patch files and boot args as they were at the time, and is being edited by the other workstream. |

## What still says sweet/topaz at the end

Plainly: **704 occurrences in 111 tracked files**; **455 of them in code**
(`xnu/patches`, `tools`, `shim`), 245 in Markdown, the rest in `README.md`.

Nothing in the code path is a name the compiler or the loader resolves through
the old spelling: no `ARM64_BOARD_CONFIG_SWEET`, no `SWEET` board macro, no
`Sweet*` class, no `SWEET_*` macro, no `SWEET.h`, no `SWEETXNU`/`SWEETLOG`
magic. The one leftover `sweet_*` identifier is the `sweet_amfi_debug` tunable
in 0035, whose C name *is* its boot-argument string and therefore stays with the
other 20 boot arguments. What is left besides that is exactly the four groups in
the table above: boot-argument names (94), ADT node/compatible strings (31),
SM6225 provenance text (104), and prose about the SM7150 inheritance (175).

## For whoever merges this

1. `fuxi-ufs-fast` is not in this branch: it adds
   `0100-fuxi-ufs-command-wait.patch` (the numbering skips 0100 here on
   purpose). That patch touches `bsd/dev/sweet_ufs.c`, which no longer exists
   under that name — when it lands, its path must become `bsd/dev/fuxi_ufs.c`
   (one-line change to its `diff --git`/`---`/`+++` headers) and its body may
   reference `sweet_ufs_*` identifiers. Rebase the rename onto it, or apply the
   same token map to it.
2. Any boot image must be rebuilt: the payload magic is now `FUXI-XNU` and the
   console-log ring is `FUXI-LOG`.
3. `MACHINE_CONFIG=SWEET` no longer exists. CI and local builds use `FUXI`.
4. Boot arguments are unchanged, so existing cmdlines keep working.

Reproduce the local verification with:

```
git worktree add /tmp/xnu xnu-8796.141.3   # or any pristine tree
PATH=tools/fakebin:$PATH SRC=/tmp/xnu PATCHDIR=$PWD/xnu/patches \
  bash tools/build-kernel-local.sh --dry-run     # expect applied=100 skipped=0
```

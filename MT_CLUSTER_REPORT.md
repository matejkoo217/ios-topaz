# UFS multithreaded driver + read clustering, rebased onto the renamed branch

Branch `fuxi-mt-cluster`, cut from `fuxi-rename2` (`9ea437d`) and pushed to
`fork` only. Nothing else was pushed; `fuxi`, `fuxi-rename`, `fuxi-rename2`,
`fuxi-offsets` and `fuxi-ufs-fast` are untouched, as are `ipsw/`, `backups/`,
`tools/extract-apfs.sh`, `tools/rebuild-image.sh`, `tools/populate-iosroot.sh`,
`shim/out/` and `RENAME_STAGE2_REPORT.md`.

| commit | what |
|---|---|
| `559b8a1` | `0102-fuxi-ufs-command-wait.patch` — the 5us/20us command wait, rebased |
| `f20aec7` | `0103-fuxi-ufs-multithreaded.patch` — 8-slot driver, rebased and renamed |
| `8338b88` | `0104-fuxi-ufs-read-cluster.patch` — read-ahead window (`ufsra`) |
| `896d362` | `tools/ufs-window-test/` — host-side self-test for the window logic |

## 1. What moved where

`fuxi-ufs-fast` (`857900a`) carries two patches against the **pre-rename** tree.
Both are diffs of `bsd/dev/sweet_ufs.c`, and the file no longer exists under that
name, so applied as-is they would fail `git apply --check` and then be **silently
skipped** by `darwin-xnu-build` (build.sh 473-478) — CI would go green with the
old single-slot driver in the kernel. That is the failure mode this integration
had to avoid, twice over.

| fuxi-ufs-fast | fuxi-mt-cluster | how it was produced |
|---|---|---|
| `0100-fuxi-ufs-command-wait.patch` (49 lines, `--- a/bsd/dev/sweet_ufs.c`) | `0102-fuxi-ufs-command-wait.patch` (55 lines, `--- a/bsd/dev/fuxi_ufs.c`) | applied to the post-rename file, then re-diffed; message updated, code identical |
| `0101-fuxi-ufs-multithreaded.patch` (966 lines, full-file replacement) | `0103-fuxi-ufs-multithreaded.patch` (975 lines, full-file replacement) | its 1043-line output run through the rename's token map, two nits (below), then re-diffed against the post-0102 file |
| — | `0104-fuxi-ufs-read-cluster.patch` (328 lines) | new work |

Numbering: this branch already uses `0100` (deliberately skipped upstream, see
`RENAME_STAGE2_REPORT.md`) and `0101` (`fuxi-retire-sweet-board`), so the UFS
trio is `0102`/`0103`/`0104` — contiguous, and applied in that order by both
`build.sh` and `tools/build-kernel-local.sh`.

### How the rename was applied without hand-editing

The token map was not guessed. It was derived from the diff between the staged
pre-rename file and the staged post-rename file, then **validated by reproducing
the rename byte for byte**: applying it to the pre-rename 890-line
`bsd/dev/sweet_ufs.c` yields a file *identical* to the `bsd/dev/fuxi_ufs.c` that
the `fuxi-rename2` series actually produces (`diff -q` clean). Only then was it
applied to the post-0101 multithreaded file.

The map, in full: `ARM64_BOARD_CONFIG_SWEET`→`_FUXI`, `sweet_ufs`→`fuxi_ufs`,
`sweet_log_`→`fuxi_log_`, `SWEET_LOG_`→`FUXI_LOG_`, `SWEET UFS:`→`FUXI UFS:`,
`SWEET LOG:`→`FUXI LOG:`, the `'S','W','E','E','T','L','O','G'` header magic →
`'F','U','X','I','-','L','O','G'`, `sweet_gpt_watch`, `sweet_sample_start`,
`sweet_keys_init`, `sweet_touch_init`, `sweet_usb_probe`, `(sweet_usb.c)`,
`tools/sweet-log-pull.sh`, `hid/SweetHID.cpp`, and
`printf("... USB skipped (topaz, sweethw=0)")`→`(fuxi, sweethw=0)` — the last one
because the rename made exactly that edit.

Two nits on top of the mechanical map, both deliberate:

- the multithreaded file header said `SWEET internal UFS root device`; it now
  says `FUXI`. (It appears as a `-` line in 0103's diff, which is why the grep of
  that patch still shows it — see §2.)
- the log thread's `tsleep` channel label went from `"sweetlog"` to `"fuxilog"`.
  It is a wait-channel label shown by `ps`/crash dumps, **not** the `sweetlog=`
  boot argument, which is parsed separately and is untouched.

### Guard rails kept intact

- the GPT write fence is `lba + count - 1 >= gpt_alt` (the corrected form from
  0101, not the `gpt_alt - 4` margin that would have refused every log flush and
  killed the ring);
- the partition-bounds check, `lba < 6`, and `lba + count - 1 > UINT32_MAX` are
  byte-for-byte unchanged, and 0104 does not touch them;
- `fuxi_ufs_rootdev`, the `ufsroot0`/`rufsroot0` devfs nodes, `rd=ufsroot0`,
  `ufsroot=`/`ufsrw=`/`ufscache=`/`ufswait=`/`ufslogsecs=` all keep their names
  and behaviour.

## 2. `git grep -i sweet` after the integration

On the driver as it is in a tree with the series applied
(`bsd/dev/fuxi_ufs.c`, 1236 lines) — 7 hits, all of them things the rename
deliberately kept:

```
bsd/dev/fuxi_ufs.c:969:  if (SecureDTLookupEntry(NULL, "/sweet-ufs", &node) != kSuccess ||
bsd/dev/fuxi_ufs.c:972:          printf("FUXI UFS: no /sweet-ufs node in the device tree\n");
bsd/dev/fuxi_ufs.c:1071:         (void)PE_parse_boot_argn("sweethw", &hw, sizeof(hw));
bsd/dev/fuxi_ufs.c:1077:                 printf("FUXI UFS: USB skipped (fuxi, sweethw=0)\n");
bsd/dev/fuxi_ufs.c:1083:  * Persistent console log ("sweetlog"). Kept in a 4 MiB ring; a thread
bsd/dev/fuxi_ufs.c:1089:  * tools/fuxi-log-pull.sh. Disabled with boot-arg sweetlog=0.
bsd/dev/fuxi_ufs.c:1208:         PE_parse_boot_argn("sweetlog", &on, sizeof(on));
```

| hit | why it stays |
|---|---|
| `/sweet-ufs` ×2 (969, 972) | Device-tree node name looked up with `SecureDTLookupEntry`. It is generated by `tools/mkadt.py`; renaming it here without the ADT would make the driver fail with `ENXIO` on every boot. A node name is a hardware-identity decision, not a rename. |
| `sweethw` ×2 (1071, 1077) | User-typed boot argument. Renaming it silently disables the USB probe for anyone booting an existing cmdline. |
| `sweetlog` ×3 (1083, 1089, 1208) | User-typed boot argument (`sweetlog=0` disables the persistent log), plus the two comments that document it. |

No `sweet_*` identifier, no `SWEET`/`FUXI` board macro, no `Sweet*` class, no
`SWEET UFS:` log prefix and no `SWEETLOG` magic is left in the file. The three
patch filenames are `fuxi`; the only `sweet` in a filename on the branch is
`0101-fuxi-retire-sweet-board.patch`, which is a `fuxi-rename2` file (it retires
the SM7150 reference board) and is not mine to rename.

On the three patches themselves (`git grep -n -i sweet -- xnu/patches/010[234]*`),
`0102` and `0104` are clean; `0103` has 8 hits, all accounted for:

| line | kind | why |
|---|---|---|
| 9 | message | names the `sweetlog=` boot argument it says it does not touch |
| 58 | **removed** line | the old `SWEET internal UFS root device.` header being replaced by `FUXI` |
| 865, 866 | **removed** lines | the pre-0103 comment about `sweettouch=`/`sweetkeys=`/`sweethw=`, which 0103 rewrites |
| 870 | context line | `PE_parse_boot_argn("sweethw", ...)` — kept boot arg |
| 876 | **removed** line | the old comment `Persistent console log ("sweetlog")` |
| 883 | **added** line | the new comment naming the same `sweetlog` boot arg |
| 923 | **removed** line | the old `tsleep` channel `"sweetlog"`, replaced by `"fuxilog"` |

`-` lines are the diff of what changed; they are not content of the resulting
file. Everything still present in the file is one of the seven kept items above.

## 3. Read clustering as implemented

The problem: the VFS/HFS+ layer issues ~4 KiB per strategy call, the driver
answers each with its own SCSI command, and the 1 MiB bounce buffer is never
filled — order 800k commands for the 3.3 GB dyld share cache. 0103 makes those
commands overlap across 8 slots; 0104 reduces how many there are.

**Window.** `RA_DEFAULT_KIB` = 256 KiB (64 device blocks), stored at offset 0 of
the slot's own 1 MiB bounce buffer. Gate: a request whose buffer is **smaller
than 64 KiB** (`RA_SMALL_READ`) uses the window; anything larger takes the plain
path, because it already fills the buffer.

**Boot argument.** `ufsra=<KiB>`. Default 256; `0` disables the window completely
and restores the pre-0104 one-command-per-request path, which is the A/B
baseline on the same kernel. Values are clamped to `RA_MIN_KIB` (8 KiB) and to
the bounce buffer (1 MiB), then rounded to device blocks; the parsed value is
printed at start-up:

```
FUXI UFS: read-ahead window 256 KiB (64 blocks), ufsra=0 disables
FUXI UFS: read-ahead disabled (ufsra=0)
```

**Per-slot state.** `struct ufs_slot` gains `win_lba` (first device block in the
window), `win_blocks` (0 = none) and `win_seq` (the `su.write_seq` at fill time).
The window is per slot because it lives in that slot's bounce buffer; a shared
window would be the same data-corruption bug the single-bounce design had.

**Serving.** `ufs_read_blocks_clustered()` returns a pointer into the bounce
buffer, so the strategy loop's `memcpy(buf + skip, want)` is unchanged in shape:
a hit is `bounce + (lba - win_lba) * 4096`, and a miss fills a window and serves
from the same place. Sequential 4 KiB reads therefore cost **one command per 64
reads**; the only remaining per-read work is a `memcpy`.

**Invalidation — four paths, all of them explicit:**

1. *Any transfer through the slot's bounce buffer* clears that slot's window, in
   `ufs_scsi_slot()` when `len != 0`. The buffer is the window's storage, so this
   is the real "slot reuse" hazard; the fill sets the window only after its own
   command completes.
2. *Any write* bumps `su.write_seq` after the command returns (also on failure,
   since a failed write may land partially) and clears the issuing slot's window.
   Every other slot's window stops matching on its next read — a write through
   slot B can no longer leave slot A serving a pre-write copy of those blocks.
3. *`SYNCHRONIZE CACHE`* bumps `su.write_seq` too (durability point).
4. *Miss, partial overlap, or fallback* clears the window before anything else.

Slots being handed between threads does not clear a window: the data has not
changed, the buffer has not been touched, and the window is self-describing
(`win_lba`/`win_blocks`/`win_seq`), so keeping it is what makes read-ahead work
across strategy calls at all. Anything that touches the buffer goes through (1).

**Clamping.** The start is aligned to the window size in device-block space
(`lba - lba % su.ra_blocks`) and then clamped **up** to `su.first_block`; the
length is clamped to `su.first_block + su.nblocks`. A window can therefore never
name a block outside the partition. The read that reaches this code has already
passed the unchanged `off > part_bytes || count > part_bytes - off` check, so a
read past the partition end still returns `EINVAL` and never reaches a window.

**Full containment, not just size.** A window is served only when
`lba >= win_lba && lba + nblocks <= win_lba + win_blocks`. This matters because
clamping can produce a window that has *enough blocks* and still ends before the
request does — the first draft checked only `blocks >= nblocks` and returned the
wrong blocks in exactly that case (caught by the harness, §4). On any partial
overlap the old window is dropped and **one aligned window covering the whole
request is fetched**; nothing is ever assembled from part of an old window and
part of a new one, so a misaligned request cannot return a mixed or stale range.
That is a deliberate simplification of "serve what matches and fetch the rest":
a boundary crossing costs one refill (once per 256 KiB of a sequential stream)
and the "cannot be wrong" property is structural rather than reasoned about.

**Untouched.** The write path, the partition bounds, `lba < 6`, and the GPT fence
are unchanged; the only fencing-adjacent code added is the `write_seq` bump.

## 4. Verification

### 4.1 The series applies, with nothing skipped

`tools/build-kernel-local.sh --dry-run` — the local mirror of the workflow, which
*counts* skips instead of ignoring them — on a pristine `xnu-8796.141.3`
worktree, run twice (before and after the containment fix):

```
staged=3 applied=103 skipped=0
```

103 = the 100 patches `fuxi-rename2` applies (the rename report's
`applied=100`) + 0102 + 0103 + 0104. The resulting
`bsd/dev/fuxi_ufs.c` is byte-identical to the file the host test was run against.

### 4.2 Host-side test of the window logic

`tools/ufs-window-test/run.sh <patched tree>/bsd/dev/fuxi_ufs.c` extracts the
four window functions **verbatim from the driver** (not a copy), compiles them
against a fake device, and checks returned bytes plus partition bounds:

```
1. 64 x 4 KiB sequential over 256 KiB: 1 commands (0.0 per read), 0.25 MiB read
2. 4000 random 4 KiB reads, 2 slots: 3916 commands, 0 reads outside
3. window invalidated across slots by write: ok
4. partition clamping at head/tail: 3 reads, 0 outside
5. ufsra=0, 64 x 4 KiB: 64 commands (expect 64)
6. 2000 misaligned/random-size reads: 1956 commands, 0 outside
7. 1 MiB read: 1 commands
8. 16 x 64 KiB sequential: 16 commands (window off for >=64 KiB by design)

ALL CHECKS PASSED (0 failures)
```

What that buys: 64 sequential 4 KiB reads become 1 command; 2000 misaligned and
random-sized reads are byte-exact; no read ever names a block outside
`[first_block, first_block + nblocks)` even with the window pinned to either end
of the partition; a write through one slot is visible to a reader holding a
window in another; `ufsra=0` restores exactly one command per read.

It is also the reason 0104 is not the first draft: the containment check was
`blocks < nblocks`, which passed for a window clamped to the partition base while
the window still ended before the request, and 3 of 2000 misaligned reads came
back with the wrong blocks. The fix is the explicit `lba + nblocks <= start +
blocks` test, and the commit records it.

### 4.3 CI

Workflow `.github/workflows/xnu.yml`, dispatched with `machine_config=FUXI` on
ref `fuxi-mt-cluster`.

| run | result |
|---|---|
| `39320390842` | **failed, infrastructure** — `git clone` of xnu timed out (`RPC failed; curl 56 … fatal: early EOF`, exit 128) before a single patch was applied. No compile was reached. |
| `39324090400` | **success** — all three patches applied, kernel built, artifact uploaded |

Run `39324090400` details (job log, `0_build.txt`):

```
⇒ Applying patch: .../0102-fuxi-ufs-command-wait.patch
⇒ Applying patch: .../0103-fuxi-ufs-multithreaded.patch
⇒ Applying patch: .../0104-fuxi-ufs-read-cluster.patch
```

- **`Skipping patch` lines: 4**, and all four are blacktop's own patches that
  have never applied in this fork (`TrustCache.patch`, `iobuffermemd_monterey`,
  `skywalk_sonoma`, `syntax_checker_sonoma`). None of `0102`/`0103`/`0104`, and
  none of the 100 predecessor patches. That is the check the rename report
  insists on: green CI alone does not prove a patch applied.
- Artifact `xnu-kernel` (id `12221529060`), `kernel.development.fuxi`,
  17,223,360 bytes, `sha256 8d312667b3f946d174c5b1c07d609b26e99acc171fc377c78ac619f0c7e1486f`
  — matches the artifact's own `SHA256SUMS` (`sha256sum -c` OK), `file` says
  `Mach-O 64-bit arm64 executable`.

Strings in that artifact, which is the only way to prove the code is *in* the
kernel rather than merely compiled next to it:

```
1   "… DMA at 0x%llx, %d slots (MT)\n"                    -> 0103 (8-slot driver)
1   "FUXI UFS: command 0x%02x timed out (slot %u)\n"      -> 0103 (per-slot doorbell)
1   "FUXI UFS: read-ahead window %u KiB (%u blocks), ufsra=0 disables\n" -> 0104
1   "FUXI UFS: read-ahead disabled (ufsra=0)\n"           -> 0104
1   "ufsra"                                               -> 0104 boot arg
0   "SWEET UFS:"                                          -> rename holds end to end
18  "FUXI UFS:"                                           -> every driver message
```

### 4.4 State of the phone during this work (context, not a test of this branch)

The kernel on the device was booted from an **earlier, pre-rename build**: its
UFS start-up line is
`SWEET UFS: "userdata" on LUN 0: first block 0x4b7840, 222283 MiB, read-write,
DMA at 0x8838e4000` — no `(MT)`, and no `ufsra`/`read-ahead` strings in any of
the `xnu/out/*.payload` built before this branch. So that boot exercises the
single-slot driver, and says nothing about 0103 or 0104.

Its persistent console ring (patch 0047, `sweetlog=1`, `ufsrw=1`,
`ufslogsecs=60`, flush #20, 298,803 bytes, 4,574 lines) shows the kernel and UFS
are healthy — root mounted read-write off `ufsroot0`, no UFS error, no command
timeout — and the boot stops in userspace: `CommCenter` crash-loops (93 crashes,
SIGABRT and SIGSEGV, "crossed thread count high watermark (32)") with
`fairplayd.H2` and `bluetoothd` re-exec'd 119 times each, while `securityd`
selector 10 (`kAKSWrapKey`) is answered `kIOReturnUnsupported` 208 times by the
AKS shim (0038/`FUXI AKS`). That is a keybag/key-wrapping gap, not an I/O
problem, and it is the thing to fix before any MT or clustering measurement can
mean anything.

Note for whoever reads the log next: `tools/fuxi-log.py` used to accept only the
post-rename `FUXI-LOG` magic and printed "log never flushed" for a ring written
by a pre-rename kernel. It now accepts `SWEETLOG` as well (same 8-byte format).


## 5. What I did NOT test (needs the phone)

Everything below is unverified here by construction; the parent owns hardware
testing:

- **No boot.** The kernel has never run with these patches on the device, so
  "the root filesystem mounts and the system reaches the UI" is untested.
- **No speed measurement.** The 64x command reduction is arithmetic
  (256 KiB / 4 KiB) plus the host-side command count; actual boot time, MB/s, and
  whether UFS 4.0 latency behaves as assumed are all unmeasured. `ufsra` exists
  so those measurements can be A/B'd on the same kernel; nobody has A/B'd them
  yet.
- **No correctness under load.** No concurrent HFS+ traffic, no multi-core
  contention across the 8 slots, no interaction with the GPT watchdog thread or
  the log flusher under clustering.
- **Nothing about cache maintenance on real hardware.** `dma_sync` on a 256 KiB
  window is 64x more cache maintenance per command than before; the host test
  models the device, not the cache.
- **Writes under clustering.** Writes are only exercised in the model; the
  device path with `ufsrw=1` and a live log ring is untested. The invalidation
  logic is the part I would watch hardest if something corrupts.
- **Error paths.** A short read, a timed-out window fill, or a reset host during
  a window fill are not exercised anywhere.
- **Compile correctness is CI's, not mine.** No local toolchain on this host
  (`build/LAST-RUN` shows `rc=2`), so the only compile evidence is Actions run
  `39324090400` (§4.3).

## 6. Reproducing

```
# series applies, and nothing is skipped
PATH=tools/fakebin:$PATH SRC=/tmp/xnu PATCHDIR=$PWD/xnu/patches MACHINE=FUXI \
  bash tools/build-kernel-local.sh --dry-run      # expect applied=103 skipped=0

# the window logic, extracted from that tree
tools/ufs-window-test/run.sh /tmp/xnu/bsd/dev/fuxi_ufs.c
```

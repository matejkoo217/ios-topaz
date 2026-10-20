# Building the kernel on a Mac, locally

GitHub Actions takes ~5 minutes per iteration plus the queue; the same build runs in
**5m05s** on the Ventura Mac (jkoo@192.168.0.136, Intel i5-8259U, 8 threads), so a
patch round trip is local once this is set up.

## What the machine needs

| piece | why | how it got there |
|---|---|---|
| macOS 13.x + **Xcode 15.2** | `iig` (IOCatalogue/RPC header generator) ships only in Xcode.app and the kernel build runs it ~200 times. 15.2 is the newest Xcode that runs on Ventura, and 15.x is the `iig` whose IORPC output matches xnu-8796 (16.x emits `IORPC.kernelContent`, which this xnu lacks). | App Store / developer.apple.com |
| Command Line Tools 14.3 | clang, make, git; the macOS SDK carries `Kernel.framework` | `softwareupdate -i "Command Line Tools for Xcode-14.3"` |
| **KDK 13.5 (22G74)** | private kernel headers + KernelSupport libs | `tools/mac`-era script below; blacktop's `build.sh` also fetches it by itself |
| `jq gum ninja ipsw cmake` | `build.sh` requires them | `tools/mac/install-deps.py` — Homebrew's installer now refuses Intel ("only supported on Apple Silicon"), so each binary comes from its own upstream release |

## One-time setup

```bash
python3 tools/mac/install-deps.py          # ~/bin/{jq,gum,ninja,ipsw,cmake}
bash    tools/mac/mac-setup.sh             # repo + dxb + patches, checks for iig
```

`mac-setup.sh` clones `matejkoo217/ios-topaz` and blacktop's `darwin-xnu-build` at
the pinned SHA (`6639065`), copies `xnu/patches/*` into `dxb/patches/`, applies the
same two `sed`s the workflow does (target `arm64` only, `-mcpu=cortex-a53`), stubs
`xcodes` (build.sh only checks that it exists) and writes `build-local.sh`.

Then, once:

```bash
sudo xcode-select -s /Applications/Xcode.app
sudo xcodebuild -license accept
# tools must be where build.sh looks: it RESETS PATH to Xcode + /usr/local/bin
for t in jq gum ninja ipsw cmake xcodes; do sudo cp ~/bin/$t /usr/local/bin/; done
```

## Build

```bash
~/ios-fuxi-mt/build-local.sh                       # DEVELOPMENT / FUXI / macOS 13.5
KERNEL_CONFIG=RELEASE ~/ios-fuxi-mt/build-local.sh
```

Output: `~/dxb/fakeroot/System/Library/Kernels/kernel.development.fuxi`, log in
`~/ios-fuxi-mt/build-last.log`.

## Making a boot image from it (on the Linux box)

```bash
python3 tools/mkpayload.py <kernel> build/mt/fuxi.adt build/mt/NNN.payload --cmdline "<cmdline>"
(cd shim && FUXI_M1_DIAG=0 bash build.sh ../build/mt/NNN.payload)
cp shim/out/shim-boot.img build/mt/shim-boot-NNN.img
```

## Things that bit us

- Homebrew install refuses this machine outright; do not retry it.
- `build.sh` line 69 sets `PATH` to `${XCODE_TOOLCHAIN}:...:/usr/local/bin`, so
  tools in `~/bin` are invisible to it — hence the copy above.
- The four blacktop patches (`TrustCache`, `iobuffermemd_monterey`,
  `skywalk_sonoma`, `syntax_checker_sonoma`) always report "Skipping patch … patch
  does not apply". That is pre-existing and harmless; every `01xx-fuxi-*` patch
  applies, which the local run confirms (`applied=134 skipped=0`).
- The first build mounts the KDK DMG with `hdiutil` and installs it with `sudo
  installer`; pre-installing it (as happened here) makes the build non-interactive.

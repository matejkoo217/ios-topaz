#!/bin/bash
# Prepare this Mac to build the fuxi XNU kernel locally instead of round-tripping
# through GitHub Actions.
#
#   bash /tmp/mac-setup.sh
#
# Installs nothing that needs an Apple ID: jq/gum/ninja/ipsw/cmake are already in
# ~/bin (install-deps.py), Command Line Tools are installed, and dxb downloads the
# KDK itself.  The one thing this cannot provide is Xcode (for `iig`), so the last
# step checks for it and says so instead of failing 200 times mid-build.
set -u

REPO_URL=${REPO_URL:-https://github.com/matejkoo217/ios-topaz.git}
REPO_DIR=${REPO_DIR:-$HOME/ios-fuxi-mt}
DXB_DIR=${DXB_DIR:-$HOME/dxb}
BRANCH=${BRANCH:-fuxi-mt-cluster}
DXB_REPO=https://github.com/blacktop/darwin-xnu-build
DXB_SHA=663906528d1cd5ea8fde7de6f16de73db9511549
export PATH="$HOME/bin:$PATH"

say() { printf '\n=== %s\n' "$*"; }

say "dependencies"
for t in jq gum ninja ipsw cmake git patch; do
	printf '  %-7s %s\n' "$t" "$(command -v "$t" || echo MISSING)"
done

# build.sh only checks that xcodes exists; Xcode is installed by hand here.
if [ ! -x "$HOME/bin/xcodes" ]; then
	printf '#!/bin/sh\nexit 0\n' > "$HOME/bin/xcodes"
	chmod +x "$HOME/bin/xcodes"
	echo "  stubbed ~/bin/xcodes (build.sh presence check only)"
fi

say "repository ($BRANCH)"
if [ -d "$REPO_DIR/.git" ]; then
	git -C "$REPO_DIR" fetch origin && git -C "$REPO_DIR" checkout "$BRANCH" \
		&& git -C "$REPO_DIR" pull --ff-only
else
	git clone --branch "$BRANCH" "$REPO_URL" "$REPO_DIR"
fi
git -C "$REPO_DIR" log --oneline -1

say "dxb build script ($DXB_SHA)"
if [ -d "$DXB_DIR/.git" ]; then
	git -C "$DXB_DIR" fetch -q --depth 1 "$DXB_REPO" "$DXB_SHA" && git -C "$DXB_DIR" checkout -q FETCH_HEAD
else
	mkdir -p "$DXB_DIR"
	git -C "$DXB_DIR" init -q
	git -C "$DXB_DIR" fetch -q --depth 1 "$DXB_REPO" "$DXB_SHA"
	git -C "$DXB_DIR" checkout -q FETCH_HEAD
fi
cp "$REPO_DIR"/xnu/patches/*.patch "$REPO_DIR"/xnu/patches/*.sh "$DXB_DIR/patches/"

# Same two edits the workflow makes: this kernel is plain arm64 for an ARMv8.2
# phone, and CC/CXX have to be single executables because xcodebuild (mig, ctf)
# wants one binary while the xnu makefiles take the wrappers.
sed -i '' 's/ARCHS="x86_64 arm64e" VALID_ARCHS="x86_64 arm64e"/ARCHS="arm64" VALID_ARCHS="arm64" OTHER_CFLAGS="-mkernel -nostdinc -Wno-packed -mcpu=cortex-a53"/' "$DXB_DIR/build.sh"
grep -c 'OTHER_CFLAGS="-mkernel -nostdinc -Wno-packed -mcpu=cortex-a53"' "$DXB_DIR/build.sh"
ls "$DXB_DIR/patches" | wc -l

say "Xcode"
if xcode-select -p >/dev/null 2>&1 && xcrun --find iig >/dev/null 2>&1; then
	echo "  Xcode ok: $(xcodebuild -version | head -2 | tr '\n' ' ')"
	echo "  iig:      $(xcrun --find iig)"
else
	echo "  MISSING: no iig -> install Xcode (App Store / developer.apple.com), then"
	echo "           sudo xcode-select -s /Applications/Xcode.app && sudo xcodebuild -license accept"
fi

cat > "$REPO_DIR/build-local.sh" <<'EOS'
#!/bin/bash
# Build the kernel locally (same steps as .github/workflows/xnu.yml).
#   ./build-local.sh                  -> DEVELOPMENT, FUXI, macOS 13.5
#   KERNEL_CONFIG=RELEASE ./build-local.sh
#   MAKEFLAGS=-n ./build-local.sh     # dry run
set -eu
export PATH="$HOME/bin:$PATH"
export MACOS_VERSION=${MACOS_VERSION:-13.5}
export KERNEL_CONFIG=${KERNEL_CONFIG:-DEVELOPMENT}
export MACHINE_CONFIG=${MACHINE_CONFIG:-FUXI}
DXB=${DXB:-$HOME/dxb}
REPO=$(cd "$(dirname "$0")" && pwd)

if ! xcrun --find iig >/dev/null 2>&1; then
	echo "no iig: install Xcode and 'sudo xcode-select -s /Applications/Xcode.app'" >&2
	exit 1
fi
cp "$REPO"/xnu/patches/*.patch "$REPO"/xnu/patches/*.sh "$DXB/patches/"
cd "$DXB"
[ -f Makefile ] && make clean >/dev/null 2>&1 || true
{ time bash build.sh; } 2>&1 | tee "$REPO/build-last.log"
echo
echo "kernel(s):"
ls -la "$DXB/fakeroot/System/Library/Kernels/" 2>/dev/null || echo "  none (see build-last.log)"
EOS
chmod +x "$REPO/build-local.sh"

say "done"
echo "  repo:   $REPO_DIR   (build-local.sh is in it)"
echo "  dxb:    $DXB_DIR"
echo "  build:  $REPO_DIR/build-local.sh"

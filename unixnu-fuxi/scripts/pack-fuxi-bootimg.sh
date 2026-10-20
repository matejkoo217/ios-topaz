#!/usr/bin/env bash
# Pack a fuxi boot image the ABL accepts.
#
# Why this exists: `unixnu bootimg` builds the right *payload* (BootShim + FD +
# appended DTB) but writes header fields this ABL rejects. Verified on the
# device 2026-10-20:
#   - our own header           -> "Failed to load/authenticate boot image: Invalid Parameter"
#   - the same payload inside a header from a known-good image the ABL already
#     accepts                     -> "Booting OKAY"
# So the payload is good and the header is not. Until the exact field the ABL
# objects to is pinned down, this grafts the accepted header onto our payload.
#
# What differs in the accepted header (v4): os_version|patch = 0x1a000191 and
# ramdisk_size = 95 with a 95-byte zero ramdisk, versus our 0/0. Patching only
# os_version produced "Load Error" instead of "Invalid Parameter", which is why
# the whole accepted header is reused rather than field-patched.
#
# Usage: pack-fuxi-bootimg.sh [output]
set -euo pipefail

ROOT=/mnt/hdd/Bomb
DONOR="$ROOT/ios-fuxi/shim/out/shim-boot.img"     # image this ABL accepts
FD="$ROOT/uefi-fuxi/Build/fuxiPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd"
DTB="$ROOT/unixnu-fuxi/Resources/DTBs/fuxi.dtb"
WORK="$ROOT/unixnu-fuxi/build/fuxi/boot"
OUT="${1:-$WORK/boot.img}"

[ -f "$DONOR" ] || { echo "donor header missing: $DONOR" >&2; exit 1; }
[ -f "$FD" ]    || { echo "firmware missing: $FD" >&2; exit 1; }
[ -f "$DTB" ]   || { echo "dtb missing: $DTB" >&2; exit 1; }

mkdir -p "$WORK"
echo "== 1/3 unixnu bootimg (payload + verification)"
cd "$ROOT/UniXNU"
python3 ./unixnu bootimg -D ../unixnu-fuxi --uefi ../uefi-fuxi \
  --fd "$FD" --dtb "$DTB" -o "$WORK/.payload.img" >/dev/null

echo "== 2/3 graft the accepted header"
python3 - "$WORK/.payload.img" "$DONOR" "$OUT" <<'PY'
import struct, sys
payload_img, donor, out = sys.argv[1:4]
mine = open(payload_img, 'rb').read()
ks, = struct.unpack_from('<I', mine, 8)
payload = mine[4096:4096 + ks]           # uncompressed shim + FD + DTB
assert payload[:4] != b'\x1f\x8b\x08', 'payload is gzip; set kernel_compression = "none"'
assert payload.find(b'ARM\x64', 56, 64) == 56, 'shim ARM64 header not at 0x38'
hdr = bytearray(open(donor, 'rb').read()[:4096])
struct.pack_into('<I', hdr, 8, len(payload))   # kernel_size
struct.pack_into('<I', hdr, 12, 0)             # ramdisk_size = 0
image = bytes(hdr) + payload
image += b'\0' * (-len(image) % 4096)
open(out, 'wb').write(image)
osv = struct.unpack_from('<I', hdr, 16)[0]
cmd = bytes(hdr[44:1580]).split(b'\0')[0]
print("   hdr os_version=%#x cmdline=%r kernel_size=%d image=%d" % (osv, cmd, len(payload), len(image)))
PY

echo "== 3/3 verify"
python3 - "$OUT" <<'PY'
import struct, sys, hashlib
d = open(sys.argv[1], 'rb').read()
ks, = struct.unpack_from('<I', d, 8)
assert d[:8] == b'ANDROID!'
assert struct.unpack_from('<I', d, 40)[0] == 4
assert d[4096 + 56:4096 + 60] == b'ARMd', 'ARM64 header missing'
assert d.find(b'_FVH') != -1, 'no firmware volume in payload'
assert b'splash_region' in d, 'no splash_region in the appended dtb'
print(f"   {len(d)} bytes  sha256={hashlib.sha256(d).hexdigest()[:16]}...")
print("   ANDROID! v4, ARM64 header @0x38, _FVH present, splash_region present")
PY

rm -f "$WORK/.payload.img"
echo "== $OUT"

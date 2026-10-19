#!/bin/bash
# run.sh -- host-side self-test for the UFS read-ahead window (0104).
#
# Compiles the window bookkeeping EXACTLY as it appears in bsd/dev/fuxi_ufs.c
# (the functions are extracted from the driver at run time, not copied) against
# a fake device, and checks the two things that would corrupt a root filesystem
# if they were wrong: returned bytes, and reads outside the partition.
#
#   tools/ufs-window-test/run.sh /path/to/patched/xnu/bsd/dev/fuxi_ufs.c
#
# The file to point at is the one in a tree with the patch series applied, e.g.
#   tools/build-kernel-local.sh --dry-run      # leaves build/src/<tag>/...
# Nothing here is built by CI and nothing here is kernel code; it is a host cc
# program (gcc or clang) that exercises the same logic.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
driver=${1:-}
cc=${CC:-cc}

if [ -z "$driver" ]; then
	echo "usage: $0 <patched-tree>/bsd/dev/fuxi_ufs.c" >&2
	exit 2
fi
[ -f "$driver" ] || { echo "no such file: $driver" >&2; exit 2; }

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

python3 "$here/extract.py" "$driver" > "$tmp/window_extract.c"
cat "$here/prelude.c" "$tmp/window_extract.c" "$here/tests.c" > "$tmp/ratest.c"
"$cc" -O1 -Wall -Wextra -Wno-unused-parameter -o "$tmp/ratest" "$tmp/ratest.c"
"$tmp/ratest"

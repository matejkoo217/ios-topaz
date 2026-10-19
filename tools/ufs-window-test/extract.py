#!/usr/bin/env python3
"""Extract the read-ahead window functions from the UFS driver, verbatim.

The point of extracting instead of vendoring is that the test then exercises the
text that is actually in the driver: if someone edits the window logic and the
markers still match, the test sees the edit.  Refuses loudly if the markers are
gone rather than silently testing nothing.
"""
import sys

START = "/*\n * Read-ahead window, per slot."
END = "/*\n * topaz: on 2026-10-19"
# Functions the test expects to find inside the extracted region.
WANT = ("slot_window_has(", "slot_window_drop(", "slot_window_fill(",
        "ufs_read_blocks_clustered(")


def main(path):
    text = open(path).read()
    try:
        start = text.index(START)
    except ValueError:
        sys.exit("marker not found: 'Read-ahead window, per slot.' comment")
    try:
        end = text.index(END, start)
    except ValueError:
        sys.exit("marker not found: the 'topaz: on 2026-10-19' GPT comment")
    region = text[start:end]
    missing = [w for w in WANT if w not in region]
    if missing:
        sys.exit("extracted region is missing: " + ", ".join(missing))
    sys.stdout.write(region)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: extract.py <bsd/dev/fuxi_ufs.c>")
    main(sys.argv[1])

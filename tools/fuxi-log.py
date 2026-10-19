#!/usr/bin/env python3
"""Decode the SWEET persistent console log (kernel patch 0047).

  fuxi-log.py AREA.bin [OUT.txt]

AREA.bin is the last (1 + ring/4096) device blocks of the userdata
partition as read by tools/fuxi-log-pull.sh: block 0 is the header
("FUXI-LOG", u32 version, u32 ring size, u64 total bytes, u64 flush seq),
the ring follows. Byte n of the console stream is at ring offset n % size.
"""
import struct, sys

data = open(sys.argv[1], 'rb').read()
magic, version, size, total, seq = struct.unpack_from('<8sIIQQ', data, 0)
# "SWEETLOG" is what kernels built before the rename wrote; a ring written by
# one of those is still a perfectly good log, and refusing to decode it only
# makes an old boot look log-less.  Format is identical (8-byte magic).
if magic not in (b'FUXI-LOG', b'SWEETLOG'):
    sys.exit(f'no FUXI-LOG/SWEETLOG header (got {magic!r}: log never flushed, or wrong area)')
ring = data[4096:4096 + size]
if total <= size:
    text = ring[:total]
else:
    start = total % size
    text = ring[start:] + ring[:start]
out = text.decode('utf-8', 'replace').replace('\r', '')
print(f'# {magic.decode()} version {version}, ring {size}, total {total} bytes, flush #{seq}'
      f'{" (wrapped: oldest bytes lost)" if total > size else ""}', file=sys.stderr)
if len(sys.argv) > 2:
    open(sys.argv[2], 'w').write(out)
else:
    sys.stdout.write(out)

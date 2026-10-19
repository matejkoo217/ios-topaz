#!/usr/bin/env python3
"""fuxi-fb -- grab the phone's screen over USB and write an image.

The kernel side (patch 0114) streams a decimated frame to UDP 5142 on the ECM
link: "FUXIFB1\0" + frame/chunk/chunks/width/height/scale/payload, then RGB
triplets.  This reassembles a frame and writes PNG (PIL if available) plus PPM
(always, dependency-free).

  tools/fuxi-fb.py                     # wait for one frame, write /tmp/fuxi/...
  tools/fuxi-fb.py -t 30 -o shot.png   # custom timeout/output
"""
import argparse
import os
import socket
import struct
import sys
import time

PORT = 5142
MAGIC = b"FUXIFB1\0"
HDR = struct.Struct("<8s7I")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-t", "--timeout", type=float, default=60.0)
    ap.add_argument("-o", "--out", default="/tmp/fuxi/screen.png")
    ap.add_argument("--port", type=int, default=PORT)
    args = ap.parse_args()

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", args.port))
    s.settimeout(1.0)

    frames = {}
    end = time.time() + args.timeout
    done = None
    while time.time() < end and done is None:
        try:
            data, src = s.recvfrom(2048)
        except socket.timeout:
            continue
        if len(data) < HDR.size or not data.startswith(MAGIC):
            continue
        magic, frame, chunk, chunks, w, h, scale, payload = HDR.unpack_from(data)
        body = data[HDR.size:HDR.size + payload]
        f = frames.setdefault(frame, {"w": w, "h": h, "scale": scale,
                                      "chunks": chunks, "parts": {}})
        f["parts"][chunk] = body
        if len(f["parts"]) == f["chunks"]:
            done = frame

    if done is None:
        print(f"no complete frame within {args.timeout:.0f}s "
              f"(partial frames: {len(frames)})", file=sys.stderr)
        return 1

    f = frames[done]
    raw = b"".join(f["parts"][i] for i in range(f["chunks"]))
    w, h = f["w"], f["h"]
    expect = w * h * 3
    if len(raw) < expect:
        print(f"short frame: {len(raw)} of {expect} bytes", file=sys.stderr)
        return 1
    raw = raw[:expect]

    ppm = os.path.splitext(args.out)[0] + ".ppm"
    with open(ppm, "wb") as fh:
        fh.write(b"P6\n%d %d\n255\n" % (w, h))
        fh.write(raw)

    wrote = [ppm]
    try:
        from PIL import Image
        img = Image.frombytes("RGB", (w, h), raw)
        img.save(args.out)
        wrote.insert(0, args.out)
    except Exception as e:                                  # noqa: BLE001
        print(f"PIL unavailable ({e}); wrote PPM only", file=sys.stderr)

    print(f"frame {done}: {w}x{h} scale {f['scale']} -> " + ", ".join(wrote))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Spam the capture request and keep listening.

The phone's XNU link is alive for roughly half a minute at a time and flaps while the
gadget re-enumerates, so "wait politely, then ask once" never gets a frame: by the time
the interface is usable the phone has reset. This asks every half second from the moment
the interface exists and listens the whole time, so whichever request lands during a
live window produces a frame.
"""
import os
import socket
import struct
import sys
import time

IFACE = os.environ.get("FUXI_IFACE", "enx02005e77ee01")
PHONE = bytes.fromhex("02005e77ee02")
HOST = bytes.fromhex("02005e77ee01")
ETH = 0x88B5
HDR = struct.Struct("<8s7I")

OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/fuxi/spam.png"
SCALE = sys.argv[2] if len(sys.argv) > 2 else "4"
BUDGET = float(sys.argv[3]) if len(sys.argv) > 3 else 150.0


def iface_present():
    return os.path.exists("/sys/class/net/" + IFACE)


def main():
    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    rx.bind(("0.0.0.0", 5142))
    rx.settimeout(0.5)

    start = time.time()
    last_ask = 0.0
    asks = 0
    frames = {}
    seen_any = False

    while time.time() - start < BUDGET:
        now = time.time()
        if iface_present() and now - last_ask >= 0.5:
            try:
                s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(ETH))
                s.bind((IFACE, 0))
                s.send(PHONE + HOST + struct.pack("!H", ETH) + ("fb " + SCALE).encode() + b"\n")
                s.close()
                last_ask = now
                asks += 1
            except OSError:
                pass
        try:
            data, _ = rx.recvfrom(2048)
        except socket.timeout:
            continue
        if len(data) < HDR.size or not data.startswith(b"FUXIFB1\0"):
            continue
        seen_any = True
        _, fr, ch, chs, w, h, sc, pl = HDR.unpack_from(data)
        f = frames.setdefault(fr, {"w": w, "h": h, "scale": sc, "chunks": chs, "p": {}})
        f["p"][ch] = data[HDR.size:HDR.size + pl]
        if len(f["p"]) == f["chunks"]:
            raw = b"".join(f["p"][i] for i in range(f["chunks"]))[:f["w"] * f["h"] * 3]
            ppm = os.path.splitext(OUT)[0] + ".ppm"
            os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
            with open(ppm, "wb") as fh:
                fh.write(b"P6\n%d %d\n255\n" % (f["w"], f["h"]))
                fh.write(raw)
            try:
                from PIL import Image
                Image.frombytes("RGB", (f["w"], f["h"]), raw).save(OUT)
            except Exception as e:                                  # noqa: BLE001
                print("PIL: %s" % e, file=sys.stderr)
            print("FRAME %d %dx%d scale %d after %d asks (%.1fs) -> %s" %
                  (fr, f["w"], f["h"], f["scale"], asks, now - start, OUT))
            return 0
    print("no frame (%d asks, %s datagrams)" %
          (asks, "some" if seen_any else "no"), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())

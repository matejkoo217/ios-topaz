#!/usr/bin/env python3
"""Send a command over the fuxi ethertype channel (0106) -- needs root (AF_PACKET)."""
import socket
import struct
import sys
import time

IFACE = sys.argv[1] if len(sys.argv) > 1 else "enx02005e77ee01"
CMD = sys.argv[2] if len(sys.argv) > 2 else "stat"
ETHTYPE = 0x88B5
PHONE = bytes.fromhex("02005e77ee02")
HOST = bytes.fromhex("02005e77ee01")

s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(ETHTYPE))
s.bind((IFACE, 0))
s.settimeout(3.0)
frame = PHONE + HOST + struct.pack("!H", ETHTYPE) + CMD.encode() + b"\n"
s.send(frame)
print(f"sent {len(frame)} bytes: {CMD}")
end = time.time() + 3
while time.time() < end:
    try:
        d = s.recv(2048)
    except socket.timeout:
        break
    if len(d) > 14 and d[6:12] == PHONE:
        print("reply:", d[14:].decode("utf-8", "replace").rstrip())

#!/usr/bin/env python3
"""Send a command over the fuxi ethertype channel (0106) -- needs root (AF_PACKET).

This is the path that works without a kernel socket: the phone claims 0x88B5
frames in its USB receive path, so no IP configuration is involved at all, and
the reply travels back the same way.  Since patch 0135 the debug shell answers
here too, so this is the way to talk to a wedged boot:

  sudo tools/fuxi-ethcmd.py enx02005e77ee01 help
  sudo tools/fuxi-ethcmd.py enx02005e77ee01 ps 20
  sudo tools/fuxi-ethcmd.py enx02005e77ee01 cat /private/var/log/system.log 4096
  sudo tools/fuxi-ethcmd.py enx02005e77ee01 uptime
  sudo tools/fuxi-ethcmd.py enx02005e77ee01 restart      # resets out of the kernel

The reply arrives as one or more frames, each carrying a slice of the text and the
last one ending with "[[fuxi-shell-end]]".
"""
import socket
import struct
import sys
import time

IFACE = sys.argv[1] if len(sys.argv) > 1 else "enx02005e77ee01"
CMD = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "stat"
ETHTYPE = 0x88B5
PHONE = bytes.fromhex("02005e77ee02")
HOST = bytes.fromhex("02005e77ee01")
END = b"[[fuxi-shell-end]]"
BUDGET = float(__import__("os").environ.get("FUXI_CMD_TIMEOUT", "6"))

s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(ETHTYPE))
s.bind((IFACE, 0))
s.settimeout(3.0)
frame = PHONE + HOST + struct.pack("!H", ETHTYPE) + CMD.encode() + b"\n"
s.send(frame)

got = b""
end = time.time() + BUDGET
while time.time() < end and END not in got:
    try:
        d = s.recv(2048)
    except socket.timeout:
        break
    if len(d) > 14 and d[6:12] == PHONE:
        got += d[14:]
        end = time.time() + 1.5          # keep reading while frames keep coming

if END in got:
    got = got[:got.index(END)]
if not got:
    print(f"no reply from the phone ({CMD})", file=sys.stderr)
    sys.exit(1)
sys.stdout.write(got.decode("utf-8", "replace"))
if not got.endswith(b"\n"):
    sys.stdout.write("\n")

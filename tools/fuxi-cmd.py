#!/usr/bin/env python3
"""fuxi-cmd -- talk to the phone's kernel command channel over USB (UDP 5141).

No root needed: this is a plain datagram to the phone's ECM address, not an
AF_PACKET frame.  The phone must have enumerated (sweethw=1 sweetusb=2) and the
host interface must own 192.168.7.1/24:

  sudo ip link set enx02005e77ee01 up
  sudo ip addr add 192.168.7.1/24 dev enx02005e77ee01

  tools/fuxi-cmd.py stat
  tools/fuxi-cmd.py cpu
  tools/fuxi-cmd.py echo hello
  tools/fuxi-cmd.py restart        # resets the phone out of the kernel

Replies come back to the same socket; --wait sets how long to listen.
"""
import argparse
import socket
import sys

PHONE = "192.168.7.2"
PORT = 5141


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", nargs="+", help="command words, e.g. cpu / restart")
    ap.add_argument("-w", "--wait", type=float, default=2.0,
                    help="seconds to wait for a reply (default 2)")
    ap.add_argument("-q", "--quiet", action="store_true", help="do not print the reply")
    args = ap.parse_args()

    line = " ".join(args.command)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(args.wait)
    s.sendto((line + "\n").encode(), (PHONE, PORT))
    got = b""
    try:
        while True:
            data, _ = s.recvfrom(2048)
            got += data
    except socket.timeout:
        pass
    if not got:
        print(f"no reply from {PHONE}:{PORT} (link down? wrong interface address?)",
              file=sys.stderr)
        return 1
    if not args.quiet:
        sys.stdout.write(got.decode("utf-8", "replace"))
        if not got.endswith(b"\n"):
            sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""fuxi-cmd -- talk to the phone's kernel command channel over USB (UDP 5141).

No root needed: this is a plain datagram to the phone's ECM address, not an
AF_PACKET frame.  The phone must have enumerated (fuxihw=1 fuxiusb=2) and the
host interface must own 192.168.7.1/24:

  sudo ip link set enx02005e77ee01 up
  sudo ip addr add 192.168.7.1/24 dev enx02005e77ee01

  tools/fuxi-cmd.py help                       # the shell's own list (patch 0134)
  tools/fuxi-cmd.py uptime
  tools/fuxi-cmd.py ps 20                      # heaviest processes, CPU time
  tools/fuxi-cmd.py cat /private/var/log/x.log 8192
  tools/fuxi-cmd.py kill 227 15
  tools/fuxi-cmd.py smp bluetoothd             # user stacks -> the console stream
  tools/fuxi-cmd.py stub fairplayd.H2,bluetoothd   # stop them at exec
  tools/fuxi-cmd.py stat | cpu | echo hello | restart

Replies come back to the same socket in 1 KiB datagrams and end with
"[[fuxi-shell-end]]", so this stops as soon as it sees the marker and only falls
back to --wait when a reply is missing.
"""
import argparse
import socket
import sys

PHONE = "192.168.7.2"
PORT = 5141
END = b"[[fuxi-shell-end]]"


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
    # Replies are addressed back to 192.168.7.1:5141 (the phone pins its peer, see
    # patch 0111), so bind that port instead of waiting on an ephemeral one.
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", PORT))
    s.settimeout(args.wait)
    s.sendto((line + "\n").encode(), (PHONE, PORT))
    got = b""
    try:
        while True:
            data, _ = s.recvfrom(2048)
            got += data
            if END in got:
                break
    except socket.timeout:
        pass
    if END in got:
        got = got[:got.index(END)]
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

#!/usr/bin/env python3
"""fuxi-netlog -- read the XNU kernel console and send commands over USB.

The phone enumerates as a CDC-ECM Ethernet device when it boots with sweethw=1
(boot arg), and bsd/dev/fuxi_netlog.c puts the kernel's console stream and a
small command channel on ethertype 0x88B5 through that same interface.  This
speaks that ethertype with an AF_PACKET socket, so nothing about the host's IP
configuration matters -- the interface can stay down and unaddressed.

  tools/fuxi-netlog.py                     stream the console (Ctrl-C to stop)
  tools/fuxi-netlog.py -c 'stat'           send one command, print the reply
  tools/fuxi-netlog.py -i usb0             skip auto-detection
  tools/fuxi-netlog.py -f out.log          stream and also append to a file

Commands the kernel understands: help, stat, cpu, log on|off, echo <text>.
Needs root (AF_PACKET).
"""
import argparse
import os
import socket
import struct
import sys
import time

ETHERTYPE = 0x88B5
PHONE_MAC = bytes.fromhex("02005e77ee02")
HOST_MAC = bytes.fromhex("02005e77ee01")


def find_iface():
    """The phone's interface, by its MAC (cdc_ether keeps it)."""
    want = PHONE_MAC.hex(":")
    for name in sorted(os.listdir("/sys/class/net")):
        try:
            with open(f"/sys/class/net/{name}/address") as f:
                if f.read().strip().lower() == want:
                    return name
        except OSError:
            continue
    return None


def open_link(iface):
    try:
        s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(ETHERTYPE))
    except PermissionError:
        sys.exit("need root: AF_PACKET requires CAP_NET_RAW")
    s.bind((iface, 0))
    s.settimeout(0.5)
    return s


def send(s, text):
    payload = text.encode() if isinstance(text, str) else text
    frame = PHONE_MAC + HOST_MAC + struct.pack("!H", ETHERTYPE) + payload
    s.send(frame)


def recv_payload(s):
    """One frame's payload, or None. Only frames from the phone count."""
    try:
        data, addr = s.recvfrom(2048)
    except socket.timeout:
        return None
    if len(data) < 14:
        return None
    if data[6:12] != PHONE_MAC:
        return None
    if struct.unpack("!H", data[12:14])[0] != ETHERTYPE:
        return None
    return data[14:]


def stream(s, out, path=None):
    fh = open(path, "ab", buffering=0) if path else None
    sys.stdout.write(f"# fuxi-netlog: listening on {out}\n")
    sys.stdout.flush()
    last = time.monotonic()
    try:
        while True:
            p = recv_payload(s)
            if p is None:
                # Nudge the link if the kernel has been silent for a while: a
                # command also proves the phone is still alive.
                if time.monotonic() - last > 5.0:
                    send(s, "stat")
                    last = time.monotonic()
                continue
            last = time.monotonic()
            sys.stdout.buffer.write(p)
            sys.stdout.buffer.flush()
            if fh:
                fh.write(p)
    except KeyboardInterrupt:
        sys.stdout.write("\n# stopped\n")
    finally:
        if fh:
            fh.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-i", "--iface", help="interface (default: the phone's MAC)")
    ap.add_argument("-c", "--cmd", action="append",
                   help="send a command; repeatable; prints replies for 2 s")
    ap.add_argument("-f", "--file", help="also append the stream to this file")
    args = ap.parse_args()

    iface = args.iface or find_iface()
    if not iface:
        sys.exit("no interface with the phone's MAC (02:00:5e:77:ee:02) -- is the "
                 "phone booted with sweethw=1 and cdc_ether bound?")
    s = open_link(iface)

    if args.cmd:
        for c in args.cmd:
            send(s, c if c.endswith("\n") else c + "\n")
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            p = recv_payload(s)
            if p:
                sys.stdout.buffer.write(p)
                sys.stdout.buffer.flush()
        return

    stream(s, iface, args.file)


if __name__ == "__main__":
    main()

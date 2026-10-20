#!/usr/bin/env python3
"""fuxi-netlog -- the phone's console and command channel over USB.

Two directions, two mechanisms, because that is what the kernel already speaks:

  logs      the kernel streams its console as UDP to 192.168.7.1:5140
            (bsd/dev/fuxi_usb.c, patch 0077).  This listens for it.
  commands  the host sends ethertype 0x88B5 frames to the phone, which claims
            them in the USB receive path and answers with a frame
            (patch 0106).  No IP configuration of any kind is involved.

The phone enumerates as a CDC-ECM device when it boots with fuxihw=1, so the
interface shows up by itself (MAC 02:00:5e:77:ee:02); its IP does not need to be
set, and cdc_ether's own 192.168.7.1/24 on the host side is what makes the UDP
half work.

  tools/fuxi-netlog.py                    stream the console
  tools/fuxi-netlog.py -c stat -c cpu     send commands, print the replies
  tools/fuxi-netlog.py -f boot.log        stream and keep a copy
  tools/fuxi-netlog.py -i usb0 -n         skip auto-detect / skip UDP logs

Needs root (AF_PACKET for the commands, UDP 5140 bind for the logs).
"""
import argparse
import os
import select
import socket
import struct
import sys
import time

LOGS = ("0.0.0.0", 5140)            # what the kernel sends
PHONE_IP = "192.168.7.2"
ETHERTYPE = 0x88B5
PHONE_MAC = bytes.fromhex("02005e77ee02")
HOST_MAC = bytes.fromhex("02005e77ee01")


def find_iface():
    want = PHONE_MAC.hex(":")
    for name in sorted(os.listdir("/sys/class/net")):
        try:
            with open(f"/sys/class/net/{name}/address") as f:
                if f.read().strip().lower() == want:
                    return name
        except OSError:
            continue
    return None


def open_cmd_socket(iface):
    try:
        s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(ETHERTYPE))
    except PermissionError:
        sys.exit("commands need root: AF_PACKET requires CAP_NET_RAW")
    s.bind((iface, 0))
    s.setblocking(False)
    return s


def open_log_socket():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(LOGS)
    except OSError as e:
        sys.exit(f"cannot bind udp/{LOGS[1]}: {e} (already running?)")
    s.setblocking(False)
    return s


def send_cmd(s, text):
    payload = text.encode() if isinstance(text, str) else text
    s.send(PHONE_MAC + HOST_MAC + struct.pack("!H", ETHERTYPE) + payload)


def read_cmd_reply(s):
    try:
        data = s.recv(2048)
    except BlockingIOError:
        return None
    if len(data) < 15 or data[6:12] != PHONE_MAC:
        return None
    if struct.unpack("!H", data[12:14])[0] != ETHERTYPE:
        return None
    return data[14:]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-i", "--iface", help="interface for commands (default: the phone's MAC)")
    ap.add_argument("-c", "--cmd", action="append", help="send a command; repeatable")
    ap.add_argument("-f", "--file", help="append the log stream to this file")
    ap.add_argument("-n", "--no-logs", action="store_true", help="commands only")
    args = ap.parse_args()

    cmd_so = None
    if args.iface or find_iface() or args.cmd:
        iface = args.iface or find_iface()
        if iface:
            cmd_so = open_cmd_socket(iface)
        elif args.cmd:
            sys.exit("no interface with the phone's MAC -- is it booted with fuxihw=1?")

    if args.cmd:
        for c in args.cmd:
            if cmd_so:
                send_cmd(cmd_so, c if c.endswith("\n") else c + "\n")
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            r = read_cmd_reply(cmd_so) if cmd_so else None
            if r:
                sys.stdout.buffer.write(r)
                sys.stdout.buffer.flush()
        return

    log_so = None if args.no_logs else open_log_socket()
    fh = open(args.file, "ab", buffering=0) if args.file else None
    socks = [s for s in (log_so, cmd_so) if s]
    if not socks:
        sys.exit("nothing to listen to: phone interface not found")
    sys.stdout.write(f"# fuxi-netlog: logs udp:{LOGS[1]}"
                     f"{', commands on ' + cmd_so.getsockname()[0] if cmd_so else ''}\n")
    sys.stdout.flush()
    try:
        while True:
            readable, _, _ = select.select(socks, [], [], 5.0)
            for s in readable:
                if s is log_so:
                    data, _ = log_so.recvfrom(4096)
                    sys.stdout.buffer.write(data)
                    sys.stdout.buffer.flush()
                    if fh:
                        fh.write(data)
                else:
                    r = read_cmd_reply(s)
                    if r:
                        sys.stdout.buffer.write(b"\n# reply: " + r)
                        sys.stdout.buffer.flush()
            # stdin: type a command and it goes to the phone
            if cmd_so and select.select([sys.stdin], [], [], 0)[0]:
                line = sys.stdin.readline()
                if not line:
                    break
                if line.strip():
                    send_cmd(cmd_so, line)
    except KeyboardInterrupt:
        sys.stdout.write("\n# stopped\n")
    finally:
        if fh:
            fh.close()


if __name__ == "__main__":
    main()

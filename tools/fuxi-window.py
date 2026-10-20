#!/usr/bin/env python3
"""Time the XNU window: from 1209:0001 appearing to it disappearing.

Polls lsusb (the gadget ID is unmistakable) and reports both edges with a monotonic
clock, so the hypervisor-watchdog theory can be tested against a number instead of a
feeling.  Also reports any netdev that appears while the gadget is up.
"""
import os
import subprocess
import time

DEADLINE = float(os.environ.get("FUXI_DEADLINE", "240"))
t0 = time.monotonic()
appeared = None
gone = None
seen_ifaces = []

while time.monotonic() - t0 < DEADLINE:
    out = subprocess.run(["lsusb"], capture_output=True, text=True).stdout
    up = "1209:0001" in out
    ifaces = [n for n in os.listdir("/sys/class/net") if n.startswith(("enx", "usb"))]
    for i in ifaces:
        if i not in seen_ifaces:
            seen_ifaces.append(i)
            print(f"  +{time.monotonic() - t0:6.1f}s netdev {i}")
    if up and appeared is None:
        appeared = time.monotonic() - t0
        print(f"  +{appeared:6.1f}s gadget 1209:0001 up")
    elif not up and appeared is not None and gone is None:
        gone = time.monotonic() - t0
        print(f"  +{gone:6.1f}s gadget gone  -> window {gone - appeared:.1f}s")
        break
    time.sleep(0.4)

if appeared is None:
    print("gadget never appeared")
elif gone is None:
    print(f"gadget still up after {time.monotonic() - t0:.1f}s")

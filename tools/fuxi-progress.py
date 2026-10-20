#!/usr/bin/env python3
"""Capture the boot screen repeatedly and report the progress bar's fill.

The bar is the only progress signal the phone gives us.  Width in pixels, with a
timestamp, turns "it feels slow" into a rate and an estimate of what is left.
"""
import os
import subprocess
import sys
import time

from PIL import Image

OUTDIR = "/tmp/fuxi/progress"
SAMPLES = int(sys.argv[1]) if len(sys.argv) > 1 else 6
GAP = float(sys.argv[2]) if len(sys.argv) > 2 else 45.0
os.makedirs(OUTDIR, exist_ok=True)

t0 = time.time()
for i in range(SAMPLES):
    shot = f"{OUTDIR}/s{i}.png"
    r = subprocess.run(["sudo", "-S", "timeout", "60", "python3",
                        "/mnt/hdd/Bomb/ios-fuxi-mt/tools/fuxi-spam.py", shot, "4", "45"],
                       input="Vipadni\n", capture_output=True, text=True)
    if not os.path.exists(shot):
        print(f"+{time.time()-t0:6.1f}s  no frame ({r.stderr.strip()[-60:]})")
    else:
        im = Image.open(shot).convert("L")
        w, h = im.size
        best = (0, 0)
        for y in range(int(h * 0.5), int(h * 0.8)):
            n = 0
            for x in range(w):
                if im.getpixel((x, y)) > 200:
                    n += 1
                elif n:
                    break
            if n > best[1]:
                best = (y, n)
        pct = 100.0 * best[1] / w if w else 0
        print(f"+{time.time()-t0:6.1f}s  bar {best[1]:3d}px at y={best[0]:3d}  ~{pct:4.1f}%"
              f"  ({shot})")
    if i != SAMPLES - 1:
        time.sleep(GAP)

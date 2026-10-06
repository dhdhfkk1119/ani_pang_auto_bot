"""Save a native-res frame whenever the screen changes (you play manually).

usage: python record.py [max_frames] [interval_sec]
"""
import sys
import time
from pathlib import Path

import cv2

import adb

out = Path(__file__).parent / "shots" / "rec"
out.mkdir(parents=True, exist_ok=True)
max_frames = int(sys.argv[1]) if len(sys.argv) > 1 else 300
interval = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0

prev, n = None, 0
while n < max_frames:
    img = adb.screencap()
    small = cv2.cvtColor(cv2.resize(img, (234, 108)), cv2.COLOR_BGR2GRAY)
    if prev is None or cv2.absdiff(small, prev).mean() > 1.5:
        cv2.imwrite(str(out / f"{int(time.time() * 1000)}.png"), img)
        prev, n = small, n + 1
        print(n, flush=True)
    time.sleep(interval)

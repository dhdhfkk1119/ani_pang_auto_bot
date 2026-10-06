"""ADB helper: screencap + tap on the connected Galaxy (landscape 2340x1080)."""
import subprocess
import time

import cv2
import numpy as np

ADB = r"D:\auto_bot\scrcpy-win64-v4.1\adb.exe"
SERIAL = None  # None -> the only connected device


def _cmd(*args):
    base = [ADB] + (["-s", SERIAL] if SERIAL else [])
    return base + list(args)


def screencap():
    """Return the current screen as a BGR numpy image."""
    raw = subprocess.run(_cmd("exec-out", "screencap", "-p"),
                         capture_output=True, check=True).stdout
    img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError("screencap failed")
    return img


GAME_PKG = "com.sundaytoz.kakao.poker.service"
PAY_WORDS = ("vending", "billing", "spay", "payment", "purchase", "checkout")

# NEVER tap these (real-money paths): 상점 button, gold/gem '+' in lobby/mission/profile
BLOCK = [
    (485, 907, 731, 1080),      # lobby 상점
    (1690, 37, 1737, 84),       # lobby gold +
    (2088, 37, 2141, 84),       # lobby gem +
]
# only valid outside a room (they overlap the in-room 방이동 button at x~1802)
BLOCK_SCREENS = [
    (1760, 30, 1850, 105),      # profile/mission gold +
    (2130, 30, 2215, 105),      # profile/mission gem +
]


class PaymentGuard(SystemExit):
    """Exit code 4: a payment screen was detected; the supervisor must not restart."""

    def __init__(self, msg):
        print(msg, flush=True)
        super().__init__(4)


def focus():
    out = subprocess.run(_cmd("shell", "dumpsys", "window"), capture_output=True,
                         text=True, errors="ignore").stdout
    return " ".join(l.strip() for l in out.splitlines() if "mCurrentFocus" in l)


def payment_guard():
    """Abort (after BACK) if a payment / non-game window has focus."""
    f = focus().lower()
    if any(w in f for w in PAY_WORDS):
        for _ in range(4):
            key(4)                       # BACK
            time.sleep(0.5)
        raise PaymentGuard("PAYMENT SCREEN DETECTED -> backed out, bot stopped: " + f)


def blocked(x, y, room=False):
    zones = BLOCK if room else BLOCK + BLOCK_SCREENS
    return any(x0 <= x <= x1 and y0 <= y <= y1 for x0, y0, x1, y1 in zones)


def tap(x, y, wait=0.0, room=False):
    """room=True: the caller verified we are inside a game room."""
    if blocked(x, y, room):
        print(f"  [guard] tap ({x},{y}) is in a purchase-related area -> refused",
              flush=True)
        return
    payment_guard()
    subprocess.run(_cmd("shell", "input", "tap", str(int(x)), str(int(y))),
                   check=True)
    if wait:
        time.sleep(wait)


def key(code):
    subprocess.run(_cmd("shell", "input", "keyevent", str(code)), check=True)

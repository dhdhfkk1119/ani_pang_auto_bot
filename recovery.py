"""Out-of-gold recovery (lobby). Order:
  1. 돈 받기 팝업이 있으면 확인 (이게 기본리필)
  2. 기본리필 (하루 5회, refill_state.json 에 날짜별로 기록)
  3. 리필이 끝나면 미션 보상을 '하나만' 받는다 (한번에 다받기 금지)
"""
import datetime
import json
from pathlib import Path

import cv2
import cvio  # noqa: F401  (unicode-safe imread/imwrite)

import adb

ROOT = Path(__file__).parent
STATE = ROOT / "refill_state.json"
UI = ROOT / "templates" / "ui"
MAX_REFILL = 5

PROFILE_TAP = (100, 67)
REFILL_TAP = (1615, 445)        # 기본리필 N회
CLOSE_TAP = (2270, 67)          # X on 내 정보 / 미션
MISSION_TAP = (1328, 995)       # 미션 icon on the lobby bottom bar
# reward buttons of the 일일 미션 tab (calibrated against a live frame)
MISSION_BTN_Y = 893
MISSION_BTN_X = (543, 1127, 1691)


def _today():
    return datetime.date.today().isoformat()


def refills_used():
    try:
        d = json.loads(STATE.read_text())
        return d["used"] if d.get("date") == _today() else 0
    except Exception:
        return 0


def _set_refills(n):
    STATE.write_text(json.dumps({"date": _today(), "used": n}))


def _best(img, name, roi):
    x0, y0, x1, y1 = roi
    t = cv2.imread(str(UI / name))
    if t is None or img is None or img.shape[0] < y1 or img.shape[1] < x1:
        return 0.0, None
    res = cv2.matchTemplate(img[y0:y1, x0:x1], t, cv2.TM_CCOEFF_NORMED)
    _, mx, _, loc = cv2.minMaxLoc(res)
    return mx, (x0 + loc[0] + t.shape[1] // 2, y0 + loc[1] + t.shape[0] // 2)


def find_confirm(img, thr=0.85):
    """Center (x,y) of the 확인 button of the free-refill popup ("실망하지 마세요!
    무료로 포커머니가 충전됐습니다!"), only when BOTH the popup title and the
    button match -> no other 확인 (shop / purchase dialogs) is ever pressed."""
    title, _ = _best(img, "confirm_refill_title.png", (600, 150, 1750, 480))
    if title < thr:
        return None
    btn, pos = _best(img, "confirm_refill_btn.png", (1000, 620, 1650, 900))
    return pos if btn >= thr else None


def press_confirm(img=None):
    img = adb.screencap() if img is None else img
    pos = find_confirm(img)
    if pos:
        print("  confirm popup ->", pos, flush=True)
        adb.tap(*pos, wait=1.5)
        return True
    return False


def is_lobby(img):
    """True only on the main lobby (never click the profile inside a room)."""
    t = cv2.imread(str(UI / "lobby_chip.png"))
    res = cv2.matchTemplate(img[400:880, 380:850], t, cv2.TM_CCOEFF_NORMED)
    return res.max() >= 0.9


def basic_refill():
    """프로필 -> 기본리필 -> (확인 팝업) -> 닫기. Counts as one refill."""
    used = refills_used()
    if used >= MAX_REFILL:
        return False
    if not is_lobby(adb.screencap()):
        print("  not in lobby -> profile tap skipped", flush=True)
        return False
    print(f"  기본리필 {used + 1}/{MAX_REFILL}", flush=True)
    adb.tap(*PROFILE_TAP, wait=2.5)
    adb.tap(*REFILL_TAP, wait=2.5)
    press_confirm()
    _set_refills(used + 1)
    adb.tap(*CLOSE_TAP, wait=2)
    return True


def active_reward(img):
    """Index of the first mission reward button that is lit (claimable)."""
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    vals = []
    for x in MISSION_BTN_X:
        vals.append(float(g[MISSION_BTN_Y - 20:MISSION_BTN_Y + 20, x - 100:x + 100].mean()))
    best = max(range(3), key=lambda i: vals[i])
    return (best, vals) if vals[best] - min(vals) > 15 else (None, vals)


def claim_one_mission():
    """Open 미션, claim exactly ONE lit reward, close. Returns True if claimed."""
    print("  미션 보상 1개 수령 시도", flush=True)
    if not is_lobby(adb.screencap()):
        print("  not in lobby -> mission tap skipped", flush=True)
        return False
    adb.tap(*MISSION_TAP, wait=2.5)
    img = adb.screencap()
    cv2.imwrite(str(ROOT / "shots" / "mission_last.png"), img)
    if is_lobby(img):                      # mission screen did not open
        print("  mission screen did not open", flush=True)
        return False
    idx, vals = active_reward(img)
    print("  reward brightness", [round(v) for v in vals], "->", idx, flush=True)
    ok = False
    if idx is not None:
        adb.tap(MISSION_BTN_X[idx], MISSION_BTN_Y, wait=2)
        press_confirm()
        ok = True
    adb.tap(*CLOSE_TAP, wait=2)
    return ok


def recover():
    """One recovery step from the lobby. Returns a short description."""
    if press_confirm():
        return "confirm"
    if basic_refill():
        return "refill"
    return "mission" if claim_one_mission() else "nothing"

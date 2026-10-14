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


def find_afk(img, thr=0.85):
    """'장시간 자리비움으로 인해 타이틀로 이동합니다' popup -> its 확인 button.
    The message AND the button must match."""
    msg, _ = _best(img, "afk_msg.png", (700, 300, 1640, 640))
    if msg < thr:
        return None
    btn, pos = _best(img, "reward_ok_btn.png", (960, 640, 1380, 840))
    return pos if btn >= thr else None


LAST_GOLD = ROOT / "logs" / "last_gold.txt"


def save_last_gold(g):
    """Remember the last gold read in a room (만 units) across restarts."""
    if g:
        try:
            LAST_GOLD.write_text(str(int(g)))
        except Exception:
            pass


def last_gold():
    try:
        return int(LAST_GOLD.read_text())
    except Exception:
        return None


def find_gift_popup(img, thr=0.85):
    """'보관함에 선물이 있어요. 확인하러 가시겠어요? [다음에] [보관함 가기]' on the lobby.
    Returns {'next': (x,y), 'go': (x,y)} or None."""
    msg, _ = _best(img, "gift_popup_msg.png", (700, 300, 1640, 640))
    if msg < thr:
        return None
    n_sc, n_pos = _best(img, "gift_popup_next.png", (760, 640, 1200, 840))
    g_sc, g_pos = _best(img, "gift_popup_go.png", (1120, 640, 1580, 840))
    if n_sc < thr or g_sc < thr:
        return None
    return {"next": n_pos, "go": g_pos}


def find_noentry(img, thr=0.85):
    """'보유 금액이 부족해 입장이 불가능합니다.' popup -> its 확인 button (same pill as the
    reward popup). Seeing it means the room could not be entered: not enough gold."""
    msg, _ = _best(img, "noentry_msg.png", (700, 300, 1640, 640))
    if msg < thr:
        return None
    btn, pos = _best(img, "reward_ok_btn.png", (960, 640, 1380, 840))
    return pos if btn >= thr else None


def find_bracket(img, thr=0.85):
    """'경기장 입장 자산 구간에 맞지 않아 로비로 이동하였습니다.' popup -> its 확인 button."""
    msg, _ = _best(img, "bracket_msg.png", (700, 300, 1640, 640))
    if msg < thr:
        return None
    btn, pos = _best(img, "reward_ok_btn.png", (960, 640, 1380, 840))
    return pos if btn >= thr else None


def find_generic_ok(img, thr=0.9):
    """Any DIMMED info popup that has the single centred 확인 pill (the shape shared by the
    reward / entry-refused / AFK popups). Purchase dialogs have two buttons and never match."""
    if img is None or img.shape[:2] != (1080, 2340):
        return None
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if g.mean() > 60:                  # a popup dims the whole screen
        return None
    btn, pos = _best(img, "reward_ok_btn.png", (960, 640, 1380, 840))
    return pos if btn >= thr else None


def find_reconnect(img, thr=0.85, btn_only_thr=0.92):
    """Center of '다시 연결' on a connection popup ("서버 연결이 일시적으로 불안정합니다",
    "네트워크 연결이 끊겼습니다", ...). Message + button must match; a very clean match
    of the button alone also counts, because that button text only exists on these popups."""
    btn, pos = _best(img, "reconnect_btn.png", (960, 640, 1380, 840))
    if btn < thr:
        return None
    msg, _ = _best(img, "reconnect_msg.png", (700, 300, 1640, 640))
    return pos if (msg >= thr or btn >= btn_only_thr) else None


def press_reward_ok(img=None):
    """확인 on the '게임머니 N 골드 획득!' popup. Only called inside the reward-claim
    flows (미션 / 보관함), never from the generic loop."""
    img = adb.screencap() if img is None else img
    sc, pos = _best(img, "reward_ok_btn.png", (960, 640, 1380, 840))
    if sc >= 0.85:
        print("  reward popup -> 확인", pos, flush=True)
        adb.tap(*pos, wait=1.5)
        return True
    return False


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


# mission screen: tab -> (tab tap point, x of each reward button). Same y for all.
MISSION_TABS = {"일일": ((420, 196), (544, 1118, 1694)),
                "주간": ((710, 196), (498, 948, 1398, 1848))}
LIT_MIN = 60     # mean gray of a claimable reward button ~96, dim ~34-40


def lit_rewards(img, xs):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    vals = [float(g[MISSION_BTN_Y - 22:MISSION_BTN_Y + 22, x - 80:x + 80].mean()) for x in xs]
    return [i for i, v in enumerate(vals) if v >= LIT_MIN], vals


def claim_one_mission(tabs=("일일", "주간")):
    """Open 미션 and claim exactly ONE lit reward (daily tab first, then weekly).
    Returns True if one was claimed."""
    print("  미션 보상 1개 수령 시도", flush=True)
    if not is_lobby(adb.screencap()):
        print("  not in lobby -> mission tap skipped", flush=True)
        return False
    adb.tap(*MISSION_TAP, wait=3)
    img = adb.screencap()
    if is_lobby(img):                      # mission screen did not open
        print("  mission screen did not open", flush=True)
        return False
    ok = False
    for name in tabs:
        tab_xy, xs = MISSION_TABS[name]
        adb.tap(*tab_xy, wait=2)
        img = adb.screencap()
        cv2.imwrite(str(ROOT / "shots" / f"mission_{name}.png"), img)
        lit, vals = lit_rewards(img, xs)
        print(f"  {name} 미션 보상 밝기 {[round(v) for v in vals]} -> 수령 가능 {lit}", flush=True)
        if lit:
            adb.tap(xs[lit[0]], MISSION_BTN_Y, wait=2)      # ONE reward only
            press_reward_ok() or press_confirm()
            ok = True
            break
    adb.tap(*CLOSE_TAP, wait=2)
    return ok


STORAGE_TAP = (846, 971)       # 보관함 on the lobby bottom bar (x>731: outside the 상점 block)
GIFT_TAB_TAP = (340, 410)      # 선물 tab inside 보관함
GIFT_RECEIVE_X = 1936          # 받기 buttons column


def find_gift_gold(img, thr=0.85):
    """y of the first gift row that contains a gold coin ('N억 골드' + 받기), else None.
    Rows with tickets / cards / gems have no coin and are never pressed."""
    t = cv2.imread(str(UI / "gift_coin.png"))
    if t is None or img is None or img.shape[0] < 900:
        return None
    y0, y1, x0, x1 = 180, 900, 1380, 1900
    res = cv2.matchTemplate(img[y0:y1, x0:x1], t, cv2.TM_CCOEFF_NORMED)
    _, mx, _, loc = cv2.minMaxLoc(res)
    if mx < thr:
        return None
    return y0 + loc[1] + t.shape[0] // 2


def is_storage_screen(img, thr=0.85):
    """The 보관함 screen header (top left)."""
    sc, _ = _best(img, "storage_header.png", (0, 0, 500, 160))
    return sc >= thr


def claim_in_storage(img=None):
    """We are ON the 보관함 screen: 선물 tab -> the gold gift's 받기 (ONE gift,
    never 모두 받기) -> 확인 -> close with X. Returns True if gold was claimed."""
    adb.tap(*GIFT_TAB_TAP, wait=1.5)
    img = adb.screencap()
    cv2.imwrite(str(ROOT / "shots" / "storage_last.png"), img)
    y = find_gift_gold(img)
    ok = False
    if y is not None:
        print(f"  gold gift row at y={y} -> 받기", flush=True)
        adb.tap(GIFT_RECEIVE_X, y, wait=2.5)
        press_reward_ok() or press_confirm()
        ok = True
    else:
        print("  no gold gift", flush=True)
    adb.tap(*CLOSE_TAP, wait=2)
    return ok


def claim_storage_gold():
    """Last resort when refills and mission rewards are used up:
    보관함 > 선물 > the gold gift > 받기 (ONE gift per call; never 모두 받기)."""
    print("  보관함 > 선물 > 골드 받기 시도", flush=True)
    if not is_lobby(adb.screencap()):
        print("  not in lobby -> storage skipped", flush=True)
        return False
    adb.tap(*STORAGE_TAP, wait=2.5)
    if is_lobby(adb.screencap()):
        print("  storage did not open", flush=True)
        return False
    return claim_in_storage()


def recover():
    """One recovery step from the lobby, in the user's order:
    무료충전 확인 -> 기본리필(5/일) -> 보관함 선물 골드 -> 미션 보상. Never pays."""
    if press_confirm():
        return "confirm"
    if basic_refill():
        return "refill"
    if claim_storage_gold():
        return "storage"
    return "mission" if claim_one_mission() else "nothing"

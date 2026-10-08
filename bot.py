"""Anipang 7-poker bot. Rule: call only with one pair or better, else die.

usage: python bot.py [max_seconds] [--dry]
Stops (without acting) when a card can't be read -> label templates/unknown.
"""
import csv
import datetime
import sys
import time
from pathlib import Path

import cv2
import cvio  # noqa: F401  (unicode-safe imread/imwrite)

import adb
import cards
import hands
import ocr
import recovery
import strategy

UI = Path(__file__).parent / "templates" / "ui"
RUN = Path(__file__).parent / "shots" / "run"
RUN.mkdir(parents=True, exist_ok=True)
MAX_FRAMES = 300
T = {p.stem: cv2.imread(str(p)) for p in UI.glob("*.png")}

BTN_Y = 1018
BTN_X = {"die": 260, "ping": 622, "ttadang": 985, "call": 1349,
         "quarter": 1712, "half": 2077}
ROOM_TAP = (614, 641)           # 1500만 room chip in lobby
OTHER_ROOM_TAP = (1170, 480)    # "다른 방 입장하기"
MOVE_ROOM_TAP = (1802, 42)      # "방이동" (top right inside a room)
ALONE_WAIT = 60                 # alone / no game starting this long -> other room
EXIT_OK, EXIT_OUT_OF_GOLD = 0, 3
LOGS = Path(__file__).parent / "logs"
LOGS.mkdir(exist_ok=True)
UNREAD = LOGS / "unreadable"     # frames where my cards could not be read (kept)
RETAP_GAP = 2.5                  # don't re-tap a choose/open card within this time
SEATS = {"TL": (318, 126, 459, 264), "ML": (318, 386, 459, 524),
         "TR": (1879, 126, 2020, 264), "MR": (1879, 386, 2020, 524)}
DRY = "--dry" in sys.argv


def active_opponents(img):
    """Opponents currently in the hand = seats that have face-up cards.
    Empty seats, '대기중' players and folded players (cards turned face-down)
    have none, so they are simply not counted."""
    out = []
    for seat in cards.OPP_ANCHOR:
        if cards.count_open(img, seat) > 0:
            out.append([c for c in cards.read_opp(img, seat) if c])
    return out


def score(img, name, roi, thr=0.9):
    y0, y1, x0, x1 = roi
    return cv2.matchTemplate(img[y0:y1, x0:x1], T[name],
                             cv2.TM_CCOEFF_NORMED).max() >= thr


def in_room(img):
    """True when the room's 방이동 button is on screen (only inside a game room)."""
    return score(img, "room_move", (0, 100, 1700, 1900), 0.85)


def state(img):
    if img.shape[:2] != (1080, 2340):
        return "unknown"
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if g.mean() < 25:
        return "loading"
    if score(img, "lobby_chip", (400, 880, 380, 850)):
        return "lobby"
    if score(img, "choose", (920, 1030, 900, 1450)):
        return "choose"
    if score(img, "open", (920, 1030, 900, 1450)):
        return "open"
    if score(img, "other_room", (400, 560, 950, 1400)):
        return "alone"
    if not in_room(img):
        return "unknown"          # shop / event popup / anything else: do NOT tap
    die = g[1000:1040, 200:320].mean()
    call = g[1000:1040, 1290:1410].mean()
    if die > 50 and call > 50:
        return "my_turn"
    return "wait"


def find_close_x(img, thr=0.8):
    """Center of an X (close) button anywhere on the screen, or None."""
    t = T["close_x"]
    res = cv2.matchTemplate(img, t, cv2.TM_CCOEFF_NORMED)
    _, mx, _, loc = cv2.minMaxLoc(res)
    if mx < thr:
        return None
    return loc[0] + t.shape[1] // 2, loc[1] + t.shape[0] // 2


def best_discard(cs):
    """Index of the card to throw away from the first 4."""
    # Without a pair, draws come before high cards: the old key compared the
    # high cards first and kept 4-5-7 over 3c-4c-7c (flush draw) / 3-4-5
    # (straight draw). Vs 1500-sim equity on 120 hands: best pick 58% -> 75%.
    def key(sub):
        v = hands.evaluate(sub)
        ranks = sorted(c[0] for c in sub)
        suited = len({c[1] for c in sub}) == 1
        spans = [ranks[2] - ranks[0]]
        if 14 in ranks:                      # A plays low too (A-2-3-4-5 백스트레이트)
            low = sorted(1 if r == 14 else r for r in ranks)
            spans.append(low[2] - low[0])
        span = min(spans) if len(set(ranks)) == 3 else 99
        conn = 3 if span == 2 else 2 if span == 3 else 1 if span == 4 else 0
        if v[0] >= hands.PAIR:
            return (1, v[0], v[1:3], suited, conn)
        return (0, suited, conn, ranks[2], ranks[1])
    best = max(range(4), key=lambda i: key([c for j, c in enumerate(cs) if j != i]))
    return best


def dim_cards(img):
    """Indices of the (greyed-out, '선택취소') card(s) on the choose/open screen."""
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return [i for i, l in enumerate(cards.CH_LEFTS)
            if g[860:880, l + 8:l + 30].mean() < 150]


def best_open(cs):
    """Index (into cs, None entries allowed) of the card to turn face-up:
    keep pairs / flush mates hidden, show the lowest loose card."""
    def key(i):
        c = cs[i]
        if c is None:
            return (0, 0, 0)
        others = [d for j, d in enumerate(cs) if j != i and d]
        paired = any(d[0] == c[0] for d in others)
        suited = any(d[1] == c[1] for d in others)
        return (paired, suited, c[0])
    return min(range(len(cs)), key=key)


def card_tap_x(i):
    """First card overlaps the avatar column (x 834-975): tap its left part so a
    late tap can never open the profile popup and cover the cards."""
    return cards.CH_LEFTS[i] + (40 if i == 0 else 96)


def tap_card(i, want):
    """Tap card i at once (the prompt only lasts a few seconds). The tap x is
    kept clear of the avatar column, so a late tap can't open the profile."""
    if DRY:
        return True
    adb.tap(card_tap_x(i), cards.CH_TAP_Y)
    return True


def find_start_button(img):
    """'게임 시작' button that appears on my seat panel once somebody joins.
    No template yet -> look for a saturated, button-shaped blob on the panel."""
    x0, x1, y0, y1 = 1000, 1500, 700, 880
    hsv = cv2.cvtColor(img[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)
    mask = ((hsv[..., 1] > 110) & (hsv[..., 2] > 140)).astype("uint8") * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9)))
    cs, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    for c in cs:
        x, y, w, h = cv2.boundingRect(c)
        if w * h >= 3000 and w > h * 1.3 and (best is None or w * h > best[2] * best[3]):
            best = (x, y, w, h)
    return None if best is None else (x0 + best[0] + best[2] // 2, y0 + best[1] + best[3] // 2)


def prune_frames():
    fs = sorted(RUN.glob("*.png"), key=lambda p: p.stat().st_mtime)
    for p in fs[:-MAX_FRAMES]:
        p.unlink(missing_ok=True)


def log_decision(cs, opp, call_amt, gold, move, why):
    path = LOGS / "decisions.csv"
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["time", "cards", "opp_open", "call_man", "gold_man", "move", "reason"])
        w.writerow([datetime.datetime.now().isoformat(timespec="seconds"),
                    " ".join(hands.fmt(c) for c in cs),
                    " | ".join(" ".join(hands.fmt(c) for c in o) for o in opp),
                    call_amt, gold, move, why])


def act(name):
    x = BTN_X[name]
    print("  ->", name, flush=True)
    if not DRY:
        adb.tap(x, BTN_Y)


def main():
    limit = float(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1][0] != "-" else 600
    if limit <= 0:
        limit = float("inf")                  # run until stopped
    t0, last, hand_n = time.time(), None, 0
    alone_since = None
    idle_since = None                       # in a room, no game running
    unknown_since = None
    invested, start_gold, last_n = 0, None, 0     # exposure in the current hand
    lobby_tries = 0
    nothing_n = 0
    pending_discard, open_retries = None, 0
    tapped = {"choose": 0.0, "open": 0.0}       # last card-tap time per prompt
    while time.time() - t0 < limit:
        img = adb.screencap()
        s = state(img)
        if s in ("loading", "lobby"):           # free-refill popup dims the lobby
            pos = recovery.find_confirm(img)
            if pos:
                print("  free refill popup -> 확인", pos, flush=True)
                adb.tap(*pos, wait=1.5)
                continue
        if s != "lobby":
            lobby_tries = 0
        if s != "alone":
            alone_since = None
        if s != "wait":
            idle_since = None
        if s != "unknown":
            unknown_since = None
        if s in ("choose", "lobby", "loading"):
            invested, start_gold = 0, None            # a new hand starts
        if s == "my_turn":
            pending_discard, open_retries = None, 0
        if s != last:
            print(f"[{time.time() - t0:5.0f}s] {s}", flush=True)
            if s != "wait":
                cv2.imwrite(str(RUN / f"{int(time.time() * 1000)}_{s}.png"), img)
                prune_frames()
            last = s
        if s == "lobby":
            lobby_tries += 1
            if lobby_tries > 3:          # can't enter the room -> out of gold
                res = recovery.recover()
                print("  lobby stuck -> recover:", res, flush=True)
                lobby_tries = 0
                nothing_n = nothing_n + 1 if res == "nothing" else 0
                if nothing_n >= 10:
                    print("OUT OF GOLD: refills used and no mission reward left. "
                          "Stopping (no payment is ever made).", flush=True)
                    return EXIT_OUT_OF_GOLD
                if res == "nothing":        # nothing claimable right now
                    time.sleep(30)
            adb.tap(*ROOM_TAP, wait=4)
        elif s == "alone":
            # alone in the room: wait for someone; else move to a populated room
            alone_since = alone_since or time.time()
            if time.time() - alone_since > ALONE_WAIT:
                print("  alone 60s+ -> 다른 방 입장하기", flush=True)
                adb.tap(*OTHER_ROOM_TAP, wait=3, room=True)
                alone_since = None
            else:
                time.sleep(1.0)
        elif s == "choose" and time.time() - tapped["choose"] < RETAP_GAP:
            time.sleep(0.3)                   # tapped already; wait for the screen to move on
        elif s == "open" and time.time() - tapped["open"] < RETAP_GAP:
            time.sleep(0.3)
        elif s == "choose":
            cs = cards.read_choose(img)
            print("  hand:", [hands.fmt(c) if c else None for c in cs])
            if None in cs:
                print("  unreadable card -> skip (auto discard)")
                time.sleep(6)
                continue
            i = best_discard(cs)
            print("  discard", hands.fmt(cs[i]))
            if tap_card(i, "choose"):
                pending_discard = i
                tapped["choose"] = time.time()
            time.sleep(0.3)
        elif s == "open":
            dims = dim_cards(img)
            if (pending_discard is not None and dims and dims != [pending_discard]
                    and open_retries < 2):
                print(f"  wrong card discarded (dim={dims}, want {pending_discard})"
                      " -> cancel and redo", flush=True)
                tap_card(dims[0], "open")
                tapped["open"] = time.time() - RETAP_GAP + 0.8
                open_retries += 1
                time.sleep(0.8)
                continue
            cs = cards.read_choose(img, dump=False)
            keep = [i for i in range(4) if i not in dims]
            i = keep[best_open([cs[k] for k in keep])]
            print("  open", hands.fmt(cs[i]) if cs[i] else i, flush=True)
            tap_card(i, "open")
            tapped["open"] = time.time()
            time.sleep(0.3)
        elif s == "my_turn":
            cs = cards.read_cards(img, dump=False)
            t_read = time.time()
            # dealing / result animation or a popup can cover the cards for a
            # moment -> keep re-reading for up to ~5s (the turn timer is 10s)
            while (len(cs) < 3 or None in cs) and time.time() - t_read < 5:
                time.sleep(0.3)
                img = adb.screencap()
                if state(img) != "my_turn":
                    break
                cs = cards.read_cards(img, dump=False)
            if state(img) != "my_turn":
                continue
            print("  hand:", [hands.fmt(c) if c else None for c in cs])
            if len(cs) < 3 or None in cs:
                cards.read_cards(img)       # dump unknown glyphs for labeling
                UNREAD.mkdir(exist_ok=True)
                cv2.imwrite(str(UNREAD / f"{int(time.time() * 1000)}.png"), img)
                if score(img, "lbl_check", (985, 1055, 1290, 1410), 0.9):
                    print("  unreadable card -> free check (frame saved in logs/unreadable)")
                    act("call")
                else:
                    print("  unreadable card -> die (frame saved in logs/unreadable)")
                    act("die")
            else:
                is_check = score(img, "lbl_check", (985, 1055, 1290, 1410), 0.9)
                opp = active_opponents(img)
                print("  opp open:", [[hands.fmt(c) for c in o] for o in opp])
                call_amt = 0 if is_check else ocr.read_amount(img, ocr.CALL_BOX)
                gold = ocr.read_balance(img)
                pot = ocr.read_amount(img, ocr.TOTAL_BOX)
                for _ in range(2):        # flying chips can cover the numbers -> re-read
                    if call_amt is not None and pot is not None:
                        break
                    time.sleep(0.3)
                    img2 = adb.screencap()
                    if call_amt is None:
                        call_amt = ocr.read_amount(img2, ocr.CALL_BOX)
                    if pot is None:
                        pot = ocr.read_amount(img2, ocr.TOTAL_BOX)
                print(f"  call {ocr.fmt(call_amt)} | pot {ocr.fmt(pot)} | gold {ocr.fmt(gold)}", flush=True)
                if len(cs) < last_n:                      # missed the hand start
                    invested, start_gold = 0, None
                last_n = len(cs)
                if start_gold is None:
                    start_gold = gold
                move, why = strategy.decide(cs, max(1, len(opp)), is_check, opp,
                                            call_amt, gold, pot, invested, start_gold)
                if move == "call" and call_amt:
                    invested += call_amt
                print(f"  {move}: {why}", flush=True)
                log_decision(cs, opp, call_amt, gold, move, why)
                act("call" if move == "call" else "die")
            time.sleep(2)
        elif s == "unknown":
            # not a room / lobby / loading screen (shop, event popup, ...): never tap
            # anything; after a while press BACK once to close it.
            pos = recovery.find_confirm(img)      # 돈 받기 popup over the lobby
            if pos:
                print("  confirm popup", flush=True)
                adb.tap(*pos, wait=1.5)
                continue
            x = find_close_x(img)                 # ads / shop / mailbox ... -> X
            if x:
                print("  unknown screen -> X button", x, flush=True)
                cv2.imwrite(str(LOGS / "unknown_last.png"), img)
                adb.tap(*x, wait=1.5)
                continue
            unknown_since = unknown_since or time.time()
            if time.time() - unknown_since > 12:
                print("  unknown screen -> BACK", flush=True)
                cv2.imwrite(str(LOGS / "unknown_last.png"), img)
                adb.payment_guard()
                adb.key(4)
                unknown_since = time.time()
            time.sleep(1.0)
        else:
            no_game = (s == "wait" and cards.count_cards(img) == 0
                    and not any(cards.count_open(img, k) for k in cards.OPP_ANCHOR)
                    and ocr.read_amount(img, ocr.TOTAL_BOX) == 0)
            if not no_game:
                idle_since = None
            else:
                idle_since = idle_since or time.time()
                if time.time() - idle_since > ALONE_WAIT:
                    print("  no game for 60s+ -> 방이동", flush=True)
                    adb.tap(*MOVE_ROOM_TAP, wait=3, room=True)
                    idle_since = None
                    continue
                btn = find_start_button(img)      # 게임 시작 button (someone joined)
                if btn:
                    print("  start button ->", btn, flush=True)
                    cv2.imwrite(str(LOGS / "start_button_last.png"), img)
                    adb.tap(*btn, wait=2, room=True)
                    continue
            pos = recovery.find_confirm(img)      # 돈 받기 등 확인 팝업
            if pos:
                print("  confirm popup", flush=True)
                adb.tap(*pos, wait=1.5)
            else:
                time.sleep(0.7)
        time.sleep(0.3)


if __name__ == "__main__":
    sys.exit(main() or EXIT_OK)

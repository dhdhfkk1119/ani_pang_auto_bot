"""Screen-recognition inventory: runs every recognizer on a saved real screenshot.

usage: python check_screens.py        (no phone needed)"""
import glob, os
import cv2
import bot, recovery, cards, ocr, hands

def load(p):
    im = cv2.imread(p)
    return im
run = sorted(glob.glob("shots/run/*.png"), key=os.path.getmtime)
def newest(tag):
    c = [p for p in run if p.endswith(f"_{tag}.png")]
    return c[-1] if c else None

rows = []
def check(name, path, fn, expect):
    if not path or not os.path.exists(path):
        rows.append((name, "(no sample)", "-", "?")); return
    try:
        got = fn(load(path))
    except Exception as e:
        got = f"ERR {type(e).__name__}"
    ok = "OK" if (expect(got) if callable(expect) else got == expect) else "FAIL"
    rows.append((name, os.path.basename(path), str(got)[:38], ok))

st = bot.state
check("로비 (새: 1억/3억 칩)", newest("lobby"), st, "lobby")
check("로비 (예전: 1500만 칩)", "shots/now2.png", st, "lobby")
check("타이틀 화면", "shots/run/1791568965621_unknown.png", st, "title")
check("방 - 내 차례", "shots/f12.png", st, "my_turn")
check("방 - 버릴 카드 선택", "shots/f7.png", st, "choose")
check("방 - 오픈 카드 선택", "shots/diag/01.png", st, "open")
check("방 - 혼자('다른 방 입장하기')", "shots/f2.png", st, "alone")
check("팝업 - 장시간 자리비움 [확인]", "shots/afk_full.png", recovery.find_afk, lambda g: g is not None)
check("팝업 - 서버 연결 불안정 [다시 연결]", "shots/reconnect_frame.png", recovery.find_reconnect, lambda g: g is not None)
check("팝업 - 보유 금액 부족 입장 불가 [확인]", "shots/noentry_full.png", recovery.find_noentry, lambda g: g is not None)
check("팝업 - 무료 충전 [확인]", "shots/broke_full.png", recovery.find_confirm, lambda g: g is not None)
check("팝업 - 보관함 선물이 있어요", "shots/gift_popup_full.png", recovery.find_gift_popup, lambda g: g is not None)
check("보관함 화면(헤더)", "shots/storage_test.png", recovery.is_storage_screen, True)
check("보관함 > 선물 > 골드 줄", "shots/storage_test.png", recovery.find_gift_gold, lambda g: g is not None)
check("미션 일일 - 수령 가능 없음", "shots/mission_daily.png", lambda im: recovery.lit_rewards(im, recovery.MISSION_TABS["일일"][1])[0], [])
check("미션 주간 - 첫 보상 활성", "shots/mission_now.png", lambda im: recovery.lit_rewards(im, recovery.MISSION_TABS["주간"][1])[0], [0])
check("상점 (결제 화면) -> unknown + X", "logs/start_button_last.png", lambda im: (st(im), bot.find_close_x(im) is not None), ("unknown", True))
check("내 정보(프로필) -> unknown + X", "shots/profile.png", lambda im: (st(im), bot.find_close_x(im) is not None), ("unknown", True))
check("카드 읽기 (내 패 7장)", "shots/f12.png", lambda im: len(cards.read_cards(im, dump=False)), 6)
check("금액 읽기 (콜)", "shots/bad1.png", lambda im: ocr.fmt(ocr.read_amount(im, ocr.CALL_BOX)), "1억 3125만")
check("금액 읽기 (내 보유금)", "shots/bad1.png", lambda im: ocr.fmt(ocr.read_balance(im)), "48억 3091만")
print(f"{'화면':36s} {'샘플':28s} {'인식 결과':38s} 판정")
for r in rows:
    print(f"{r[0]:36s} {r[1]:28s} {r[2]:38s} {r[3]}")

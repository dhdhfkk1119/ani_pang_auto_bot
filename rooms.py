"""Which lobby chip to enter. Chips (left to right): 1500만, 1억, 3억, ... Each has an asset
bracket. The server tells us when we picked wrong:
  '경기장 입장 자산 구간에 맞지 않아 로비로 이동하였습니다'  -> too rich: go one chip right
  '보유 금액이 부족해 입장이 불가능합니다'                  -> too poor: go one chip left
The learned bounds are remembered (logs/rooms.json) and dropped when gold changes a lot."""
import json
from pathlib import Path

FILE = Path(__file__).parent / "logs" / "rooms.json"
ROOM_X = (610, 1030, 1450, 1870)     # centres of the 4 visible chips (native px)
ROOM_Y = 650
MAX_IDX = len(ROOM_X) - 1


def _load():
    try:
        return json.loads(FILE.read_text())
    except Exception:
        return {"idx": 0, "floor": 0, "cap": MAX_IDX, "gold": None}


def _save(d):
    try:
        FILE.write_text(json.dumps(d))
    except Exception:
        pass


def _fresh(d, gold):
    """Forget the learned bounds when gold moved by more than 35% since they were learned."""
    if gold and d.get("gold") and abs(gold - d["gold"]) > 0.35 * d["gold"]:
        d = {"idx": 0, "floor": 0, "cap": MAX_IDX, "gold": None}
    return d


def index(gold=None):
    d = _fresh(_load(), gold)
    d["idx"] = max(d["floor"], min(d["idx"], d["cap"], MAX_IDX))
    _save(d)
    return d["idx"]


def tap_xy(gold=None):
    return (ROOM_X[index(gold)], ROOM_Y)


def too_rich(gold=None):
    """Bracket mismatch: this chip is below my asset bracket -> next chip to the right."""
    d = _fresh(_load(), gold)
    d["floor"] = min(d["idx"] + 1, MAX_IDX)
    d["idx"] = d["floor"]
    d["cap"] = max(d["cap"], d["floor"])
    d["gold"] = gold or d.get("gold")
    _save(d)
    return d["idx"]


def too_poor(gold=None):
    """Not enough gold for this chip -> previous chip to the left."""
    d = _fresh(_load(), gold)
    d["cap"] = max(d["idx"] - 1, 0)
    d["idx"] = d["cap"]
    d["floor"] = min(d["floor"], d["cap"])
    d["gold"] = gold or d.get("gold")
    _save(d)
    return d["idx"]

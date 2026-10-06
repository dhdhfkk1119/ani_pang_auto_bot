"""Read '1억 3125만 골드' style gold amounts (fixed font -> segment + template match).

Amounts are returned in 만 units (1억 = 10000).
"""
from pathlib import Path

import cv2
import numpy as np

TPL = Path(__file__).parent / "templates" / "ocr"
TPL_BAL = Path(__file__).parent / "templates" / "ocr_bal"
SIZE = (24, 32)
CALL_BOX = (552, 580, 1060, 1365)    # y0,y1,x0,x1  (CALL row)
TOTAL_BOX = (503, 531, 1060, 1365)
BAL_BOX = (824, 852, 820, 990)       # my balance under the avatar (no '골드')


def segments(img, box, thr=110, mingap=2, rel=None):
    """rel: threshold may drop to rel*brightest pixel on dim frames."""
    y0, y1, x0, x1 = box
    g = cv2.cvtColor(img[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
    if rel:
        thr = min(thr, rel * float(g.max()))
    ink = (g > thr).astype(np.uint8)
    cols = ink.sum(axis=0) > 0
    out, s, gap = [], None, 0
    for i, v in enumerate(list(cols) + [False] * (mingap + 1)):
        if v:
            if s is None:
                s = i
            gap = 0
        elif s is not None:
            gap += 1
            if gap >= mingap:
                e = i - gap
                seg = ink[:, s:e + 1]
                ys = np.nonzero(seg.sum(axis=1))[0]
                if seg.sum() >= 6:
                    seg = seg[ys.min():ys.max() + 1]
                    out.append((x0 + s, cv2.resize(seg * 255, SIZE, interpolation=cv2.INTER_AREA)))
                s = None
    return out


def load():
    return {p.stem.split("_")[0]: [] for p in TPL.glob("*.png")} if False else _load()


def _load(tpl_dir=None):
    d = {}
    for p in (tpl_dir or TPL).glob("*.png"):
        d.setdefault(p.stem.split("_")[0], []).append(cv2.imread(str(p), 0))
    return d


def classify(seg, tpls):
    best, score = None, 0.0
    for k, ts in tpls.items():
        for t in ts:
            s = 1 - np.abs(seg.astype(float) - t.astype(float)).mean() / 255
            if s > score:
                best, score = k, s
    return best, score


def read_amount(img, box, thr=0.80, thr_seg=150, tpl_dir=None, rel=0.71):
    """-> amount in 만 units (sub-만 remainders are ignored), None if unreadable."""
    tpls = _load(tpl_dir)
    total, cur, seen = 0, "", False
    for _, seg in segments(img, box, thr=thr_seg, mingap=1, rel=rel):
        k, sc = classify(seg, tpls)
        if k is None or sc < thr:
            return None
        if k.isdigit():
            cur += k
        elif k == "eok":
            if not cur:
                return None
            total += int(cur) * 10000; cur = ""; seen = True
        elif k == "man":
            if not cur:
                return None
            total += int(cur); cur = ""; seen = True
        elif k in ("gol", "deu"):
            break
    if cur and not seen and int(cur) >= 10000:
        return int(cur) // 10000       # plain gold >= 1만 (not seen in practice)
    return total if (seen or cur == "0" or cur == "") else total


def fmt(v):
    if v is None:
        return "?"
    return f"{v // 10000}억 {v % 10000}만" if v >= 10000 else f"{v}만"


def read_balance(img):
    """My gold under the avatar (in 만 units), e.g. '76억8830만' -> 768830."""
    return read_amount(img, BAL_BOX, thr=0.80, thr_seg=105, tpl_dir=TPL_BAL, rel=0.55)

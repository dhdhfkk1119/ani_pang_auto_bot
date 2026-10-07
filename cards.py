"""Read my own cards from a 2340x1080 landscape frame (template matching).

Layout (after discarding): cards start at x=1006, step 54px, overlapped;
only the left strip (rank on top, suit below) of each card is visible except
the last one. Unknown glyphs are dumped to templates/unknown/ for labeling.
"""
from pathlib import Path

import cv2
import cvio  # noqa: F401  (unicode-safe imread/imwrite)
import numpy as np

import hands

TPL = Path(__file__).parent / "templates"
X0, STEP, MAXN = 1006, 54, 7
RANK_BOX = (4, 640, 52, 702)    # x offset from card left, y0, x1 offset, y1
SUIT_BOX = (4, 704, 52, 750)
SIZE = (32, 40)                  # normalized glyph size (w, h)
RANKS = {"A": 14, "K": 13, "Q": 12, "J": 11, "10": 10, "9": 9, "8": 8,
         "7": 7, "6": 6, "5": 5, "4": 4, "3": 3, "2": 2}


def count_cards(img):
    """Number of stacked cards, via the faint seam every 54px along the white
    margin above the rank glyphs (y=635..637; glyphs start at ~641)."""
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    row = g[635:638, :].mean(axis=0)
    if row[X0 + 20] < 180:
        return 0
    n = 1
    for i in range(1, MAXN):
        xl = X0 + STEP * i
        if row[xl - 6:xl + 4].min() < row[xl - 12] - 20 and row[xl + 10] > 150:
            n += 1
        else:
            break
    return n


def _glyph(img, box, left):
    x0, y0, x1, y1 = box
    patch = img[y0:y1, left + x0:left + x1]
    g = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)
    bg = np.median(g)
    ink = (np.abs(g.astype(int) - bg) > 60).astype(np.uint8) * 255
    ys, xs = np.nonzero(ink)
    if len(xs) < 20:
        return None, None
    ink = ink[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    # color: red ink vs black ink
    b, gr, r = (patch[..., i][ys.min():ys.max() + 1, xs.min():xs.max() + 1]
                for i in range(3))
    red = float(r[ink > 0].mean()) - float(b[ink > 0].mean()) > 40
    return cv2.resize(ink, SIZE, interpolation=cv2.INTER_AREA), red


def _solid(g):
    """Glyph that is ink almost everywhere = the card is covered/dimmed (popup,
    dealing or result animation), not an unknown glyph -> never dump it."""
    return g is not None and g.mean() > 200


def load_templates(kind):
    out = {}
    for p in (TPL / kind).glob("*.png"):
        out[p.stem.split("_")[0]] = cv2.imread(str(p), 0)
    return out


def _match(glyph, tpls):
    best, score = None, -1.0
    for k, t in tpls.items():
        s = 1 - np.abs(glyph.astype(float) - t.astype(float)).mean() / 255
        if s > score:
            best, score = k, s
    return best, score


def read_cards(img, thr=0.88, dump=True):
    """-> list of (rank, suit) or None for unreadable slot."""
    rt, st = load_templates("rank"), load_templates("suit")
    out = []
    for i in range(count_cards(img)):
        left = X0 + STEP * i
        rg, rred = _glyph(img, RANK_BOX, left)
        sg, sred = _glyph(img, SUIT_BOX, left)
        card = None
        if rg is not None and sg is not None:
            r, rs = _match(rg, rt)
            s, ss = _match(sg, st)
            if r and s and rs >= thr and ss >= thr:
                card = (RANKS[r], s)
        if (card is None and dump and rg is not None and sg is not None
                and not _solid(rg) and not _solid(sg)):
            d = TPL / "unknown"
            d.mkdir(parents=True, exist_ok=True)
            k = int(np.random.randint(1 << 30))
            cv2.imwrite(str(d / f"rank_{k}.png"), rg)
            cv2.imwrite(str(d / f"suit_{k}_{'red' if sred else 'blk'}.png"), sg)
        out.append(card)
    return out


def learn(img, labels):
    """Save templates from a frame whose stacked cards are known, e.g. 'AH AD 5S'."""
    for i, c in enumerate(labels.split()):
        left = X0 + STEP * i
        rg, _ = _glyph(img, RANK_BOX, left)
        sg, _ = _glyph(img, SUIT_BOX, left)
        for kind, name, g in (("rank", c[:-1], rg), ("suit", c[-1], sg)):
            d = TPL / kind
            d.mkdir(parents=True, exist_ok=True)
            n = len(list(d.glob(f"{name}_*.png")))
            cv2.imwrite(str(d / f"{name}_{n}.png"), g)


# ---- discard-selection layout (4 wide cards) ----
CH_LEFTS = [763, 970, 1176, 1383]
CH_TAP_Y = 772
CH_DY = 14  # card top is 14px lower than in the stacked layout


def read_choose(img, thr=0.88, dump=True):
    """Read the 4 cards of the discard-selection screen."""
    rt, st = load_templates("rank"), load_templates("suit")
    rbox = (2, RANK_BOX[1] + CH_DY, 54, RANK_BOX[3] + CH_DY)
    sbox = (2, SUIT_BOX[1] + CH_DY, 54, SUIT_BOX[3] + CH_DY)
    out = []
    for left in CH_LEFTS:
        rg, _ = _glyph(img, rbox, left)
        sg, sred = _glyph(img, sbox, left)
        card = None
        if rg is not None and sg is not None:
            r, rs = _match(rg, rt)
            s, ss = _match(sg, st)
            if r and s and rs >= thr and ss >= thr:
                card = (RANKS[r], s)
            elif dump and not _solid(rg) and not _solid(sg):
                d = TPL / "unknown"
                d.mkdir(parents=True, exist_ok=True)
                k = int(np.random.randint(1 << 30))
                cv2.imwrite(str(d / f"rank_{k}.png"), rg)
                cv2.imwrite(str(d / f"suit_{k}_{'red' if sred else 'blk'}.png"), sg)
        out.append(card)
    return out


def learn_choose(img, labels):
    """Save templates from a discard-selection frame with known cards."""
    for left, c in zip(CH_LEFTS, labels.split()):
        rg, _ = _glyph(img, (2, RANK_BOX[1] + CH_DY, 54, RANK_BOX[3] + CH_DY), left)
        sg, _ = _glyph(img, (2, SUIT_BOX[1] + CH_DY, 54, SUIT_BOX[3] + CH_DY), left)
        for kind, name, g in (("rank", c[:-1], rg), ("suit", c[-1], sg)):
            d = TPL / kind
            d.mkdir(parents=True, exist_ok=True)
            n = len(list(d.glob(f"{name}_*.png")))
            cv2.imwrite(str(d / f"{name}_{n}.png"), g)


# ---- opponents' open cards ----
# first 2 cards of every player are face-down; open cards start at index 2.
OPP_ANCHOR = {"TL": (486, 120), "ML": (486, 380), "TR": (1500, 120), "MR": (1500, 380)}
OPP_STEP = 37
OPP_RBOX = (4, 4, 36, 50)
OPP_SBOX = (4, 50, 36, 80)


def count_open(img, seat):
    """Number of face-up cards of an opponent (0 when folded / not dealt)."""
    ax, ay = OPP_ANCHOR[seat]
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    row = g[ay + 2:ay + 5, :].mean(axis=0)
    x2 = ax + OPP_STEP * 2
    if row[x2 + 12] < 200:
        return 0
    n = 1
    for i in range(3, 7):
        xl = ax + OPP_STEP * i
        if row[xl - 6:xl + 4].min() < row[xl - 12] - 15 and row[xl + 10] > 150:
            n += 1
        else:
            break
    return n


def _opp_glyphs(img, seat, i):
    ax, ay = OPP_ANCHOR[seat]
    left = ax + OPP_STEP * i
    rb = (OPP_RBOX[0], ay + OPP_RBOX[1], OPP_RBOX[2], ay + OPP_RBOX[3])
    sb = (OPP_SBOX[0], ay + OPP_SBOX[1], OPP_SBOX[2], ay + OPP_SBOX[3])
    return _glyph(img, rb, left)[0], _glyph(img, sb, left)[0]


def read_opp(img, seat, thr=0.82):
    """-> list of (rank,suit) or None per open card (None = unreadable)."""
    rt, st = load_templates("rank"), load_templates("suit")
    out = []
    for k in range(count_open(img, seat)):
        rg, sg = _opp_glyphs(img, seat, 2 + k)
        card = None
        if rg is not None and sg is not None:
            r, rs = _match(rg, rt)
            s, ss = _match(sg, st)
            if r and s and rs >= thr and ss >= thr:
                card = (RANKS[r], s)
        out.append(card)
    return out


def learn_opp(img, seat, labels):
    for k, c in enumerate(labels.split()):
        rg, sg = _opp_glyphs(img, seat, 2 + k)
        for kind, name, g in (("rank", c[:-1], rg), ("suit", c[-1], sg)):
            d = TPL / kind
            n = len(list(d.glob(f"{name}_*.png")))
            cv2.imwrite(str(d / f"{name}_{n}.png"), g)

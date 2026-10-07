"""Replay the logged hands through the CURRENT strategy.decide and compare money.

Parses logs/bot_*.log (call / pot / gold / hand / opponents per decision), rebuilds
each hand, takes the real result from the gold change to the next hand, and asks:
if today's rules had played it, where would they have folded and what would that
have saved / cost?  Hands whose gold change is not explained by the pot (safe
deposits, refills, rewards) are dropped.

usage: python replay.py [log files ...]
"""
import glob
import re
import sys
from collections import defaultdict

import hands
import strategy

UNIT = 10000.0                                   # 만 -> 억


def to_man(txt):
    if txt is None or txt.strip() in ("?", "None"):
        return None
    t = txt.replace(" ", "")
    m = re.fullmatch(r"(?:(\d+)억)?(?:(\d+)만)?", t)
    if not m or not (m.group(1) or m.group(2)):
        return None
    return int(m.group(1) or 0) * 10000 + int(m.group(2) or 0)


def parse(paths):
    rx = re.compile(
        r"  hand: (\[.*?\])\n  opp open: (\[.*?\])\n  call (\S+(?: \S+)?) \| pot (\S+(?: \S+)?) \| gold (\S+(?: \S+)?)\n"
        r"  (call|die): (.*?)\n  -> (\w+)")
    out = []
    for p in paths:
        txt = open(p, encoding="utf-8", errors="ignore").read()
        for m in rx.finditer(txt):
            cards = hands.parse(" ".join(re.findall(r"'(\w+)'", m.group(1))))
            opp = [hands.parse(" ".join(re.findall(r"'(\w+)'", g)))
                   for g in re.findall(r"\[(.*?)\]", m.group(2)[1:-1]) if g.strip()]
            out.append(dict(cards=cards, opp=opp, call=to_man(m.group(3)) or 0,
                            pot=to_man(m.group(4)), gold=to_man(m.group(5)),
                            move=m.group(6), reason=m.group(7)))
    return out


def group(rows):
    hs, cur = [], None
    for r in rows:
        if cur is None or r["cards"][:3] != cur[0]["cards"][:3]:
            cur = [r]
            hs.append(cur)
        else:
            cur.append(r)
    return hs


def main():
    paths = sys.argv[1:] or sorted(glob.glob("logs/bot_*.log"))
    hs = group(parse(paths))
    print(len(hs), "hands parsed from", len(paths), "log file(s)")
    tot_real = tot_new = 0.0
    used = skipped = changed = 0
    folded_wins, folded_losses = [], []
    for i, h in enumerate(hs[:-1]):
        g0, g1 = h[0]["gold"], hs[i + 1][0]["gold"]
        if g0 is None or g1 is None:
            continue
        delta = g1 - g0
        pots = [r["pot"] or 0 for r in h]
        # gold change must be explainable by this hand's pot, else it is an outside event
        if abs(delta) > 1.6 * max(pots + [1]) + 3000:
            skipped += 1
            continue
        used += 1
        invested = 0
        new_delta, cut = delta, None
        for r in h:
            if r["call"] == 0 and r["move"] == "call":
                continue                          # free check
            mv, _ = strategy.decide(r["cards"], max(1, len(r["opp"])), r["call"] == 0,
                                    r["opp"], r["call"], r["gold"], r["pot"],
                                    invested, h[0]["gold"])
            if r["move"] == "die":
                break                             # the real bot folded here anyway
            if mv == "die":
                cut = r
                new_delta = -invested             # fold now: lose only what is in
                break
            invested += r["call"]
        tot_real += delta
        tot_new += new_delta
        if cut is not None:
            changed += 1
            (folded_wins if delta > 0 else folded_losses).append(delta - new_delta)
    print(f"hands used {used}, dropped as outside gold events {skipped}")
    print(f"real result            : {tot_real / UNIT:8.1f}억")
    print(f"current rules, replayed: {tot_new / UNIT:8.1f}억   (changed {changed} hands)")
    print(f"  folds that would have thrown away a win : {len(folded_wins)} hands, "
          f"{-sum(folded_wins) / UNIT:.1f}억 forgone")
    print(f"  folds that would have saved a loss      : {len(folded_losses)} hands, "
          f"{-sum(folded_losses) / UNIT:.1f}억 saved")


if __name__ == "__main__":
    main()

"""Realized money of every CALL decision, bucketed (what is actually profitable?)."""
import glob, re, statistics as st, sys
import replay, hands

rows = replay.parse(sorted(glob.glob("logs/bot_*.log")))
H = replay.group(rows)
data = []
for i, h in enumerate(H[:-1]):
    g0, g1 = h[0]["gold"], H[i + 1][0]["gold"]
    if g0 is None or g1 is None:
        continue
    delta = g1 - g0
    pots = [r["pot"] or 0 for r in h]
    if abs(delta) > 1.6 * max(pots + [1]) + 3000:
        continue                                   # outside gold event
    inv = 0
    for r in h:
        if r["call"] == 0:
            continue
        m = re.search(r"eq=([\d.]+)\(raw ([\d.]+)\)", r["reason"]) or re.search(r"eq=([\d.]+)", r["reason"])
        eq = float(m.group(1)) if m else None
        raw = float(m.group(2)) if m and m.lastindex == 2 else eq
        nd = re.search(r"need=([\d.]+)", r["reason"])
        need = float(nd.group(1)) if nd else (r["call"] / (r["pot"] + r["call"]) if r["pot"] else None)
        if r["move"] == "call" and eq is not None and need:
            data.append(dict(n=len(r["cards"]), call=r["call"], pot=r["pot"] or 0, eq=eq, raw=raw,
                             need=need, margin=eq / need, made=hands.evaluate(r["cards"])[0],
                             real=delta + inv, win=delta > 0, hand=i))
            inv += r["call"]
        elif r["move"] == "call":
            inv += r["call"]
print(len(data), "call decisions with outcome,", len({d["hand"] for d in data}), "hands")

def table(title, key, edges):
    print(f"\n{title}")
    print(f"{'bucket':>12s} {'n':>4s} {'win%':>5s} {'avg real(억)':>12s} {'sum(억)':>8s}")
    for lo, hi in zip(edges[:-1], edges[1:]):
        b = [d for d in data if lo <= key(d) < hi]
        if not b: continue
        print(f"{lo:5.2f}-{hi:5.2f} {len(b):4d} {100*sum(d['win'] for d in b)/len(b):5.0f} "
              f"{st.mean(d['real'] for d in b)/10000:12.2f} {sum(d['real'] for d in b)/10000:8.1f}")

table("by margin = equity / pot-odds-need", lambda d: d["margin"], [0, 1.0, 1.15, 1.3, 1.6, 2.0, 3.0, 99])
table("by call/pot (bet size)", lambda d: d["call"] / max(d["pot"], 1), [0, .1, .2, .35, .5, .8, 99])
for n in (5, 6, 7):
    sub = [d for d in data if d["n"] == n]
    print(f"\nstreet n={n}: {len(sub)} calls, win% {100*sum(d['win'] for d in sub)/max(1,len(sub)):.0f}, "
          f"net {sum(d['real'] for d in sub)/10000:.1f}억")
    for lo, hi in ((0, 1.15), (1.15, 1.5), (1.5, 2.2), (2.2, 99)):
        b = [d for d in sub if lo <= d["margin"] < hi]
        if b: print(f"   margin {lo:.2f}-{hi:4.2f}: n={len(b):3d} win%={100*sum(d['win'] for d in b)/len(b):3.0f} net={sum(d['real'] for d in b)/10000:7.1f}억")

"""Backtest the equity model against logged hands (logs/decisions.csv).

For every hand I stayed in until the 7th card, recompute the equity at each of my
call decisions and compare with the actual outcome (gold delta > 0)."""
import csv, math, re, sys
import hands, strategy

rows = list(csv.DictReader(open("logs/decisions.csv", encoding="utf-8-sig")))
f3 = lambda r: tuple(r["cards"].split()[:3])
H, cur = [], None
for r in rows:
    if cur is None or f3(r) != f3(cur[0]):
        cur = [r]; H.append(cur)
    else:
        cur.append(r)
def gold(r):
    try: return int(r["gold_man"])
    except Exception: return None
samples = []
for i, h in enumerate(H[:-1]):
    s, n = gold(h[0]), gold(H[i + 1][0])
    if s is None or n is None or h[-1]["move"] == "die" or len(h[-1]["cards"].split()) != 7:
        continue
    win = 1 if n - s > 0 else 0
    for r in h:
        if r["move"] != "call" or r["reason"] == "free check":
            continue
        cs = hands.parse(r["cards"])
        opp = [hands.parse(o) for o in r["opp_open"].split(" | ") if o.strip()]
        call = int(r["call_man"]) if r["call_man"] not in ("", "None") else None
        samples.append((cs, opp, win, call))
print(len(samples), "call decisions from", len({id(x) for x in H}), "hands")

def brier(q, sims=300):
    tot = 0
    bins = {}
    for cs, opp, win, call in samples:
        e, _ = strategy.simulate(cs, max(1, len(opp)), opp, sims=sims, seed=1,
                                 bet_faced=bool(call), stay_q=q)
        tot += (e - win) ** 2
        b = min(int(e * 5), 4); bins.setdefault(b, []).append((e, win))
    return tot / len(samples), bins

for q in (0.0, 0.5, 0.7, 0.85, 0.95):
    b, bins = brier(q)
    cal = "  ".join(f"{k/5:.1f}+: pred {sum(e for e,_ in v)/len(v):.2f} act {sum(w for _,w in v)/len(v):.2f} (n={len(v)})" for k, v in sorted(bins.items()))
    print(f"stay_q={q:<4}  Brier={b:.4f} | {cal}", flush=True)

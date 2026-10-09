"""Grid over the call margin (equity / pot-odds need) with a train/test split by time.

Equity of each logged decision is simulated once and cached, so the grid is fast.
For each setting: replay all hands, report the money in both halves of the data.
A setting is only trustworthy if it helps in BOTH halves."""
import functools, glob, itertools, sys
import hands, replay, strategy

_sim = strategy.simulate
@functools.lru_cache(maxsize=None)
def _cached(cards, opp, bet_faced):
    return _sim(list(cards), max(1, len(opp)), [list(o) for o in opp], sims=500, seed=7, bet_faced=bet_faced)
strategy.simulate = lambda mine, n_opp, opp_open=(), sims=500, seed=None, bet_faced=False, stay_q=0.0: \
    _cached(tuple(mine), tuple(tuple(o) for o in opp_open), bool(bet_faced))

def run(hs):
    real = new = 0.0
    changed = 0
    for i, h in enumerate(hs[:-1]):
        g0, g1 = h[0]["gold"], hs[i + 1][0]["gold"]
        if g0 is None or g1 is None:
            continue
        delta = g1 - g0
        if abs(delta) > 1.6 * max([r["pot"] or 0 for r in h] + [1]) + 3000:
            continue
        inv, nd, cut = 0, delta, False
        for r in h:
            if r["call"] == 0 and r["move"] == "call":
                continue
            mv, _ = strategy.decide(r["cards"], max(1, len(r["opp"])), r["call"] == 0, r["opp"],
                                    r["call"], r["gold"], r["pot"], inv, h[0]["gold"])
            if r["move"] == "die":
                break
            if mv == "die":
                nd, cut = -inv, True
                break
            inv += r["call"]
        real += delta; new += nd; changed += cut
    return real / 1e4, new / 1e4, changed

hs = replay.group(replay.parse(sorted(glob.glob("logs/bot_*.log"))))
mid = len(hs) // 2
A, B = hs[:mid], hs[mid:]
print(len(hs), "hands; half A", len(A), "half B", len(B))
print(f"{'margin':>7s} {'pairFB':>6s} | {'A real':>7s} {'A new':>7s} | {'B real':>7s} {'B new':>7s} | {'all gain':>8s}")
rows = []
for m, fb in itertools.product((1.05, 1.3, 1.6, 2.0, 2.4, 3.0), (True, False)):
    strategy.MARGIN = {5: m, 6: max(m, 1.15), 7: max(m, 1.15)}
    strategy.PAIR_FALLBACK = fb
    ar, an, _ = run(A); br, bn, _ = run(B)
    rows.append((m, fb, ar, an, br, bn))
    print(f"{m:7.2f} {str(fb):>6s} | {ar:7.1f} {an:7.1f} | {br:7.1f} {bn:7.1f} | {(an-ar)+(bn-br):8.1f}", flush=True)

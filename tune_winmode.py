"""Expected number of hands WON (and the cost) for policies, on the logged hands.

A hand is 'won' with the calibrated win probability p of the last decision the policy
still plays (folding earlier = 0). Free checks are always taken. Cost proxy = money put
in per hand; EV proxy = p*(pot+call) - money in. Optimistic: p is the model's own estimate."""
import glob, functools
import hands, replay, strategy
exec(open('tune_margin.py').read().split("hs = replay.group")[0])      # cached simulate
hs = replay.group(replay.parse(sorted(glob.glob("logs/bot_*.log"))))
print(len(hs), "hands")

def evaluate(hlist):
    wins = cost = ev = 0.0; n = 0; played = 0
    for h in hlist:
        n += 1
        inv = 0; p_last = 0.0; pot_last = 0; alive = True; touched = False
        for r in h:
            if r["call"] == 0:
                continue
            mv, _ = strategy.decide(r["cards"], max(1, len(r["opp"])), False, r["opp"], r["call"],
                                    r["gold"], r["pot"], inv, h[0]["gold"])
            raw, _p2 = strategy.simulate(r["cards"], max(1, len(r["opp"])), r["opp"])
            p = strategy.winprob(raw, len(r["cards"]), r["cards"], r["opp"], r["call"], r["pot"])
            p = p if p is not None else raw * 0.74
            if mv == "die":
                alive = False
                break
            inv += r["call"]; p_last = p; pot_last = (r["pot"] or 0) + r["call"]; touched = True
        if alive and not touched:                        # only free checks: use the last logged equity
            raw, _ = strategy.simulate(h[-1]["cards"], max(1, len(h[-1]["opp"])), h[-1]["opp"])
            p_last = raw * 0.74
        if alive:
            played += 1
            wins += p_last; cost += inv; ev += p_last * pot_last - inv
    return wins / n, played / n, cost / n / 1e4, ev / n / 1e4

base = dict(WIN_MODE=strategy.WIN_MODE, WIN_EQ=strategy.WIN_EQ, WIN_CALL_FRAC=strategy.WIN_CALL_FRAC,
            WIN_EXPOSURE_FRAC=strategy.WIN_EXPOSURE_FRAC)
CONF = [("gold mode (no win mode)", dict(WIN_MODE=False)),
        ("current: eq>=.10, call<=gold/10, hand<=30%", dict(WIN_MODE=True, WIN_EQ=.10, WIN_CALL_FRAC=1/10, WIN_EXPOSURE_FRAC=.3)),
        ("eq>=.05, gold/10, 30%", dict(WIN_MODE=True, WIN_EQ=.05, WIN_CALL_FRAC=1/10, WIN_EXPOSURE_FRAC=.3)),
        ("eq>=.15, gold/10, 30%", dict(WIN_MODE=True, WIN_EQ=.15, WIN_CALL_FRAC=1/10, WIN_EXPOSURE_FRAC=.3)),
        ("eq>=.20, gold/10, 30%", dict(WIN_MODE=True, WIN_EQ=.20, WIN_CALL_FRAC=1/10, WIN_EXPOSURE_FRAC=.3)),
        ("eq>=.10, gold/5, 40%", dict(WIN_MODE=True, WIN_EQ=.10, WIN_CALL_FRAC=1/5, WIN_EXPOSURE_FRAC=.4)),
        ("eq>=.15, gold/5, 40%", dict(WIN_MODE=True, WIN_EQ=.15, WIN_CALL_FRAC=1/5, WIN_EXPOSURE_FRAC=.4)),
        ("eq>=.10, gold/20, 20%", dict(WIN_MODE=True, WIN_EQ=.10, WIN_CALL_FRAC=1/20, WIN_EXPOSURE_FRAC=.2))]
k = len(hs) // 2
print(f"{'policy':46s} | exp. win rate (all / 1st half / 2nd half) | hands played | money in/hand | EV/hand(억)")
for name, c in CONF:
    for kk, v in {**base, **c}.items(): setattr(strategy, kk, v)
    a = evaluate(hs); b = evaluate(hs[:k]); d = evaluate(hs[k:])
    print(f"{name:46s} | {a[0]*100:5.1f}% / {b[0]*100:5.1f}% / {d[0]*100:5.1f}%          | {a[1]*100:5.1f}%      | {a[2]:6.2f}억      | {a[3]:+6.2f}", flush=True)

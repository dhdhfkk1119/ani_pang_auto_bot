"""Old calibration vs the fitted win-probability model, with margins retuned.
Evaluated on three time blocks; a setting is only trusted if it beats the old rule in each."""
import glob, functools
import hands, replay, strategy
exec(open('tune_margin.py').read().split("hs = replay.group")[0])      # cached simulate + run()
hs = replay.group(replay.parse(sorted(glob.glob("logs/bot_*.log"))))
k = len(hs) // 3
blocks = [hs[:k], hs[k:2 * k], hs[2 * k:]]
base = dict(STRONG_EQ=.65, BIG_BET_EQ=.55, TWO_PAIR_7TH_MIN=.45, HARD_EQ=.85, EQ_QUARTER=.8, EQ_TEN_EOK=.7)
def setup(use, margin, scale):
    strategy.USE_WINPROB = use
    strategy.MARGIN = dict(zip((5, 6, 7), margin))
    for n_, v in base.items(): setattr(strategy, n_, round(v * scale, 3))
CONF = [("OLD calibrate, margins 1.05/1.3/1.5", False, (1.05, 1.3, 1.5), 1.0)]
for scale in (1.0, 0.8):
    for m in ((1.0, 1.0, 1.0), (1.05, 1.15, 1.3), (1.05, 1.3, 1.5), (1.25, 1.25, 1.25), (1.5, 1.5, 1.5)):
        CONF.append((f"NEW winprob, margins {m[0]}/{m[1]}/{m[2]}, thresholds x{scale}", True, m, scale))
print(f"{len(hs)} hands in 3 blocks of ~{k}\n{'setting':62s} | " + " | ".join(f"block{i+1} real->new" for i in range(3)) + " | total gain")
for name, use, m, sc in CONF:
    setup(use, m, sc)
    out = [run(b) for b in blocks]
    gain = sum(n - r for r, n, _ in out)
    print(f"{name:62s} | " + " | ".join(f"{r:6.1f}->{n:6.1f}" for r, n, _ in out) + f" | {gain:7.1f}", flush=True)

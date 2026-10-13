"""Fit a logistic win-probability calibration on the logged CALL decisions and check it
with a time-blocked cross-validation (never trained on the hands it is scored on)."""
import glob, json, math, re, sys
import numpy as np
import hands, replay

def build():
    rows = replay.parse(sorted(glob.glob("logs/bot_*.log")))
    H = replay.group(rows)
    X, y, hid = [], [], []
    for i, h in enumerate(H[:-1]):
        g0, g1 = h[0]["gold"], H[i + 1][0]["gold"]
        if g0 is None or g1 is None:
            continue
        delta = g1 - g0
        ref = max([r["pot"] or 0 for r in h] + [3 * r["call"] for r in h] + [1])
        if abs(delta) > 1.6 * ref + 3000:
            continue
        start_n = max(len(r["opp"]) for r in h)
        for r in h:
            if r["call"] == 0 or r["move"] != "call":
                continue
            m = re.search(r"eq=([\d.]+)\(raw ([\d.]+)\)", r["reason"]) or re.search(r"eq=([\d.]+)", r["reason"])
            if not m:
                continue
            raw = float(m.group(2)) if m.lastindex == 2 else float(m.group(1))
            X.append(features(raw, len(r["cards"]), len(r["opp"]), start_n, r["opp"], r["cards"], r["call"], r["pot"] or 0))
            y.append(1.0 if delta > 0 else 0.0)
            hid.append(i)
    return np.array(X), np.array(y), np.array(hid)

def features(raw, n, nopp, start_n, opp, cards, call, pot):
    vis = max([hands.evaluate(o)[0] if o else 0 for o in opp] + [0])
    made = hands.evaluate(cards)[0]
    p = min(max(raw, 0.02), 0.98)
    return [1.0, math.log(p / (1 - p)), (nopp - 2) / 2.0, max(0, start_n - nopp) / 2.0,
            1.0 if vis == hands.PAIR else 0.0, 1.0 if vis >= hands.TWO_PAIR else 0.0,
            1.0 if n == 6 else 0.0, 1.0 if n >= 7 else 0.0,
            1.0 if made == hands.TWO_PAIR else 0.0, 1.0 if made >= hands.TRIPLE else 0.0,
            min(call / pot, 1.5) if pot else 0.5]
NAMES = ["bias", "logit(raw eq)", "n_opp-2", "folded", "opp pair shown", "opp 2pair+ shown",
         "6th card", "7th card", "my two pair", "my trips+", "call/pot"]

def fit(X, y, l2=3.0, iters=60):
    w = np.zeros(X.shape[1]); w[1] = 1.0
    for _ in range(iters):
        p = 1 / (1 + np.exp(-X @ w))
        g = X.T @ (p - y) + l2 * np.r_[0, w[1:] * 0 + (w[1:] - np.r_[1.0, np.zeros(len(w) - 2)])]
        Wd = p * (1 - p)
        Hs = (X.T * Wd) @ X + l2 * np.eye(len(w))
        w -= np.linalg.solve(Hs, g)
    return w

def predict(w, X): return 1 / (1 + np.exp(-X @ w))
def brier(p, y): return float(np.mean((p - y) ** 2))
def logloss(p, y): p = np.clip(p, 1e-4, 1 - 1e-4); return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))

if __name__ == "__main__":
    X, y, hid = build()
    print(len(y), "decisions;", "base win rate %.3f" % y.mean())
    raw = 1 / (1 + np.exp(-X[:, 1]))
    folds = np.digitize(hid, np.quantile(hid, [0.2, 0.4, 0.6, 0.8]))     # 5 time blocks
    res = {"raw eq": [], "raw*0.74": [], "logistic": []}
    P = np.zeros(len(y))
    for f in range(5):
        tr, te = folds != f, folds == f
        w = fit(X[tr], y[tr]); P[te] = predict(w, X[te])
    for name, p in (("raw eq", raw), ("raw*0.74", raw * 0.74), ("logistic (5-fold time CV)", P)):
        print(f"{name:28s} Brier {brier(p, y):.4f}  logloss {logloss(p, y):.4f}")
    w = fit(X, y)
    print("\nfull-data coefficients:")
    for n_, c in zip(NAMES, w): print(f"  {n_:18s} {c:+.3f}")
    json.dump(dict(names=NAMES, w=[float(c) for c in w]), open("winprob_model.json", "w"))
    # calibration of the CV predictions
    print("\nCV calibration (predicted -> actual):")
    for lo, hi in ((0, .15), (.15, .3), (.3, .45), (.45, .6), (.6, .8), (.8, 1.01)):
        b = (P >= lo) & (P < hi)
        if b.sum() > 10: print(f"  {lo:.2f}-{hi:.2f}  n={int(b.sum()):4d}  pred {P[b].mean():.2f}  actual {y[b].mean():.2f}")

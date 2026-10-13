"""Does the model under/over-estimate my win chance depending on the table?
Groups every logged CALL decision by number of active opponents and by how strong the
opponents' OPEN cards look, and compares predicted equity with the real result."""
import glob, re, statistics as st
import hands, replay

rows = replay.parse(sorted(glob.glob("logs/bot_*.log")))
H = replay.group(rows)
data = []
for i, h in enumerate(H[:-1]):
    g0, g1 = h[0]["gold"], H[i + 1][0]["gold"]
    if g0 is None or g1 is None:
        continue
    delta = g1 - g0
    ref = max([r["pot"] or 0 for r in h] + [3 * r["call"] for r in h] + [1])
    if abs(delta) > 1.6 * ref + 3000:
        continue                                      # refill / gift / other gold event
    start_n = max(len(r["opp"]) for r in h)
    inv = 0
    for r in h:
        if r["call"] == 0:
            continue
        m = re.search(r"eq=([\d.]+)\(raw ([\d.]+)\)", r["reason"]) or re.search(r"eq=([\d.]+)", r["reason"])
        if r["move"] == "call" and m:
            eq = float(m.group(1)); raw = float(m.group(2)) if m.lastindex == 2 else eq
            vis = [hands.evaluate(o)[0] if o else 0 for o in r["opp"]]
            data.append(dict(n=len(r["cards"]), nopp=len(r["opp"]), folded=max(0, start_n - len(r["opp"])),
                             eq=eq, raw=raw, made=hands.evaluate(r["cards"])[0],
                             vis=max(vis) if vis else 0, win=delta > 0, real=delta + inv,
                             call=r["call"], hand=i))
            inv += r["call"]
        elif r["move"] == "call":
            inv += r["call"]
print(len(data), "call decisions in", len({d["hand"] for d in data}), "hands")

def table(title, keyf, labels):
    print(f"\n{title}")
    print(f"{'group':22s} {'n':>4s} {'pred':>5s} {'actual':>6s} {'ratio':>5s}")
    for lab, f in labels:
        b = [d for d in data if f(d)]
        if len(b) < 8: continue
        p = st.mean(d["eq"] for d in b); a = st.mean(d["win"] for d in b)
        print(f"{lab:22s} {len(b):4d} {p:5.2f} {a:6.2f} {a/p:5.2f}")
table("by number of ACTIVE opponents", None, [("1 opponent", lambda d: d["nopp"] == 1), ("2 opponents", lambda d: d["nopp"] == 2),
      ("3 opponents", lambda d: d["nopp"] == 3), ("4 opponents", lambda d: d["nopp"] >= 4)])
table("by how many players already FOLDED", None, [("none folded", lambda d: d["folded"] == 0), ("1 folded", lambda d: d["folded"] == 1),
      ("2 folded", lambda d: d["folded"] == 2), ("3+ folded", lambda d: d["folded"] >= 3)])
table("by strongest OPEN hand of the opponents", None, [("only high cards", lambda d: d["vis"] == hands.TOP),
      ("a pair showing", lambda d: d["vis"] == hands.PAIR), ("two pair / trips showing", lambda d: d["vis"] in (hands.TWO_PAIR, hands.TRIPLE)),
      ("straight+ showing", lambda d: d["vis"] >= hands.STRAIGHT)])
table("my made hand x opponents' open strength", None, [
      ("pair/top, opp weak", lambda d: d["made"] <= hands.PAIR and d["vis"] == hands.TOP),
      ("pair/top, opp pair+", lambda d: d["made"] <= hands.PAIR and d["vis"] >= hands.PAIR),
      ("two pair, opp weak", lambda d: d["made"] == hands.TWO_PAIR and d["vis"] == hands.TOP),
      ("two pair, opp pair+", lambda d: d["made"] == hands.TWO_PAIR and d["vis"] >= hands.PAIR),
      ("trips+, opp weak", lambda d: d["made"] >= hands.TRIPLE and d["vis"] == hands.TOP),
      ("trips+, opp pair+", lambda d: d["made"] >= hands.TRIPLE and d["vis"] >= hands.PAIR)])
table("by street", None, [("5th card", lambda d: d["n"] == 5), ("6th card", lambda d: d["n"] == 6), ("7th card", lambda d: d["n"] >= 7)])

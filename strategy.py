"""Probability-based call/die decision for 7-card stud (Korean rules).

Rules (from the user):
  * only die or call(check); decide within 10s
  * continue with a made pair+, or a draw with a real chance of two-pair+
    / straight / flush; give up if nothing is made by the 6th card
  * never call more than 2/3 of my gold unless win probability is high
  * apply standard poker probabilities for 2~5 players
"""
import random

import hands

FULL = [(r, s) for r in range(2, 15) for s in "SDHC"]


def _complete(cards, dead, rng, total=7):
    deck = [c for c in FULL if c not in dead]
    need = total - len(cards)
    return list(cards) + rng.sample(deck, need), deck


def simulate(mine, n_opp, opp_open=(), sims=500, seed=None, bet_faced=False, stay_q=0.0):
    """-> (equity, p_improve, p_twopair_plus).

    mine: my known cards (3..7). opp_open: visible opponent cards (list per
    opponent or empty). Unknown opponent cards are drawn at random.
    """
    rng = random.Random(seed)
    known = set(mine)
    opp_known = [list(o) for o in opp_open] + [[] for _ in range(max(0, n_opp - len(opp_open)))]
    for o in opp_known:
        known.update(o)
    win = 0.0
    made_two = 0
    used = 0
    for _ in range(sims):
        deck = [c for c in FULL if c not in known]
        rng.shuffle(deck)
        i = 0
        my = list(mine)
        while len(my) < 7:
            my.append(deck[i]); i += 1
        myv = hands.evaluate(my)
        best_opp = None
        for o in opp_known:
            for _try in range(6):
                oc = list(o)
                while len(oc) < 7:
                    oc.append(deck[i % len(deck)]); i += 1
                ov = hands.evaluate(oc)
                # an opponent still in the hand rarely holds only a top card:
                # redraw his hidden cards with probability stay_q
                if ov[0] >= hands.PAIR or stay_q <= 0 or rng.random() >= stay_q:
                    break
            if best_opp is None or ov > best_opp:
                best_opp = ov
        if bet_faced and best_opp is not None and best_opp[0] < hands.PAIR and rng.random() < 0.6:
            continue                    # someone bet: nobody holding only a top card is unlikely
        used += 1
        if myv[0] >= hands.TWO_PAIR:
            made_two += 1
        if best_opp is None or myv > best_opp:
            win += 1
        elif myv == best_opp:
            win += 0.5
    used = max(used, 1)
    return win / used, made_two / used


def start_pattern(first3):
    """User's 'don't die early' conditions on the first 3 cards (after the discard).
    Returns the matching pattern name or None."""
    if len(first3) < 3:
        return None
    ranks = [c[0] for c in first3]
    if len(set(ranks)) == 1:
        return "트리플"
    if len(set(ranks)) < 3:
        return "원페어"
    if len({c[1] for c in first3}) == 1:
        return "같은 무늬 3장"
    for r in (ranks, [1 if x == 14 else x for x in ranks]):   # ace high / low
        r = sorted(r)
        if r[2] - r[0] == 2:
            return "연속 3장"
        if r[2] - r[0] == 3:
            return "한 칸 빈 연속"
    return None


TEN_EOK = 100000      # 10억 in 만 units


# Calibration from logged hands (backtest.py): at the 7th-card bet only opponents
# with strong hands are left, so the plain simulation is overconfident.
# actual/predicted win ratio per made-hand group, shrunk toward 1 (small samples).
RATIO_7TH = {"low": 0.64, "two_pair": 0.68, "trips_straight": 0.86, "flush_up": 0.89}
RATIO_EARLY = {"low": 1.0, "two_pair": 0.92, "trips_straight": 0.97, "flush_up": 0.95}


def calibrate(equity, n, made):
    grp = ("low" if made <= hands.PAIR else "two_pair" if made == hands.TWO_PAIR
           else "trips_straight" if made <= hands.MOUNTAIN else "flush_up")
    return equity * (RATIO_7TH if n >= 7 else RATIO_EARLY)[grp]


def visible_summary(opp_open):
    """Best visible hand name per opponent (for the log)."""
    return [hands.NAMES[hands.evaluate(o)[0]] if o else "?" for o in opp_open]


def decide(mine, n_opp, is_check, opp_open=(), call=None, gold=None, pot=None,
           invested=0, start_gold=None):
    """Return ('call'|'die', reason). call/gold/pot are in 만 units (None = unknown).

    Core: call when my win probability beats the pot odds  call / (pot + call).
    The user's start-hand conditions and money limits stay as extra rules."""
    n = len(mine)
    made = hands.evaluate(mine)[0]
    if is_check:
        return "call", "free check"
    if call and gold and call >= gold * 0.95:
        return "die", f"call {call}만 ~ all-in (gold {gold}만)"
    raw_eq, p2 = simulate(mine, n_opp, opp_open, bet_faced=bool(call))
    equity = calibrate(raw_eq, n, made)
    fair = 1.0 / (n_opp + 1)
    need = call / (pot + call) if (call and pot) else 0.8 * fair   # pot odds
    vis = ",".join(visible_summary(opp_open))
    info = (f"n={n} opp={n_opp} made={hands.NAMES[made]} eq={equity:.2f}(raw {raw_eq:.2f}) need={need:.2f} "
            f"fair={fair:.2f} p2+={p2:.2f} vis=[{vis}]")
    if call and gold and call >= gold / 4:
        if n <= 5 or equity < 0.8:
            return "die", info + f" | call {call}만 >= 1/4 of gold {gold}만"
    # total committed in THIS hand (earlier calls + this one) must stay under 1/4
    # of the gold I had when the hand started, unless the hand is a near-lock
    if call and start_gold and invested + call >= start_gold / 4 and equity < 0.8:
        return "die", info + (f" | hand exposure {invested + call}만 >= 1/4 of "
                              f"start gold {start_gold}만")
    if call and call >= TEN_EOK and made < hands.TWO_PAIR and equity < 0.7:
        return "die", info + f" | call {call}만 >= 10억 without two pair"
    if n <= 5:
        pat = start_pattern(mine[:3])
        if equity >= need * 1.05:
            return "call", info + " | equity beats pot odds"
        if pat:
            return "call", info + f" | start: {pat}"
        if made >= hands.PAIR:
            return "call", info + " | pair+"
        return "die", info + " | equity below pot odds, no start pattern/pair"
    if equity >= need * 1.15 and (made >= hands.PAIR or p2 >= 0.25):
        return "call", info + " | equity beats pot odds"
    return "die", info + " | equity below pot odds"

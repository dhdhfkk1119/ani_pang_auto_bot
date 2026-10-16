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


def best_discard_mc(cards4, n_opp=3, sims=250, seed=11):
    """Index (0..3) of the card to throw away: the one whose remaining 3 cards have the
    highest simulated chance to win a hand (opponents' cards unknown). Ties -> None."""
    best, best_eq = None, -1.0
    scores = []
    for i in range(4):
        keep = [c for j, c in enumerate(cards4) if j != i]
        eq, _ = simulate(keep, n_opp, (), sims=sims, seed=seed)
        scores.append(eq)
    top = max(scores)
    cands = [i for i, e in enumerate(scores) if e >= top - 1e-9]
    return (cands[0] if len(cands) == 1 else None), scores


def is_draw(mine):
    """4+ cards of one suit or 4 cards inside a 5-rank window, and not yet a flush/straight."""
    if len(mine) >= 7 or hands.evaluate(mine)[0] >= hands.STRAIGHT:
        return False
    if max(sum(1 for _, s in mine if s == su) for su in "SDHC") >= 4:
        return True
    ranks = {r for r, _ in mine} | ({1} if any(r == 14 for r, _ in mine) else set())
    return max(sum(1 for x in range(lo, lo + 5) if x in ranks) for lo in range(1, 11)) >= 4


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
# equity must beat the pot-odds need by this factor (per street). The need only
# counts the CURRENT call, not the escalating bets that follow (tune_margin.py).
# 2.0 chosen by tune_margin.py: on 684 logged hands it beat the old 1.05/1.15 in all three
# thirds of the data (real -> replayed: -88.9->-15.7, -61.6->+81.4, +57.5->+121.3)
# 2026-10-12: 2.0 was replaced. Live it folded 90% of hands (49 hands: 1 win,
# -16.6억, 37 folded at the 5th card without one bet). Replaying 876 hands on the
# call decisions alone: 2.0 = +275억 / 98 wins, 1.05-1.15-1.15 = +292억 / 160 wins,
# 1.05-1.3-1.5 = +314억 / 156 wins. Differences in gold are within noise; the
# number of hands won is not.
MARGIN = {5: 1.05, 6: 1.3, 7: 1.5}
WIN_MODE = True            # maximise hands won (gold losses accepted); False = gold mode
WIN_EQ = 0.10# min win probability for a win-mode call (tune_winmode.py: .10 -> 17.0%, .05 -> 18.8% expected win rate)
WIN_CALL_FRAC = 1 / 10     # win-mode call must be <= this fraction of current gold
WIN_EXPOSURE_FRAC = 0.3
# Win mode, bigger bets (tune from the 10-15/16 logs, 391 folds facing a bet): the old
# "big bet" fold lost ~18.6 expected wins. Calls with eq >= 0.15 and call <= gold/3 were +9.3
# wins and +51억 EV; draws below that cost more than they win, so draws get a smaller allowance.
WIN_BIG_EQ = 0.15
LOW_RAW_BOOST = 1.3        # pair/two pair with raw eq < 0.6 (see decide)
FAVOURITE_EQ = 0.5         # calibrated eq at which money limits stop applying
CHEAP_FRAC = 1 / 20        # calls up to this share of gold only need eq >= pot-odds need
WIN_BIG_NEED = 1.0         # calls > gold/10 also need equity >= pot-odds need x this
WIN_DRAW_NEED = 0.8        # draws (implied odds) need equity >= need x this
WIN_BIG_CALL_FRAC = 1 / 3
WIN_DRAW_EQ = 0.10# flush / straight draw before the 7th card
WIN_DRAW_CALL_FRAC = 1 / 5
WIN_BIG_EXPOSURE_FRAC = 0.5
# Overnight run 10-16 (570 hands, gold 533억 -> 0.95억): win-mode entries below eq 0.10 won 7 of 84
# hands (-448억); win-mode calls at the 7th card below eq 0.25 won 4 of 63 (-377억) while eq >= 0.25 won
# 14 of 34. So the win mode is switched off below these equities.
WIN_EQ_7TH = 0.25    # ... and the hand total <= this fraction of start gold
PAIR_FALLBACK = False  # n<=5: calling any pair+ below the margin lost money (margin<1: 139 calls, -87억)
STRONG_EQ = 0.52# trips+ with this equity = strong: play through money limits
STRONG_NEED_CLAUSE = True   # trips+ also 'strong' when equity >= need*1.15
# Hard caps that even a 'strong' hand must obey (None = off). Live 10-13: trips called
# 39.8억 into an 86억 pot and 19.2억 more = -58억, trips 27.9억 = -28억, flush 17.2억
# = -17억 (all "strong made hand: ignore money limits"); gold 49억 -> 0 in ~1h.
HARD_CALL_FRAC = 1 / 2      # one call >= this fraction of current gold needs HARD_EQ
HARD_EXPOSURE_FRAC = 0.5    # hand exposure >= this fraction of start gold needs HARD_EQ
HARD_EQ = 0.68
EQ_QUARTER = 0.64# a call >= 1/4 of gold / hand exposure >= 1/4 of start gold needs this equity
EQ_TEN_EOK = 0.56# a call >= 10억 without two pair needs this equity
# tune_strong.py: on 1223 earlier hands these caps cost ~42억 (one big winning hand is
# folded) but they stop the three -28/-58/-17억 calls of 10-13 (gold 49억 -> 0).
BIG_BET_FRAC = 1 / 8  # a call this big (vs start gold) needs BIG_BET_EQ equity
BIG_BET_EQ = 0.44# replay of 69 hands: -77.8억 -> -45.9억, no winning hand cut
TWO_PAIR_7TH_MIN = 0.36# replay of 718 hands: with no start-pattern calls +279억


# Calibration from logged hands (backtest.py): at the 7th-card bet only opponents
# with strong hands are left, so the plain simulation is overconfident.
# actual/predicted win ratio per made-hand group, shrunk toward 1 (small samples).
RATIO_7TH = {"low": 0.64, "two_pair": 0.68, "trips_straight": 0.86, "flush_up": 0.89}
RATIO_EARLY = {"low": 1.0, "two_pair": 0.92, "trips_straight": 0.97, "flush_up": 0.95}


# Logistic win-probability calibration fitted on the logged calls (fit_winprob.py,
# 5-block time CV: Brier 0.2049 raw -> 0.1841 raw*0.74 -> 0.1796). Inputs besides the
# simulated equity: street, my made hand, opponents' open hand, call/pot (bet size).
import json as _json
from pathlib import Path as _Path
try:
    _WP = _json.loads((_Path(__file__).parent / "winprob_model.json").read_text())["w"]
except Exception:
    _WP = None
USE_WINPROB = True
# Thresholds below that compare with `equity` were retuned x0.8 for the calibrated scale
# (tune_winprob.py, 3 time blocks, margins 1.05/1.3/1.5): old rule +206억 vs new +631억 in the
# replay, better in every block. In-sample for the fit; judge it on hands logged after 10-14.


def winprob(raw_eq, n, mine, opp_open, call, pot):
    """Calibrated chance that I end up winning this hand (or None if no model)."""
    import math
    if not _WP:
        return None
    vis = max([hands.evaluate(o)[0] if o else 0 for o in opp_open] + [0])
    made = hands.evaluate(mine)[0]
    p = min(max(raw_eq, 0.02), 0.98)
    x = [1.0, math.log(p / (1 - p)),
         1.0 if vis == hands.PAIR else 0.0, 1.0 if vis >= hands.TWO_PAIR else 0.0,
         1.0 if n == 6 else 0.0, 1.0 if n >= 7 else 0.0,
         1.0 if made == hands.TWO_PAIR else 0.0, 1.0 if made >= hands.TRIPLE else 0.0,
         min(call / pot, 1.5) if (call and pot) else 0.5]
    z = sum(a * b for a, b in zip(_WP, x))
    return 1 / (1 + math.exp(-z))


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
    if is_check or call == 0:
        # 콜 for "0 골드" is as free as 체크: 96 such spots were folded (log 10-07~08)
        return "call", "free check" if is_check else "free call (0 골드)"
    raw_eq, p2 = simulate(mine, n_opp, opp_open, bet_faced=bool(call))
    equity = None
    if USE_WINPROB:
        equity = winprob(raw_eq, n, mine, opp_open, call, pot)
    if equity is None:
        equity = calibrate(raw_eq, n, made)
    # showdown check 10-14~16 (7th card calls): the model is right in the middle
    # but too low for pair / two pair with raw < 0.6 (pred 0.17/0.19, won
    # 0.22/0.27) and for flush+ (pred 0.71, won 0.90)
    if made in (hands.PAIR, hands.TWO_PAIR) and raw_eq < 0.6:
        equity = min(raw_eq, equity * LOW_RAW_BOOST)
    elif made >= hands.FLUSH:
        equity = max(equity, raw_eq * 0.95)
    fair = 1.0 / (n_opp + 1)
    need = call / (pot + call) if (call and pot) else 0.8 * fair   # pot odds
    vis = ",".join(visible_summary(opp_open))
    info = (f"n={n} opp={n_opp} made={hands.NAMES[made]} eq={equity:.2f}(raw {raw_eq:.2f}) need={need:.2f} "
            f"fair={fair:.2f} p2+={p2:.2f} vis=[{vis}]")
    # a made monster is never folded to a big bet / all-in: folding a full house
    # (-37억) and trips at eq 0.75 (-4.7억, -8.9억) after calling the smaller
    # bets cost more than every other leak together (log 2026-10-07)
    # trips+ that beat the pot odds also play through the money limits: trips
    # called at the 7th card won 59%, while 5 trips folded to big bets lost 119억
    # already all-in (gold 0): calling costs nothing more, folding throws the pot
    # away (10-16: A-flush folded all-in to a 10억 pot by the hard cap below)
    if gold == 0 and call:
        return "call", info + " | already all-in: call costs nothing"
    # flush or better is never folded to a money limit (same hand: eq 0.60 vs HARD_EQ)
    if made >= hands.FLUSH and equity >= need:
        return "call", info + " | flush+ beats pot odds: ignore money limits"
    # WIN MODE: a call that beats the pot odds is never folded by a money limit
    # (10-16 12:18~14:20: 11-17 of 109 folds were like that at a small bankroll)
    if WIN_MODE and call and equity >= need:
        return "call", info + " | win mode: equity beats pot odds, ignore money limits"
    # favourite: more likely to win than not and beating the pot odds -> call any
    # size (10-15~16: 9 folds to big bets at eq >= 0.5 = 5.2 wins thrown away)
    if call and equity >= FAVOURITE_EQ and equity >= need:
        return "call", info + f" | favourite: eq >= {FAVOURITE_EQ} beats pot odds, ignore money limits"
    # a cheap call that beats the pot odds is never folded by a hand-type rule
    # (10-16: 77-99 two pair folded at the 7th card with need 0.02, eq 0.19)
    if call and gold and call <= gold * CHEAP_FRAC and equity >= need:
        return "call", info + f" | cheap call beats pot odds (<= gold/{round(1 / CHEAP_FRAC)})"
    if HARD_CALL_FRAC and call and gold and call >= gold * HARD_CALL_FRAC and equity < HARD_EQ:
        return "die", info + f" | hard cap: call {call}만 >= {HARD_CALL_FRAC:.2f} of gold {gold}만"
    if (HARD_EXPOSURE_FRAC and call and start_gold
            and invested + call >= start_gold * HARD_EXPOSURE_FRAC and equity < HARD_EQ):
        return "die", info + (f" | hard cap: hand exposure {invested + call}만 >= "
                              f"{HARD_EXPOSURE_FRAC:.2f} of start gold {start_gold}만")
    strong = (made >= hands.FULL_HOUSE or (made >= hands.TRIPLE and equity >= STRONG_EQ)
              or (STRONG_NEED_CLAUSE and made >= hands.TRIPLE and equity >= need * 1.15))
    if strong:
        if equity >= need:
            return "call", info + " | strong made hand: ignore money limits"
        return "die", info + " | strong hand but equity below pot odds"
    # WIN-COUNT MODE (user, 2026-10-15): the goal is the number of hands won, gold
    # losses accepted. Any affordable call with a real chance is taken, even
    # below the pot odds. Logs 10-12~14 (1242 hands): folds with eq >= 0.15 and
    # call <= gold/10 were ~93 expected extra wins at ~0 expected cost (1st call).
    if (WIN_MODE and call and gold and call <= gold * WIN_CALL_FRAC
            and equity >= (WIN_EQ_7TH if n >= 7 else WIN_EQ)
            and (not start_gold or invested + call <= start_gold * WIN_EXPOSURE_FRAC)):
        return "call", info + f" | win mode: eq >= {WIN_EQ} and call <= gold/{round(1 / WIN_CALL_FRAC)}"
    if WIN_MODE and call and gold and (not start_gold or invested + call <= start_gold * WIN_BIG_EXPOSURE_FRAC):
        # big calls must not burn the bankroll: 10-16 09:00-09:30 lost 50억 in 25 min
        # on 2~8억 calls at eq 0.15 (gold/3 rule) -> once broke, no more wins at all
        if (equity >= (WIN_EQ_7TH if n >= 7 else WIN_BIG_EQ) and call <= gold * WIN_BIG_CALL_FRAC
                and equity >= need * WIN_BIG_NEED):
            return "call", info + f" | win mode: eq >= {WIN_BIG_EQ} and call <= gold/{round(1 / WIN_BIG_CALL_FRAC)}"
        if (equity >= WIN_DRAW_EQ and call <= gold * WIN_DRAW_CALL_FRAC and is_draw(mine)
                and equity >= need * WIN_DRAW_NEED):
            return "call", info + f" | win mode: draw, eq >= {WIN_DRAW_EQ} and call <= gold/{round(1 / WIN_DRAW_CALL_FRAC)}"
    if call and gold and call >= gold * 0.95:
        return "die", info + f" | call {call}만 ~ all-in (gold {gold}만)"
    # opponents escalate (0.75억 -> 3.75억 -> 18.75억): calling the middle bet with
    # a weak hand only to fold the big one bled ~100억. Stop at the first big bet.
    base = start_gold or gold
    if call and base and n >= 5 and call >= base * BIG_BET_FRAC and equity < BIG_BET_EQ:
        return "die", info + f" | big bet {call}만 >= 1/{round(1 / BIG_BET_FRAC)} of {base}만 with weak hand"
    if call and gold and call >= gold / 4:
        if n <= 5 or equity < EQ_QUARTER:
            return "die", info + f" | call {call}만 >= 1/4 of gold {gold}만"
    # total committed in THIS hand (earlier calls + this one) must stay under 1/4
    # of the gold I had when the hand started, unless the hand is a near-lock
    if call and start_gold and invested + call >= start_gold / 4 and equity < EQ_QUARTER:
        return "die", info + (f" | hand exposure {invested + call}만 >= 1/4 of "
                              f"start gold {start_gold}만")
    if call and call >= TEN_EOK and made < hands.TWO_PAIR and equity < EQ_TEN_EOK:
        return "die", info + f" | call {call}만 >= 10억 without two pair"
    # two pair at the 7th card was over-estimated: eq 0.3-0.4 won 7/34 (-136억)
    if n >= 7 and made == hands.TWO_PAIR and equity < TWO_PAIR_7TH_MIN:
        return "die", info + f" | two pair at 7th needs eq >= {TWO_PAIR_7TH_MIN}"
    if n <= 5:
        if equity >= need * MARGIN[5]:
            return "call", info + " | equity beats pot odds"
        # start patterns (3 suited / connected ...) no longer override the pot
        # odds: 112 such hands won 7 times and lost 207억 (log 10-07~08)
        if PAIR_FALLBACK and made >= hands.PAIR:
            return "call", info + " | pair+"
        return "die", info + " | equity below pot odds, no pair"
    if equity >= need * MARGIN[min(n, 7)] and (made >= hands.PAIR or p2 >= 0.25):
        return "call", info + " | equity beats pot odds"
    return "die", info + " | equity below pot odds"

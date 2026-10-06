"""Korean 7-poker hand evaluation.

Card = (rank, suit); rank 2..14 (A=14), suit in 'S','D','H','C'.
Korean suit order: spade > diamond > heart > club.
Category order (low -> high), matching the in-game 족보 panel:
  탑, 원페어, 투페어, 트리플, 스트레이트, 백스트레이트, 마운틴, 플러시,
  풀하우스, 포카드, 스트레이트플러시, 백스트레이트플러시, 로열스트레이트플러시
"""
from collections import Counter
from itertools import combinations

SUIT_ORDER = {"C": 0, "H": 1, "D": 2, "S": 3}

(TOP, PAIR, TWO_PAIR, TRIPLE, STRAIGHT, BACK_STRAIGHT, MOUNTAIN, FLUSH,
 FULL_HOUSE, FOUR_CARD, STRAIGHT_FLUSH, BACK_STRAIGHT_FLUSH,
 ROYAL_STRAIGHT_FLUSH) = range(13)

NAMES = ["탑", "원페어", "투페어", "트리플", "스트레이트", "백스트레이트",
         "마운틴", "플러시", "풀하우스", "포카드", "스트레이트플러시",
         "백스트레이트플러시", "로열스트레이트플러시"]

_RANK_CH = {14: "A", 13: "K", 12: "Q", 11: "J", 10: "10"}


def parse(text):
    """'AS KD 10H 2C' -> [(14,'S'), ...]"""
    out = []
    for tok in text.split():
        r, s = tok[:-1].upper(), tok[-1].upper()
        rank = {"A": 14, "K": 13, "Q": 12, "J": 11}.get(r) or int(r)
        out.append((rank, s))
    return out


def fmt(card):
    return f"{_RANK_CH.get(card[0], card[0])}{card[1]}"


def _eval5(cards):
    ranks = sorted((c[0] for c in cards), reverse=True)
    suits = {c[1] for c in cards}
    flush = len(suits) == 1
    cnt = Counter(ranks)
    groups = sorted(cnt.items(), key=lambda kv: (kv[1], kv[0]), reverse=True)
    uniq = len(cnt) == 5
    mountain = uniq and ranks == [14, 13, 12, 11, 10]
    back = uniq and ranks == [14, 5, 4, 3, 2]
    straight = uniq and ranks[0] - ranks[4] == 4
    top = max(cards, key=lambda c: (c[0], SUIT_ORDER[c[1]]))

    if flush and mountain:
        return (ROYAL_STRAIGHT_FLUSH, 14, SUIT_ORDER[top[1]])
    if flush and back:
        return (BACK_STRAIGHT_FLUSH, 5, SUIT_ORDER[top[1]])
    if flush and straight:
        return (STRAIGHT_FLUSH, ranks[0], SUIT_ORDER[top[1]])
    if groups[0][1] == 4:
        return (FOUR_CARD, groups[0][0], groups[1][0])
    if groups[0][1] == 3 and groups[1][1] == 2:
        return (FULL_HOUSE, groups[0][0], groups[1][0])
    if flush:
        return (FLUSH, *ranks, SUIT_ORDER[top[1]])
    if mountain:
        return (MOUNTAIN, 14, SUIT_ORDER[top[1]])
    if back:
        return (BACK_STRAIGHT, 5, SUIT_ORDER[top[1]])
    if straight:
        return (STRAIGHT, ranks[0], SUIT_ORDER[top[1]])
    return _multi(groups, cards)


def _multi(groups, cards):
    """Pairs/trips/top. Ties on the same ranks are broken by suit (Korean)."""
    best_suit = lambda r: max(SUIT_ORDER[c[1]] for c in cards if c[0] == r)
    kick = [r for r, n in groups if n == 1]
    if groups[0][1] == 3:
        return (TRIPLE, groups[0][0], *kick)
    if groups[0][1] == 2 and len(groups) > 1 and groups[1][1] == 2:
        hi, lo = groups[0][0], groups[1][0]
        return (TWO_PAIR, hi, lo, *kick, best_suit(hi))
    if groups[0][1] == 2:
        return (PAIR, groups[0][0], *kick, best_suit(groups[0][0]))
    ranks = sorted((c[0] for c in cards), reverse=True)
    return (TOP, *ranks, best_suit(ranks[0]))


def evaluate(cards):
    """Best hand value (comparable tuple) from 1..7 cards. Higher is better."""
    cards = list(cards)
    if len(cards) < 5:
        groups = sorted(Counter(c[0] for c in cards).items(),
                        key=lambda kv: (kv[1], kv[0]), reverse=True)
        if groups[0][1] == 4:
            return (FOUR_CARD, groups[0][0], 0)
        return _multi(groups, cards)
    return max(_eval5(c) for c in combinations(cards, 5))


def name(value):
    return NAMES[value[0]]

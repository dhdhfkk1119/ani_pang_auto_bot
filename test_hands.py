from hands import *


def h(t):
    return evaluate(parse(t))


def test_categories():
    assert h("AS KS QS JS 10S 2C 3D")[0] == ROYAL_STRAIGHT_FLUSH
    assert h("AH 2H 3H 4H 5H 9C KD")[0] == BACK_STRAIGHT_FLUSH
    assert h("6H 7H 8H 9H 10H 2C KD")[0] == STRAIGHT_FLUSH
    assert h("9S 9H 9D 9C 2C 3D 4D")[0] == FOUR_CARD
    assert h("9S 9H 9D 4C 4D 2C 7D")[0] == FULL_HOUSE
    assert h("2H 5H 9H JH KH 3C 4D")[0] == FLUSH
    assert h("AS KD QH JC 10S 2C 3D")[0] == MOUNTAIN
    assert h("AS 2D 3H 4C 5S 9C KD")[0] == BACK_STRAIGHT
    assert h("5S 6D 7H 8C 9S AC KD")[0] == STRAIGHT
    assert h("9S 9H 9D 4C 5D 2C 7D")[0] == TRIPLE
    assert h("9S 9H 4D 4C 5D 2C 7D")[0] == TWO_PAIR
    assert h("9S 9H 3D 4C 5D 2C 7D")[0] == PAIR
    assert h("AS 8H 3D 4C 6D 2C 10D")[0] == TOP


def test_order():
    order = ["AS KS QS JS 10S", "AH 2H 3H 4H 5H", "6H 7H 8H 9H 10H",
             "9S 9H 9D 9C 2C", "9S 9H 9D 4C 4D", "2H 5H 9H JH KH",
             "AS KD QH JC 10S", "AS 2D 3H 4C 5S", "5S 6D 7H 8C 9S",
             "9S 9H 9D 4C 5D", "9S 9H 4D 4C 5D", "9S 9H 3D 4C 5D",
             "AS 8H 3D 4C 6D"]
    vals = [h(x) for x in order]
    assert vals == sorted(vals, reverse=True)


def test_ties_and_suit():
    assert h("KS KD 3H 4C 5D") > h("QS QD 3H 4C 5D")
    # same pair rank: spade pair beats club/heart pair
    assert h("9S 9C 3H 4C 7D") > h("9H 9C 3H 4C 7D")
    assert h("AS 8H 3D 4C 6D")[0] == TOP
    # back straight beats normal straight, loses to mountain
    assert h("AS 2D 3H 4C 5S") > h("9S 10D JH QC KS")
    # 5 high straight flush < 6 high
    assert h("AH 2H 3H 4H 5H") > h("9H 10H JH QH KH")


def test_partial():
    assert evaluate(parse("9S 9H 4D"))[0] == PAIR
    assert evaluate(parse("9S 9H 9D"))[0] == TRIPLE
    assert evaluate(parse("9S 4H"))[0] == TOP


if __name__ == "__main__":
    for f in (test_categories, test_order, test_ties_and_suit, test_partial):
        f()
    print("all ok")

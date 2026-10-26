import pytest

from swingtrader.accounting import Ledger


def L():
    return Ledger(100_000, {"MES": 5.0})


def test_long_round_trip():
    lg = L()
    lg.fill("MES", 1, 2, 4000.0, 2.0)
    lg.mark("MES", 4010.0)
    assert lg.unrealized() == pytest.approx(10 * 2 * 5)
    assert lg.equity() == pytest.approx(100_000 - 2 + 100)
    r = lg.fill("MES", -1, 2, 4020.0, 2.0)
    assert r == pytest.approx(20 * 2 * 5)
    assert lg.position("MES").qty == 0
    assert lg.equity() == pytest.approx(100_000 + 200 - 4)
    lg.check_invariants()


def test_short_partial_and_add():
    lg = L()
    lg.fill("MES", -1, 3, 4000.0, 0.0)
    lg.fill("MES", -1, 1, 4040.0, 0.0)          # add: avg 4010
    assert lg.position("MES").avg_price == pytest.approx(4010.0)
    r = lg.fill("MES", 1, 2, 3990.0, 0.0)       # cover 2 at 3990 -> +20*2*5
    assert r == pytest.approx(200.0)
    assert lg.position("MES").qty == -2
    lg.mark("MES", 4000.0)
    assert lg.unrealized() == pytest.approx((4000 - 4010) * -2 * 5)


def test_flip():
    lg = L()
    lg.fill("MES", 1, 1, 4000.0, 0.0)
    r = lg.fill("MES", -1, 3, 3990.0, 0.0)      # close 1 (-50) and open short 2 @3990
    assert r == pytest.approx(-50.0)
    pos = lg.position("MES")
    assert pos.qty == -2 and pos.avg_price == 3990.0


def test_charges_and_invariants():
    lg = L()
    lg.charge(12.5, "roll")
    assert lg.equity() == pytest.approx(100_000 - 12.5)
    lg.check_invariants()
    with pytest.raises(ValueError):
        lg.charge(-1)
    with pytest.raises(ValueError):
        lg.fill("MES", 1, 0, 4000.0, 0.0)
    with pytest.raises(ValueError):
        lg.fill("MES", 1, 1, 4000.0, -1.0)

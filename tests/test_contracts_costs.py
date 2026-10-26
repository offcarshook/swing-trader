import datetime as dt

import pytest

from swingtrader.contracts import SPECS, contract_code, front_expiry, roll_dates, third_friday
from swingtrader.costs import GAP_STOP, MARKET, STOP, CostModel


def test_mes_spec():
    s = SPECS["MES"]
    assert s.multiplier == 5.0 and s.tick_size == 0.25
    assert s.tick_value == pytest.approx(1.25)
    assert s.points_to_dollars(10, 2) == pytest.approx(100.0)
    assert SPECS["ES"].tick_value == pytest.approx(12.5)
    assert SPECS["MNQ"].tick_value == pytest.approx(0.5)


def test_round_to_tick():
    s = SPECS["MES"]
    assert s.round_to_tick(4000.1) == 4000.0
    assert s.round_to_tick(4000.13) == 4000.25
    assert s.round_to_tick(4000.01, "up") == 4000.25
    assert s.round_to_tick(4000.24, "down") == 4000.0
    assert s.round_to_tick(4000.25, "down") == 4000.25


def test_third_friday_and_rolls():
    assert third_friday(2024, 3) == dt.date(2024, 3, 15)
    assert third_friday(2025, 12) == dt.date(2025, 12, 19)
    spec = SPECS["MES"]
    rolls = roll_dates(dt.date(2024, 1, 1), dt.date(2024, 12, 31), spec)
    assert rolls == [dt.date(2024, 3, 7), dt.date(2024, 6, 13), dt.date(2024, 9, 12), dt.date(2024, 12, 12)]
    assert contract_code("MES", dt.date(2024, 3, 6)) == "MESH24"
    assert contract_code("MES", dt.date(2024, 3, 7)) == "MESM24"
    assert contract_code("MES", dt.date(2024, 12, 20)) == "MESH25"
    assert front_expiry(dt.date(2024, 3, 7), spec) == dt.date(2024, 6, 21)


def test_fill_prices_are_adverse(costs):
    t = costs.spec.tick_size
    assert costs.fill_price(4000, 1, MARKET) == 4000 + 1 * t
    assert costs.fill_price(4000, -1, MARKET) == 4000 - 1 * t
    assert costs.fill_price(4000, -1, STOP) == 4000 - 2 * t
    assert costs.fill_price(4000, -1, GAP_STOP) == 4000 - 2 * t
    assert costs.fill_price(4000, 1, MARKET, thin_session=True) == 4000 + 2 * t
    with pytest.raises(ValueError):
        costs.fill_price(4000, 0, MARKET)


def test_fees_and_multiplier(spec, cfg):
    base = CostModel.from_config(spec, cfg["costs"])
    x2 = CostModel.from_config(spec, cfg["costs"], multiplier=2.0)
    assert base.fees(3) == pytest.approx(3 * 1.00)
    assert x2.fees(3) == pytest.approx(2 * base.fees(3))
    assert x2.slippage_ticks(MARKET) == 2 * base.slippage_ticks(MARKET)
    # roll = 2 legs fees + 2 legs x 1 tick
    assert base.roll_cost(2) == pytest.approx(2 * base.fees(2) + 2 * 1.0 * spec.tick_value * 2)
    # round trip: 2 sides fees + (1 market + 2 stop) ticks
    assert base.est_round_trip_per_contract() == pytest.approx(2.0 + 3 * 1.25)

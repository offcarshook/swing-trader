import math

import pytest

from swingtrader.risk import RiskLimits, RiskManager


def test_sizing_by_stop_distance_and_tick_value(risk, costs):
    # equity 100k, 1% risk = $1000; stop 20 pts = $100/contract + round-trip cost 5.75
    d = risk.size_entry(100_000, 4000.0, 3980.0, 1)
    per = 20 * 5 + costs.est_round_trip_per_contract()
    assert d.risk_per_contract == pytest.approx(per)
    assert d.contracts == min(math.floor(1000 / per), 20)  # max_contracts may bind
    assert d.approved


def test_risk_cap_binds(risk):
    d = risk.size_entry(100_000, 4000.0, 3850.0, 1)  # 150 pts -> $750 + costs per contract
    assert d.contracts == 1 and d.binding_limit == "risk_per_trade"
    d = risk.size_entry(50_000, 4000.0, 3850.0, 1)   # $500 budget < one contract's risk
    assert not d.approved and "risk_per_trade" in d.rejected_reason


def test_notional_and_margin_caps(limits, spec, costs):
    lim = RiskLimits(**{**limits.__dict__, "risk_per_trade_pct": 5.0, "max_open_risk_pct": 10.0,
                        "max_notional_leverage": 1.0, "max_contracts": 100})
    rm = RiskManager(lim, spec, costs)
    d = rm.size_entry(100_000, 5000.0, 4990.0, 1)
    # notional per contract 25k -> 4 contracts at 1x; margin 0.5*100k/2500 = 20
    assert d.contracts == 4 and d.binding_limit == "notional"


def test_short_side_and_wrong_side_stop(risk):
    assert risk.size_entry(100_000, 4000.0, 4030.0, -1).approved
    assert not risk.size_entry(100_000, 4000.0, 3970.0, -1).approved   # short stop below entry
    assert not risk.size_entry(100_000, 4000.0, 4010.0, 1).approved    # long stop above entry


def test_min_stop_distance(risk):
    d = risk.size_entry(100_000, 4000.0, 3999.0, 1)   # 4 ticks < 8
    assert not d.approved and "min_stop_ticks" in d.rejected_reason


@pytest.mark.parametrize("mult", [5.0, 1.5, float("inf")])
def test_overlay_cannot_increase_size(risk, mult):
    base = risk.size_entry(100_000, 4000.0, 3980.0, 1, size_multiplier=1.0).contracts
    got = risk.size_entry(100_000, 4000.0, 3980.0, 1, size_multiplier=mult).contracts
    assert got <= base


@pytest.mark.parametrize("mult", [0.0, -1.0, float("nan")])
def test_overlay_veto(risk, mult):
    assert not risk.size_entry(100_000, 4000.0, 3980.0, 1, size_multiplier=mult).approved


def test_halt_and_day_block(risk):
    risk.block_day()
    assert not risk.size_entry(100_000, 4000.0, 3980.0, 1).approved
    risk.start_session()
    assert risk.size_entry(100_000, 4000.0, 3980.0, 1).approved
    risk.halt("dd")
    assert not risk.size_entry(100_000, 4000.0, 3980.0, 1).approved
    with pytest.raises(PermissionError):
        risk.reset_halt("ok")
    risk.reset_halt("I have reviewed the drawdown")
    assert risk.size_entry(100_000, 4000.0, 3980.0, 1).approved


def test_open_risk_budget(risk):
    d = risk.size_entry(100_000, 4000.0, 3980.0, 1, open_risk=1990.0)  # 2% cap - 1990 = $10 left
    assert not d.approved


def test_loss_limits(risk):
    assert risk.daily_loss_breached(100_000, 97_000)
    assert not risk.daily_loss_breached(100_000, 97_001)
    assert risk.drawdown_breached(120_000, 96_000)
    assert not risk.drawdown_breached(120_000, 96_001)
    # 3% of 100k = 3000 room; 2 contracts * $5 = $10/pt -> 300 pts below ref for a long
    assert risk.daily_stop_price(100_000, 100_000, 4000.0, 1, 2) == pytest.approx(3700.0)
    assert risk.daily_stop_price(100_000, 100_000, 4000.0, -1, 2) == pytest.approx(4300.0)
    assert risk.daily_stop_price(100_000, 96_000, 4000.0, 1, 2) == 4000.0  # already through


def test_invalid_limits(limits):
    with pytest.raises(ValueError):
        RiskLimits(**{**limits.__dict__, "risk_per_trade_pct": 0})
    with pytest.raises(ValueError):
        RiskLimits(**{**limits.__dict__, "max_open_risk_pct": 0.5})

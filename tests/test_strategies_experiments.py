from types import SimpleNamespace

import pytest

from swingtrader.research.experiments import ExperimentLog, HoldoutGuard, HoldoutReuseError
from swingtrader.strategies import DonchianBreakout, TrendContinuation, TrendPullback
from swingtrader.strategies.base import PositionView

TREND = {"fast": 50, "slow": 100, "trail_atr": 3.0, "stop_atr": 2.5, "allow_short": False}


def row(**kw):
    base = dict(no_trade_vol=False, atr=50.0, close=4000.0)
    base.update(kw)
    return SimpleNamespace(**base)


def test_trend_entry_rules():
    s = TrendContinuation(params=TREND)
    d = s.decide(row(up=True, up_prev=False, cross_up_fast=False, down=False, down_prev=False,
                     cross_dn_fast=False), PositionView())
    assert d.entry_side == 1 and d.stop_distance == pytest.approx(125.0)
    d = s.decide(row(up=True, up_prev=True, cross_up_fast=False, down=False, down_prev=False,
                     cross_dn_fast=False), PositionView())
    assert d.entry_side == 0
    d = s.decide(row(up=True, up_prev=False, cross_up_fast=True, no_trade_vol=True, down=False,
                     down_prev=False, cross_dn_fast=False), PositionView())
    assert d.entry_side == 0 and d.reason.startswith("no-trade")
    # short only if allowed
    d = s.decide(row(up=False, up_prev=False, cross_up_fast=False, down=True, down_prev=False,
                     cross_dn_fast=False), PositionView())
    assert d.entry_side == 0


def test_trend_exit_and_trailing_tightens_only():
    s = TrendContinuation(params=TREND)
    pos = PositionView(side=1, entry_price=4000, stop=3900.0, bars_held=5, best_close=4100.0)
    d = s.decide(row(close=4050.0, ma_slow=3950.0), pos)
    assert d.stop == pytest.approx(4100 - 150)
    pos.stop = 3990.0
    d = s.decide(row(close=4050.0, ma_slow=3950.0, atr=100.0), pos)  # trail 3800 < 3990
    assert d.stop == pytest.approx(3990.0)
    assert s.decide(row(close=3940.0, ma_slow=3950.0), pos).exit


def test_breakout_rules():
    s = DonchianBreakout(params={"entry_lookback": 55, "exit_lookback": 20, "stop_atr": 2.0, "allow_short": False})
    assert s.decide(row(close=4100.0, dc_hi=4090.0, dc_lo=3800.0), PositionView()).entry_side == 1
    assert s.decide(row(close=4080.0, dc_hi=4090.0, dc_lo=3800.0), PositionView()).entry_side == 0
    assert s.decide(row(close=3700.0, dc_hi=4090.0, dc_lo=3800.0), PositionView()).entry_side == 0
    pos = PositionView(side=1, entry_price=4100, stop=4000.0, bars_held=3, best_close=4150)
    assert s.decide(row(ex_lo=4050.0, ex_hi=4200.0), pos).stop == 4050.0
    assert s.decide(row(ex_lo=3950.0, ex_hi=4200.0), pos).stop == 4000.0


def test_pullback_rules():
    s = TrendPullback(params={"trend_len": 100, "rsi_len": 3, "rsi_entry": 15, "exit_ma": 5, "max_hold": 10,
                              "stop_atr": 2.5})
    assert s.decide(row(close=4000.0, ma_trend=3900.0, rsi=10.0), PositionView()).entry_side == 1
    assert s.decide(row(close=3800.0, ma_trend=3900.0, rsi=10.0), PositionView()).entry_side == 0
    assert s.decide(row(close=4000.0, ma_trend=3900.0, rsi=30.0), PositionView()).entry_side == 0
    pos = PositionView(side=1, entry_price=3990, stop=3860.0, bars_held=2, best_close=4000)
    assert s.decide(row(close=4010.0, ma_trend=3900.0, ma_exit=4005.0), pos).exit
    pos.bars_held = 10
    assert s.decide(row(close=3995.0, ma_trend=3900.0, ma_exit=4005.0), pos).exit


def test_holdout_guard(tmp_path):
    g = HoldoutGuard(tmp_path / "h.json")
    g.authorize("trend[a]", "h1")
    g.authorize("trend[a]", "h1")  # same candidate re-run is allowed (reproduction)
    with pytest.raises(HoldoutReuseError):
        g.authorize("breakout[b]", "h2")
    rec = g.authorize("breakout[b]", "h2", override_reason="documented reason")
    assert rec["evaluation_number"] == 3 and rec["override_reason"]


def test_experiment_log_append_only(tmp_path):
    log = ExperimentLog(tmp_path / "log.jsonl")
    log.append("a", {"x": 1})
    log.append("b", {"x": 2})
    recs = log.read()
    assert [r["kind"] for r in recs] == ["a", "b"] and all("ts" in r for r in recs)

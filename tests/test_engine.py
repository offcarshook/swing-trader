from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import pytest

from swingtrader.backtest.engine import run_backtest
from swingtrader.backtest.metrics import summarize
from swingtrader.risk import RiskLimits, RiskManager
from swingtrader.strategies import TrendContinuation
from swingtrader.strategies.base import Decision, Strategy

from conftest import make_bars


@dataclass
class Scripted(Strategy):
    """Emits pre-scripted decisions keyed by bar position; records what it saw."""
    script: dict = field(default_factory=dict)
    seen: list = field(default_factory=list)
    name: str = "scripted"

    @property
    def warmup(self):
        return 0

    def features(self, bars):
        f = pd.DataFrame(index=bars.index)
        f["close"] = bars["close"]
        f["i"] = np.arange(len(bars))
        f["atr"] = 10.0
        return f

    def decide(self, r, pos):
        self.seen.append((int(r.i), pos.side))
        return self.script.get(int(r.i), Decision())


def run(bars, strat, spec, costs, risk, **kw):
    return run_backtest(bars, strat, spec, costs, risk, bars.index[0], bars.index[-1], 100_000, **kw)


def test_entry_executes_next_rth_open_not_signal_bar(spec, costs, risk):
    bars = make_bars(np.linspace(4000, 4050, 20))
    s = Scripted(script={3: Decision(entry_side=1, stop_distance=40.0)})
    res = run(bars, s, spec, costs, risk)
    t = res.trades.iloc[0]
    assert t["entry_date"] == bars.index[4]
    assert t["entry_price"] == pytest.approx(bars["rth_open"].iloc[4] + spec.tick_size)  # 1 tick slippage
    assert t["initial_stop"] == pytest.approx(spec.round_to_tick(t["entry_price"] - 40.0, "down"))


def test_stop_fill_intraday_and_gap(spec, costs, risk):
    closes = [4000] * 6 + [3990] * 4
    bars = make_bars(closes)
    s = Scripted(script={1: Decision(entry_side=1, stop_distance=8.0)})
    res = run(bars, s, spec, costs, risk)
    t = res.trades.iloc[0]
    # stop ~ 3992 is hit by the post-open low (open 4000 - spread) on bar 2? low=4000-2=3998 -> not hit.
    # The 3990 close bar (index 6) has low 3988 -> stop hit intraday at stop - 2 ticks.
    assert t["exit_reason"] == "stop"
    assert t["exit_price"] == pytest.approx(t["initial_stop"] - 2 * spec.tick_size)

    gap = make_bars([4000] * 6 + [3900] * 4)
    gap.loc[gap.index[6], ["open", "pre_low", "pre_high"]] = [3900.0, 3900.0, 3900.0]
    res = run(gap, Scripted(script={1: Decision(entry_side=1, stop_distance=8.0)}), spec, costs, risk)
    t = res.trades.iloc[0]
    assert t["exit_reason"] == "stop_gap"
    assert t["exit_price"] == pytest.approx(3900.0 - 2 * spec.tick_size)  # open minus gap slippage


def test_signal_exit_at_next_open(spec, costs, risk):
    bars = make_bars(np.linspace(4000, 4100, 15))
    s = Scripted(script={1: Decision(entry_side=1, stop_distance=40.0), 5: Decision(exit=True, reason="x")})
    t = run(bars, s, spec, costs, risk).trades.iloc[0]
    assert t["exit_date"] == bars.index[6] and t["exit_reason"] == "x"
    assert t["exit_price"] == pytest.approx(bars["rth_open"].iloc[6] - spec.tick_size)


def test_equity_identity_and_costs(spec, costs, risk):
    bars = make_bars(np.r_[np.linspace(4000, 4100, 30), np.linspace(4100, 4000, 30)])
    s = Scripted(script={2: Decision(entry_side=1, stop_distance=40.0), 20: Decision(exit=True),
                         35: Decision(entry_side=-1, stop_distance=40.0), 50: Decision(exit=True)})
    res = run(bars, s, spec, costs, risk)
    assert len(res.trades) == 2
    assert res.equity.iloc[-1] == pytest.approx(100_000 + res.trades["net_pnl"].sum())
    assert (res.trades["fees"] > 0).all()


def test_no_lookahead_future_bars_do_not_change_past(spec, costs, risk, limits):
    rng = np.random.default_rng(1)
    closes = 4000 + np.cumsum(rng.normal(0, 15, 400))
    bars = make_bars(closes)
    strat = TrendContinuation(params={"fast": 20, "slow": 50, "trail_atr": 3.0, "stop_atr": 2.5,
                                      "allow_short": True}, vol_filter_lookback=60)
    a = run(bars, strat, spec, costs, RiskManager(limits, spec, costs))
    cut = bars.index[300]
    mutated = bars.copy()
    mutated.loc[mutated.index > cut, ["open", "high", "low", "close", "rth_open", "rth_close", "pre_high",
                                      "pre_low", "post_high", "post_low"]] *= 1.3
    b = run(mutated, strat, spec, costs, RiskManager(limits, spec, costs))
    ta = a.trades[a.trades["exit_date"] <= cut].reset_index(drop=True)
    tb = b.trades[b.trades["exit_date"] <= cut].reset_index(drop=True)
    pd.testing.assert_frame_equal(ta, tb)
    pd.testing.assert_series_equal(a.equity.loc[:cut], b.equity.loc[:cut])


@pytest.mark.parametrize("mult,expect_trade", [(5.0, True), (1.0, True), (0.0, False)])
def test_overlay_can_only_shrink_or_veto(spec, costs, risk, mult, expect_trade):
    bars = make_bars(np.linspace(4000, 4050, 20))
    s = Scripted(script={3: Decision(entry_side=1, stop_distance=40.0)})
    base = run(bars, Scripted(script={3: Decision(entry_side=1, stop_distance=40.0)}), spec, costs,
               RiskManager(risk.limits, spec, costs))
    res = run(bars, s, spec, costs, RiskManager(risk.limits, spec, costs), entry_filter=lambda d, side, r: mult)
    if expect_trade:
        assert res.trades.iloc[0]["contracts"] <= base.trades.iloc[0]["contracts"]
    else:
        assert res.trades.empty


def test_drawdown_halt_blocks_new_entries(spec, costs, limits):
    lim = RiskLimits(**{**limits.__dict__, "max_drawdown_halt_pct": 1.0, "risk_per_trade_pct": 5.0,
                        "max_open_risk_pct": 5.0})
    rm = RiskManager(lim, spec, costs)
    bars = make_bars(np.r_[[4000] * 5, np.linspace(4000, 3700, 10), [3700] * 15])
    s = Scripted(script={1: Decision(entry_side=1, stop_distance=400.0),
                         20: Decision(entry_side=1, stop_distance=40.0)})
    res = run(bars, s, spec, costs, rm)
    assert res.halted is not None
    assert len(res.trades) == 1 and res.trades.iloc[0]["exit_reason"] == "drawdown_halt"
    assert (res.events["event"] == "entry_blocked").any()


def test_daily_loss_stop(spec, costs, limits):
    lim = RiskLimits(**{**limits.__dict__, "risk_per_trade_pct": 10.0, "max_open_risk_pct": 10.0,
                        "daily_loss_limit_pct": 1.0, "max_drawdown_halt_pct": 50.0})
    rm = RiskManager(lim, spec, costs)
    bars = make_bars([4000] * 5 + [3960] * 5, spread=1.0)
    s = Scripted(script={1: Decision(entry_side=1, stop_distance=300.0)})
    t = run(bars, s, spec, costs, rm).trades.iloc[0]
    assert t["exit_reason"].startswith("daily_loss_stop")
    # loss on the day is capped near 1% of equity (plus slippage)
    assert -t["gross_pnl"] <= 0.011 * 100_000 + t["contracts"] * 10


def test_roll_cost_charged_when_held_across_roll(spec, costs, risk):
    bars = make_bars(np.linspace(4000, 4100, 40), start="2024-02-26")  # spans 2024-03-07 roll
    s = Scripted(script={1: Decision(entry_side=1, stop_distance=40.0)})
    t = run(bars, s, spec, costs, risk).trades.iloc[0]
    assert t["rolls"] == 1
    assert t["roll_costs"] == pytest.approx(costs.roll_cost(t["contracts"]))


def test_summary_metrics_basic(spec, costs, risk):
    bars = make_bars(np.linspace(4000, 4200, 60))
    s = Scripted(script={1: Decision(entry_side=1, stop_distance=40.0), 30: Decision(exit=True)})
    res = run(bars, s, spec, costs, risk)
    m = summarize(res.equity, res.trades, res.start_equity, res.in_market)
    assert m["trades"] == 1 and m["profit_factor"] == float("inf")
    assert m["net_return_pct"] > 0 and m["max_drawdown_pct"] >= 0

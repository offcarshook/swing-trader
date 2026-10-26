"""Regression tests for the ETF audit fixes: price basis, dividends, windows, lockouts, caps."""

import numpy as np
import pandas as pd
import pytest

from swingtrader.etf.data import (common_window, coverage, factor_from_dividends, raw_from_adjusted,
                                  signal_view)
from swingtrader.etf.engine import RiskCfg, build_signals, simulate
from swingtrader.etf.research import buy_hold
from swingtrader.etf.strategies import Params

P = Params("dip", "long", "rsi2<", 10, 2.0, None, 3)
NOCOST = dict(commission_per_share=0, slip_bps=0, slip_bps_wide=0, stop_extra_bps=0)


def bars(n=400, seed=0, start="2015-01-01"):
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.01, n)))
    o = c * (1 + rng.normal(0, 0.003, n))
    h = np.maximum(o, c) * 1.004
    lo = np.minimum(o, c) * 0.996
    idx = pd.bdate_range(start, periods=n)
    return pd.DataFrame({"open": o, "high": h, "low": lo, "close": c, "volume": 1e6,
                         "adj_factor": 1.0, "dividend": 0.0}, index=idx)


def sig(df, k, dist, sym="X", pid=None, d=1, level=np.nan):
    return pd.DataFrame([{"sym": sym, "rank": 0, "pid": pid or P.id, "entry_date": df.index[k], "dir": d,
                          "stop_dist": dist, "entry_level": level, "signal_date": df.index[k - 1], "regime": "up"}])


def test_fills_use_raw_prices_and_dividends_are_credited():
    df = bars()
    k = 300
    df.loc[df.index[k + 1], "dividend"] = 2.0          # ex-date while the position is held
    df["adj_factor"] = factor_from_dividends(df["close"], df["dividend"])
    r = simulate({"X": df}, [P], df.index[0], df.index[-1], RiskCfg(**NOCOST), sigs=sig(df, k, 1000.0))
    t = r.trades.iloc[0]
    assert t.entry == pytest.approx(df.open.iloc[k])     # raw open, not open * adj_factor
    assert t.dividends == pytest.approx(2.0 * t.shares)
    assert t.pnl == pytest.approx((df.close.iloc[k + 3] - df.open.iloc[k]) * t.shares + 2.0 * t.shares)


def test_short_pays_dividend_and_borrow():
    df = bars()
    k = 300
    df.loc[df.index[k + 1], "dividend"] = 1.0
    ps = Params("short", "short", "rsi2>", 90, 2.0, None, 3)
    r = simulate({"X": df}, [ps], df.index[0], df.index[-1], RiskCfg(**NOCOST, borrow_bps_annual=100),
                 sigs=sig(df, k, 1000.0, pid=ps.id, d=-1))
    t = r.trades.iloc[0]
    assert t.dividends == pytest.approx(-1.0 * t.shares) and t.borrow > 0


def test_raw_adjusted_round_trip():
    raw = bars(300)
    raw.loc[raw.index[[50, 120, 250]], "dividend"] = [0.5, 0.7, 0.9]
    f = factor_from_dividends(raw["close"], raw["dividend"])
    adj = raw[["open", "high", "low", "close", "volume"]].copy()
    for c in ("open", "high", "low", "close"):
        adj[c] = raw[c] * f
    back = raw_from_adjusted(adj, raw["dividend"][raw["dividend"] > 0])
    np.testing.assert_allclose(back["close"], raw["close"], rtol=1e-12)
    np.testing.assert_allclose(back["dividend"], raw["dividend"])


def test_ex_dividend_drop_is_not_a_gap_signal():
    df = bars(400, seed=5)
    k = 350
    d = 0.03 * df.close.iloc[k - 1]                     # 3% dividend: raw open gaps down 3%
    df.iloc[k:, :4] = df.iloc[k:, :4] - d
    df.loc[df.index[k], "dividend"] = d
    df["adj_factor"] = factor_from_dividends(df["close"], df["dividend"])
    fade = Params("gap", "long", "fade", 0.5, 1.0, 1.0, 1, None, False)
    s = build_signals({"X": df}, [fade])
    assert df.index[k] not in set(s["entry_date"])


def test_position_closed_when_instrument_data_ends():
    a, b = bars(seed=1), bars(seed=2)
    a = a.iloc[:303]                                     # instrument A ends on session 302
    r = simulate({"A": a, "B": b}, [P], a.index[0], b.index[-1], RiskCfg(**NOCOST),
                 sigs=sig(a, 301, 1000.0, sym="A"))
    t = r.trades.iloc[0]
    assert t.reason == "instrument_data_end" and t.exit_date == a.index[-1]


def test_daily_loss_lockout_blocks_next_session_and_dd_lockout_halts():
    df = bars()
    k = 300
    df.iloc[k, df.columns.get_loc("low")] = df.open.iloc[k] - 50     # stop hit on entry day: big loss
    s = pd.concat([sig(df, k, 1.0), sig(df, k + 1, 1000.0)], ignore_index=True)
    cfg = RiskCfg(**NOCOST, risk_pct=1.0, daily_loss_lockout_pct=0.5)
    r = simulate({"X": df}, [P], df.index[0], df.index[-1], cfg, sigs=s)
    assert len(r.trades) == 1 and r.skipped["daily_loss_lockout"] == 1
    cfg = RiskCfg(**NOCOST, risk_pct=1.0, max_dd_lockout_pct=0.5)
    r = simulate({"X": df}, [P], df.index[0], df.index[-1], cfg, sigs=s)
    assert r.halted_on == str(df.index[k].date()) and r.skipped["dd_lockout"] == 1


def test_cluster_cap_limits_correlated_exposure():
    syms = {s: bars(seed=i) for i, s in enumerate(("SPY", "QQQ", "TLT"))}
    k = 300
    s = pd.concat([sig(syms[x], k, 1.0, sym=x) for x in syms], ignore_index=True)
    cfg = RiskCfg(**NOCOST, max_gross=100, clusters={"SPY": "eq", "QQQ": "eq", "TLT": "rates"},
                  max_cluster_risk_pct=1.0)
    r = simulate(syms, [P], syms["SPY"].index[0], syms["SPY"].index[-1], cfg, sigs=s)
    assert sorted(r.trades.sym) == ["QQQ", "TLT"]  # same-day order is alphabetical (deterministic) and r.skipped["cluster_risk_cap"] == 1


def test_overlay_can_only_scale_down_or_veto():
    df = bars()
    k = 300
    r = simulate({"X": df}, [P], df.index[0], df.index[-1], RiskCfg(**NOCOST), sigs=sig(df, k, 10.0),
                 entry_filter=lambda s: (5.0, "tries to upsize"))
    base = simulate({"X": df}, [P], df.index[0], df.index[-1], RiskCfg(**NOCOST), sigs=sig(df, k, 10.0))
    assert r.trades.shares.iloc[0] == base.trades.shares.iloc[0]
    r = simulate({"X": df}, [P], df.index[0], df.index[-1], RiskCfg(**NOCOST), sigs=sig(df, k, 10.0),
                 entry_filter=lambda s: (0.0, "veto"))
    assert r.trades.empty and r.skipped["overlay_veto"] == 1


def test_kill_switch_blocks_entries():
    df = bars()
    r = simulate({"X": df}, [P], df.index[0], df.index[-1], RiskCfg(**NOCOST, kill_switch_from=str(df.index[300].date())),
                 sigs=sig(df, 300, 10.0))
    assert r.trades.empty and r.skipped["kill_switch"] == 1


def test_windows_and_buy_hold_report_exact_dates():
    a, b = bars(300, start="2020-01-01"), bars(500, start="2019-06-03")
    w = common_window({"A": a, "B": b}, "2019-01-01", "2030-01-01")
    assert w == (str(a.index[0].date()), str(min(a.index[-1], b.index[-1]).date()))
    cov = coverage({"A": a}, "2020-03-02", "2030-01-01")
    assert cov["A"]["first"] == "2020-03-02" and cov["A"]["last"] == str(a.index[-1].date())
    bh = buy_hold(a, "2020-03-02", "2030-01-01")
    assert bh["last"] == str(a.index[-1].date())


def test_worst_equity_never_above_close_equity():
    df = bars()
    r = simulate({"X": df}, [P], df.index[0], df.index[-1], RiskCfg(), sigs=sig(df, 300, 1.5))
    assert (r.equity_worst <= r.equity + 1e-9).all()

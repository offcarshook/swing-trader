import numpy as np
import pandas as pd
import pytest

from swingtrader.etf.data import audit, parse_csv
from swingtrader.etf.engine import RiskCfg, simulate
from swingtrader.etf.strategies import Params, features, grid, signals


def bars(n=400, seed=0, drift=0.0005):
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(drift, 0.01, n)))
    o = c * (1 + rng.normal(0, 0.003, n))
    h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.004, n)))
    l = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.004, n)))
    idx = pd.bdate_range("2015-01-01", periods=n)
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": 1e6}, index=idx)


def one_signal(df, k, dist, level=np.nan, d=1):
    return pd.DataFrame([{"sym": "X", "rank": 0, "pid": P.id, "entry_date": df.index[k], "dir": d,
                          "stop_dist": dist, "entry_level": level}])


P = Params("dip", "long", "rsi2<", 10, 2.0, None, 3)
NOCOST = RiskCfg(commission_per_share=0, slip_bps=0, slip_bps_wide=0, stop_extra_bps=0)


@pytest.mark.parametrize("p", grid(), ids=lambda p: p.id)
def test_signals_are_causal(p):
    df = bars(500, seed=3)
    full = signals(df, p)
    cut = 420
    part = signals(df.iloc[:cut], p)
    # every signal decided on data <= cut-2 must be identical with or without the future
    a = full[full.entry_i < cut - 1].reset_index(drop=True)
    b = part[part.entry_i < cut - 1].reset_index(drop=True)
    pd.testing.assert_frame_equal(a, b)


def test_one_percent_sizing_and_time_stop():
    df = bars()
    k = 300
    r = simulate({"X": df}, [P], df.index[0], df.index[-1], NOCOST, sigs=one_signal(df, k, 1000.0))
    t = r.trades.iloc[0]
    assert t.shares == int(1000 // 1000.0)  # 1% of 100k / 1000 per share
    assert t.reason == "time" and t.sessions == 3 and t.exit_date == df.index[k + 3]
    assert t.exit == pytest.approx(df.close.iloc[k + 3])


def test_gap_through_stop_fills_at_open():
    df = bars()
    k = 300
    df.iloc[k + 1, df.columns.get_loc("open")] = df.open.iloc[k] - 5
    df.iloc[k + 1, df.columns.get_loc("high")] = max(df.high.iloc[k + 1], df.open.iloc[k + 1])
    df.iloc[k + 1, df.columns.get_loc("low")] = min(df.low.iloc[k + 1], df.open.iloc[k + 1])
    df.iloc[k, df.columns.get_loc("low")] = df.open.iloc[k] - 0.5  # entry bar must not stop out
    r = simulate({"X": df}, [P], df.index[0], df.index[-1], NOCOST, sigs=one_signal(df, k, 1.0))
    t = r.trades.iloc[0]
    assert t.reason == "stop_gap" and t.exit == pytest.approx(df.open.iloc[k + 1])
    assert t.r < -1  # gap risk is real: worse than -1R


def test_open_risk_cap_blocks_extra_positions():
    syms = {f"S{i}": bars(seed=i) for i in range(6)}
    k = 300
    sig = pd.concat([one_signal(syms[s], k, 1.0).assign(sym=s) for s in syms], ignore_index=True)
    r = simulate(syms, [P], syms["S0"].index[0], syms["S0"].index[-1],
                 RiskCfg(max_open_risk_pct=4.0, max_gross=100, **{k_: 0 for k_ in
                         ("commission_per_share", "slip_bps", "slip_bps_wide", "stop_extra_bps")}), sigs=sig)
    assert len(r.trades) <= 4 and r.skipped["open_risk_cap"] >= 2


def test_breakout_not_triggered_and_no_same_bar_target():
    df = bars()
    k = 300
    p = Params("nrb", "long", "nr7", 0, 1.0, 0.1, 3)
    lvl = df.high.iloc[k] + 100
    r = simulate({"X": df}, [p], df.index[0], df.index[-1], NOCOST, sigs=one_signal(df, k, 1.0, lvl).assign(pid=p.id))
    assert r.trades.empty and r.skipped["not_triggered"] == 1


def test_calendar_signal_enters_last_session_of_month():
    df = bars(400)
    p = Params("calendar", "long", "tom", 0, 2.0, None, 3, None, False)
    s = signals(df, p)
    ent = df.index[s.entry_i]
    nxt = df.index[np.minimum(s.entry_i + 1, len(df) - 1)]
    assert (ent.month != nxt.month).all()


def test_parse_csv_adjusts_and_audit(tmp_path):
    f = tmp_path / "X.csv"
    f.write_text("date,open,high,low,close,adj close,volume\n2020-01-03,10,11,9,10,5,1\n2020-01-02,10,11,9,10,5,1\n")
    d = parse_csv(f)
    assert d.index.is_monotonic_increasing and d.close.iloc[0] == 5 and d.high.iloc[0] == 5.5
    assert audit({"X": d})["X"]["usable"] is False


def test_features_month_position():
    f = features(bars(60))
    assert f["day_of_month"].min() == 1 and f["days_left"].min() == 0

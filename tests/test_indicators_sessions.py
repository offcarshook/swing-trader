import numpy as np
import pandas as pd
import pytest

from swingtrader import indicators as ind
from swingtrader.data.quality import drop_out_of_hours
from swingtrader.data.sessions import build_sessions, session_dates
from swingtrader.regime import classify

from conftest import make_bars


def test_indicators_are_causal():
    rng = np.random.default_rng(0)
    bars = make_bars(4000 + np.cumsum(rng.normal(0, 10, 300)))
    mutated = bars.copy()
    mutated.iloc[200:, :4] *= 1.5
    for fn in (lambda b: ind.atr(b, 20), lambda b: ind.rsi(b["close"], 3), lambda b: ind.sma(b["close"], 50),
               lambda b: ind.donchian_high(b, 20), lambda b: ind.trailing_percentile(ind.atr(b, 20), 60),
               lambda b: ind.adx(b, 14), lambda b: classify(b, vol_lookback=60)["regime"]):
        a, m = fn(bars), fn(mutated)
        pd.testing.assert_series_equal(a.iloc[:200], m.iloc[:200], check_names=False)


def test_atr_constant_range():
    bars = make_bars([4000.0] * 50, spread=5.0)
    assert ind.atr(bars, 14).iloc[-1] == pytest.approx(10.0)


def test_rsi_bounds_and_extremes():
    up = pd.Series(np.arange(1, 50, dtype=float))
    assert ind.rsi(up, 3).iloc[-1] == pytest.approx(100.0)
    r = ind.rsi(pd.Series(np.random.default_rng(1).normal(0, 1, 500).cumsum()), 3).dropna()
    assert r.between(0, 100).all()


def test_donchian_excludes_current_bar():
    bars = make_bars([1, 2, 3, 4, 100], spread=0.0)
    assert ind.donchian_high(bars, 3).iloc[-1] == pytest.approx(4.0)


def _minutes(start, end):
    idx = pd.date_range(start, end, freq="1min")
    n = len(idx)
    px = 4000 + np.arange(n) * 0.25
    return pd.DataFrame({"open": px, "high": px + 0.5, "low": px - 0.5, "close": px + 0.25, "volume": 1}, index=idx)


def test_session_mapping():
    idx = pd.DatetimeIndex(["2024-01-07 17:00", "2024-01-08 08:30", "2024-01-08 15:59", "2024-01-08 17:00"])
    d = session_dates(idx)
    assert list(d.strftime("%Y-%m-%d")) == ["2024-01-08", "2024-01-08", "2024-01-08", "2024-01-09"]


def test_build_sessions_columns():
    m = pd.concat([_minutes("2024-01-07 17:00", "2024-01-08 15:59"), _minutes("2024-01-08 17:00", "2024-01-09 15:59")])
    m, info = drop_out_of_hours(m)
    s = build_sessions(m)
    assert list(s.index.strftime("%Y-%m-%d")) == ["2024-01-08", "2024-01-09"]
    first = s.iloc[0]
    mm = m.loc["2024-01-07 17:00":"2024-01-08 15:59"]
    assert first["open"] == mm["open"].iloc[0]
    assert first["rth_open"] == m.loc["2024-01-08 08:30", "open"]
    assert first["rth_close"] == m.loc["2024-01-08 14:59", "close"]
    assert first["pre_low"] == mm.loc[:"2024-01-08 08:29", "low"].min()
    assert first["post_high"] == mm.loc["2024-01-08 08:30":, "high"].max()
    assert first["n_rth_bars"] == 390


def test_weekend_bars_dropped():
    m = _minutes("2024-01-05 15:50", "2024-01-05 15:59")
    bad = pd.DataFrame({"open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0], "volume": [1]},
                       index=pd.DatetimeIndex(["2024-01-06 23:00"]))
    clean, info = drop_out_of_hours(pd.concat([m, bad]))
    assert info["weekend_bars_dropped"] == 1 and len(clean) == len(m)


def test_holiday_session_without_rth_is_merged():
    # Sunday evening trades, Monday holiday with no RTH bars, Tuesday normal.
    m = pd.concat([_minutes("2024-01-14 17:00", "2024-01-15 07:00"),
                   _minutes("2024-01-15 17:00", "2024-01-16 15:59")])
    s = build_sessions(m)
    assert list(s.index.strftime("%Y-%m-%d")) == ["2024-01-16"]
    assert bool(s.iloc[0]["merged_holiday"])

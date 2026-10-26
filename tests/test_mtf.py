"""Multi-timeframe alignment: completed bars only, timestamp joins, sessions, DST, gaps."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from swingtrader.mtf import engine as E
from swingtrader.mtf.bars import asof, build_all, daily_bars, intraday_bars


def minutes(start="2023-03-06 17:00", end="2023-03-17 16:00", seed=0, drop=None):
    """Synthetic CME-like 1-minute bars: trading 17:00-16:00 CT Sun-Fri, nothing 16:00-17:00."""
    idx = pd.date_range(start, end, freq="1min", inclusive="left")
    idx = idx[(idx.hour != 16)]                                    # maintenance break
    wd, hr = idx.weekday, idx.hour
    idx = idx[~((wd == 4) & (hr >= 17)) & ~(wd == 5) & ~((wd == 6) & (hr < 17))]
    if drop is not None:
        idx = idx[~drop(idx)]
    rng = np.random.default_rng(seed)
    c = 4000 + np.cumsum(rng.normal(0, 0.5, len(idx)))
    o = np.r_[c[0], c[:-1]]
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) + 0.25, "low": np.minimum(o, c) - 0.25, "close": c,
                         "volume": 10}, index=idx)


def test_bars_are_session_anchored_and_stamped_at_completion():
    m = minutes()
    h4 = intraday_bars(m, 240)
    starts = pd.DatetimeIndex(h4["start"]).time
    assert {str(t) for t in starts} <= {"17:00:00", "21:00:00", "01:00:00", "05:00:00", "09:00:00", "13:00:00"}
    last = h4[h4["start"].dt.time == pd.Timestamp("13:00").time()]
    assert (last["available_at"].dt.time == pd.Timestamp("16:00").time()).all()   # capped at session end
    h1 = intraday_bars(m, 60)
    assert (h1["available_at"] - h1["start"] <= pd.Timedelta(hours=1)).all()
    d = daily_bars(m)
    assert (d["available_at"] == d["session"] + pd.Timedelta(hours=16)).all()


def test_incomplete_higher_timeframe_bar_is_never_visible():
    m = minutes()
    h4 = intraday_bars(m, 240)
    t = pd.DatetimeIndex([pd.Timestamp("2023-03-08 10:15"), pd.Timestamp("2023-03-08 13:00")])
    a = asof(t, h4, ["close"], "h4_")
    # at 10:15 the 09:00-13:00 bar is still forming -> the 05:00-09:00 bar is the latest complete one
    assert a["h4_available_at"].iloc[0] == pd.Timestamp("2023-03-08 09:00")
    # at exactly 13:00 the 09:00-13:00 bar has just completed and may be used
    assert a["h4_available_at"].iloc[1] == pd.Timestamp("2023-03-08 13:00")
    expected = m.loc["2023-03-08 09:00":"2023-03-08 12:59", "close"].iloc[-1]
    assert a["h4_close"].iloc[1] == pytest.approx(expected)


def test_no_lookahead_under_truncation():
    m = minutes(end="2023-03-24 16:00")
    cut = pd.Timestamp("2023-03-21 11:07")
    g_full = E.decision_frame(E.features(build_all(m, ("15m", "1h", "4h"))))
    g_cut = E.decision_frame(E.features(build_all(m[m.index < cut], ("15m", "1h", "4h"))))
    common = g_cut.index[g_cut.index <= cut.floor("15min")]
    cols = ["m15_trig", "h4_up", "h1_rsi2", "h1_atr", "h1_setup_at", "d_up", "d_rsi2"]
    pd.testing.assert_frame_equal(g_full.loc[common, cols], g_cut.loc[common, cols])


def test_dst_weeks_have_regular_sessions():
    # US DST began 2023-03-12 (Sunday 02:00) and ended 2023-11-05: CME was closed both times
    for start, end in (("2023-03-09 17:00", "2023-03-15 16:00"), ("2023-11-02 17:00", "2023-11-08 16:00")):
        h1 = intraday_bars(minutes(start, end), 60)
        per = h1.groupby("session").size()
        assert (per == 23).all()                            # 17:00 -> 16:00 = 23 hourly buckets


def test_missing_minutes_never_fabricate_bars():
    gap = lambda idx: (idx >= pd.Timestamp("2023-03-08 10:00")) & (idx < pd.Timestamp("2023-03-08 11:00"))  # noqa: E731
    h1 = intraday_bars(minutes(drop=gap), 60)
    assert pd.Timestamp("2023-03-08 10:00") not in set(h1["start"])
    assert h1["n_minutes"].min() >= 1


def test_early_close_keeps_conservative_completion_time():
    early = lambda idx: (idx.date == pd.Timestamp("2023-03-10").date()) & (idx.hour * 60 + idx.minute >= 12 * 60 + 15)  # noqa: E731
    h4 = intraday_bars(minutes(drop=early), 240)
    b = h4[(h4["session"] == pd.Timestamp("2023-03-10")) & (h4["start"].dt.hour == 9)]
    assert b["available_at"].iloc[0] == pd.Timestamp("2023-03-10 13:00")   # not 12:15


MES = Path("data/raw/mes_1m_eth")


@pytest.mark.skipif(not MES.exists(), reason="needs the pinned MES 1-minute files")
def test_real_mes_entries_fill_after_decision():
    from swingtrader.config import load_config
    from swingtrader.data.loaders import load_mes_1m
    m = load_mes_1m(Path("data/raw")).loc["2020-01-01":"2021-12-31"]   # >= 126 sessions of warm-up
    f = E.features(build_all(m, ("15m", "1h", "4h")))
    g = E.decision_frame(f)
    v = E.VARIANTS["D_full_mtf"]
    ent, _ = E.signals(g, f, v)
    r = E.simulate(m, f, g, ent, v, load_config()["costs"], E.SimCfg(), "2021-06-01", "2021-12-31")
    t = r["trades"]
    assert len(t) > 0 and (t.entry_time >= t.decision).all() and (t.exit_time >= t.entry_time).all()

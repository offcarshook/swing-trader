"""Data-quality validation and independent cross-checks.

Nothing here repairs prices. Invalid bars are DROPPED and counted; missing data
stays missing (no forward-fill, no interpolation, no synthetic bars).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from swingtrader.data.loaders import ohlc_integrity


def drop_out_of_hours(m1: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Remove bars that cannot exist for CME equity futures (weekend / daily halt)."""
    idx = m1.index
    mins = idx.hour * 60 + idx.minute
    weekend = ((idx.weekday == 4) & (mins >= 16 * 60)) | (idx.weekday == 5) | (
        (idx.weekday == 6) & (mins < 17 * 60))
    halt = (mins >= 16 * 60) & (mins < 17 * 60)
    bad = weekend | halt
    info = {
        "weekend_bars_dropped": int(weekend.sum()),
        "halt_bars_dropped": int((halt & ~weekend).sum()),
        "dropped_timestamps": [str(t) for t in idx[bad][:20]],
    }
    return m1[~bad], info


def expected_sessions(start, end, calendar: str = "CME_Equity") -> pd.DatetimeIndex | None:
    """Exchange calendar via pandas_market_calendars when available (LumiBot env)."""
    try:
        import pandas_market_calendars as pmc
    except Exception:  # pragma: no cover - optional dependency
        return None
    cal = pmc.get_calendar(calendar)
    sched = cal.schedule(start_date=start, end_date=end)
    return pd.DatetimeIndex(sched.index).normalize()


def session_report(sess: pd.DataFrame, min_rth_bars: int = 300, calendar: str = "CME_Equity") -> dict:
    short = sess[sess["n_rth_bars"] < min_rth_bars]
    big_gap = sess[sess["max_gap_min"] > 30]
    lr = np.log(sess["close"]).diff()
    z = (lr / lr.rolling(60, min_periods=20).std().shift(1)).abs()
    out = {
        "sessions": int(len(sess)),
        "first": str(sess.index.min().date()),
        "last": str(sess.index.max().date()),
        "short_sessions(<%d RTH bars)" % min_rth_bars: int(len(short)),
        "holiday_merged_sessions": int(sess["merged_holiday"].sum()),
        "sessions_with_gap_gt_30min": {str(d.date()): float(g) for d, g in big_gap["max_gap_min"].items()},
        "return_outliers_gt_6sigma": {str(d.date()): round(float(v), 4) for d, v in lr[z > 6].items()},
        "median_bars_per_session": float(sess["n_bars"].median()),
    }
    exp = expected_sessions(sess.index.min(), sess.index.max(), calendar)
    if exp is not None:
        missing = exp.difference(sess.index)
        extra = sess.index.difference(exp)
        out["calendar_missing_sessions"] = [str(d.date()) for d in missing]
        out["calendar_extra_sessions"] = [str(d.date()) for d in extra]
    return out


def minute_report(m1: pd.DataFrame, tick: float) -> dict:
    rep = ohlc_integrity(m1, tick)
    jump = (m1["close"].pct_change().abs() > 0.015)
    rep["minute_moves_gt_1.5pct"] = int(jump.sum())
    rep["minute_moves_gt_1.5pct_dates"] = sorted({str(t.date()) for t in m1.index[jump]})[:30]
    if "volume" in m1:
        rep["zero_volume_bars"] = int((m1["volume"] <= 0).sum())
    return rep


def infer_roll_offsets(mes_adj: pd.DataFrame, es_raw: pd.DataFrame) -> pd.DataFrame:
    """Infer the back-adjustment schedule of the MES series against unadjusted ES.

    For every common minute, offset = MES_adj_close - ES_close. Within one
    contract period the offset is constant (MES and ES share expiries and price);
    a change marks a roll in either series. Returns one row per day with the
    median offset and its dispersion.
    """
    j = mes_adj[["close"]].join(es_raw[["close", "instrument_id"]], how="inner", lsuffix="_mes", rsuffix="_es")
    j["offset"] = j["close_mes"] - j["close_es"]
    day = j.groupby(j.index.normalize()).agg(
        offset=("offset", "median"),
        offset_iqr=("offset", lambda x: float(x.quantile(0.75) - x.quantile(0.25))),
        n=("offset", "size"),
        es_instrument=("instrument_id", "last"),
    )
    return day


def roll_audit(day_offsets: pd.DataFrame, tick: float = 0.25) -> dict:
    off = day_offsets["offset"]
    step = off.diff()
    changes = day_offsets[step.abs() > 2 * tick].copy()
    changes["step"] = step[step.abs() > 2 * tick]
    stable = day_offsets["offset_iqr"]
    return {
        "days_compared": int(len(day_offsets)),
        "median_intraday_offset_iqr_points": float(stable.median()),
        "pct_days_offset_iqr_le_1tick": float((stable <= tick + 1e-9).mean() * 100),
        "offset_changes": [
            {"date": str(d.date()), "new_offset": float(r.offset), "step": float(r.step),
             "es_instrument": str(r.es_instrument)}
            for d, r in changes.iterrows()
        ],
    }


def aligned_changes(level_a: pd.Series, level_b: pd.Series, reference_calendar: pd.DatetimeIndex,
                    pct_of: pd.Series | None = None) -> tuple[pd.Series, pd.Series]:
    """Day-over-day changes of two level series, only where BOTH have the session
    and the immediately preceding session of `reference_calendar` (no holes).
    If `pct_of` is given, changes are expressed in % of pct_of's previous value."""
    df = pd.concat({"a": level_a, "b": level_b}, axis=1).dropna()
    prev_ref = pd.Series(reference_calendar[:-1], index=reference_calendar[1:])
    prev_common = pd.Series(df.index[:-1], index=df.index[1:])
    ok = prev_common.index[prev_common.values == prev_ref.reindex(prev_common.index).values]
    da = df["a"].diff().loc[ok]
    db = df["b"].diff().loc[ok]
    if pct_of is not None:
        base = pct_of.shift(1).reindex(ok)
        da, db = da / base * 100, db / base * 100
    return da, db


def return_crosscheck(a: pd.Series, b: pd.Series, label: str, exclude: pd.DatetimeIndex | None = None) -> dict:
    """Compare two daily change series on common dates (e.g. MES vs ES points, MES vs SPX %)."""
    df = pd.concat({"a": a, "b": b}, axis=1).dropna()
    if exclude is not None and len(exclude):
        df = df[~df.index.isin(exclude)]
    diff = df["a"] - df["b"]
    return {
        "label": label,
        "n_days": int(len(df)),
        "corr": float(df["a"].corr(df["b"])),
        "mean_abs_diff": float(diff.abs().mean()),
        "p95_abs_diff": float(diff.abs().quantile(0.95)),
        "max_abs_diff": float(diff.abs().max()),
        "max_abs_diff_date": str(diff.abs().idxmax().date()) if len(diff) else None,
    }

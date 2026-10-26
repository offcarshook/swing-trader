"""Build daily session bars from 1-minute bars.

A CME equity-index session runs 17:00 CT (previous calendar day) to 16:00 CT.
Session date = calendar date on which the session ends. A Globex session that
has no RTH bars at all (holiday such as MLK/Presidents Day) is merged into the
following session so every session bar has an RTH open to trade at.

Columns produced (all derived only from bars inside the session -> no look-ahead):
  open/high/low/close/volume     full Globex session
  rth_open                       open of the first bar at/after 08:30 (entry/exit price reference)
  rth_close                      close of the last bar before 15:00 (~settlement time)
  pre_high/pre_low               session start .. before RTH open (overnight stop checks)
  post_high/post_low             RTH open .. session end (stop checks after an RTH-open entry)
  n_bars, n_rth_bars, max_gap_min, merged_holiday
"""

from __future__ import annotations

import numpy as np
import pandas as pd

RTH_OPEN_MIN = 8 * 60 + 30
RTH_CLOSE_MIN = 15 * 60
SESSION_START_MIN = 17 * 60


def session_dates(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Map naive-CT bar-start timestamps to session dates (17:00 CT rolls to next day)."""
    shifted = index + pd.Timedelta(hours=7)  # 17:00 -> 00:00 next day
    d = shifted.normalize()
    # Saturday/Sunday labels cannot be sessions: Friday 17:00+ does not trade, and
    # Sunday 17:00 maps to Monday already. Defensive roll-forward anyway.
    wd = d.weekday
    d = d + pd.to_timedelta(np.where(wd == 5, 2, np.where(wd == 6, 1, 0)), unit="D")
    return pd.DatetimeIndex(d)


def build_sessions(m1: pd.DataFrame, rth_only_source: bool = False) -> pd.DataFrame:
    """Aggregate 1-min bars into session bars.

    rth_only_source=True is for the SPX cash index (no overnight trading): the
    session is the RTH day itself and pre_* columns are NaN. The index's 08:30
    opening print is often stale (it understates the overnight move by ~20% vs.
    MES, measured in the data report), so for that source `rth_open`/`open` are
    the CLOSE of the first RTH minute -- the first price a trader could act on.
    """
    df = m1.copy()
    minutes = df.index.hour * 60 + df.index.minute
    in_rth = (minutes >= RTH_OPEN_MIN) & (minutes < RTH_CLOSE_MIN)
    df["sdate"] = df.index.normalize() if rth_only_source else session_dates(df.index)
    df["in_rth"] = in_rth
    if rth_only_source:
        df = df[df["in_rth"]]

    # Merge sessions without RTH bars into the next session.
    has_rth = df.groupby("sdate")["in_rth"].any()
    no_rth = has_rth[~has_rth].index
    merged = pd.Series(False, index=has_rth.index)
    if len(no_rth):
        rth_dates = has_rth[has_rth].index
        remap = {}
        for d in no_rth:
            nxt = rth_dates[rth_dates > d]
            if len(nxt):
                remap[d] = nxt[0]
                merged.loc[nxt[0]] = True
        if remap:
            df["sdate"] = df["sdate"].replace(remap)
        df = df[df["sdate"].isin(rth_dates)]

    df["ts"] = df.index
    # Sessions start at 17:00 CT, so the "pre" part is everything before the
    # first RTH bar of that session (calendar time strictly earlier).
    g = df.groupby("sdate", sort=True)
    out = pd.DataFrame({
        "open": g["open"].first(),
        "high": g["high"].max(),
        "low": g["low"].min(),
        "close": g["close"].last(),
        "n_bars": g.size(),
        "start_ts": g["ts"].first(),
        "end_ts": g["ts"].last(),
    })
    if "volume" in df:
        out["volume"] = g["volume"].sum()

    rth = df[df["in_rth"]]
    gr = rth.groupby("sdate")
    out["rth_open"] = gr["close"].first() if rth_only_source else gr["open"].first()
    if rth_only_source:
        out["open"] = out["rth_open"]
    out["rth_open_ts"] = gr["ts"].first()
    out["rth_close"] = gr["close"].last()
    out["rth_high"] = gr["high"].max()
    out["rth_low"] = gr["low"].min()
    out["n_rth_bars"] = gr.size()

    first_rth_ts = out["rth_open_ts"].reindex(df["sdate"]).to_numpy()
    pre_mask = df["ts"].to_numpy() < first_rth_ts
    pre = df[pre_mask].groupby("sdate")
    post = df[~pre_mask].groupby("sdate")
    out["pre_high"] = pre["high"].max()
    out["pre_low"] = pre["low"].min()
    out["post_high"] = post["high"].max()
    out["post_low"] = post["low"].min()

    gaps = df["ts"].diff().dt.total_seconds().div(60)
    gaps[df["sdate"] != df["sdate"].shift()] = np.nan
    out["max_gap_min"] = gaps.groupby(df["sdate"]).max().fillna(0)
    out["merged_holiday"] = merged.reindex(out.index).fillna(False).astype(bool)
    out.index.name = "session"
    return out

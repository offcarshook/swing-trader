"""Multi-timeframe bars built ONLY from genuine 1-minute observations, with completion times.

Exchange time: naive US/Central (CME convention used by the source files). A session runs
17:00 CT (previous calendar day) -> 16:00 CT; US daylight-saving switches happen at 02:00 on
Sundays while CME equity futures are closed, so local-time arithmetic is exact (verified: no
duplicate or missing timestamps around the 2019-2026 DST changes).

Every bar carries
  start         first minute of the bucket (session-anchored: buckets start at 17:00 CT)
  available_at  the moment the bar is COMPLETE = nominal bucket end, capped at the 16:00 session
                end. Early-close days keep the nominal end (conservative: never earlier than the
                last minute that could belong to the bar).
  n_minutes     number of real 1-minute bars inside (no bucket is fabricated when empty).
A lower timeframe may only see a higher-timeframe bar whose available_at <= its own decision
time (`asof`), so an incomplete 4-hour or daily bar is never visible.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from swingtrader.data.sessions import session_dates

SESSION_END = pd.Timedelta(hours=16)
SESSION_START_OFFSET = pd.Timedelta(hours=7)   # 17:00 CT previous day = session date - 7h
TIMEFRAMES = {"5m": 5, "15m": 15, "1h": 60, "4h": 240}


def _session_frame(m1: pd.DataFrame) -> pd.DataFrame:
    sd = session_dates(m1.index)
    df = m1.copy()
    df["session"] = sd
    df["session_start"] = sd - SESSION_START_OFFSET
    return df


def intraday_bars(m1: pd.DataFrame, minutes: int) -> pd.DataFrame:
    df = _session_frame(m1)
    tf = pd.Timedelta(minutes=minutes)
    k = (df.index - df["session_start"]) // tf
    df["start"] = df["session_start"] + k * tf
    g = df.groupby("start", sort=True)
    out = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                        "close": g["close"].last(), "volume": g["volume"].sum(), "n_minutes": g.size(),
                        "session": g["session"].first()})
    out["available_at"] = np.minimum(out.index + tf, out["session"] + SESSION_END)
    out.index.name = "start"
    return out.reset_index().set_index("available_at", drop=False)


def daily_bars(m1: pd.DataFrame) -> pd.DataFrame:
    """Full Globex session bars, available at 16:00 CT on the session date."""
    df = _session_frame(m1)
    g = df.groupby("session", sort=True)
    out = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                        "close": g["close"].last(), "volume": g["volume"].sum(), "n_minutes": g.size()})
    out["session"] = out.index
    out["start"] = out.index - SESSION_START_OFFSET
    out["available_at"] = out.index + SESSION_END
    return out.set_index("available_at", drop=False)


def build_all(m1: pd.DataFrame, timeframes=("5m", "15m", "1h", "4h")) -> dict[str, pd.DataFrame]:
    bars = {tf: intraday_bars(m1, TIMEFRAMES[tf]) for tf in timeframes}
    bars["1d"] = daily_bars(m1)
    return bars


def asof(base_times: pd.Series | pd.DatetimeIndex, higher: pd.DataFrame, cols: list[str], prefix: str) -> pd.DataFrame:
    """For each decision time, the columns of the latest higher-TF bar COMPLETED at or before it.
    Alignment is by timestamp (merge_asof on available_at), never by row position."""
    left = pd.DataFrame({"t": pd.DatetimeIndex(base_times)}).reset_index(drop=True)
    right = higher[["available_at", *cols]].rename(columns={c: f"{prefix}{c}" for c in cols})
    right = right.rename(columns={"available_at": f"{prefix}available_at"}).sort_values(f"{prefix}available_at")
    out = pd.merge_asof(left.sort_values("t"), right, left_on="t", right_on=f"{prefix}available_at",
                        direction="backward", allow_exact_matches=True)
    return out.set_index("t")

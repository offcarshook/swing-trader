"""Raw file loaders -> clean 1-minute frames indexed by naive US/Central timestamps.

Timestamp convention (verified in the data report): bars are labelled by their
START minute in US/Central. Globex reopens at 17:00 (first bar 17:00) and halts
at 16:00 (last bar 15:59). RTH is the 08:30..14:59 bars; the 15:00 bar is the
first post-close minute and appears identically in both MES files.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from swingtrader.data.sources import SOURCES, local_path

OHLC = ["open", "high", "low", "close"]


def _read_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["datetime"] = pd.to_datetime(df["datetime"], format="%Y-%m-%d %H:%M:%S")
    df = df.set_index("datetime").sort_index()
    for c in OHLC:
        df[c] = df[c].astype("float64")
    if "volume" in df:
        df["volume"] = df["volume"].astype("int64")
    return df


def load_mes_1m(raw_dir: Path) -> pd.DataFrame:
    """Full-session MES 1-min bars (ETH + RTH files merged, exact duplicates dropped)."""
    eth = _read_csv(local_path(raw_dir, SOURCES["mes_1m_eth"]))
    rth = _read_csv(local_path(raw_dir, SOURCES["mes_1m_rth"]))
    both = pd.concat([eth, rth]).sort_index(kind="stable")
    dup = both.index.duplicated(keep="first")
    if dup.any():
        # Only identical duplicates are acceptable; anything else is a data conflict.
        dups = both[both.index.duplicated(keep=False)]
        conflicting = dups.groupby(level=0).nunique().gt(1).any(axis=1)
        if conflicting.any():
            raise ValueError(f"conflicting duplicate bars at {list(conflicting[conflicting].index[:5])}")
        both = both[~dup]
    return both


def load_spx_1m(raw_dir: Path) -> pd.DataFrame:
    return _read_csv(local_path(raw_dir, SOURCES["spx_1m"]))


def load_mnq_1m(raw_dir: Path) -> pd.DataFrame:
    return _read_csv(local_path(raw_dir, SOURCES["mnq_1m"]))


def load_vix_daily(raw_dir: Path) -> pd.DataFrame:
    df = _read_csv(local_path(raw_dir, SOURCES["vix_daily"]))
    df.index = df.index.normalize()
    return df


def load_es_databento_1m(raw_dir: Path) -> pd.DataFrame:
    """Unadjusted ES front-month bars converted from UTC to naive US/Central."""
    df = pd.read_parquet(local_path(raw_dir, SOURCES["es_1m_databento"]))
    df = df[["instrument_id", *OHLC, "volume"]].copy()
    df.index = df.index.tz_convert("America/Chicago").tz_localize(None)
    df.index.name = "datetime"
    return df.sort_index()


def ohlc_integrity(df: pd.DataFrame, tick: float | None = None) -> dict:
    """Bar-level integrity counts (all should be zero for clean data)."""
    hi_bad = (df["high"] < df[["open", "close"]].max(axis=1)) | (df["high"] < df["low"])
    lo_bad = df["low"] > df[["open", "close"]].min(axis=1)
    out = {
        "rows": int(len(df)),
        "non_positive": int((df[OHLC] <= 0).any(axis=1).sum()),
        "nan": int(df[OHLC].isna().any(axis=1).sum()),
        "high_inconsistent": int(hi_bad.sum()),
        "low_inconsistent": int(lo_bad.sum()),
        "duplicate_ts": int(df.index.duplicated().sum()),
        "unsorted": int(not df.index.is_monotonic_increasing),
    }
    if tick:
        off = np.abs(df[OHLC].to_numpy() / tick - np.round(df[OHLC].to_numpy() / tick)) > 1e-6
        out["off_tick_grid"] = int(off.any(axis=1).sum())
    return out

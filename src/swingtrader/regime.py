"""Explicit, testable market-regime labels (used for gating and reporting).

  trend_up    close > SMA(100) and SMA(100) higher than 20 sessions ago
  trend_down  close < SMA(100) and SMA(100) lower than 20 sessions ago
  range       otherwise
  high_vol    flag: ATR(20)/close above the 80th percentile of the trailing 252 sessions
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from swingtrader import indicators as ind


def classify(df: pd.DataFrame, trend_len: int = 100, slope_len: int = 20, atr_len: int = 20,
             vol_lookback: int = 252, high_vol_pct: float = 80) -> pd.DataFrame:
    ma = ind.sma(df["close"], trend_len)
    slope = ma - ma.shift(slope_len)
    up = (df["close"] > ma) & (slope > 0)
    down = (df["close"] < ma) & (slope < 0)
    label = np.where(up, "trend_up", np.where(down, "trend_down", "range"))
    label = pd.Series(label, index=df.index).where(ma.notna() & slope.notna(), "warmup")
    atr_pct = ind.atr(df, atr_len) / df["close"] * 100
    vol_rank = ind.trailing_percentile(atr_pct, vol_lookback)
    return pd.DataFrame({"regime": label, "atr_pct": atr_pct, "vol_rank": vol_rank,
                         "high_vol": vol_rank > high_vol_pct})

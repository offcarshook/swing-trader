"""Causal indicators: the value at row t uses only rows <= t.

They are computed on additively back-adjusted prices, so point-based measures
(ATR, channels, moving averages) are exact; percent measures are slightly
understated early in the series because the adjustment adds a positive constant.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - prev_close).abs(), (df["low"] - prev_close).abs()], axis=1)
    return tr.max(axis=1)


def atr(df: pd.DataFrame, n: int) -> pd.Series:
    """Wilder ATR, seeded with the simple mean of the first n true ranges."""
    tr = true_range(df).to_numpy()
    out = np.full(len(tr), np.nan)
    if len(tr) > n:
        out[n] = np.nanmean(tr[1:n + 1])
        for i in range(n + 1, len(tr)):
            out[i] = (out[i - 1] * (n - 1) + tr[i]) / n
    return pd.Series(out, index=df.index)


def rsi(s: pd.Series, n: int) -> pd.Series:
    """Wilder RSI."""
    d = s.diff().to_numpy()
    up = np.where(d > 0, d, 0.0)
    dn = np.where(d < 0, -d, 0.0)
    out = np.full(len(s), np.nan)
    if len(s) > n:
        au, ad = up[1:n + 1].mean(), dn[1:n + 1].mean()
        out[n] = 100.0 if ad == 0 else 100 - 100 / (1 + au / ad)
        for i in range(n + 1, len(s)):
            au = (au * (n - 1) + up[i]) / n
            ad = (ad * (n - 1) + dn[i]) / n
            out[i] = 100.0 if ad == 0 else 100 - 100 / (1 + au / ad)
    return pd.Series(out, index=s.index)


def donchian_high(df: pd.DataFrame, n: int) -> pd.Series:
    """Highest high of the PRIOR n sessions (excludes the current row)."""
    return df["high"].shift(1).rolling(n, min_periods=n).max()


def donchian_low(df: pd.DataFrame, n: int) -> pd.Series:
    return df["low"].shift(1).rolling(n, min_periods=n).min()


def trailing_percentile(s: pd.Series, lookback: int) -> pd.Series:
    """Percentile rank (0-100) of today's value within the trailing window incl. today."""
    def rank_last(x: np.ndarray) -> float:
        return float((x[:-1] < x[-1]).mean() * 100) if len(x) > 1 else np.nan
    return s.rolling(lookback, min_periods=max(20, lookback // 2)).apply(rank_last, raw=True)


def adx(df: pd.DataFrame, n: int = 14) -> pd.Series:
    up = df["high"].diff()
    dn = -df["low"].diff()
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = true_range(df)
    alpha = 1 / n
    atr_ = tr.ewm(alpha=alpha, adjust=False, min_periods=n).mean()
    pdi = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=alpha, adjust=False, min_periods=n).mean() / atr_
    mdi = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=alpha, adjust=False, min_periods=n).mean() / atr_
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.ewm(alpha=alpha, adjust=False, min_periods=n).mean()

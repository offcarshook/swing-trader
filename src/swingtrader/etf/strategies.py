"""The five 1-3 day ETF families, as causal signal generators on daily bars.

A signal is decided with data up to the signal bar and filled on the entry bar:
  * close-decided signals (dip, NR breakout, calendar, shorts) fill on the NEXT bar,
  * gap signals are decided at the entry bar's open (open vs. prior close) and fill at
    that open; nothing later than the open is used.
Stops are in ATR(14) units of the signal bar; `target_r` is a multiple of the initial
risk; `max_hold` is the number of sessions after the entry session (time stop at that
session's close, so every trade lasts 1-3 sessions); `exit_sma` exits at the next open
once the close crosses back over SMA(n) (the classic dip-buy exit).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from swingtrader.indicators import atr, rsi, sma


@dataclass(frozen=True)
class Params:
    family: str
    side: str = "long"            # long | short
    variant: str = ""             # family-specific switch (e.g. nr7 / inside, fade / go)
    threshold: float = 0.0        # family-specific trigger level
    stop_atr: float = 1.5
    target_r: float | None = None
    max_hold: int = 3
    exit_sma: int | None = None
    trend_filter: bool = True

    @property
    def id(self) -> str:
        t = "none" if self.target_r is None else f"{self.target_r:g}R"
        x = f"_x{self.exit_sma}" if self.exit_sma else ""
        tf = "" if self.trend_filter else "_notrend"
        return f"{self.family}_{self.side}_{self.variant}{self.threshold:g}_s{self.stop_atr:g}_{t}_h{self.max_hold}{x}{tf}"

    def to_dict(self) -> dict:
        return asdict(self) | {"id": self.id}


def features(df: pd.DataFrame) -> pd.DataFrame:
    f = pd.DataFrame(index=df.index)
    f["atr"] = atr(df, 14)
    f["sma200"], f["sma50"], f["sma5"] = sma(df["close"], 200), sma(df["close"], 50), sma(df["close"], 5)
    f["rsi2"] = rsi(df["close"], 2)
    f["uptrend"] = (df["close"] > f["sma200"]) & (f["sma50"] > f["sma50"].shift(10))
    f["downtrend"] = (df["close"] < f["sma200"]) & (f["sma50"] < f["sma50"].shift(10))
    rng = df["high"] - df["low"]
    f["nr4"] = rng == rng.rolling(4).min()
    f["nr7"] = rng == rng.rolling(7).min()
    f["inside"] = (df["high"] < df["high"].shift(1)) & (df["low"] > df["low"].shift(1))
    c, h, l, o = df["close"], df["high"], df["low"], df["open"]
    f["ibs"] = ((c - l) / (h - l).replace(0, np.nan)).fillna(0.5)
    f["down3"] = (c < c.shift(1)) & (c.shift(1) < c.shift(2)) & (c.shift(2) < c.shift(3))
    f["up3"] = (c > c.shift(1)) & (c.shift(1) > c.shift(2)) & (c.shift(2) > c.shift(3))
    m20, s20 = c.rolling(20).mean(), c.rolling(20).std()
    f["bb_low"], f["bb_high"] = c < m20 - 2 * s20, c > m20 + 2 * s20
    f["low7"] = c <= c.rolling(7).min()
    f["high10"] = c >= c.shift(1).rolling(10).max()
    hh, ll = h.rolling(10).max(), l.rolling(10).min()
    f["wr"] = 100 * (c - hh) / (hh - ll).replace(0, np.nan)
    f["outside_weak"] = (h > h.shift(1)) & (l < l.shift(1)) & (f["ibs"] < 0.25)
    f["key_rev"] = (o < l.shift(1)) & (c > c.shift(1))
    f["mon_down"] = (pd.Series(df.index.dayofweek, index=df.index) == 0) & (c < o)
    month = df.index.to_period("M")
    pos = pd.Series(np.arange(len(df)), index=df.index)
    f["day_of_month"] = pos.groupby(month).cumcount() + 1                       # 1 = first session
    f["days_left"] = (pos.groupby(month).transform("count") - f["day_of_month"]).astype(float)  # 0 = last session
    # the final month in the data may be incomplete: its session count is not known yet
    if len(df) and df.index[-1] < df.index[-1] + pd.offsets.BMonthEnd(0):
        f.loc[month == month[-1], "days_left"] = np.nan
    return f


def _frame(idx_sig, idx_entry, p: Params, stop_dist, entry_level=None) -> pd.DataFrame:
    n = len(idx_sig)
    return pd.DataFrame({
        "sig_i": idx_sig, "entry_i": idx_entry, "dir": np.full(n, 1 if p.side == "long" else -1),
        "stop_dist": stop_dist, "entry_level": np.full(n, np.nan) if entry_level is None else entry_level,
    })


def signals(df: pd.DataFrame, p: Params, f: pd.DataFrame | None = None) -> pd.DataFrame:
    """All signals for one symbol. Columns: sig_i, entry_i, dir, stop_dist, entry_level (NaN = market at open)."""
    f = features(df) if f is None else f
    a = f["atr"].to_numpy()
    n = len(df)
    ok = ~np.isnan(a) & ~f["sma200"].isna().to_numpy()
    up, dn = f["uptrend"].to_numpy(), f["downtrend"].to_numpy()
    if p.family == "dip":                      # 1. dip-buy in an uptrend (RSI(2) washout)
        cond = ok & (f["rsi2"].to_numpy() < p.threshold) & (up if p.trend_filter else True)
    elif p.family == "short":                  # 5. downtrend shorts (RSI(2) bounce into resistance)
        cond = ok & (f["rsi2"].to_numpy() > p.threshold) & (dn if p.trend_filter else True)
    elif p.family == "calendar":               # 4. turn-of-month: enter at the open of the last session
        # signal on the second-to-last session's close (days_left == 1) -> fill next open
        cond = ok & (f["days_left"].to_numpy() == 1) & (up if p.trend_filter else True)
        if p.threshold > 0:                    # optional washout filter: only after a down week
            cond &= (df["close"] < df["close"].shift(5)).to_numpy()
    elif p.family == "nrb":                    # 2. NR4/NR7/inside-day breakout via buy/sell stop
        setup = f[p.variant].to_numpy() & ok
        trend = up if p.side == "long" else dn
        cond = setup & (trend if p.trend_filter else True)
        i = np.flatnonzero(cond[:-1])
        lvl = (df["high"] if p.side == "long" else df["low"]).to_numpy()[i]
        rng = (df["high"] - df["low"]).to_numpy()[i]
        # stop at the other side of the setup bar, floored at stop_atr * ATR so tiny ranges can't explode size
        return _frame(i, i + 1, p, np.maximum(rng, p.stop_atr * a[i]), lvl)
    elif p.family == "gap":                    # 3. gap fade / gap-and-go, decided at the open
        prev_close, op = df["close"].shift(1).to_numpy(), df["open"].to_numpy()
        a_prev = np.roll(a, 1); a_prev[0] = np.nan
        g = (op - prev_close) / a_prev
        # fade: long a gap DOWN in an uptrend (short a gap up in a downtrend); go: follow the gap
        if p.variant == "fade":
            want = -p.threshold if p.side == "long" else p.threshold
            hit = g <= want if p.side == "long" else g >= want
        else:
            hit = g >= p.threshold if p.side == "long" else g <= -p.threshold
        trend_prev = np.roll(up if p.side == "long" else dn, 1)
        trend_prev[0] = False
        ok_prev = np.roll(ok, 1); ok_prev[0] = False
        cond = ok_prev & np.nan_to_num(hit, nan=0).astype(bool) & (trend_prev if p.trend_filter else True)
        j = np.flatnonzero(cond)
        return _frame(j - 1, j, p, p.stop_atr * a_prev[j])
    elif p.family in ("mr", "mom", "mrshort"):  # 6-17. extra families (grid v2)
        v = p.variant
        if v == "ibs":
            setup = f["ibs"].to_numpy() < p.threshold
        elif v == "ibs_hi":
            setup = f["ibs"].to_numpy() > p.threshold
        elif v == "wr":
            setup = f["wr"].to_numpy() < p.threshold
        else:
            setup = f[v].to_numpy().astype(bool)
        trend = dn if p.family == "mrshort" else up
        cond = ok & setup & (trend if p.trend_filter else True)
    else:
        raise ValueError(p.family)
    i = np.flatnonzero(np.asarray(cond)[:-1])
    return _frame(i, i + 1, p, p.stop_atr * a[i])


def grid_v2() -> list[Params]:
    """Grid v2 (12 more families, 24 candidates), registered after the v1 final test had been run."""
    g: list[Params] = []
    for v, th in (("ibs", 0.2), ("down3", 0), ("bb_low", 0), ("low7", 0), ("wr", -90),
                  ("outside_weak", 0), ("key_rev", 0), ("mon_down", 0)):
        g.append(Params("mr", "long", v, th, 2.0, None, 3, 5))
        g.append(Params("mr", "long", v, th, 1.5, 1.0, 3))
    for v, th in (("ibs_hi", 0.8), ("up3", 0), ("bb_high", 0)):
        g.append(Params("mrshort", "short", v, th, 2.0, None, 3, 5))
        g.append(Params("mrshort", "short", v, th, 1.5, 1.0, 3))
    g.append(Params("mom", "long", "high10", 0, 1.5, 1.5, 3))
    g.append(Params("mom", "long", "high10", 0, 1.0, 1.0, 2))
    return g


def grid() -> list[Params]:
    """Pre-registered candidates: <= 8 per family, written before any backtest ran."""
    g: list[Params] = []
    for th in (5, 10):
        for x in (5, None):
            g.append(Params("dip", "long", "rsi2<", th, 2.0, None if x else 1.0, 3, x))
    for v in ("nr7", "nr4", "inside"):
        for t in (1.0, 1.5):
            g.append(Params("nrb", "long", v, 0, 1.0, t, 3))
    g.append(Params("nrb", "short", "nr7", 0, 1.0, 1.0, 3))
    g.append(Params("nrb", "short", "inside", 0, 1.0, 1.0, 3))
    for th in (0.5, 1.0):
        g.append(Params("gap", "long", "fade", th, 1.0, 1.0, 1))
        g.append(Params("gap", "long", "fade", th, 1.5, None, 3, 5))
        g.append(Params("gap", "long", "go", th, 1.0, 1.5, 2))
        g.append(Params("gap", "short", "fade", th, 1.0, 1.0, 1))
    for th in (0, 1):
        for tf in (True, False):
            g.append(Params("calendar", "long", "tom", th, 2.0, None, 3, None, tf))
    for th in (90, 95):
        for x in (5, None):
            g.append(Params("short", "short", "rsi2>", th, 2.0, None if x else 1.0, 3, x))
    return g

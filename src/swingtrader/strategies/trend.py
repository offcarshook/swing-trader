"""S1 - Trend continuation.

Hypothesis: equity-index trends persist over weeks (time-series momentum). Enter
when a medium-term uptrend is established or resumes; ride it with a volatility
trailing stop; leave when the trend structure breaks.

Exact rules (evaluated on the completed session bar t, acted on at t+1 RTH open):
  up_state(t)   = close > SMA(slow) and SMA(fast) > SMA(slow) and SMA(slow) > SMA(slow)[t-20]
  ENTRY LONG    = flat and up_state(t) and (not up_state(t-1)  OR  close crosses above SMA(fast))
                  and not no_trade_vol(t)
  initial stop  = fill - stop_atr * ATR(t)
  trailing stop = highest close since entry - trail_atr * ATR(t)   (tighten only)
  EXIT          = close < SMA(slow)  -> market exit at next RTH open
  SHORT         = exact mirror (only when allow_short)
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from swingtrader import indicators as ind
from swingtrader.strategies.base import Decision, PositionView, Strategy


@dataclass
class TrendContinuation(Strategy):
    name: str = "trend"
    family: str = "trend"

    @property
    def warmup(self) -> int:
        return max(self.params["slow"] + 21, super().warmup)

    def features(self, bars: pd.DataFrame) -> pd.DataFrame:
        p = self.params
        f = self.base_features(bars)
        c = bars["close"]
        f["ma_fast"] = ind.sma(c, p["fast"])
        f["ma_slow"] = ind.sma(c, p["slow"])
        rising = f["ma_slow"] > f["ma_slow"].shift(20)
        falling = f["ma_slow"] < f["ma_slow"].shift(20)
        f["up"] = (c > f["ma_slow"]) & (f["ma_fast"] > f["ma_slow"]) & rising
        f["down"] = (c < f["ma_slow"]) & (f["ma_fast"] < f["ma_slow"]) & falling
        f["up_prev"] = f["up"].shift(1, fill_value=False)
        f["down_prev"] = f["down"].shift(1, fill_value=False)
        f["cross_up_fast"] = (c > f["ma_fast"]) & (c.shift(1) <= f["ma_fast"].shift(1))
        f["cross_dn_fast"] = (c < f["ma_fast"]) & (c.shift(1) >= f["ma_fast"].shift(1))
        return f

    def decide(self, r, pos: PositionView) -> Decision:
        p = self.params
        if pos.side == 0:
            if r.no_trade_vol:
                return Decision(reason="no-trade: extreme volatility")
            if r.up and (not r.up_prev or r.cross_up_fast):
                return Decision(entry_side=1, stop_distance=p["stop_atr"] * r.atr, reason="trend up resume")
            if p.get("allow_short") and r.down and (not r.down_prev or r.cross_dn_fast):
                return Decision(entry_side=-1, stop_distance=p["stop_atr"] * r.atr, reason="trend down resume")
            return Decision()
        if pos.side > 0:
            if r.close < r.ma_slow:
                return Decision(exit=True, reason="close below slow MA")
            trail = pos.best_close - p["trail_atr"] * r.atr
        else:
            if r.close > r.ma_slow:
                return Decision(exit=True, reason="close above slow MA")
            trail = pos.best_close + p["trail_atr"] * r.atr
        return Decision(stop=self.tighten(pos, trail), reason="trail")

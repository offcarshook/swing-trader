"""S2 - Momentum breakout (Donchian channel).

Hypothesis: a close beyond the N-session range signals new information / flows
that tend to follow through for several sessions.

Exact rules:
  ENTRY LONG  = flat and close(t) > highest high of sessions t-N..t-1 and not no_trade_vol(t)
  initial stop = fill - stop_atr * ATR(t)
  resting stop = max(initial stop, lowest low of the prior M sessions)  (updated each close, tighten only)
  SHORT        = mirror (only when allow_short)
  No discretionary/close-based exit: the channel stop is the exit.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from swingtrader import indicators as ind
from swingtrader.strategies.base import Decision, PositionView, Strategy


@dataclass
class DonchianBreakout(Strategy):
    name: str = "breakout"
    family: str = "breakout"

    @property
    def warmup(self) -> int:
        return max(self.params["entry_lookback"] + 1, super().warmup)

    def features(self, bars: pd.DataFrame) -> pd.DataFrame:
        p = self.params
        f = self.base_features(bars)
        f["dc_hi"] = ind.donchian_high(bars, p["entry_lookback"])
        f["dc_lo"] = ind.donchian_low(bars, p["entry_lookback"])
        # exit channel includes today's bar: the stop is set after the close for the next session
        f["ex_lo"] = bars["low"].rolling(p["exit_lookback"], min_periods=p["exit_lookback"]).min()
        f["ex_hi"] = bars["high"].rolling(p["exit_lookback"], min_periods=p["exit_lookback"]).max()
        return f

    def decide(self, r, pos: PositionView) -> Decision:
        p = self.params
        if pos.side == 0:
            if r.no_trade_vol:
                return Decision(reason="no-trade: extreme volatility")
            if r.close > r.dc_hi:
                return Decision(entry_side=1, stop_distance=p["stop_atr"] * r.atr, reason="breakout up")
            if p.get("allow_short") and r.close < r.dc_lo:
                return Decision(entry_side=-1, stop_distance=p["stop_atr"] * r.atr, reason="breakout down")
            return Decision()
        channel = r.ex_lo if pos.side > 0 else r.ex_hi
        return Decision(stop=self.tighten(pos, channel), reason="channel stop")

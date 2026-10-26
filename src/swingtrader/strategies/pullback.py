"""S3 - Pullback entry within an uptrend (long only).

Hypothesis: short-term oversold dips inside a medium-term uptrend in equity
indices tend to mean-revert over a few sessions (liquidity provision).

Exact rules:
  ENTRY LONG   = flat and close > SMA(trend_len) and RSI(rsi_len) < rsi_entry and not no_trade_vol
  initial stop = fill - stop_atr * ATR(t)                       (resting, intraday)
  EXIT         = close > SMA(exit_ma)              -> next RTH open
               | sessions held >= max_hold         -> next RTH open (time stop)
               | close < SMA(trend_len)            -> next RTH open (trend invalidated)
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from swingtrader import indicators as ind
from swingtrader.strategies.base import Decision, PositionView, Strategy


@dataclass
class TrendPullback(Strategy):
    name: str = "pullback"
    family: str = "pullback"

    @property
    def warmup(self) -> int:
        return max(self.params["trend_len"] + 1, super().warmup)

    def features(self, bars: pd.DataFrame) -> pd.DataFrame:
        p = self.params
        f = self.base_features(bars)
        c = bars["close"]
        f["ma_trend"] = ind.sma(c, p["trend_len"])
        f["ma_exit"] = ind.sma(c, p["exit_ma"])
        f["rsi"] = ind.rsi(c, p["rsi_len"])
        return f

    def decide(self, r, pos: PositionView) -> Decision:
        p = self.params
        if pos.side == 0:
            if r.no_trade_vol:
                return Decision(reason="no-trade: extreme volatility")
            if r.close > r.ma_trend and r.rsi < p["rsi_entry"]:
                return Decision(entry_side=1, stop_distance=p["stop_atr"] * r.atr, reason="oversold in uptrend")
            return Decision()
        if r.close > r.ma_exit:
            return Decision(exit=True, reason="reverted above exit MA")
        if pos.bars_held >= p["max_hold"]:
            return Decision(exit=True, reason="time stop")
        if r.close < r.ma_trend:
            return Decision(exit=True, reason="trend invalidated")
        return Decision(stop=pos.stop)

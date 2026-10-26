"""Strategy interface.

A strategy sees one completed session bar at a time (plus causal features) and
returns a Decision. It never sizes, never fills and never touches the ledger:
the engine executes its decisions at the NEXT session's RTH open, with resting
stops active intraday. That separation is what lets the same strategy object run
in the internal backtester, inside LumiBot and in the paper runner.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from swingtrader import indicators as ind


@dataclass
class PositionView:
    side: int = 0                 # +1 long, -1 short, 0 flat
    entry_price: float = 0.0
    stop: float | None = None
    bars_held: int = 0            # completed sessions since entry (0 on the entry session close)
    best_close: float = 0.0       # highest close since entry if long, lowest if short


@dataclass
class Decision:
    entry_side: int = 0           # request entry at next RTH open (engine ignores unless flat)
    stop_distance: float | None = None   # initial stop distance in points from the entry fill
    exit: bool = False            # exit at next RTH open
    stop: float | None = None     # proposed resting stop; engine only ever tightens
    reason: str = ""


@dataclass
class Strategy:
    params: dict = field(default_factory=dict)
    atr_period: int = 20
    vol_filter_pct: float = 95.0
    vol_filter_lookback: int = 252
    name: str = "base"
    family: str = "base"

    @property
    def label(self) -> str:
        p = ",".join(f"{k}={v}" for k, v in sorted(self.params.items()))
        return f"{self.name}[{p}]"

    @property
    def warmup(self) -> int:
        return self.vol_filter_lookback // 2

    def base_features(self, bars: pd.DataFrame) -> pd.DataFrame:
        f = pd.DataFrame(index=bars.index)
        f["close"] = bars["close"]
        f["high"] = bars["high"]
        f["low"] = bars["low"]
        f["atr"] = ind.atr(bars, self.atr_period)
        f["atr_pct"] = f["atr"] / bars["close"] * 100
        f["vol_rank"] = ind.trailing_percentile(f["atr_pct"], self.vol_filter_lookback)
        # No-trade condition shared by all strategies: extreme volatility.
        f["no_trade_vol"] = f["vol_rank"] > self.vol_filter_pct
        return f

    def features(self, bars: pd.DataFrame) -> pd.DataFrame:
        raise NotImplementedError

    def decide(self, row, pos: PositionView) -> Decision:
        raise NotImplementedError

    @staticmethod
    def tighten(pos: PositionView, proposed: float | None) -> float | None:
        if proposed is None or pos.stop is None:
            return proposed if pos.stop is None else pos.stop
        return max(pos.stop, proposed) if pos.side > 0 else min(pos.stop, proposed)

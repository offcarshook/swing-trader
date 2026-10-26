"""Simple baselines every candidate must beat.

  ma_cross   long when SMA(50) > SMA(200), flat otherwise; 3 ATR initial stop; same risk sizing
  random     random entries at the candidate's own entry rate with the candidate's
             stop distance and holding-period distribution (Monte Carlo, many seeds)
  buy & hold is not a Strategy: see backtest.engine.buy_and_hold (1x notional, monthly rebalance)
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from swingtrader import indicators as ind
from swingtrader.strategies.base import Decision, PositionView, Strategy


@dataclass
class MACrossBaseline(Strategy):
    name: str = "ma_cross"
    family: str = "baseline"
    params: dict = field(default_factory=lambda: {"fast": 50, "slow": 200, "stop_atr": 3.0})

    @property
    def warmup(self) -> int:
        return self.params["slow"] + 1

    def features(self, bars: pd.DataFrame) -> pd.DataFrame:
        f = self.base_features(bars)
        f["ma_fast"] = ind.sma(bars["close"], self.params["fast"])
        f["ma_slow"] = ind.sma(bars["close"], self.params["slow"])
        return f

    def decide(self, r, pos: PositionView) -> Decision:
        bull = r.ma_fast > r.ma_slow
        if pos.side == 0:
            if bull:
                return Decision(entry_side=1, stop_distance=self.params["stop_atr"] * r.atr, reason="golden")
            return Decision()
        if not bull:
            return Decision(exit=True, reason="death cross")
        return Decision(stop=pos.stop)


@dataclass
class RandomEntry(Strategy):
    """Enters long with probability `p_entry` on any flat session; exits after a
    holding period drawn from `hold_days`; initial stop `stop_atr` ATR."""
    name: str = "random"
    family: str = "baseline"
    params: dict = field(default_factory=lambda: {"p_entry": 0.05, "hold_days": [5], "stop_atr": 2.5,
                                                   "seed": 0, "side": 1})

    def __post_init__(self):
        self._rng = np.random.default_rng(self.params["seed"])
        self._hold = None

    def features(self, bars: pd.DataFrame) -> pd.DataFrame:
        return self.base_features(bars)

    def decide(self, r, pos: PositionView) -> Decision:
        p = self.params
        if pos.side == 0:
            if self._rng.random() < p["p_entry"] and np.isfinite(r.atr):
                self._hold = int(self._rng.choice(p["hold_days"]))
                side = -1 if self._rng.random() < p.get("p_short", 0.0) else p.get("side", 1)
                return Decision(entry_side=side, stop_distance=p["stop_atr"] * r.atr, reason="random")
            return Decision()
        if pos.bars_held >= (self._hold or 1):
            return Decision(exit=True, reason="random hold elapsed")
        return Decision(stop=pos.stop)

from swingtrader.strategies.base import Decision, PositionView, Strategy
from swingtrader.strategies.baselines import MACrossBaseline, RandomEntry
from swingtrader.strategies.breakout import DonchianBreakout
from swingtrader.strategies.pullback import TrendPullback
from swingtrader.strategies.trend import TrendContinuation

FAMILIES = {
    "trend": TrendContinuation,
    "breakout": DonchianBreakout,
    "pullback": TrendPullback,
    "ma_cross": MACrossBaseline,
}


def make_strategy(family: str, params: dict, cfg: dict | None = None) -> Strategy:
    sd = (cfg or {}).get("strategy_defaults", {})
    kw = {}
    if sd:
        kw = {"atr_period": sd["atr_period"], "vol_filter_pct": sd["vol_filter_pct"],
              "vol_filter_lookback": sd["vol_filter_lookback"]}
    return FAMILIES[family](params=dict(params), **kw)


__all__ = ["Decision", "PositionView", "Strategy", "TrendContinuation", "DonchianBreakout",
           "TrendPullback", "MACrossBaseline", "RandomEntry", "FAMILIES", "make_strategy"]

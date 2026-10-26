"""Convenience wiring: config -> spec/costs/risk -> run a candidate."""

from __future__ import annotations

import pandas as pd

from swingtrader.backtest.engine import BacktestResult, buy_and_hold, run_backtest
from swingtrader.contracts import SPECS
from swingtrader.costs import CostModel
from swingtrader.regime import classify
from swingtrader.risk import RiskLimits, RiskManager
from swingtrader.strategies import make_strategy


def components(cfg: dict, cost_multiplier: float = 1.0, risk_overrides: dict | None = None):
    spec = SPECS[cfg["instrument"]]
    costs = CostModel.from_config(spec, cfg["costs"], multiplier=cost_multiplier)
    risk_cfg = {**cfg["risk"], **(risk_overrides or {})}
    risk = RiskManager(RiskLimits.from_config(risk_cfg), spec, costs)
    return spec, costs, risk


def run_candidate(cfg: dict, bars: pd.DataFrame, family: str, params: dict, start, end,
                  cost_multiplier: float = 1.0, risk_overrides: dict | None = None,
                  entry_filter=None) -> BacktestResult:
    spec, costs, risk = components(cfg, cost_multiplier, risk_overrides)
    strat = make_strategy(family, params, cfg)
    regimes = classify(bars)["regime"]
    return run_backtest(bars, strat, spec, costs, risk, start, end, cfg["account"]["starting_equity"],
                        entry_filter=entry_filter, regimes=regimes, instrument=cfg["instrument"])


def run_buy_hold(cfg: dict, bars: pd.DataFrame, start, end, cost_multiplier: float = 1.0,
                 leverage: float = 1.0) -> BacktestResult:
    spec, costs, _ = components(cfg, cost_multiplier)
    return buy_and_hold(bars, spec, costs, start, end, cfg["account"]["starting_equity"], leverage,
                        instrument=cfg["instrument"])

"""One-shot evaluation of the selected candidate on the untouched MES holdout."""

from __future__ import annotations

import pandas as pd

from swingtrader.backtest.metrics import by_year_trades, monthly_returns, summarize, yearly_returns
from swingtrader.backtest.runner import run_buy_hold, run_candidate
from swingtrader.config import config_hash, resolve
from swingtrader.research.experiments import HoldoutGuard
from swingtrader.research.selection import random_baseline


def holdout_window(cfg: dict) -> tuple[str, str | None]:
    s = cfg["splits"]
    return s["holdout_start"], s["holdout_end"]


def evaluate_holdout(cfg: dict, mes: pd.DataFrame, selection: dict, override_reason: str | None = None,
                     n_random: int = 200) -> dict:
    chosen = selection.get("selected")
    promotable = chosen is not None
    if chosen is None:
        chosen = selection["top_ranked_if_none_passed"]
    family, params = chosen["family"], chosen["params"]
    cand_hash = config_hash({"family": family, "params": params, "costs": cfg["costs"], "risk": cfg["risk"]})
    guard = HoldoutGuard()
    access = guard.authorize(chosen["id"], cand_hash, override_reason)

    a, b = holdout_window(cfg)
    runs = {f"{m:g}x": run_candidate(cfg, mes, family, params, a, b, cost_multiplier=m) for m in (1.0, 2.0, 3.0)}
    base = runs["1x"]
    summary = summarize(base.equity, base.trades, base.start_equity, base.in_market)
    stress = {k: {kk: summarize(r.equity, r.trades, r.start_equity)[kk]
                  for kk in ("net_return_pct", "profit_factor", "expectancy_usd", "max_drawdown_pct")}
              for k, r in runs.items()}
    # slippage-only stress: +2 ticks on every fill, fees unchanged
    slip_cfg = {**cfg, "costs": {**cfg["costs"],
                                 "market_slippage_ticks": cfg["costs"]["market_slippage_ticks"] + 2,
                                 "stop_slippage_ticks": cfg["costs"]["stop_slippage_ticks"] + 2}}
    slip = run_candidate(slip_cfg, mes, family, params, a, b)
    stress["+2 ticks slippage"] = {kk: summarize(slip.equity, slip.trades, slip.start_equity)[kk]
                                   for kk in ("net_return_pct", "profit_factor", "expectancy_usd", "max_drawdown_pct")}

    sources = {"mes": (mes, a, b)}
    ev_like = {"trades": base.trades, "params": params, "runs": {"mes": base},
               "combined": {"total_net_pnl": float(base.trades["net_pnl"].sum()) if not base.trades.empty else 0.0}}
    rnd = random_baseline(cfg, sources, ev_like, n_random)
    bh = run_buy_hold(cfg, mes, a, b)
    ma = run_candidate(cfg, mes, "ma_cross", {"fast": 50, "slow": 200, "stop_atr": 3.0}, a, b)

    gates = cfg["promotion"]
    fails = []
    if not promotable:
        fails.append("candidate did not pass training gates")
    if summary["trades"] < gates["min_trades"]:
        fails.append(f"trades {summary['trades']} < {gates['min_trades']}")
    if summary["profit_factor"] < gates["min_profit_factor"]:
        fails.append(f"profit factor {summary['profit_factor']} < {gates['min_profit_factor']}")
    if summary["max_drawdown_pct"] > gates["max_drawdown_pct"]:
        fails.append(f"max DD {summary['max_drawdown_pct']}% > {gates['max_drawdown_pct']}%")
    if gates["require_positive_at_2x_costs"] and stress["2x"]["net_return_pct"] <= 0:
        fails.append("not profitable at 2x costs")

    out_dir = resolve("results")
    base.equity.to_csv(out_dir / "holdout_equity.csv", header=True)
    if not base.trades.empty:
        base.trades.to_csv(out_dir / "holdout_trades.csv", index=False)

    return {
        "candidate": chosen["id"], "family": family, "params": params, "hash": cand_hash,
        "promotable_from_training": promotable,
        "holdout_access": access, "holdout_history": guard.history(),
        "window": [a, str(base.equity.index[-1].date())],
        "summary": summary,
        "monthly_returns_pct": {str(k.date()): round(v, 3) for k, v in monthly_returns(base.equity, base.start_equity).items()},
        "yearly_returns_pct": yearly_returns(base.equity, base.start_equity).round(2).to_dict(),
        "trades_by_year": by_year_trades(base.trades).to_dict(orient="index"),
        "cost_stress": stress,
        "random_baseline": rnd,
        "baselines": {
            "buy_hold_1x": summarize(bh.equity, bh.trades, bh.start_equity, bh.in_market),
            "ma_cross": summarize(ma.equity, ma.trades, ma.start_equity, ma.in_market),
        },
        "promotion": {"passed": not fails, "failures": fails, "gates": gates},
    }

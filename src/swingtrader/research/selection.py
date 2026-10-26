"""Training-only candidate evaluation and selection (docs/VALIDATION_PROTOCOL.md).

Nothing in this module reads holdout data: every run is clipped to the training
windows (S&P 500 proxy 2008-2019 and MES 2019-2023).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from swingtrader.backtest.engine import run_backtest
from swingtrader.backtest.metrics import (drawdown_periods, fold_metrics, monthly_returns, summarize,
                                         trade_stats, yearly_returns)
from swingtrader.backtest.runner import components, run_buy_hold, run_candidate
from swingtrader.config import config_hash
from swingtrader.strategies.baselines import RandomEntry


def train_sources(cfg: dict, mes: pd.DataFrame, spx: pd.DataFrame) -> dict:
    s = cfg["splits"]
    return {
        "spx": (spx, s["proxy_start"], s["proxy_end"]),
        "mes": (mes, s["train_start"], s["train_end"]),
    }


def candidate_id(family: str, params: dict) -> str:
    return f"{family}[" + ",".join(f"{k}={v}" for k, v in sorted(params.items())) + "]"


def evaluate(cfg, sources, family, params, cost_mult=1.0, risk_overrides=None) -> dict:
    runs = {src: run_candidate(cfg, bars, family, params, a, b, cost_mult, risk_overrides)
            for src, (bars, a, b) in sources.items()}
    folds = []
    for src, a, b in cfg["splits"]["walk_forward_folds"]:
        r = runs[src]
        fm = fold_metrics(r.equity, r.trades, [(a, b)])[0]
        folds.append({"source": src, **fm})
    trades = pd.concat([r.trades.assign(source=s) for s, r in runs.items() if not r.trades.empty],
                       ignore_index=True) if any(not r.trades.empty for r in runs.values()) else pd.DataFrame()
    per_source = {s: summarize(r.equity, r.trades, r.start_equity, r.in_market) for s, r in runs.items()}
    sharpe = [f["sharpe"] for f in folds]
    combined = {
        **trade_stats(trades),
        "max_drawdown_pct": max(p["max_drawdown_pct"] for p in per_source.values()),
        "median_fold_sharpe": float(np.median(sharpe)),
        "positive_folds": int(sum(f["net_pnl"] > 0 for f in folds)),
        "total_net_pnl": round(float(trades["net_pnl"].sum()) if not trades.empty else 0.0, 2),
    }
    return {"id": candidate_id(family, params), "family": family, "params": params,
            "hash": config_hash({"family": family, "params": params}),
            "combined": combined, "folds": folds, "per_source": per_source, "runs": runs, "trades": trades}


def random_baseline(cfg, sources, ev: dict, n_seeds: int = 100) -> dict:
    """Random entries matched to the candidate's entry rate, side mix, stop and holding time."""
    totals = []
    hold = ev["trades"]["sessions_held"].clip(lower=1).astype(int).tolist() if not ev["trades"].empty else [5]
    p_short = float((ev["trades"]["side"] < 0).mean()) if not ev["trades"].empty else 0.0
    stop_atr = ev["params"].get("stop_atr", 2.5)
    rates = {}
    for src, r in ev["runs"].items():
        flat = int((~r.in_market).sum())
        n = len(r.trades)
        rates[src] = n / flat if flat else 0.0
    src_salt = {"spx": 1, "mes": 2}  # stable across processes (str hash() is randomised)
    feats_cache: dict = {}
    for seed in range(n_seeds):
        tot = 0.0
        for src, (bars, _a, b) in sources.items():
            spec, costs, risk = components(cfg)
            strat = RandomEntry(params={"p_entry": rates[src], "hold_days": hold, "stop_atr": stop_atr,
                                        "seed": seed * 7919 + src_salt.get(src, 3), "side": 1,
                                        "p_short": p_short},
                                atr_period=cfg["strategy_defaults"]["atr_period"],
                                vol_filter_lookback=cfg["strategy_defaults"]["vol_filter_lookback"])
            if src not in feats_cache:
                feats_cache[src] = strat.features(bars)
            strat.features = lambda _b, _f=feats_cache[src]: _f
            # same start date as the candidate run so the windows are comparable
            res = run_backtest(bars, strat, spec, costs, risk, ev["runs"][src].equity.index[0], b,
                               cfg["account"]["starting_equity"], instrument=cfg["instrument"])
            tot += float(res.trades["net_pnl"].sum()) if not res.trades.empty else 0.0
        totals.append(tot)
    totals = np.array(totals)
    cand = ev["combined"]["total_net_pnl"]
    return {"n_seeds": n_seeds, "candidate_total_net_pnl": cand,
            "random_mean": round(float(totals.mean()), 2), "random_p50": round(float(np.median(totals)), 2),
            "random_p90": round(float(np.percentile(totals, 90)), 2),
            "candidate_percentile": round(float((totals < cand).mean() * 100), 1)}


def apply_gates(cfg, ev: dict, rnd: dict) -> list[str]:
    g, c = cfg["selection"], ev["combined"]
    fails = []
    if c["trades"] < g["min_trades"]:
        fails.append(f"trades {c['trades']} < {g['min_trades']}")
    if c["profit_factor"] < g["min_profit_factor"]:
        fails.append(f"profit factor {c['profit_factor']} < {g['min_profit_factor']}")
    if c["max_drawdown_pct"] > g["max_drawdown_pct"]:
        fails.append(f"max DD {c['max_drawdown_pct']}% > {g['max_drawdown_pct']}%")
    if c["positive_folds"] < g["min_positive_folds"]:
        fails.append(f"positive folds {c['positive_folds']} < {g['min_positive_folds']}")
    if rnd["candidate_percentile"] < g["must_beat_random_pctile"]:
        fails.append(f"beats only {rnd['candidate_percentile']}% of random entries < {g['must_beat_random_pctile']}%")
    return fails


def anchored_walk_forward(evals: list[dict]) -> dict:
    """Simulate choosing the best-so-far candidate (median fold Sharpe over past folds)
    and recording its NEXT fold: an out-of-sample estimate of the selection process."""
    n_folds = len(evals[0]["folds"])
    rows = []
    for k in range(1, n_folds):
        scores = [np.median([f["sharpe"] for f in e["folds"][:k]]) for e in evals]
        best = evals[int(np.argmax(scores))]
        nxt = best["folds"][k]
        avg_all = float(np.mean([e["folds"][k]["return_pct"] for e in evals]))
        rows.append({"fold": f"{nxt['source']} {nxt['fold']}", "chosen": best["id"],
                     "chosen_return_pct": nxt["return_pct"], "chosen_sharpe": nxt["sharpe"],
                     "avg_all_candidates_return_pct": round(avg_all, 2)})
    return {"steps": rows,
            "mean_chosen_return_pct": round(float(np.mean([r["chosen_return_pct"] for r in rows])), 3),
            "mean_all_return_pct": round(float(np.mean([r["avg_all_candidates_return_pct"] for r in rows])), 3)}


def baselines_on(cfg, sources) -> dict:
    out = {}
    for src, (bars, a, b) in sources.items():
        bh = run_buy_hold(cfg, bars, a, b)
        out[f"buy_hold_1x_{src}"] = summarize(bh.equity, bh.trades, bh.start_equity, bh.in_market)
        out[f"buy_hold_1x_{src}"]["yearly"] = yearly_returns(bh.equity, bh.start_equity).round(2).to_dict()
        ma = run_candidate(cfg, bars, "ma_cross", {"fast": 50, "slow": 200, "stop_atr": 3.0}, a, b)
        out[f"ma_cross_{src}"] = summarize(ma.equity, ma.trades, ma.start_equity, ma.in_market)
    return out


RISK_SCALING = [1.0, 2.0, 3.0, 5.0, 8.0]


def risk_scaling(cfg, sources, family, params) -> list[dict]:
    """How much risk would the 5-8%/month target need? Training data only."""
    rows = []
    for rpt in RISK_SCALING:
        ov = {"risk_per_trade_pct": rpt, "max_open_risk_pct": rpt, "max_notional_leverage": 15.0,
              "max_margin_utilization": 0.95, "max_contracts": 1000, "daily_loss_limit_pct": 50.0,
              "max_drawdown_halt_pct": 90.0}
        row = {"risk_per_trade_pct": rpt}
        for src, (bars, a, b) in sources.items():
            r = run_candidate(cfg, bars, family, params, a, b, 1.0, ov)
            m = summarize(r.equity, r.trades, r.start_equity, r.in_market)
            row[src] = {k: m[k] for k in ("avg_monthly_return_pct", "cagr_pct", "max_drawdown_pct",
                                          "worst_month_pct", "months_ge_5pct", "avg_contracts")}
        rows.append(row)
    return rows


def run_selection(cfg, mes, spx, n_random: int = 100, progress=print) -> dict:
    sources = train_sources(cfg, mes, spx)
    evals, table = [], []
    for family, grid in cfg["candidates"].items():
        for params in grid:
            ev = evaluate(cfg, sources, family, params)
            rnd = random_baseline(cfg, sources, ev, n_random)
            fails = apply_gates(cfg, ev, rnd)
            ev["random"] = rnd
            ev["gate_failures"] = fails
            evals.append(ev)
            c = ev["combined"]
            table.append({"id": ev["id"], "family": family, "passed": not fails, "failures": fails,
                          "trades": c["trades"], "profit_factor": c["profit_factor"],
                          "expectancy_usd": c["expectancy_usd"], "expectancy_r": c["expectancy_r"],
                          "max_dd_pct": c["max_drawdown_pct"], "median_fold_sharpe": round(c["median_fold_sharpe"], 3),
                          "positive_folds": c["positive_folds"], "random_pctile": rnd["candidate_percentile"],
                          "total_net_pnl": c["total_net_pnl"],
                          "spx_net_return_pct": ev["per_source"]["spx"]["net_return_pct"],
                          "mes_net_return_pct": ev["per_source"]["mes"]["net_return_pct"]})
            progress(f"  {ev['id']}: trades={c['trades']} PF={c['profit_factor']} "
                     f"medSharpe={c['median_fold_sharpe']:.2f} rnd%={rnd['candidate_percentile']} "
                     f"{'PASS' if not fails else 'FAIL: ' + '; '.join(fails)}")

    passed = [e for e in evals if not e["gate_failures"]]
    rank_key = lambda e: e["combined"]["median_fold_sharpe"]  # noqa: E731
    ranked_all = sorted(evals, key=rank_key, reverse=True)
    selected = max(passed, key=rank_key) if passed else None
    top = selected or ranked_all[0]
    family_best = {}
    for fam in cfg["candidates"]:
        fe = [e for e in evals if e["family"] == fam]
        fp = [e for e in fe if not e["gate_failures"]]
        b = max(fp or fe, key=rank_key)
        family_best[fam] = {"id": b["id"], "passed_gates": not b["gate_failures"]}

    cost_stress = {}
    for mult in (1.0, 2.0, 3.0):
        e = evaluate(cfg, sources, top["family"], top["params"], cost_mult=mult)
        cost_stress[f"{mult:g}x"] = {"total_net_pnl": e["combined"]["total_net_pnl"],
                                     "profit_factor": e["combined"]["profit_factor"],
                                     "expectancy_usd": e["combined"]["expectancy_usd"],
                                     "spx_net_return_pct": e["per_source"]["spx"]["net_return_pct"],
                                     "mes_net_return_pct": e["per_source"]["mes"]["net_return_pct"]}

    result = {
        "protocol": "docs/VALIDATION_PROTOCOL.md (with Amendment 1)",
        "train_windows": {k: [str(v[1]), str(v[2])] for k, v in sources.items()},
        "candidates": table,
        "selected": None if selected is None else {"id": selected["id"], "family": selected["family"],
                                                   "params": selected["params"], "hash": selected["hash"]},
        "top_ranked_if_none_passed": None if selected else {"id": top["id"], "family": top["family"],
                                                             "params": top["params"], "hash": top["hash"],
                                                             "note": "did not pass training gates; NOT promotable"},
        "family_best": family_best,
        "anchored_walk_forward": anchored_walk_forward(evals),
        "top_detail": {"id": top["id"], "folds": top["folds"], "per_source": top["per_source"],
                       "random": top["random"],
                       "worst_drawdowns": {s: drawdown_periods(r.equity, r.start_equity, 3)
                                           for s, r in top["runs"].items()},
                       "worst_months": {s: {str(k.date()): round(v, 2) for k, v in
                                            monthly_returns(r.equity, r.start_equity).nsmallest(5).items()}
                                        for s, r in top["runs"].items()},
                       "yearly": {s: yearly_returns(r.equity, r.start_equity).round(2).to_dict()
                                  for s, r in top["runs"].items()}},
        "cost_stress_top": cost_stress,
        "baselines": baselines_on(cfg, sources),
        "risk_scaling_top": risk_scaling(cfg, sources, top["family"], top["params"]),
    }
    return result, evals

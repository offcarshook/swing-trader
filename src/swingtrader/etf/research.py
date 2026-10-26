"""Train-only selection, one-shot final test, reports.

Protocol (pre-registered in config/etf.yaml before any run):
  1. every candidate in `strategies.grid()` runs on the TRAIN window only;
  2. gates at 2x costs: >= min_trades, profit factor >= min_pf, positive expectancy,
     positive in >= min_fold_share of yearly folds, total P&L above the
     `random_pctile` percentile of random-entry runs with the same exits;
  3. per family the passing candidate with the best train Sharpe is kept; the
     portfolio is the union of kept candidates under the shared risk cap;
  4. that portfolio runs ONCE on the final window, registered with HoldoutGuard.
"""

from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd

from swingtrader.etf.engine import RiskCfg, build_signals, metrics, simulate
from swingtrader.etf.strategies import Params, features, grid, grid_v2


GRIDS = {"v1": grid, "v2": grid_v2, "all": lambda: grid() + grid_v2()}


def risk_from_cfg(cfg: dict, cost_mult: float = 1.0) -> RiskCfg:
    return RiskCfg(**{**cfg["risk"], **cfg["costs"], "cost_mult": cost_mult})


def group(p: Params) -> str:
    """Selection keeps one candidate per group: the v1 family, or family:setup for v2."""
    return p.family if p.family in ("dip", "nrb", "gap", "calendar", "short") else f"{p.family}:{p.variant}"


def random_baseline(bars, p: Params, feats, n_trades: int, start, end, risk: RiskCfg, seeds: int, rng) -> np.ndarray:
    """Total P&L of `seeds` runs that enter at random eligible opens with the candidate's exits."""
    pools = {}
    for s, df in bars.items():
        a = feats[s]["atr"].to_numpy()
        idx = np.flatnonzero((df.index >= pd.Timestamp(start)) & (df.index <= pd.Timestamp(end)))
        idx = idx[(idx > 0) & ~np.isnan(a[np.maximum(idx - 1, 0)])]
        pools[s] = (idx, a)
    syms = [s for s in bars if len(pools[s][0])]
    out = []
    for _ in range(seeds):
        rows = []
        for _k in range(max(n_trades, 1)):
            s = syms[rng.integers(len(syms))]
            idx, a = pools[s]
            j = int(idx[rng.integers(len(idx))])
            rows.append({"sym": s, "rank": 0, "pid": p.id, "entry_date": bars[s].index[j],
                         "dir": 1 if p.side == "long" else -1, "stop_dist": p.stop_atr * a[j - 1],
                         "entry_level": np.nan})
        r = simulate(bars, [p], start, end, risk, sigs=pd.DataFrame(rows))
        out.append(r.trades["pnl"].sum() if len(r.trades) else 0.0)
    return np.array(out)


def fold_returns(res, folds) -> list[float | None]:
    out = []
    for a, b in folds:
        t = res.trades
        t = t[(t.entry_date >= pd.Timestamp(a)) & (t.entry_date <= pd.Timestamp(b))] if len(t) else t
        out.append(None if len(t) < 3 else float(t.pnl.sum()))
    return out


def evaluate_train(cfg: dict, bars: dict[str, pd.DataFrame], seeds: int | None = None, grid_name: str = "v1") -> dict:
    sp, g = cfg["splits"], cfg["gates"]
    folds = [(f"{y}-01-01", f"{y}-12-31") for y in range(int(sp["train_start"][:4]), int(sp["train_end"][:4]) + 1)]
    feats = {s: features(df) for s, df in bars.items()}
    rng = np.random.default_rng(cfg.get("seed", 7))
    seeds = g["random_seeds"] if seeds is None else seeds
    cands = []
    for p in GRIDS[grid_name]():
        sigs = build_signals(bars, [p], feats)
        r1 = simulate(bars, [p], sp["train_start"], sp["train_end"], risk_from_cfg(cfg, 1.0), sigs=sigs)
        r2 = simulate(bars, [p], sp["train_start"], sp["train_end"], risk_from_cfg(cfg, 2.0), sigs=sigs)
        m1, m2 = metrics(r1, cfg["risk"]["equity"]), metrics(r2, cfg["risk"]["equity"])
        fr = [x for x in fold_returns(r2, folds) if x is not None]
        fold_share = float(np.mean([x > 0 for x in fr])) if fr else 0.0
        pnl2 = r2.trades["pnl"].sum() if len(r2.trades) else 0.0
        pct = None
        fails = []
        if m2["trades"] < g["min_trades"]:
            fails.append(f"trades {m2['trades']} < {g['min_trades']}")
        if m2.get("profit_factor", 0) < g["min_pf"]:
            fails.append(f"PF@2x {m2.get('profit_factor')} < {g['min_pf']}")
        if m2.get("expectancy_r", -1) <= 0:
            fails.append("expectancy@2x <= 0")
        if fold_share < g["min_fold_share"]:
            fails.append(f"positive folds {fold_share:.0%} < {g['min_fold_share']:.0%}")
        if not fails and seeds:
            base = random_baseline(bars, p, feats, m2["trades"], sp["train_start"], sp["train_end"],
                                   risk_from_cfg(cfg, 2.0), seeds, rng)
            pct = float((base < pnl2).mean() * 100)
            if pct < g["random_pctile"]:
                fails.append(f"random-entry percentile {pct:.0f} < {g['random_pctile']}")
        cands.append({**p.to_dict(), "group": group(p), "train_1x": m1, "train_2x": m2, "fold_share": round(fold_share, 2),
                      "n_folds": len(fr), "random_pctile": pct, "passed": not fails, "failures": fails})
    kept = {}
    for c in cands:
        if c["passed"] and (c["group"] not in kept or c["train_1x"]["sharpe"] > kept[c["group"]]["train_1x"]["sharpe"]):
            kept[c["group"]] = c
    chosen = [Params(**{k: v for k, v in c.items() if k in Params.__dataclass_fields__}) for c in kept.values()]
    port = None
    if chosen:
        rp = simulate(bars, chosen, sp["train_start"], sp["train_end"], risk_from_cfg(cfg, 1.0))
        port = {"metrics_1x": metrics(rp, cfg["risk"]["equity"]), "skipped": rp.skipped,
                "metrics_2x": metrics(simulate(bars, chosen, sp["train_start"], sp["train_end"],
                                               risk_from_cfg(cfg, 2.0)), cfg["risk"]["equity"])}
    return {"grid": grid_name, "stack": cfg["risk"].get("stack_symbols", False), "symbols": sorted(bars), "splits": sp, "gates": g, "candidates": cands,
            "selected": [c["id"] for c in kept.values()], "selected_params": [p.to_dict() for p in chosen],
            "train_portfolio": port}


def selection_hash(sel: dict) -> str:
    return hashlib.sha256(json.dumps([sel["selected_params"], sel["symbols"], sel["splits"], sel.get("stack", False)],
                                     sort_keys=True, default=str).encode()).hexdigest()[:16]


def final_test(cfg: dict, bars: dict[str, pd.DataFrame], sel: dict) -> dict:
    sp = cfg["splits"]
    params = [Params(**{k: v for k, v in d.items() if k in Params.__dataclass_fields__}) for d in sel["selected_params"]]
    out = {"selected": sel["selected"], "window": [sp["final_start"], sp["final_end"]]}
    for mult in (1.0, 2.0, 3.0):
        r = simulate(bars, params, sp["final_start"], sp["final_end"], risk_from_cfg(cfg, mult))
        m = metrics(r, cfg["risk"]["equity"])
        out[f"costs_{mult:g}x"] = m
        if mult == 1.0:
            out["skipped"], res = r.skipped, r
    t = res.trades
    if len(t):
        out["by_family"] = t.groupby("family").agg(trades=("pnl", "size"), pnl=("pnl", "sum"),
                                                   win=("pnl", lambda x: float((x > 0).mean())),
                                                   avg_r=("r", "mean")).round(3).to_dict("index")
        out["by_year"] = t.groupby(t.entry_date.dt.year)["pnl"].agg(["size", "sum"]).round(0).to_dict("index")
        out["sessions_hist"] = t.sessions.value_counts().sort_index().to_dict()
        wk = t.groupby(t.entry_date.dt.to_period("W")).size().reindex(
            pd.period_range(res.equity.index[0], res.equity.index[-1], freq="W"), fill_value=0)
        out["weeks_with_0_setups_pct"] = round(float((wk == 0).mean() * 100), 1)
        out["weeks_in_1_to_5_pct"] = round(float(((wk >= 1) & (wk <= 5)).mean() * 100), 1)
    win = {s: b.loc[sp["final_start"]:sp["final_end"]] for s, b in bars.items()}
    bh = {s: round(100.0 * float(w["close"].iloc[-1] / w["open"].iloc[0] - 1), 2) for s, w in win.items() if len(w)}
    out["buy_and_hold_pct"] = bh
    return out, res

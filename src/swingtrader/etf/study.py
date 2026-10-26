"""Corrected-basis ETF study: reproducible end-to-end evidence for docs/ETF_RESULTS.md et al.

    python -m swingtrader etf-study [--wf-seeds 20] [--boot 2000]

Everything is computed from data/raw/etf_full (real SPY and QQQ daily bars, executable prices +
dividends) and the frozen corrected-basis training selection. The 2021+ window was already
viewed in round 3, so every 2021+ number here is labelled `previously_viewed`; nothing in this
module can make it an untouched holdout.
"""

from __future__ import annotations

import dataclasses
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from swingtrader.config import load_config, resolve
from swingtrader.etf.analytics import report
from swingtrader.etf.data import common_window, load_basket
from swingtrader.etf.engine import RiskCfg, simulate
from swingtrader.etf.research import buy_hold, evaluate_train, risk_from_cfg
from swingtrader.etf.strategies import Params
from swingtrader.rules.account import AccountRules, rolling_starts

SYMS = ["SPY", "QQQ"]
VIEWED = "previously_viewed (round 3 evaluated 2021+ once; corrected-basis rerun is a second look)"


def _params(sel: dict) -> list[Params]:
    return [Params(**{k: v for k, v in d.items() if k in Params.__dataclass_fields__}) for d in sel["selected_params"]]


def _risk(cfg, mult=1.0, **over) -> RiskCfg:
    r = risk_from_cfg(cfg, mult)
    return dataclasses.replace(r, **over)


def _run(bars, params, start, end, risk, **kw):
    return simulate(bars, params, start, end, risk, **kw)


def window_block(cfg, bars, params, start, end, label) -> dict:
    out = {"label": label, "status": VIEWED, "requested": [start, end]}
    for mult in (0.0, 1.0, 2.0, 3.0):
        r = _run(bars, params, start, end, _risk(cfg, mult))
        rep = report(r, cfg["risk"]["equity"])
        out[f"costs_{mult:g}x"] = rep
        if mult == 1.0:
            out["_result"] = r
    out["actual_window"] = out["costs_1x"]["window"]
    out["benchmarks_total_return"] = {s: buy_hold(b, *out["actual_window"]) for s, b in bars.items()}
    if len(bars) > 1:
        trs = [v["total_return_pct"] for v in out["benchmarks_total_return"].values() if v]
        out["benchmarks_total_return"]["equal_weight_no_rebalance_pct"] = round(float(np.mean(trs)), 2)
    return out


def stacking_ablation(cfg, bars, params, start, end) -> dict:
    base = _run(bars, params, start, end, _risk(cfg, stack_symbols=False))
    stk = _run(bars, params, start, end, _risk(cfg, stack_symbols=True))
    rb, rs = report(base), report(stk)
    scale = rb["avg_gross_exposure_pct"] / rs["avg_gross_exposure_pct"] if rs["avg_gross_exposure_pct"] else 1.0
    eq = _run(bars, params, start, end, _risk(cfg, stack_symbols=True, risk_pct=cfg["risk"]["risk_pct"] * scale))
    clus = _run(bars, params, start, end, _risk(cfg, stack_symbols=True, clusters={s: "us_equity" for s in bars},
                                                max_cluster_risk_pct=cfg["risk"]["risk_pct"] * 2))
    rows = {}
    for name, r in (("one_position_per_instrument", base), ("stacked_same_risk_per_trade", stk),
                    (f"stacked_equal_exposure_risk_{cfg['risk']['risk_pct'] * scale:.2f}pct", eq),
                    ("stacked_cluster_cap_2R_us_equity", clus)):
        x = report(r)
        rows[name] = {k: x.get(k) for k in ("trades", "total_return_pct", "cagr_pct", "max_dd_pct", "sharpe",
                                             "profit_factor", "avg_gross_exposure_pct", "time_in_market_pct",
                                             "expectancy_r")}
        g = x.get("avg_gross_exposure_pct") or 0
        rows[name]["cagr_per_100pct_avg_gross"] = round(100 * x["cagr_pct"] / g, 2) if g else None
    return {"window": [start, end], "status": VIEWED, "variants": rows,
            "note": "equal-exposure variant scales risk per trade so average gross exposure matches the "
                    "one-position book; compare CAGR per unit of exposure, not raw return"}


def _perturb(p: Params, **kw) -> Params:
    return dataclasses.replace(p, **kw)


THRESH_STEP = {"ibs": 0.05, "wr": 5.0, "rsi2<": 2.5, "rsi2>": 2.5}


def robustness(cfg, bars, params, windows: dict) -> dict:
    """Perturb every selected candidate in the same direction, one knob at a time."""
    variants = {"baseline": params}
    for d in (-1, 1):
        variants[f"threshold_{'minus' if d < 0 else 'plus'}_1step"] = [
            _perturb(p, threshold=p.threshold + d * THRESH_STEP[p.variant]) if p.variant in THRESH_STEP else p
            for p in params]
    variants["stop_atr_x0.75"] = [_perturb(p, stop_atr=p.stop_atr * 0.75) for p in params]
    variants["stop_atr_x1.25"] = [_perturb(p, stop_atr=p.stop_atr * 1.25) for p in params]
    variants["max_hold_2"] = [_perturb(p, max_hold=2) for p in params]
    variants["max_hold_4"] = [_perturb(p, max_hold=4) for p in params]
    for p in params:
        variants[f"without_{p.id}"] = [q for q in params if q is not p]
    out = {}
    for wname, (s, e) in windows.items():
        rows = {}
        for vname, ps in variants.items():
            r = _run(bars, ps, s, e, _risk(cfg))
            x = report(r)
            rows[vname] = {k: x.get(k) for k in ("trades", "total_return_pct", "profit_factor", "max_dd_pct", "sharpe")}
        for name, over in (("costs_2x", {"cost_mult": 2.0}), ("costs_3x", {"cost_mult": 3.0}),
                           ("entry_delay_1_session", {"entry_delay": 1}), ("missed_fills_10pct", {"miss_fill_prob": 0.1}),
                           ("missed_fills_25pct", {"miss_fill_prob": 0.25})):
            x = report(_run(bars, params, s, e, _risk(cfg, **over)))
            rows[name] = {k: x.get(k) for k in ("trades", "total_return_pct", "profit_factor", "max_dd_pct", "sharpe")}
        out[wname] = rows
    return out


def filter_strictness(cfg, bars, train=("2008-01-01", "2016-12-31"), valid=("2017-01-01", "2020-12-31")) -> dict:
    """Frequency vs. expectancy for a range of entry thresholds (training + validation only)."""
    grid = {"ibs": [0.1, 0.15, 0.2, 0.25, 0.3, 0.35], "wr": [-97.5, -95, -90, -85, -80, -75]}
    out = {}
    for v, ths in grid.items():
        rows = []
        for th in ths:
            p = Params("mr", "long", v, th, 2.0 if v == "ibs" else 1.5, None if v == "ibs" else 1.0, 3,
                       5 if v == "ibs" else None)
            row = {"threshold": th}
            for nm, (s, e) in (("train", train), ("validation", valid)):
                x = report(_run(bars, [p], s, e, _risk(cfg, 2.0)))
                row[nm] = {k: x.get(k) for k in ("trades", "trades_per_week", "expectancy_r", "profit_factor",
                                                 "total_return_pct", "max_dd_pct")}
            rows.append(row)
        out[v] = rows
    return {"costs": "2x", "families": out,
            "note": "thresholds are not re-selected from this table; it shows how expectancy changes as the "
                    "filter is relaxed to raise frequency"}


def walk_forward(cfg, bars, first_test_year=2013, last_test_year=None, seeds=20) -> dict:
    """Anchored walk-forward of the WHOLE selection procedure (grid 'all', same gates)."""
    last = last_test_year or max(b.index.max().year for b in bars.values())
    folds = []
    for y in range(first_test_year, last + 1):
        c = json.loads(json.dumps(cfg))
        c["splits"]["train_end"] = f"{y - 1}-12-31"
        sel = evaluate_train(c, bars, seeds=seeds, grid_name="all")
        ps = _params(sel)
        row = {"test_year": y, "selected": sel["selected"],
               "status": VIEWED if y >= 2021 else "out-of-sample within the research period"}
        if ps:
            x = report(_run(bars, ps, f"{y}-01-01", f"{y}-12-31", _risk(cfg)))
            row.update({k: x.get(k) for k in ("trades", "total_return_pct", "profit_factor", "max_dd_pct")})
        else:
            row.update({"trades": 0, "total_return_pct": 0.0})
        allc = [Params(**{k: v for k, v in cd.items() if k in Params.__dataclass_fields__})
                for cd in sel["candidates"]]
        rets = [report(_run(bars, [p], f"{y}-01-01", f"{y}-12-31", _risk(cfg))).get("total_return_pct", 0.0)
                for p in allc]
        row["avg_single_candidate_return_pct"] = round(float(np.mean(rets)), 2)
        folds.append(row)
    df = pd.DataFrame(folds)
    pre = df[df.test_year < 2021]
    chain = lambda s: round(100 * float(np.prod(1 + s / 100) - 1), 2)  # noqa: E731
    return {"folds": folds, "seeds": seeds,
            "chained_oos_return_pct_2013_2020": chain(pre.total_return_pct),
            "positive_folds_2013_2020": f"{int((pre.total_return_pct > 0).sum())}/{len(pre)}",
            "selected_beats_avg_candidate_2013_2020": f"{int((pre.total_return_pct > pre.avg_single_candidate_return_pct).sum())}/{len(pre)}",
            "chained_return_pct_2021_plus_viewed": chain(df[df.test_year >= 2021].total_return_pct)}


def block_bootstrap(res, n=2000, mean_block=10, seed=7) -> dict:
    """Stationary bootstrap of daily portfolio returns (keeps short-range clustering; cannot
    create regimes that are not in the sample)."""
    r = res.equity.pct_change().dropna().to_numpy()
    rng = np.random.default_rng(seed)
    m, tot, dds = len(r), [], []
    for _ in range(n):
        idx = np.empty(m, int)
        i = rng.integers(m)
        for t in range(m):
            idx[t] = i
            i = rng.integers(m) if rng.random() < 1 / mean_block else (i + 1) % m
        path = np.cumprod(1 + r[idx])
        tot.append(path[-1] - 1)
        dds.append((path / np.maximum.accumulate(path) - 1).min())
    tot, dds = np.array(tot), np.array(dds)
    q = lambda a, p: round(100 * float(np.quantile(a, p)), 2)  # noqa: E731
    return {"samples": n, "mean_block_days": mean_block,
            "total_return_pct_p5_p50_p95": [q(tot, .05), q(tot, .5), q(tot, .95)],
            "max_dd_pct_p5_p50_p95": [q(dds, .05), q(dds, .5), q(dds, .95)],
            "prob_total_return_below_zero": round(float((tot < 0).mean()), 3)}


def deflated_sharpe(res, n_trials: int, trial_sharpes: list[float]) -> dict:
    """Bailey & Lopez de Prado deflated Sharpe ratio (daily returns, annualised SR reported)."""
    from statistics import NormalDist
    nd = NormalDist()
    r = res.equity.pct_change().dropna().to_numpy()
    sr = r.mean() / r.std()
    T = len(r)
    skew = float(((r - r.mean()) ** 3).mean() / r.std() ** 3)
    kurt = float(((r - r.mean()) ** 4).mean() / r.std() ** 4)
    v = float(np.var(np.array(trial_sharpes) / math.sqrt(252))) if len(trial_sharpes) > 1 else 0.0
    g = 0.5772156649
    sr0 = math.sqrt(v) * ((1 - g) * nd.inv_cdf(1 - 1 / n_trials) + g * nd.inv_cdf(1 - 1 / (n_trials * math.e)))
    z = (sr - sr0) * math.sqrt(T - 1) / math.sqrt(1 - skew * sr + (kurt - 1) / 4 * sr ** 2)
    return {"annualised_sharpe": round(sr * math.sqrt(252), 3), "n_trials": n_trials,
            "expected_max_sharpe_under_null_annualised": round(sr0 * math.sqrt(252), 3),
            "deflated_sharpe_probability": round(nd.cdf(z), 3), "observations": T}


def account_rule_study(cfg, res_by_window: dict) -> dict:
    out = {}
    for sc in cfg.get("account_rule_scenarios", []):
        sc = dict(sc)
        horizon = int(sc.pop("horizon_sessions", 60))
        rules = AccountRules.from_dict(sc)
        out[rules.name] = {w: {k: v for k, v in rolling_starts(r, rules, horizon).items() if k != "rows"}
                           for w, r in res_by_window.items()}
    return out


def _clean(o):
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items() if not str(k).startswith("_")}
    if isinstance(o, list):
        return [_clean(v) for v in o]
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    return o


def run_study(wf_seeds: int = 20, boot: int = 2000, skip_wf: bool = False) -> dict:
    cfg = load_config(resolve("config/etf.yaml"))
    out_dir = resolve("results/etf/study")
    out_dir.mkdir(parents=True, exist_ok=True)
    sel = json.loads((out_dir / "train_selection_corrected.json").read_text())
    params = _params(sel)
    bars = load_basket(resolve("data/raw/etf_full"), SYMS)
    fs = cfg["splits"]["final_start"]
    s_end, q_end = str(bars["SPY"].index.max().date()), str(bars["QQQ"].index.max().date())
    cs, ce = common_window(bars, fs, cfg["splits"]["final_end"])
    windows = {
        "SPY_only": ({"SPY": bars["SPY"]}, fs, s_end),
        "QQQ_only": ({"QQQ": bars["QQQ"]}, fs, q_end),
        "common_portfolio": (bars, cs, ce),
    }
    study = {"selection": {"selected": sel["selected"], "hash": sel["hash"]},
             "config_snapshot": cfg, "data": {s: {"first": str(b.index.min().date()), "last": str(b.index.max().date()),
                                                  "sessions": int(len(b)), "price_basis": b.attrs.get("price_basis")}
                                              for s, b in bars.items()}}
    from swingtrader.research.experiments import HoldoutGuard
    study["holdout_registry_entry"] = HoldoutGuard("results/etf/holdout_registry_full2etf.json").authorize(
        "+".join(sel["selected"]), sel["hash"],
        override_reason="corrected price basis (raw fills + dividends) rerun on the 2021+ window that round 3 "
                        "already evaluated; reported as previously viewed, not as an untouched holdout")
    res = {}
    for name, (b, s, e) in windows.items():
        blk = window_block(cfg, b, params, s, e, name)
        res[name] = blk.pop("_result")
        res[name].trades.to_csv(out_dir / f"trades_{name}.csv", index=False)
        res[name].equity.to_csv(out_dir / f"equity_{name}.csv")
        if res[name].signals is not None:
            res[name].signals.to_csv(out_dir / f"opportunities_{name}.csv", index=False)
        study[name] = blk
    # training-period reference (where selection happened) for the same frozen book
    tr = _run(bars, params, cfg["splits"]["train_start"], cfg["splits"]["train_end"], _risk(cfg))
    study["train_period_reference"] = {"window": [cfg["splits"]["train_start"], cfg["splits"]["train_end"]],
                                       "costs_1x": report(tr)}
    res["train_2008_2020"] = tr
    study["stacking_ablation"] = stacking_ablation(cfg, bars, params, cs, ce)
    study["robustness"] = robustness(cfg, bars, params, {"train_2008_2020": (cfg["splits"]["train_start"],
                                                                             cfg["splits"]["train_end"]),
                                                         "common_viewed": (cs, ce)})
    study["filter_strictness"] = filter_strictness(cfg, bars)
    study["bootstrap_common"] = block_bootstrap(res["common_portfolio"], n=boot)
    trial_sr = [c["train_1x"].get("sharpe", 0.0) for c in sel["candidates"]]
    # trials: 52 candidates x 5 selection rounds run on related data (proxy v1, proxy all, 2-ETF,
    # 15-ETF, corrected 2-ETF) -- a conservative count of the search that produced this book
    study["multiple_testing"] = {"train_portfolio": deflated_sharpe(tr, 52 * 5, trial_sr),
                                 "common_viewed": deflated_sharpe(res["common_portfolio"], 52 * 5, trial_sr)}
    study["account_rules"] = account_rule_study(cfg, {"train_2008_2020": tr, "common_viewed": res["common_portfolio"]})
    if not skip_wf:
        study["walk_forward"] = walk_forward(cfg, bars, seeds=wf_seeds)
    (out_dir / "study.json").write_text(json.dumps(_clean(study), indent=1, default=str))
    return study

"""MTF comparison study on genuine MES 1-minute data -> results/mtf/mtf_study.json (+ trade CSVs).

    python -m swingtrader mtf-study
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from swingtrader.config import load_config, resolve
from swingtrader.data.loaders import load_mes_1m
from swingtrader.mtf import engine as E
from swingtrader.mtf.bars import build_all


def run_mtf_study() -> dict:
    cfg, mcfg = load_config(), load_config(resolve("config/mtf.yaml"))
    out_dir = resolve("results/mtf")
    out_dir.mkdir(parents=True, exist_ok=True)
    m = load_mes_1m(resolve(cfg["data"]["raw_dir"]))
    bars = build_all(m, ("15m", "1h", "4h"))
    f = E.features(bars)
    g = E.decision_frame(f)
    per = mcfg["periods"]
    out = {"config": mcfg, "data": {"first_minute": str(m.index[0]), "last_minute": str(m.index[-1]),
                                    "minutes": int(len(m)), "bars": {k: int(len(v)) for k, v in bars.items()},
                                    "decision_points_rth_15m": int(len(g))},
           "costs": cfg["costs"], "variants": {}}
    for name, v in E.VARIANTS.items():
        ent, diag = E.signals(g, f, v)
        row = {"definition": v.__dict__, "candidates": int(len(ent)), "diagnostics_full_sample": diag}
        for pname, (s, e) in per.items():
            mults = mcfg["stress"]["cost_mults"] if pname != "final_viewed" else [1.0]
            for cm in mults:
                r = E.simulate(m, f, g, ent, v, cfg["costs"], E.SimCfg(cost_mult=cm), s, e)
                row[f"{pname}_costs_{cm:g}x"] = E.metrics(r)
                if cm == 1.0:
                    t = r["trades"]
                    if len(t):
                        t.to_csv(out_dir / f"trades_{name}_{pname}.csv", index=False)
                        row[f"{pname}_by_year"] = {str(y): round(float(x.pnl.sum()), 0)
                                                   for y, x in t.groupby(t.entry_time.dt.year)}
            if pname != "final_viewed":
                r = E.simulate(m, f, g, ent, v, cfg["costs"], E.SimCfg(entry_delay_min=5), s, e)
                row[f"{pname}_delay5min"] = {k: E.metrics(r).get(k) for k in ("trades", "expectancy_r", "profit_factor")}
        out["variants"][name] = row
    out["verdict"] = verdict(out)
    (out_dir / "mtf_study.json").write_text(json.dumps(out, indent=1, default=str))
    return out


def verdict(out: dict) -> dict:
    v = out["variants"]

    def exp(name, period):
        x = v[name].get(f"{period}_costs_2x", {})
        return x.get("expectancy_r") if x.get("trades", 0) else None

    res = {}
    for side in ("", "_short"):
        base = [f"A_daily_only{side}", f"B_context_only{side}"]
        for name in (f"C_context_setup{side}", f"D_full_mtf{side}", f"E_moderate{side}"):
            ok, why = True, []
            for p in ("train", "validation"):
                e = exp(name, p)
                if e is None:
                    ok = False; why.append(f"no {p} trades"); continue
                for b in base:
                    eb = exp(b, p)
                    if eb is not None and e <= eb:
                        ok = False; why.append(f"{p}: {e} <= {b} {eb}")
            if v[name].get("train_costs_2x", {}).get("trades", 0) < 100:
                ok = False; why.append("fewer than 100 train trades")
            res[name] = {"adds_value_per_rule": ok, "why_not": why}
    return res

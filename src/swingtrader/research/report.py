"""Markdown reports generated from the JSON results (no numbers are typed by hand)."""

from __future__ import annotations

import json

from swingtrader.config import resolve


def _table(rows: list[dict], cols: list[str]) -> str:
    if not rows:
        return "_none_\n"
    head = "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n"
    body = "".join("| " + " | ".join(_fmt(r.get(c, "")) for c in cols) + " |\n" for r in rows)
    return head + body


def _fmt(v) -> str:
    if isinstance(v, float):
        return f"{v:,.2f}" if abs(v) >= 100 else f"{v:.3g}" if abs(v) < 0.01 and v != 0 else f"{v:.2f}"
    if isinstance(v, list):
        return "; ".join(map(str, v)) if v else "-"
    return str(v)


KEYS = ["net_return_pct", "cagr_pct", "avg_monthly_return_pct", "median_monthly_return_pct",
        "pct_positive_months", "worst_month_pct", "months_ge_5pct", "max_drawdown_pct", "sharpe",
        "trades", "win_rate_pct", "profit_factor", "expectancy_usd", "expectancy_r",
        "avg_sessions_held", "avg_calendar_days_held", "exposure_pct", "total_fees_usd", "total_roll_costs_usd"]


def _metric_cols(named: dict[str, dict]) -> str:
    cols = ["metric", *named.keys()]
    rows = [{"metric": k, **{n: m.get(k, "") for n, m in named.items()}} for k in KEYS]
    return _table(rows, cols)


def train_report(sel: dict) -> str:
    out = ["# Training-period selection report\n",
           f"Protocol: {sel['protocol']}. Training windows: `{sel['train_windows']}`. "
           "No holdout data is used anywhere in this report.\n",
           "## All candidates (failed experiments included)\n",
           _table(sel["candidates"], ["id", "passed", "trades", "profit_factor", "expectancy_usd", "expectancy_r",
                                      "max_dd_pct", "median_fold_sharpe", "positive_folds", "random_pctile",
                                      "spx_net_return_pct", "mes_net_return_pct", "failures"])]
    if sel["selected"]:
        out.append(f"\n**Selected:** `{sel['selected']['id']}`\n")
    else:
        t = sel["top_ranked_if_none_passed"]
        out.append(f"\n**No candidate passed every training gate.** Top-ranked by median fold Sharpe: "
                   f"`{t['id']}` -- {t['note']}.\n")
    out.append("\nBest per family: " + ", ".join(f"{k}: `{v['id']}` ({'pass' if v['passed_gates'] else 'fail'})"
                                                  for k, v in sel["family_best"].items()) + "\n")
    td = sel["top_detail"]
    out.append(f"\n## Top candidate detail: `{td['id']}`\n\n### Walk-forward folds (one continuous run per source)\n")
    out.append(_table(td["folds"], ["source", "fold", "net_pnl", "return_pct", "sharpe", "trades"]))
    out.append("\n### Per-source metrics vs baselines\n")
    named = {f"{td['id'].split('[')[0]} {s}": m for s, m in td["per_source"].items()}
    for k, v in sel["baselines"].items():
        named[k] = v
    out.append(_metric_cols(named))
    out.append("\n### Yearly returns (%)\n")
    years = sorted({y for d in td["yearly"].values() for y in d})
    out.append(_table([{"year": y, **{s: td["yearly"][s].get(y, "") for s in td["yearly"]}} for y in years],
                      ["year", *td["yearly"].keys()]))
    r = td["random"]
    out.append(f"\n### Random-entry baseline\n{r['n_seeds']} seeds, matched entry rate, side mix, stop and holding "
               f"time. Candidate total net P&L ${r['candidate_total_net_pnl']:,.0f} vs random median "
               f"${r['random_p50']:,.0f} (p90 ${r['random_p90']:,.0f}) -> beats **{r['candidate_percentile']}%** "
               "of random runs.\n")
    out.append("\n### Losing periods (training)\n")
    for src, eps in td.get("worst_drawdowns", {}).items():
        out.append(f"\n**{src}** worst drawdowns:\n\n")
        out.append(_table(eps, ["depth_pct", "dd_start", "trough", "recovered"]))
        wm = td.get("worst_months", {}).get(src, {})
        out.append("\nWorst months: " + ", ".join(f"{k[:7]} {v}%" for k, v in wm.items()) + "\n")
    out.append("\n### Cost sensitivity (training)\n")
    out.append(_table([{"costs": k, **v} for k, v in sel["cost_stress_top"].items()],
                      ["costs", "total_net_pnl", "profit_factor", "expectancy_usd", "spx_net_return_pct",
                       "mes_net_return_pct"]))
    wf = sel["anchored_walk_forward"]
    out.append("\n## Anchored walk-forward of the SELECTION PROCESS\nAt each fold, pick the candidate with the best "
               "median Sharpe over earlier folds, then record its next fold.\n\n")
    out.append(_table(wf["steps"], ["fold", "chosen", "chosen_return_pct", "chosen_sharpe",
                                    "avg_all_candidates_return_pct"]))
    out.append(f"\nMean next-fold return of the chosen candidate: {wf['mean_chosen_return_pct']}% vs "
               f"{wf['mean_all_return_pct']}% for the average candidate.\n")
    out.append("\n## Can 5-8% per month be reached by scaling risk? (training data, top candidate)\n"
               "Risk limits loosened only for this experiment (leverage cap 15x, DD halt 90%).\n\n")
    rows = []
    for row in sel["risk_scaling_top"]:
        for s in ("spx", "mes"):
            rows.append({"risk_per_trade_pct": row["risk_per_trade_pct"], "source": s, **row[s]})
    out.append(_table(rows, ["risk_per_trade_pct", "source", "avg_monthly_return_pct", "cagr_pct",
                             "max_drawdown_pct", "worst_month_pct", "months_ge_5pct", "avg_contracts"]))
    return "".join(out)


def holdout_report(h: dict) -> str:
    s = h["summary"]
    out = ["# Holdout report (MES, unseen data)\n",
           f"Candidate `{h['candidate']}` evaluated on {h['window'][0]} .. {h['window'][1]}. "
           f"Holdout evaluation #{h['holdout_access']['evaluation_number']} "
           f"(registry: results/holdout_registry.json).\n"]
    if h["holdout_access"].get("override_reason"):
        out.append(f"\n> WARNING: holdout re-used with override: {h['holdout_access']['override_reason']}\n")
    if not h["promotable_from_training"]:
        out.append("\n> This candidate did NOT pass the training gates. Shown for information only.\n")
    out.append("\n## Metrics vs baselines\n")
    out.append(_metric_cols({"candidate": s, "buy_hold_1x": h["baselines"]["buy_hold_1x"],
                             "ma_cross_50_200": h["baselines"]["ma_cross"]}))
    out.append("\n## Cost / slippage stress\n")
    out.append(_table([{"scenario": k, **v} for k, v in h["cost_stress"].items()],
                      ["scenario", "net_return_pct", "profit_factor", "expectancy_usd", "max_drawdown_pct"]))
    r = h["random_baseline"]
    out.append(f"\n## Random-entry baseline\nBeats {r['candidate_percentile']}% of {r['n_seeds']} matched random runs "
               f"(random median ${r['random_p50']:,.0f}, candidate ${r['candidate_total_net_pnl']:,.0f}).\n")
    out.append("\n## Yearly returns (%)\n")
    out.append(_table([{"year": y, "return_pct": v} for y, v in h["yearly_returns_pct"].items()], ["year", "return_pct"]))
    if h.get("worst_drawdowns") is not None:
        out.append("\n## Losing periods\n### Worst drawdowns\n")
        out.append(_table(h["worst_drawdowns"], ["depth_pct", "dd_start", "trough", "recovered"]))
        neg = {m: v for m, v in h["monthly_returns_pct"].items() if v < 0}
        out.append("\n### Losing months\n" + (", ".join(f"{m[:7]} {v}%" for m, v in neg.items()) or "none") + "\n")
        out.append(f"\n### Losing trades ({len(h.get('losing_trades', []))})\n")
        out.append(_table(h.get("losing_trades", []), ["entry_date", "exit_date", "contracts", "entry_price",
                                                        "exit_price", "exit_reason", "net_pnl"]))
    out.append("\n## Monthly returns (%)\n")
    out.append(_table([{"month": m, "return_pct": v} for m, v in h["monthly_returns_pct"].items()], ["month", "return_pct"]))
    p = h["promotion"]
    out.append(f"\n## Promotion to paper trading: **{'PASSED' if p['passed'] else 'NOT PASSED'}**\n")
    for f in p["failures"]:
        out.append(f"- {f}\n")
    return "".join(out)


def data_report(q: dict) -> str:
    out = ["# Data quality report\n\nGenerated by `swingtrader data`. Nothing is repaired or synthesised: invalid "
           "bars are dropped and counted; missing sessions stay missing.\n\n## Sources (pinned)\n"]
    out.append(_table([{"key": k, **{kk: v[kk] for kk in ("repo", "revision", "file")},
                        "sha256_ok": (v["sha256"] == v["pinned_sha256"]) if v["pinned_sha256"] else "unpinned"}
                       for k, v in q["sources"].items()], ["key", "repo", "revision", "file", "sha256_ok"]))
    out.append("\n## MES 1-minute integrity\n```json\n" + json.dumps(q["mes_minute"], indent=1) + "\n```\n")
    ms = q["mes_sessions"]
    out.append("\n## MES sessions\n```json\n" + json.dumps(ms, indent=1) + "\n```\n")
    out.append("\n## Independent cross-checks\n")
    out.append(_table([q["crosscheck_mes_vs_es_points"], q["crosscheck_mes_vs_spx_pct"]],
                      ["label", "n_days", "corr", "mean_abs_diff", "p95_abs_diff", "max_abs_diff", "max_abs_diff_date"]))
    ra = q["roll_audit_vs_es"]
    out.append(f"\n## Roll audit (MES back-adjusted vs unadjusted ES)\nOffset MES_adj - ES is constant within a "
               f"contract: median intraday IQR {ra['median_intraday_offset_iqr_points']} pts, "
               f"{ra['pct_days_offset_iqr_le_1tick']:.1f}% of days within 1 tick. Offset changes (rolls in either "
               "series, or ES-file gaps):\n\n")
    out.append(_table(ra["offset_changes"], ["date", "new_offset", "step", "es_instrument"]))
    out.append(f"\nCME-convention roll dates in the same window: {', '.join(ra['calendar_roll_dates_in_window'])}\n")
    out.append("\n## Instrument audit extras\n```json\n" + json.dumps(
        {"mnq": q["mnq_audit"], "es": {k: v for k, v in q["es_audit"].items() if k != "minute_moves_gt_1.5pct_dates"},
         "mes_holes": q["mes_audit"], "spx_sessions": {k: v for k, v in q["spx_sessions"].items()
                                                       if k != "sessions_with_gap_gt_30min"}},
        indent=1, default=str) + "\n```\n")
    return "".join(out)


def write(name: str, text: str) -> None:
    p = resolve("results") / name
    p.write_text(text)

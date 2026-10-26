"""Command-line entry point: `swingtrader <command>` (or `python -m swingtrader`)."""

from __future__ import annotations

import argparse
import json
import logging
import sys

from swingtrader.config import load_config, resolve


def _load_json(name: str) -> dict:
    p = resolve("results") / name
    if not p.exists():
        sys.exit(f"{p} not found - run the previous step first")
    return json.loads(p.read_text())


def cmd_download(cfg, args):
    from swingtrader.data.sources import CORE_SOURCES, download
    for key in CORE_SOURCES:
        p = download(key, resolve(cfg["data"]["raw_dir"]), force=args.force)
        print(f"{key}: {p}")


def cmd_data(cfg, args):
    from swingtrader.data.pipeline import build_all
    from swingtrader.research import report
    q = build_all(cfg)
    report.write("DATA_QUALITY.md", report.data_report(q))
    print("wrote results/data_quality.json and results/DATA_QUALITY.md")


def cmd_select(cfg, args):
    from swingtrader.data.pipeline import load_sessions
    from swingtrader.research import report
    from swingtrader.research.experiments import ExperimentLog
    from swingtrader.research.selection import run_selection
    mes, spx = load_sessions(cfg), load_sessions(cfg, "spx_sessions")
    print("Evaluating candidates on TRAINING windows only ...")
    sel, evals = run_selection(cfg, mes, spx, n_random=args.random_seeds)
    (resolve("results") / "train_selection.json").write_text(json.dumps(sel, indent=1, default=str))
    report.write("TRAIN_REPORT.md", report.train_report(sel))
    top = sel["selected"] or sel["top_ranked_if_none_passed"]
    for e in evals:
        if e["id"] == top["id"]:
            e["trades"].to_csv(resolve("results") / "train_trades_top.csv", index=False)
            for src, r in e["runs"].items():
                r.equity.to_csv(resolve("results") / f"train_equity_top_{src}.csv", header=True)
    ExperimentLog().append("train_selection", {
        "selected": sel["selected"], "top_ranked_if_none_passed": sel["top_ranked_if_none_passed"],
        "candidates": [{k: c[k] for k in ("id", "passed", "trades", "profit_factor", "median_fold_sharpe",
                                          "random_pctile", "failures")} for c in sel["candidates"]]}, cfg)
    print(f"selected: {sel['selected']}\nwrote results/train_selection.json, results/TRAIN_REPORT.md")


def cmd_holdout(cfg, args):
    from swingtrader.data.pipeline import load_sessions
    from swingtrader.research import report
    from swingtrader.research.experiments import ExperimentLog
    from swingtrader.research.holdout import evaluate_holdout
    sel = _load_json("train_selection.json")
    h = evaluate_holdout(cfg, load_sessions(cfg), sel, override_reason=args.override_reason)
    (resolve("results") / "holdout_result.json").write_text(json.dumps(h, indent=1, default=str))
    (resolve("results") / "promotion.json").write_text(json.dumps(
        {"candidate": h["candidate"], "family": h["family"], "params": h["params"], "hash": h["hash"],
         **h["promotion"]}, indent=1))
    report.write("HOLDOUT_REPORT.md", report.holdout_report(h))
    ExperimentLog().append("holdout_evaluation", {"candidate": h["candidate"], "summary": h["summary"],
                                                  "promotion": h["promotion"],
                                                  "evaluation_number": h["holdout_access"]["evaluation_number"]}, cfg)
    print(json.dumps({"candidate": h["candidate"], **{k: h["summary"][k] for k in (
        "net_return_pct", "avg_monthly_return_pct", "max_drawdown_pct", "trades", "profit_factor")},
        "promotion": h["promotion"]}, indent=1))


def cmd_report(cfg, args):
    """Regenerate markdown from saved artefacts (does NOT re-run the holdout)."""
    import pandas as pd

    from swingtrader.backtest.metrics import drawdown_periods
    from swingtrader.research import report
    res = resolve("results")
    if (res / "data_quality.json").exists():
        report.write("DATA_QUALITY.md", report.data_report(_load_json("data_quality.json")))
    if (res / "train_selection.json").exists():
        report.write("TRAIN_REPORT.md", report.train_report(_load_json("train_selection.json")))
    if (res / "holdout_result.json").exists():
        h = _load_json("holdout_result.json")
        eq = pd.read_csv(res / "holdout_equity.csv", index_col=0, parse_dates=True).iloc[:, 0]
        h["worst_drawdowns"] = drawdown_periods(eq, cfg["account"]["starting_equity"], 3)
        tr = pd.read_csv(res / "holdout_trades.csv") if (res / "holdout_trades.csv").exists() else pd.DataFrame()
        h["losing_trades"] = tr[tr["net_pnl"] <= 0][["entry_date", "exit_date", "contracts", "entry_price",
                                                     "exit_price", "exit_reason", "net_pnl"]].to_dict("records") \
            if not tr.empty else []
        report.write("HOLDOUT_REPORT.md", report.holdout_report(h))
    print("reports regenerated in results/")


def cmd_lumibot(cfg, args):
    from swingtrader.lumibot_bridge.run_backtest import run_lumibot_backtest
    res = run_lumibot_backtest(cfg, args.start, args.end, family=args.family, params_json=args.params)
    print(json.dumps(res, indent=1, default=str))


def cmd_agent(cfg, args):
    from swingtrader.agents.adapter import research_cli
    print(json.dumps(research_cli(cfg, args.date, dry_run=args.dry_run), indent=1, default=str))


def _etf_bars(ecfg, source):
    from swingtrader.etf import data as ed
    if source == "spx-proxy":
        return {"SPY": ed.spx_daily_proxy(resolve(ecfg["data"]["raw_dir"]))}
    return ed.load_basket(resolve(ecfg["data"]["full_dir" if source == "full" else "av_dir"]), ecfg["basket"])


def cmd_etf(cfg, args):
    from swingtrader.etf import data as ed
    from swingtrader.etf import report as er
    from swingtrader.etf.research import evaluate_train, final_test, selection_hash
    from swingtrader.research.experiments import ExperimentLog, HoldoutGuard
    ecfg = load_config(resolve("config/etf.yaml"))
    out = resolve("results/etf")
    out.mkdir(parents=True, exist_ok=True)
    if args.stack:
        ecfg["risk"]["stack_symbols"] = True
    tag = args.source + ("" if args.grid == "v1" else f"_{args.grid}") + ("_stack" if args.stack else "")
    if args.step == "fetch":
        print(json.dumps(ed.fetch_basket(resolve(ecfg["data"]["av_dir"]), ecfg["basket"]), indent=1))
        return
    bars = _etf_bars(ecfg, args.source)
    if args.step == "audit":
        a = ed.audit(bars)
        (out / f"audit_{tag}.json").write_text(json.dumps(a, indent=1))
        print(json.dumps(a, indent=1))
    elif args.step == "select":
        sel = evaluate_train(ecfg, bars, seeds=args.random_seeds, grid_name=args.grid)
        sel["hash"] = selection_hash(sel)
        (out / f"train_selection_{tag}.json").write_text(json.dumps(sel, indent=1, default=str))
        er.write(out / f"TRAIN_{tag}.md", er.train_md(sel, tag))
        ExperimentLog("results/etf/experiment_log.jsonl").append(f"etf_train_{tag}", {
            "selected": sel["selected"], "hash": sel["hash"],
            "passed": [c["id"] for c in sel["candidates"] if c["passed"]]}, ecfg)
        print("selected:", sel["selected"])
    elif args.step == "final":
        sel = json.loads((out / f"train_selection_{tag}.json").read_text())
        if not sel["selected"]:
            sys.exit("no candidate passed the training gates - there is nothing to test")
        HoldoutGuard(f"results/etf/holdout_registry_{args.source}.json").authorize(
            "+".join(sel["selected"]), sel["hash"], args.override_reason)
        res, run = final_test(ecfg, bars, sel)
        (out / f"final_{tag}.json").write_text(json.dumps(res, indent=1, default=str))
        run.trades.to_csv(out / f"final_trades_{tag}.csv", index=False)
        run.equity.to_csv(out / f"final_equity_{tag}.csv")
        er.write(out / f"FINAL_{tag}.md", er.final_md(res, sel, tag))
        ExperimentLog("results/etf/experiment_log.jsonl").append(f"etf_final_{tag}", res, ecfg)
        print(json.dumps(res["costs_1x"], indent=1))


def cmd_etf_study(cfg, args):
    from swingtrader.etf.study import run_study
    run_study(wf_seeds=args.wf_seeds, boot=args.boot, skip_wf=args.skip_wf)
    print("wrote results/etf/study/study.json (+ trades/equity/opportunity CSVs)")


def cmd_paper(cfg, args):
    from swingtrader.paper.runner import run_paper
    print(json.dumps(run_paper(cfg, as_of=args.as_of, dry_run=args.dry_run, mode=args.mode, start=args.start),
                     indent=1, default=str))


def main(argv=None):
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(prog="swingtrader")
    ap.add_argument("--config", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("download", help="download pinned data files (sha256-verified)")
    p.add_argument("--force", action="store_true")
    sub.add_parser("data", help="build session bars + data-quality report")
    p = sub.add_parser("select", help="evaluate candidates on TRAINING data and select one")
    p.add_argument("--random-seeds", type=int, default=100)
    p = sub.add_parser("holdout", help="evaluate the selected candidate ONCE on the unseen holdout")
    p.add_argument("--override-reason", default=None)
    p.add_argument("--grid", choices=["v1", "v2", "all"], default="v1")
    p.add_argument("--stack", action="store_true", help="let different strategies hold the same ETF")
    sub.add_parser("report", help="regenerate markdown reports from saved results (no re-runs)")
    p = sub.add_parser("lumibot-backtest", help="re-run a candidate through LumiBot's backtester")
    p.add_argument("--start", default=None)
    p.add_argument("--end", default=None)
    p.add_argument("--family", default=None)
    p.add_argument("--params", default=None, help="JSON params (default: promoted/selected candidate)")
    p = sub.add_parser("agent-research", help="TradingAgents thesis for a date (separate env)")
    p.add_argument("--date", required=True)
    p.add_argument("--dry-run", action="store_true")
    p = sub.add_parser("etf", help="ETF 1-3 day phase: fetch | audit | select | final")
    p.add_argument("step", choices=["fetch", "audit", "select", "final"])
    p.add_argument("--source", choices=["av", "full", "spx-proxy"], default="full")
    p.add_argument("--random-seeds", type=int, default=None)
    p.add_argument("--override-reason", default=None)
    p.add_argument("--grid", choices=["v1", "v2", "all"], default="v1")
    p.add_argument("--stack", action="store_true", help="let different strategies hold the same ETF")
    p = sub.add_parser("etf-study", help="corrected-basis ETF study (windows, ablations, rules, walk-forward)")
    p.add_argument("--wf-seeds", type=int, default=20)
    p.add_argument("--boot", type=int, default=2000)
    p.add_argument("--skip-wf", action="store_true")
    p = sub.add_parser("paper", help="paper-trading step (requires a promoted candidate)")
    p.add_argument("--as-of", default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--mode", choices=["local", "lumibot"], default="local")
    p.add_argument("--start", default=None, help="paper start session (first run only)")
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    {"download": cmd_download, "data": cmd_data, "select": cmd_select, "holdout": cmd_holdout, "report": cmd_report,
     "lumibot-backtest": cmd_lumibot, "agent-research": cmd_agent, "paper": cmd_paper, "etf": cmd_etf, "etf-study": cmd_etf_study}[args.cmd](cfg, args)


if __name__ == "__main__":
    main()

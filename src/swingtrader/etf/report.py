"""Markdown reports for the ETF phase (written from saved JSON, no re-runs)."""

from __future__ import annotations

from pathlib import Path


def write(path: Path, text: str) -> None:
    path.write_text(text)


def _m(m: dict, keys=("trades", "trades_per_week", "win_rate", "profit_factor", "expectancy_r",
                      "avg_sessions", "total_return_pct", "monthly_pct", "max_dd_pct", "sharpe")) -> str:
    return " | ".join(str(m.get(k, "")) for k in keys)


HDR = "| trades | /week | win | PF | exp R | sessions | total % | %/month | max DD % | Sharpe |"


def train_md(sel: dict, tag: str) -> str:
    sp = sel["splits"]
    lines = [f"# ETF phase - training selection ({tag})", "",
             f"Symbols: {', '.join(sel['symbols'])}. Train window {sp['train_start']} -> {sp['train_end']} only.",
             f"Gates at 2x costs: {sel['gates']}.", "",
             f"**Selected:** {', '.join(sel['selected']) or 'nothing passed'}", "",
             "## All candidates (2x costs)", "",
             "| candidate | pass | " + HDR[2:].replace(" |", " |", 99) + " folds+ | rand pct | failures |",
             "|" + "---|" * 14]
    for c in sorted(sel["candidates"], key=lambda c: (not c["passed"], c["family"], -c["train_2x"].get("sharpe", -9))):
        lines.append(f"| {c['id']} | {'yes' if c['passed'] else 'no'} | {_m(c['train_2x'])} | "
                     f"{c['fold_share']:.0%} of {c['n_folds']} | {c['random_pctile'] if c['random_pctile'] is not None else '-'} | "
                     f"{'; '.join(c['failures'])} |")
    if sel["train_portfolio"]:
        tp = sel["train_portfolio"]
        lines += ["", "## Combined train portfolio (shared 1% risk / 4% open-risk cap)", "", HDR, "|" + "---|" * 10,
                  f"| {_m(tp['metrics_1x'])} |  (1x costs)", f"| {_m(tp['metrics_2x'])} |  (2x costs)", "",
                  f"Signals skipped by the risk layer: {tp['skipped']}"]
    return "\n".join(lines) + "\n"


def final_md(res: dict, sel: dict, tag: str) -> str:
    lines = [f"# ETF phase - final test ({tag})", "",
             f"Window {res['window'][0]} -> {res['window'][1]}, run once after training selection "
             f"(registry: results/etf/holdout_registry_{tag}.json).", "",
             f"Portfolio: {', '.join(res['selected'])}", "", "| costs | " + HDR[2:], "|" + "---|" * 11]
    for k in ("costs_1x", "costs_2x", "costs_3x"):
        lines.append(f"| {k[6:]} | {_m(res[k])} |")
    lines += ["", f"Buy & hold over the same window: {res['buy_and_hold_pct']}",
              f"Skipped by risk layer: {res.get('skipped')}",
              f"Weeks with zero setups: {res.get('weeks_with_0_setups_pct')}%, weeks with 1-5 setups: "
              f"{res.get('weeks_in_1_to_5_pct')}%",
              f"Holding sessions histogram: {res.get('sessions_hist')}", "", "## By family", "",
              "| family | trades | P&L $ | win | avg R |", "|---|---|---|---|---|"]
    for f, v in (res.get("by_family") or {}).items():
        lines.append(f"| {f} | {v['trades']} | {v['pnl']:.0f} | {v['win']:.2f} | {v['avg_r']:.2f} |")
    lines += ["", "## By year (entry year)", "", "| year | trades | P&L $ |", "|---|---|---|"]
    for y, v in (res.get("by_year") or {}).items():
        lines.append(f"| {y} | {v['size']:.0f} | {v['sum']:.0f} |")
    return "\n".join(lines) + "\n"

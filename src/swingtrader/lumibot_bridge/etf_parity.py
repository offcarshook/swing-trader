"""Reference engine vs Lumibot parity report for the ETF book (writes results/parity/*).

    .venv/bin/python -m swingtrader lumibot-etf [--start 2019-01-02 --end 2019-12-31] [--full]

Comparison rules:
  * Lumibot reports a fill with the clock of the NEXT iteration; the price is the open of the bar
    for the session in which the order was submitted. Fill timestamps are therefore mapped back to
    the session whose bar priced them (`bar_session`) before matching.
  * Trades are matched on (symbol, entry bar session); quantities, fill prices, exit sessions and
    P&L (before fees) are compared field by field.
  * Positions still open at the end of the window are listed separately (the reference engine
    marks them out at the last close; Lumibot keeps them open).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from swingtrader.etf.engine import RiskCfg, simulate
from swingtrader.etf.strategies import Params


def _prev_session(cal: pd.DatetimeIndex, d) -> pd.Timestamp:
    d = pd.Timestamp(d)
    i = cal.searchsorted(d) - 1
    return cal[max(i, 0)]


def compare(bars: dict[str, pd.DataFrame], params: list[dict], risk: dict, start, end, cost_mult: float,
            log_dir: str) -> dict:
    from swingtrader.lumibot_bridge.etf_backtest import run_etf_lumibot
    lb = run_etf_lumibot(bars, params, risk, start, end, cost_mult=cost_mult, log_dir=log_dir)
    ps = [Params(**{k: v for k, v in d.items() if k in Params.__dataclass_fields__}) for d in params]
    rc = RiskCfg.from_dict({**risk, "cost_mult": cost_mult})
    ref_lb = simulate(bars, ps, start, end, rc, exec_style="lumibot")
    ref_rs = simulate(bars, ps, start, end, rc, exec_style="reference")
    cal = pd.DatetimeIndex(sorted(set().union(*[b.index for b in bars.values()])))
    lt = lb["trades"].copy()
    if len(lt):
        lt["entry_bar"] = [_prev_session(cal, d) for d in lt.entry_date]
        lt["exit_bar"] = [_prev_session(cal, d) for d in lt.exit_date]
    rt = ref_lb.trades.copy()
    rt = rt[rt.reason != "end_of_window"]
    m = rt.merge(lt, left_on=["sym", "entry_date"], right_on=["sym", "entry_bar"], how="outer",
                 suffixes=("_ref", "_lb"), indicator=True)
    both = m[m["_merge"] == "both"]
    rows = []
    for _, x in both.iterrows():
        rows.append({"sym": x.sym, "entry_session": str(x.entry_date_ref.date()),
                     "exit_session_ref": str(pd.Timestamp(x.exit_date_ref).date()),
                     "exit_session_lb": str(pd.Timestamp(x.exit_bar).date()),
                     "shares_ref": int(x.shares_ref), "shares_lb": int(x.shares_lb),
                     "entry_ref": round(float(x.entry_ref), 4), "entry_lb": round(float(x.entry_lb), 4),
                     "exit_ref": round(float(x.exit_ref), 4), "exit_lb": round(float(x.exit_lb), 4),
                     "reason_ref": x.reason_ref, "reason_lb": x.reason_lb,
                     "pnl_ex_fees_ref": round(float(x.dir_ref * (x.exit_ref - x.entry_ref) * x.shares_ref), 2),
                     "pnl_ex_fees_lb": round(float(x.pnl_ex_costs), 2),
                     "dividends_ref": round(float(x.dividends_ref), 2),
                     "dividends_lb": round(float(x.dividends_lb), 2) if "dividends_lb" in x else 0.0})
    cmp = pd.DataFrame(rows)
    out = {
        "window": [str(start), str(end)], "cost_mult": cost_mult, "lumibot_version": lb["lumibot_version"],
        "trades_reference_lumibot_timing": int(len(rt)), "trades_lumibot": int(len(lt)),
        "matched": int(len(cmp)),
        "only_reference": m[m["_merge"] == "left_only"][["sym", "entry_date_ref"]].astype(str).values.tolist(),
        "only_lumibot": m[m["_merge"] == "right_only"][["sym", "entry_bar"]].astype(str).values.tolist(),
        "open_at_end_lumibot": list(lb["book_open"]),
    }
    if len(cmp):
        out.update({
            "same_shares": int((cmp.shares_ref == cmp.shares_lb).sum()),
            "same_entry_price": int((np.isclose(cmp.entry_ref, cmp.entry_lb, atol=1e-6)).sum()),
            "same_exit_session": int((cmp.exit_session_ref == cmp.exit_session_lb).sum()),
            "same_exit_price": int((np.isclose(cmp.exit_ref, cmp.exit_lb, atol=1e-6)).sum()),
            "pnl_ex_fees_ref_total": round(float(cmp.pnl_ex_fees_ref.sum()), 2),
            "pnl_ex_fees_lb_total": round(float(cmp.pnl_ex_fees_lb.sum()), 2),
            "dividends_ref_total": round(float(cmp.dividends_ref.sum()), 2),
            "dividend_entitlements_lb_ledger_total": round(float(cmp.dividends_lb.sum()), 2),
        })
    eq = lb["equity"]
    out["final_value_lumibot"] = round(lb["final_value"], 2) if lb["final_value"] else None
    out["final_equity_reference_lumibot_timing"] = round(float(ref_lb.equity.iloc[-1]), 2)
    out["final_equity_reference_own_timing"] = round(float(ref_rs.equity.iloc[-1]), 2)
    out["trades_reference_own_timing"] = int(len(ref_rs.trades))
    if eq is not None:
        j = pd.concat({"lumibot": eq, "ref": ref_lb.equity}, axis=1).dropna()
        out["equity_days_compared"] = int(len(j))
        out["equity_daily_change_corr"] = round(float(j.diff().corr().iloc[0, 1]), 4) if len(j) > 2 else None
        out["equity_daily_change_corr_lb_shift1"] = round(float(
            j["lumibot"].diff().shift(-1).corr(j["ref"].diff())), 4) if len(j) > 2 else None
    return out, cmp, lb


def run_parity(bars, params, risk, out_dir: Path, fixture=("2019-01-02", "2019-12-31"), full=None) -> dict:
    from swingtrader.lumibot_bridge.etf_strategy import lumibot_supported
    out_dir.mkdir(parents=True, exist_ok=True)
    params, excluded = lumibot_supported(params)
    rep = {"book_members_run": [d["id"] for d in params], "excluded_open_decided_or_stop_entry": excluded,
           "note": "excluded members need an intraday clock at the open (not available in Lumibot daily "
                   "backtests); the reference engine runs the full book"}
    zero = {**risk, "commission_per_share": 0.0, "slip_bps": 0.0, "slip_bps_wide": 0.0, "stop_extra_bps": 0.0,
            "borrow_bps_annual": 0.0}
    for name, rk, w in (("fixture_zero_cost", zero, fixture), ("fixture_costs_1x", risk, fixture)):
        r, cmp, lb = compare(bars, params, rk, w[0], w[1], 1.0, str(out_dir / "lumibot_logs"))
        rep[name] = r
        cmp.to_csv(out_dir / f"{name}_trades.csv", index=False)
        lb["ledger"].to_csv(out_dir / f"{name}_lumibot_ledger.csv", index=False)
    if full:
        r, cmp, lb = compare(bars, params, risk, full[0], full[1], 1.0, str(out_dir / "lumibot_logs"))
        rep["production_window_costs_1x"] = r
        cmp.to_csv(out_dir / "production_window_trades.csv", index=False)
        lb["ledger"].to_csv(out_dir / "production_window_lumibot_ledger.csv", index=False)
    (out_dir / "parity.json").write_text(json.dumps(rep, indent=1, default=str))
    return rep

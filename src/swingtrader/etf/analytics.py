"""Full performance report for one simulated run (reference engine `Result`).

All figures are net of every modelled cost unless labelled gross. The monthly equivalent is
geometric over the exact simulated calendar window, never cumulative return / months.
Small samples are labelled: fewer than `MIN_RELIABLE_TRADES` trades -> "unreliable".
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from swingtrader.etf.engine import Result

MIN_RELIABLE_TRADES = 100


def _dd_duration_days(eq: pd.Series) -> int:
    under = eq < eq.cummax()
    longest, start = 0, None
    for d, u in under.items():
        if u and start is None:
            start = d
        elif not u and start is not None:
            longest = max(longest, (d - start).days)
            start = None
    if start is not None:
        longest = max(longest, (eq.index[-1] - start).days)
    return longest


def report(res: Result, start_equity: float = 100_000.0) -> dict:
    t, eq = res.trades, res.equity
    out: dict = {"window": [str(eq.index[0].date()), str(eq.index[-1].date())] if len(eq) else None,
                 "sessions": int(len(eq))}
    if not len(eq):
        return out
    days = max((eq.index[-1] - eq.index[0]).days, 1)
    years = days / 365.25
    total = eq.iloc[-1] / start_equity - 1
    rets = eq.pct_change().fillna(eq.iloc[0] / start_equity - 1)
    me = eq.resample("ME").last()
    mret = pd.concat([pd.Series([start_equity]), me]).pct_change().dropna().iloc[: len(me)]
    mret.index = me.index
    downside = rets[rets < 0]
    out.update({
        "total_return_pct": round(100 * total, 2),
        "cagr_pct": round(100 * ((1 + total) ** (1 / years) - 1), 2) if total > -1 else None,
        "geometric_monthly_pct": round(100 * ((1 + total) ** (1 / (years * 12)) - 1), 3) if total > -1 else None,
        "months": int(len(mret)), "positive_months_pct": round(100 * float((mret > 0).mean()), 1),
        "best_month_pct": round(100 * float(mret.max()), 2), "worst_month_pct": round(100 * float(mret.min()), 2),
        "monthly_returns_pct": {str(k.date())[:7]: round(100 * float(v), 3) for k, v in mret.items()},
        "max_dd_pct": round(100 * float((eq / eq.cummax() - 1).min()), 2),
        "max_dd_duration_days": _dd_duration_days(eq),
        "sharpe": round(float(rets.mean() / rets.std() * np.sqrt(252)), 2) if rets.std() > 0 else 0.0,
        "sortino": round(float(rets.mean() / downside.std() * np.sqrt(252)), 2) if len(downside) > 1 else None,
    })
    if res.equity_worst is not None:
        out["max_dd_intraday_worst_pct"] = round(100 * float((res.equity_worst / eq.cummax() - 1).min()), 2)
    if res.exposure is not None and len(res.exposure):
        ex = res.exposure
        out["time_in_market_pct"] = round(100 * float((ex.positions > 0).mean()), 1)
        out["avg_gross_exposure_pct"] = round(100 * float((ex.gross / eq).mean()), 1)
        out["avg_net_exposure_pct"] = round(100 * float((ex.net / eq).mean()), 1)
        out["max_gross_exposure_pct"] = round(100 * float((ex.gross / eq).max()), 1)
        out["avg_open_risk_pct"] = round(100 * float((ex.open_risk / eq).mean()), 2)
    weeks = pd.period_range(eq.index[0], eq.index[-1], freq="W")
    if not len(t):
        out.update({"trades": 0, "zero_trade_weeks_pct": 100.0, "reliability": "no trades"})
        return out
    wk = t.groupby(t.entry_date.dt.to_period("W")).size().reindex(weeks, fill_value=0)
    win, loss = t.pnl[t.pnl > 0], t.pnl[t.pnl <= 0]
    net = float(t.pnl.sum())
    top5 = float(t.pnl.nlargest(5).sum())
    out.update({
        "trades": int(len(t)), "reliability": "ok" if len(t) >= MIN_RELIABLE_TRADES else "unreliable (small sample)",
        "trades_per_week": round(len(t) / len(weeks), 2), "trades_per_month": round(len(t) / max(len(mret), 1), 2),
        "zero_trade_weeks_pct": round(100 * float((wk == 0).mean()), 1),
        "weeks_with_1_to_5_trades_pct": round(100 * float(((wk >= 1) & (wk <= 5)).mean()), 1),
        "win_rate": round(float((t.pnl > 0).mean()), 3),
        "avg_winner_usd": round(float(win.mean()), 2) if len(win) else 0.0,
        "avg_loser_usd": round(float(loss.mean()), 2) if len(loss) else 0.0,
        "profit_factor": round(float(win.sum() / -loss.sum()), 3) if loss.sum() < 0 else None,
        "expectancy_usd": round(float(t.pnl.mean()), 2), "expectancy_r": round(float(t.r.mean()), 3),
        "net_pnl_usd": round(net, 2),
        "gross_pnl_usd": round(float(t.gross_pnl.sum()), 2) if "gross_pnl" in t else None,
        "commission_usd": round(float(t.commission.sum()), 2) if "commission" in t else None,
        "slippage_usd": round(float(t.slippage_usd.sum()), 2) if "slippage_usd" in t else None,
        "dividends_usd": round(float(t.dividends.sum()), 2) if "dividends" in t else None,
        "borrow_usd": round(float(t.borrow.sum()), 2) if "borrow" in t else None,
        "top5_trades_share_of_net_pct": round(100 * top5 / net, 1) if net > 0 else None,
        "holding_sessions_median": float(t.sessions.median()),
        "holding_sessions_hist": {int(k): int(v) for k, v in t.sessions.value_counts().sort_index().items()},
        "exit_reasons": {str(k): int(v) for k, v in t.reason.value_counts().items()},
    })
    for key, col in (("by_year", t.entry_date.dt.year), ("by_symbol", t.sym), ("by_family", t.pid),
                     ("by_direction", t.dir.map({1: "long", -1: "short"})), ("by_regime", t.get("regime"))):
        if col is None:
            continue
        g = t.groupby(col)
        out[key] = {str(k): {"trades": int(len(v)), "pnl_usd": round(float(v.pnl.sum()), 0),
                             "win_rate": round(float((v.pnl > 0).mean()), 3), "avg_r": round(float(v.r.mean()), 3)}
                    for k, v in g}
    if res.signals is not None and len(res.signals):
        s = res.signals
        out["opportunities"] = {"detected": int(len(s)), "accepted": int((s.status == "accepted").sum()),
                                "rejected_by_reason": {str(k): int(v) for k, v in
                                                       s[s.status != "accepted"].status.value_counts().items()},
                                "same_symbol_same_day_duplicates": int(s.duplicated(["date", "sym"]).sum())}
    return out

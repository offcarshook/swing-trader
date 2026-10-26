"""Performance metrics computed from a session equity curve and a trade list."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


def monthly_returns(equity: pd.Series, start_equity: float) -> pd.Series:
    eq = pd.concat([pd.Series([start_equity], index=[equity.index[0] - pd.Timedelta(days=1)]), equity])
    m = eq.resample("ME").last().dropna()
    return m.pct_change().dropna() * 100


def yearly_returns(equity: pd.Series, start_equity: float) -> pd.Series:
    eq = pd.concat([pd.Series([start_equity], index=[equity.index[0] - pd.Timedelta(days=1)]), equity])
    y = eq.resample("YE").last().dropna()
    out = y.pct_change().dropna() * 100
    out.index = out.index.year
    return out


def drawdown(equity: pd.Series) -> pd.Series:
    peak = equity.cummax()
    return (equity / peak - 1) * 100


def max_dd_duration(equity: pd.Series) -> int:
    """Longest stretch (sessions) spent below a prior equity peak."""
    under = equity < equity.cummax()
    best = run = 0
    for u in under:
        run = run + 1 if u else 0
        best = max(best, run)
    return best


def summarize(equity: pd.Series, trades: pd.DataFrame, start_equity: float,
              in_market: pd.Series | None = None) -> dict:
    if equity.empty:
        return {}
    end_eq = float(equity.iloc[-1])
    years = max((equity.index[-1] - equity.index[0]).days / 365.25, 1e-9)
    daily = equity.pct_change().dropna()
    if len(equity):
        daily = pd.concat([pd.Series([equity.iloc[0] / start_equity - 1]), daily])
    mret = monthly_returns(equity, start_equity)
    dd = drawdown(pd.concat([pd.Series([start_equity]), equity.reset_index(drop=True)]))
    sd = daily.std()
    out = {
        "start": str(equity.index[0].date()),
        "end": str(equity.index[-1].date()),
        "years": round(years, 2),
        "start_equity": start_equity,
        "end_equity": round(end_eq, 2),
        "net_return_pct": round((end_eq / start_equity - 1) * 100, 2),
        "cagr_pct": round(((end_eq / start_equity) ** (1 / years) - 1) * 100, 2) if end_eq > 0 else -100.0,
        "avg_monthly_return_pct": round(float(mret.mean()), 3) if len(mret) else 0.0,
        "median_monthly_return_pct": round(float(mret.median()), 3) if len(mret) else 0.0,
        "pct_positive_months": round(float((mret > 0).mean() * 100), 1) if len(mret) else 0.0,
        "best_month_pct": round(float(mret.max()), 2) if len(mret) else 0.0,
        "worst_month_pct": round(float(mret.min()), 2) if len(mret) else 0.0,
        "months_ge_5pct": int((mret >= 5).sum()),
        "max_drawdown_pct": round(float(-dd.min()), 2),
        "max_dd_duration_sessions": max_dd_duration(equity),
        "sharpe": round(float(daily.mean() / sd * math.sqrt(252)), 2) if sd > 0 else 0.0,
        "sortino": _sortino(daily),
        "exposure_pct": round(float(in_market.mean() * 100), 1) if in_market is not None and len(in_market) else None,
    }
    out.update(trade_stats(trades))
    return out


def _sortino(daily: pd.Series) -> float:
    neg = daily[daily < 0]
    dsd = math.sqrt((neg ** 2).sum() / max(len(daily), 1))
    return round(float(daily.mean() / dsd * math.sqrt(252)), 2) if dsd > 0 else 0.0


def trade_stats(trades: pd.DataFrame) -> dict:
    if trades is None or trades.empty:
        return {"trades": 0, "win_rate_pct": 0.0, "profit_factor": 0.0, "expectancy_usd": 0.0,
                "expectancy_r": 0.0, "avg_sessions_held": 0.0, "avg_calendar_days_held": 0.0,
                "total_fees_usd": 0.0, "total_roll_costs_usd": 0.0, "longest_losing_streak": 0}
    pnl = trades["net_pnl"]
    gw, gl = pnl[pnl > 0].sum(), -pnl[pnl < 0].sum()
    streak = best = 0
    for p in pnl:
        streak = streak + 1 if p <= 0 else 0
        best = max(best, streak)
    return {
        "trades": int(len(trades)),
        "long_trades": int((trades["side"] > 0).sum()),
        "short_trades": int((trades["side"] < 0).sum()),
        "win_rate_pct": round(float((pnl > 0).mean() * 100), 1),
        "profit_factor": round(float(gw / gl), 3) if gl > 0 else float("inf") if gw > 0 else 0.0,
        "expectancy_usd": round(float(pnl.mean()), 2),
        "expectancy_r": round(float(trades["r_multiple"].mean()), 3),
        "avg_win_usd": round(float(pnl[pnl > 0].mean()), 2) if (pnl > 0).any() else 0.0,
        "avg_loss_usd": round(float(pnl[pnl <= 0].mean()), 2) if (pnl <= 0).any() else 0.0,
        "avg_sessions_held": round(float(trades["sessions_held"].mean()), 2),
        "avg_calendar_days_held": round(float(trades["calendar_days"].mean()), 2),
        "avg_contracts": round(float(trades["contracts"].mean()), 2),
        "total_fees_usd": round(float(trades["fees"].sum()), 2),
        "total_roll_costs_usd": round(float(trades["roll_costs"].sum()), 2),
        "longest_losing_streak": int(best),
        "exit_reasons": trades["exit_reason"].value_counts().to_dict(),
    }


def by_year_trades(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    t = trades.copy()
    t["year"] = pd.to_datetime(t["exit_date"]).dt.year
    g = t.groupby("year")["net_pnl"]
    return pd.DataFrame({"trades": g.size(), "net_pnl": g.sum().round(2),
                         "win_rate": (g.apply(lambda x: (x > 0).mean() * 100)).round(1)})


def fold_metrics(equity: pd.Series, trades: pd.DataFrame, folds: list[tuple[str, str]]) -> list[dict]:
    """Per-period metrics of ONE continuous run (used for walk-forward stability)."""
    out = []
    for a, b in folds:
        e = equity.loc[a:b]
        if e.empty:
            out.append({"fold": f"{a}..{b}", "net_pnl": 0.0, "sharpe": 0.0, "trades": 0})
            continue
        prev = equity.loc[:pd.Timestamp(a) - pd.Timedelta(days=1)]
        base = float(prev.iloc[-1]) if len(prev) else float(e.iloc[0])
        d = pd.concat([pd.Series([base]), e.reset_index(drop=True)]).pct_change().dropna()
        t = trades[(pd.to_datetime(trades["exit_date"]) >= a) & (pd.to_datetime(trades["exit_date"]) <= b)] \
            if not trades.empty else trades
        out.append({
            "fold": f"{a}..{b}",
            "net_pnl": round(float(e.iloc[-1] - base), 2),
            "return_pct": round(float((e.iloc[-1] / base - 1) * 100), 2),
            "sharpe": round(float(d.mean() / d.std() * np.sqrt(252)), 2) if d.std() > 0 else 0.0,
            "trades": int(len(t)),
        })
    return out

"""Daily-bar portfolio simulator for 1-3 day ETF trades.

Rules (conservative where the daily bar is ambiguous):
  * size: shares = floor(risk_pct * equity_prev_close / stop_distance); a trade is skipped
    when it would push total open initial risk above `max_open_risk_pct`, gross notional
    above `max_gross` x equity, or open a second position in the same ETF;
  * a stop gapped through fills at the open (plus stop slippage), otherwise at the stop;
    when stop and target are both inside a bar the stop wins;
  * stop-entry (breakout) trades cannot take profit on the entry bar but can be stopped;
  * SMA exits are decided at the close and filled at the next open; the time stop is a
    market-on-close order on session `max_hold` after entry.
Costs: per-share commission plus slippage in basis points, scaled by `cost_mult`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from swingtrader.etf.strategies import Params, features, signals

# extra slippage for the thinner / more volatile members of the basket
WIDE = {"SLV", "USO", "XLE", "SMH", "EEM"}


@dataclass
class RiskCfg:
    equity: float = 100_000.0
    risk_pct: float = 1.0
    max_open_risk_pct: float = 4.0
    max_gross: float = 2.0
    commission_per_share: float = 0.005
    slip_bps: float = 1.0
    slip_bps_wide: float = 3.0
    stop_extra_bps: float = 2.0
    cost_mult: float = 1.0
    stack_symbols: bool = False      # True: different strategies may hold the same ETF at once


@dataclass
class Result:
    trades: pd.DataFrame
    equity: pd.Series
    skipped: dict = field(default_factory=dict)


def _align(bars: dict[str, pd.DataFrame]) -> tuple[pd.DatetimeIndex, dict]:
    cal = pd.DatetimeIndex(sorted(set().union(*[b.index for b in bars.values()])))
    return cal, {s: b.reindex(cal) for s, b in bars.items()}


def build_signals(bars: dict[str, pd.DataFrame], params: list[Params], feats: dict | None = None) -> pd.DataFrame:
    rows = []
    for rank, p in enumerate(params):
        for s, df in bars.items():
            f = feats[s] if feats else features(df)
            sg = signals(df, p, f)
            if not len(sg):
                continue
            sg["sym"], sg["rank"], sg["pid"] = s, rank, p.id
            sg["entry_date"] = df.index[sg["entry_i"].to_numpy()]
            rows.append(sg)
    if not rows:
        return pd.DataFrame(columns=["sym", "rank", "pid", "entry_date", "dir", "stop_dist", "entry_level"])
    return pd.concat(rows, ignore_index=True)


def simulate(bars: dict[str, pd.DataFrame], params: list[Params], start, end, risk: RiskCfg | None = None,
             sigs: pd.DataFrame | None = None, feats: dict | None = None) -> Result:
    risk = risk or RiskCfg()
    pmap = {p.id: p for p in params}
    sigs = build_signals(bars, params, feats) if sigs is None else sigs
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    sigs = sigs[(sigs["entry_date"] >= start) & (sigs["entry_date"] <= end)]
    sigs = sigs.sort_values(["entry_date", "rank", "sym"], kind="stable")
    by_day = {d: g for d, g in sigs.groupby("entry_date")}
    cal, al = _align(bars)
    cal = cal[(cal >= start) & (cal <= end)]
    arr = {s: {c: b[c].reindex(cal).to_numpy() for c in ("open", "high", "low", "close")} for s, b in al.items()}
    smas = {}
    for p in params:
        if p.exit_sma:
            for s, b in bars.items():
                smas[(s, p.exit_sma)] = b["close"].rolling(p.exit_sma).mean().reindex(cal).to_numpy()

    def slip(sym):
        return (risk.slip_bps_wide if sym in WIDE else risk.slip_bps) * risk.cost_mult / 1e4

    eq_prev, realized = risk.equity, 0.0
    open_pos: list[dict] = []
    trades, curve = [], np.empty(len(cal))
    skipped = {"open_risk_cap": 0, "same_symbol": 0, "gross_cap": 0, "not_triggered": 0, "zero_size": 0}

    def close_pos(pos, k, px, reason):
        nonlocal realized
        comm = risk.commission_per_share * risk.cost_mult * pos["shares"]
        pnl = pos["dir"] * (px - pos["entry"]) * pos["shares"] - comm - pos["entry_comm"]
        realized += pnl
        trades.append({"sym": pos["sym"], "pid": pos["pid"], "family": pmap[pos["pid"]].family, "dir": pos["dir"],
                       "entry_date": cal[pos["k"]], "exit_date": cal[k], "entry": pos["entry"], "exit": px,
                       "stop": pos["stop"], "shares": pos["shares"], "risk_usd": pos["risk_usd"],
                       "pnl": pnl, "r": pnl / pos["risk_usd"], "sessions": pos["held"], "reason": reason})

    for k, day in enumerate(cal):
        # ---- manage open positions on today's bar
        still = []
        for pos in open_pos:
            a = arr[pos["sym"]]
            o, h, l, c = a["open"][k], a["high"][k], a["low"][k], a["close"][k]
            if np.isnan(o):
                still.append(pos)
                continue
            pos["held"] += 1
            d, st, tg, s_ = pos["dir"], pos["stop"], pos["target"], slip(pos["sym"])
            if pos.get("exit_next_open"):
                close_pos(pos, k, o * (1 - d * s_), "sma_exit"); continue
            if d * (o - st) <= 0:
                close_pos(pos, k, o * (1 - d * (s_ + risk.stop_extra_bps * risk.cost_mult / 1e4)), "stop_gap"); continue
            if tg is not None and d * (o - tg) >= 0:
                close_pos(pos, k, o * (1 - d * s_), "target_gap"); continue
            if (l <= st) if d > 0 else (h >= st):
                close_pos(pos, k, st * (1 - d * (s_ + risk.stop_extra_bps * risk.cost_mult / 1e4)), "stop"); continue
            if tg is not None and ((h >= tg) if d > 0 else (l <= tg)):
                close_pos(pos, k, tg, "target"); continue
            if pos["held"] >= pos["max_hold"]:
                close_pos(pos, k, c * (1 - d * s_), "time"); continue
            if pos["exit_sma"] is not None:
                m = smas[(pos["sym"], pos["exit_sma"])][k]
                if not np.isnan(m) and d * (c - m) > 0:
                    pos["exit_next_open"] = True
            still.append(pos)
        open_pos = still

        # ---- new entries
        for _, sg in (by_day[day].iterrows() if day in by_day else []):
            sym, d = sg["sym"], int(sg["dir"])
            a = arr[sym]
            o, h, l, c = a["open"][k], a["high"][k], a["low"][k], a["close"][k]
            if np.isnan(o):
                continue
            if any(p_["sym"] == sym and (not risk.stack_symbols or p_["pid"] == sg["pid"]) for p_ in open_pos):
                skipped["same_symbol"] += 1; continue
            s_ = slip(sym)
            stop_entry = not np.isnan(sg["entry_level"])
            if stop_entry:
                lvl = sg["entry_level"]
                if (h < lvl) if d > 0 else (l > lvl):
                    skipped["not_triggered"] += 1; continue
                fill = (max(o, lvl) if d > 0 else min(o, lvl)) * (1 + d * s_)
            else:
                fill = o * (1 + d * s_)
            dist = float(sg["stop_dist"])
            shares = int(risk.risk_pct / 100 * eq_prev // dist) if dist > 0 else 0
            if shares <= 0:
                skipped["zero_size"] += 1; continue
            risk_usd = shares * dist
            if sum(p_["risk_usd"] for p_ in open_pos) + risk_usd > risk.max_open_risk_pct / 100 * eq_prev + 1e-9:
                skipped["open_risk_cap"] += 1; continue
            if sum(p_["shares"] * p_["entry"] for p_ in open_pos) + shares * fill > risk.max_gross * eq_prev:
                skipped["gross_cap"] += 1; continue
            p = pmap[sg["pid"]]
            pos = {"sym": sym, "pid": p.id, "dir": d, "entry": fill, "shares": shares, "k": k, "held": 0,
                   "stop": fill - d * dist, "risk_usd": risk_usd, "max_hold": p.max_hold, "exit_sma": p.exit_sma,
                   "target": None if p.target_r is None else fill + d * p.target_r * dist,
                   "entry_comm": risk.commission_per_share * risk.cost_mult * shares}
            # same-bar handling: stop can hit; target only for market-at-open entries
            st, tg = pos["stop"], pos["target"]
            if (l <= st) if d > 0 else (h >= st):
                close_pos(pos, k, st * (1 - d * (s_ + risk.stop_extra_bps * risk.cost_mult / 1e4)), "stop"); continue
            if tg is not None and not stop_entry and ((h >= tg) if d > 0 else (l <= tg)):
                close_pos(pos, k, tg, "target"); continue
            if pos["exit_sma"] is not None:
                m = smas[(sym, pos["exit_sma"])][k]
                if not np.isnan(m) and d * (c - m) > 0:
                    pos["exit_next_open"] = True
            open_pos.append(pos)

        unreal = 0.0
        for p_ in open_pos:
            c = arr[p_["sym"]]["close"][k]
            if not np.isnan(c):
                p_["last"] = c
            unreal += p_["dir"] * (p_.get("last", p_["entry"]) - p_["entry"]) * p_["shares"] - p_["entry_comm"]
        eq_prev = risk.equity + realized + unreal
        curve[k] = eq_prev

    for p_ in open_pos:  # end of window: mark out at the last close
        close_pos(p_, len(cal) - 1, p_.get("last", p_["entry"]), "end_of_data")
    return Result(pd.DataFrame(trades), pd.Series(curve, index=cal, name="equity"), skipped)


def metrics(res: Result, start_equity: float = 100_000.0) -> dict:
    t, eq = res.trades, res.equity
    weeks = max(len(eq) / 5.0, 1e-9)
    if not len(t):
        return {"trades": 0, "trades_per_week": 0.0, "total_return_pct": 0.0, "max_dd_pct": 0.0}
    gp, gl = t.loc[t.pnl > 0, "pnl"].sum(), -t.loc[t.pnl < 0, "pnl"].sum()
    rets = eq.pct_change().dropna()
    years = len(eq) / 252
    dd = (eq / eq.cummax() - 1).min()
    total = eq.iloc[-1] / start_equity - 1
    return {
        "trades": int(len(t)), "trades_per_week": round(len(t) / weeks, 2),
        "win_rate": round(float((t.pnl > 0).mean()), 3),
        "profit_factor": round(float(gp / gl), 2) if gl > 0 else float("inf"),
        "expectancy_r": round(float(t.r.mean()), 3), "avg_sessions": round(float(t.sessions.mean()), 2),
        "total_return_pct": round(100 * total, 2),
        "cagr_pct": round(100 * ((1 + total) ** (1 / years) - 1), 2) if years > 0 and total > -1 else None,
        "monthly_pct": round(100 * ((1 + total) ** (1 / (years * 12)) - 1), 3) if years > 0 and total > -1 else None,
        "max_dd_pct": round(100 * float(dd), 2),
        "sharpe": round(float(rets.mean() / rets.std() * np.sqrt(252)), 2) if rets.std() > 0 else 0.0,
    }


def yearly(res: Result) -> pd.Series:
    eq = res.equity
    return eq.groupby(eq.index.year).last().pct_change().fillna(eq.groupby(eq.index.year).last().iloc[0] / eq.iloc[0] - 1) \
        if len(eq) else pd.Series(dtype=float)

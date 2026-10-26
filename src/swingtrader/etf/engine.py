"""Daily-bar portfolio simulator for 1-3 day ETF trades (the reference engine).

Price basis (see etf/data.py): indicators and signals are computed on the total-return
adjusted view (`signal_view`); every fill, stop, target and mark uses EXECUTABLE raw prices.
Cash dividends are credited to longs (debited to shorts) on the ex-date; shorts also pay a
borrow fee per session held.

Rules (conservative where the daily bar is ambiguous):
  * size: shares = floor(risk_pct * equity_prev_close / stop_distance) x entry multiplier
    (an optional research overlay may only scale this DOWN, clamped to [0, 1]);
  * a trade is skipped when it would push total open initial risk above `max_open_risk_pct`,
    risk in its correlation cluster above `max_cluster_risk_pct`, gross notional above
    `max_gross` x equity, |net notional| above `max_net_exposure` x equity, or open a second
    position in the same ETF (unless `stack_symbols`, then only the same strategy is blocked);
  * a stop gapped through fills at the open (plus stop slippage), otherwise at the stop;
    when stop and target are both inside a bar the stop wins;
  * stop-entry (breakout) trades cannot take profit on the entry bar but can be stopped;
  * SMA exits are decided at the close and filled at the next open; the time stop is a
    market-on-close order on session `max_hold` after entry;
  * a position whose instrument's data ends is closed at that instrument's last close;
  * lockouts: a close-to-close equity loss >= `daily_loss_lockout_pct` blocks entries on the
    next session; a drawdown from the equity peak >= `max_dd_lockout_pct` flattens at the next
    open and halts the run (a new simulation session is required); `kill_switch_from` blocks
    all new entries from that date.
Costs: per-share commission plus slippage in basis points, scaled by `cost_mult`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, fields

import numpy as np
import pandas as pd

from swingtrader.etf.data import signal_view
from swingtrader.etf.risk import PortfolioRiskGate
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
    borrow_bps_annual: float = 30.0  # general-collateral borrow for liquid ETFs (shorts only)
    max_net_exposure: float | None = None
    clusters: dict | None = None     # symbol -> cluster name (e.g. us_equity, rates, metals)
    max_cluster_risk_pct: float | None = None
    daily_loss_lockout_pct: float | None = None
    max_dd_lockout_pct: float | None = None
    kill_switch_from: str | None = None
    entry_delay: int = 0             # execution-delay stress: market entries fill N sessions later
    miss_fill_prob: float = 0.0      # missed-fill stress (seeded)
    seed: int = 7

    @classmethod
    def from_dict(cls, d: dict) -> RiskCfg:
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in names})


@dataclass
class Result:
    trades: pd.DataFrame
    equity: pd.Series                       # close-to-close marked equity
    skipped: dict = field(default_factory=dict)
    equity_worst: pd.Series | None = None   # adverse intraday equity (bar lows for longs / highs for shorts)
    equity_best: pd.Series | None = None    # favourable intraday equity (bar highs for longs / lows for shorts)
    signals: pd.DataFrame | None = None     # every opportunity with its accept / reject reason
    exposure: pd.DataFrame | None = None    # per-session gross / net notional and open risk
    halted_on: str | None = None


def _align(bars: dict[str, pd.DataFrame]) -> tuple[pd.DatetimeIndex, dict]:
    cal = pd.DatetimeIndex(sorted(set().union(*[b.index for b in bars.values()])))
    return cal, {s: b.reindex(cal) for s, b in bars.items()}


def build_signals(bars: dict[str, pd.DataFrame], params: list[Params], feats: dict | None = None,
                  entry_delay: int = 0) -> pd.DataFrame:
    """Signals from the adjusted view, converted to executable (raw) price units."""
    rows = []
    for rank, p in enumerate(params):
        for s, df in bars.items():
            sv = signal_view(df)
            f = feats[s] if feats else features(sv)
            sg = signals(sv, p, f)
            if not len(sg):
                continue
            fac = df["adj_factor"].to_numpy() if "adj_factor" in df else np.ones(len(df))
            k = fac[sg["sig_i"].to_numpy()]
            sg["stop_dist"] = sg["stop_dist"] / k        # adjusted distance -> raw distance
            sg["entry_level"] = sg["entry_level"] / k    # adjusted high/low -> raw high/low of that bar
            if entry_delay:
                mkt = sg["entry_level"].isna()
                sg.loc[mkt, "entry_i"] = sg.loc[mkt, "entry_i"] + entry_delay
                sg = sg[sg["entry_i"] < len(df)]
            up = f["uptrend"].to_numpy()[sg["sig_i"].to_numpy()]
            dn = f["downtrend"].to_numpy()[sg["sig_i"].to_numpy()]
            sg["regime"] = np.where(up, "up", np.where(dn, "down", "neutral"))
            sg["sym"], sg["rank"], sg["pid"] = s, rank, p.id
            sg["entry_date"] = df.index[sg["entry_i"].to_numpy()]
            sg["signal_date"] = df.index[sg["sig_i"].to_numpy()]
            rows.append(sg)
    if not rows:
        return pd.DataFrame(columns=["sym", "rank", "pid", "entry_date", "signal_date", "dir", "stop_dist",
                                     "entry_level", "regime"])
    return pd.concat(rows, ignore_index=True)


EntryFilter = Callable[[dict], tuple[float, str]]


def simulate(bars: dict[str, pd.DataFrame], params: list[Params], start, end, risk: RiskCfg | None = None,
             sigs: pd.DataFrame | None = None, feats: dict | None = None,
             entry_filter: EntryFilter | None = None, exec_style: str = "reference") -> Result:
    """exec_style="lumibot" reproduces the Lumibot adapter's order timing for parity checks:
    protective stop/target orders start acting on the session AFTER the entry, and the time stop
    is a market order at the open after session `max_hold` (Lumibot has no market-on-close)."""
    if exec_style not in ("reference", "lumibot"):
        raise ValueError(exec_style)
    lb = exec_style == "lumibot"
    risk = risk or RiskCfg()
    pmap = {p.id: p for p in params}
    sigs = build_signals(bars, params, feats, risk.entry_delay) if sigs is None else sigs
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    sigs = sigs[(sigs["entry_date"] >= start) & (sigs["entry_date"] <= end)]
    sigs = sigs.sort_values(["entry_date", "rank", "sym"], kind="stable")
    by_day = {d: g for d, g in sigs.groupby("entry_date")}
    cal, al = _align(bars)
    cal = cal[(cal >= start) & (cal <= end)]
    cols = ("open", "high", "low", "close", "dividend", "adj_factor")
    arr = {s: {c: (b[c].reindex(cal).to_numpy() if c in b else
                   np.where(b["close"].reindex(cal).notna(), 0.0 if c == "dividend" else 1.0, np.nan))
               for c in cols} for s, b in al.items()}
    last_k = {s: (int(np.flatnonzero(~np.isnan(a["close"]))[-1]) if (~np.isnan(a["close"])).any() else -1)
              for s, a in arr.items()}
    smas = {}
    for p in params:
        if p.exit_sma:
            for s, b in bars.items():
                adj_close = signal_view(b)["close"]
                smas[(s, p.exit_sma)] = (adj_close.rolling(p.exit_sma).mean().reindex(cal).to_numpy(),
                                         adj_close.reindex(cal).to_numpy())
    gate = PortfolioRiskGate(risk)
    rng = np.random.default_rng(risk.seed)

    def slip(sym):
        return (risk.slip_bps_wide if sym in WIDE else risk.slip_bps) * risk.cost_mult / 1e4

    def stop_slip(sym):
        return slip(sym) + risk.stop_extra_bps * risk.cost_mult / 1e4

    realized = 0.0
    open_pos: list[dict] = []
    trades, sig_log, expo = [], [], []
    curve, worst = np.empty(len(cal)), np.empty(len(cal))
    skipped = {k: 0 for k in ("open_risk_cap", "cluster_risk_cap", "same_symbol", "gross_cap", "net_cap",
                              "not_triggered", "zero_size", "missed_fill", "daily_loss_lockout", "dd_lockout",
                              "kill_switch", "overlay_veto", "no_bar")}
    worst_extra = best_extra = 0.0
    best = np.empty(len(cal))
    occupied_at_open: list[dict] = []

    DECIDED_BEFORE_OPEN = ("sma_exit", "time_open", "dd_lockout")

    def close_pos(pos, k, px, reason, ref_px):
        nonlocal realized, worst_extra, best_extra
        if reason not in DECIDED_BEFORE_OPEN and pos["k"] < k:
            occupied_at_open.append({**pos, "mark": pos.get("last", pos["entry"])})
        if reason == "time_open":
            reason = "time"
        comm = risk.commission_per_share * risk.cost_mult * pos["shares"]
        gross = pos["dir"] * (ref_px - pos["entry_ref"]) * pos["shares"]
        pnl = pos["dir"] * (px - pos["entry"]) * pos["shares"] - comm - pos["entry_comm"] + pos["div"] - pos["borrow"]
        realized += pnl
        a = arr[pos["sym"]]
        if reason in ("time", "target") and not np.isnan(a["low"][k]):
            adverse = a["low"][k] if pos["dir"] > 0 else a["high"][k]
            worst_extra += max(0.0, pos["dir"] * (px - adverse)) * pos["shares"]
        if not np.isnan(a["high"][k]):
            fav = a["high"][k] if pos["dir"] > 0 else a["low"][k]
            best_extra += max(0.0, pos["dir"] * (fav - px)) * pos["shares"]
        slip_usd = (pos["dir"] * (pos["entry"] - pos["entry_ref"]) + pos["dir"] * (ref_px - px)) * pos["shares"]
        trades.append({"sym": pos["sym"], "pid": pos["pid"], "family": pmap[pos["pid"]].family, "dir": pos["dir"],
                       "signal_date": pos["signal_date"], "entry_date": cal[pos["k"]], "exit_date": cal[k],
                       "entry": pos["entry"], "exit": px, "stop": pos["stop"], "shares": pos["shares"],
                       "risk_usd": pos["risk_usd"], "pnl": pnl, "r": pnl / pos["risk_usd"],
                       "gross_pnl": gross, "commission": comm + pos["entry_comm"], "slippage_usd": slip_usd,
                       "dividends": pos["div"], "borrow": pos["borrow"], "sessions": pos["held"], "reason": reason,
                       "regime": pos["regime"], "overlay_mult": pos["mult"]})

    for k, day in enumerate(cal):
        worst_extra = best_extra = 0.0
        # ---- dividends and borrow on positions held over the previous close
        for pos in open_pos:
            a = arr[pos["sym"]]
            if np.isnan(a["open"][k]):
                continue
            d = a["dividend"][k]
            if d > 0:
                pos["div"] += pos["dir"] * d * pos["shares"]
            if pos["dir"] < 0:
                pos["borrow"] += pos["shares"] * pos.get("last", pos["entry"]) * risk.borrow_bps_annual / 1e4 / 252

        # ---- drawdown lockout: flatten at the open, then stay halted
        if gate.halted and open_pos:
            for pos in open_pos:
                a = arr[pos["sym"]]
                o = a["open"][k] if not np.isnan(a["open"][k]) else pos.get("last", pos["entry"])
                pos["held"] += 1
                close_pos(pos, k, o * (1 - pos["dir"] * slip(pos["sym"])), "dd_lockout", o)
            open_pos = []

        # ---- manage open positions on today's bar
        still = []
        occupied_at_open: list[dict] = []   # exits that happen AFTER the open still occupy the book at the open
        for pos in open_pos:
            a = arr[pos["sym"]]
            o, h, l, c = a["open"][k], a["high"][k], a["low"][k], a["close"][k]
            if np.isnan(o):
                still.append(pos)
                continue
            pos["held"] += 1
            d, st, tg, sym = pos["dir"], pos["stop"], pos["target"], pos["sym"]
            if pos.get("exit_next_open"):
                close_pos(pos, k, o * (1 - d * slip(sym)), "sma_exit", o); continue
            if lb and pos["held"] > pos["max_hold"]:
                close_pos(pos, k, o * (1 - d * slip(sym)), "time_open", o); continue
            if d * (o - st) <= 0:
                close_pos(pos, k, o * (1 - d * stop_slip(sym)), "stop_gap", o); continue
            if tg is not None and d * (o - tg) >= 0:
                close_pos(pos, k, o * (1 - d * slip(sym)), "target_gap", o); continue
            if (l <= st) if d > 0 else (h >= st):
                close_pos(pos, k, st * (1 - d * stop_slip(sym)), "stop", st); continue
            if tg is not None and ((h >= tg) if d > 0 else (l <= tg)):
                close_pos(pos, k, tg, "target", tg); continue
            if not lb and pos["held"] >= pos["max_hold"]:
                close_pos(pos, k, c * (1 - d * slip(sym)), "time", c); continue
            if k == last_k[sym]:
                close_pos(pos, k, c * (1 - d * slip(sym)), "instrument_data_end", c); continue
            if pos["exit_sma"] is not None:
                m, ac = smas[(sym, pos["exit_sma"])]
                if not np.isnan(m[k]) and d * (ac[k] - m[k]) > 0:
                    pos["exit_next_open"] = True
            still.append(pos)
        open_pos = still

        # ---- new entries
        for _, sg in (by_day[day].iterrows() if day in by_day else []):
            sym, d = sg["sym"], int(sg["dir"])
            rec = {"date": day, "signal_date": sg.get("signal_date"), "sym": sym, "pid": sg["pid"], "dir": d,
                   "regime": sg.get("regime")}

            def reject(reason):
                skipped[reason] += 1
                rec["status"] = reason
                sig_log.append(rec)

            a = arr[sym]
            o, h, l, c = a["open"][k], a["high"][k], a["low"][k], a["close"][k]
            if np.isnan(o):
                reject("no_bar"); continue
            # the decision is made BEFORE the open: positions that will only exit later today
            # (intraday / gap stops, targets, closes) still count against slots and risk budget
            book = [{**p_, "mark": p_.get("last", p_["entry"])} for p_ in open_pos] + occupied_at_open
            why = gate.blocked(day)
            if why:
                reject(why); continue
            if any(p_["sym"] == sym and (not risk.stack_symbols or p_["pid"] == sg["pid"]) for p_ in book):
                reject("same_symbol"); continue
            s_ = slip(sym)
            stop_entry = not np.isnan(sg["entry_level"])
            if stop_entry:
                lvl = sg["entry_level"]
                if (h < lvl) if d > 0 else (l > lvl):
                    reject("not_triggered"); continue
                ref = max(o, lvl) if d > 0 else min(o, lvl)
            else:
                ref = o
            fill = ref * (1 + d * s_)
            mult, why = 1.0, ""
            if entry_filter is not None:
                mult, why = entry_filter({**sg.to_dict(), "date": day})
                rec["overlay"] = why
            if risk.miss_fill_prob and rng.random() < risk.miss_fill_prob:
                reject("missed_fill"); continue
            dist = float(sg["stop_dist"])
            dec = gate.check_entry(day=day, sym=sym, pid=sg["pid"], direction=d, fill=fill, stop_dist=dist,
                                   positions=book, mult=mult)
            if not dec.approved:
                reject(dec.reason); continue
            shares, risk_usd = dec.shares, dec.risk_usd
            mult = min(max(float(mult), 0.0), 1.0)
            p = pmap[sg["pid"]]
            pos = {"sym": sym, "pid": p.id, "dir": d, "entry": fill, "entry_ref": ref, "shares": shares, "k": k,
                   "held": 0, "stop": fill - d * dist, "risk_usd": risk_usd, "max_hold": p.max_hold,
                   "exit_sma": p.exit_sma, "target": None if p.target_r is None else fill + d * p.target_r * dist,
                   "entry_comm": risk.commission_per_share * risk.cost_mult * shares, "div": 0.0, "borrow": 0.0,
                   "signal_date": sg.get("signal_date"), "regime": sg.get("regime"), "mult": mult}
            rec["status"] = "accepted"
            sig_log.append(rec)
            st, tg = pos["stop"], pos["target"]
            if not lb and ((l <= st) if d > 0 else (h >= st)):
                close_pos(pos, k, st * (1 - d * stop_slip(sym)), "stop", st); continue
            if not lb and tg is not None and not stop_entry and ((h >= tg) if d > 0 else (l <= tg)):
                close_pos(pos, k, tg, "target", tg); continue
            if k == last_k[sym]:
                close_pos(pos, k, c * (1 - d * slip(sym)), "instrument_data_end", c); continue
            if pos["exit_sma"] is not None:
                m, ac = smas[(sym, pos["exit_sma"])]
                if not np.isnan(m[k]) and d * (ac[k] - m[k]) > 0:
                    pos["exit_next_open"] = True
            open_pos.append(pos)

        # ---- marks, worst intraday equity, exposure, lockouts
        unreal, adverse, favour = 0.0, 0.0, 0.0
        gross = net = open_risk = 0.0
        for p_ in open_pos:
            a = arr[p_["sym"]]
            if not np.isnan(a["close"][k]):
                p_["last"] = a["close"][k]
                worst_px = a["low"][k] if p_["dir"] > 0 else a["high"][k]
                adverse += max(0.0, p_["dir"] * (p_["last"] - worst_px)) * p_["shares"]
                best_px = a["high"][k] if p_["dir"] > 0 else a["low"][k]
                favour += max(0.0, p_["dir"] * (best_px - p_["last"])) * p_["shares"]
            unreal += (p_["dir"] * (p_.get("last", p_["entry"]) - p_["entry"]) * p_["shares"] - p_["entry_comm"]
                       + p_["div"] - p_["borrow"])
            notional = p_["shares"] * p_.get("last", p_["entry"])
            gross += notional
            net += p_["dir"] * notional
            open_risk += p_["risk_usd"]
        eq_today = risk.equity + realized + unreal
        curve[k] = eq_today
        worst[k] = eq_today - adverse - worst_extra
        best[k] = eq_today + favour + best_extra
        expo.append((gross, net, open_risk, len(open_pos)))
        gate.on_close(day, eq_today)

    for p_ in open_pos:  # end of window: mark out at the last close
        c = p_.get("last", p_["entry"])
        close_pos(p_, len(cal) - 1, c, "end_of_window", c)
    ex = pd.DataFrame(expo, index=cal, columns=["gross", "net", "open_risk", "positions"])
    return Result(pd.DataFrame(trades), pd.Series(curve, index=cal, name="equity"), skipped,
                  pd.Series(worst, index=cal, name="equity_worst"), pd.Series(best, index=cal, name="equity_best"),
                  pd.DataFrame(sig_log), ex, gate.halted_on)


def metrics(res: Result, start_equity: float = 100_000.0) -> dict:
    """Headline metrics (geometric monthly equivalent over the exact simulated window)."""
    t, eq = res.trades, res.equity
    weeks = max(len(eq) / 5.0, 1e-9)
    if not len(t):
        return {"trades": 0, "trades_per_week": 0.0, "total_return_pct": 0.0, "max_dd_pct": 0.0}
    gp, gl = t.loc[t.pnl > 0, "pnl"].sum(), -t.loc[t.pnl < 0, "pnl"].sum()
    rets = eq.pct_change().dropna()
    days = (eq.index[-1] - eq.index[0]).days if len(eq) > 1 else 0
    years = max(days / 365.25, 1e-9)
    dd = (eq / eq.cummax() - 1).min()
    total = eq.iloc[-1] / start_equity - 1
    return {
        "trades": int(len(t)), "trades_per_week": round(len(t) / weeks, 2),
        "win_rate": round(float((t.pnl > 0).mean()), 3),
        "profit_factor": round(float(gp / gl), 2) if gl > 0 else float("inf"),
        "expectancy_r": round(float(t.r.mean()), 3), "avg_sessions": round(float(t.sessions.mean()), 2),
        "total_return_pct": round(100 * total, 2),
        "cagr_pct": round(100 * ((1 + total) ** (1 / years) - 1), 2) if total > -1 else None,
        "monthly_pct": round(100 * ((1 + total) ** (1 / (years * 12)) - 1), 3) if total > -1 else None,
        "max_dd_pct": round(100 * float(dd), 2),
        "sharpe": round(float(rets.mean() / rets.std() * np.sqrt(252)), 2) if rets.std() > 0 else 0.0,
    }

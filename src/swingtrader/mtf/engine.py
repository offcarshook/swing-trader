"""Multi-timeframe MES research engine (1-3 session holds, decisions on completed bars).

Timeframes and their roles (each can be switched off for ablations):
  1d   context: close > SMA50 and SMA50 rising over 10 sessions; volatility regime: ATR14% below
       its trailing 80th percentile
  4h   intermediate trend: EMA20 > EMA50
  1h   primary setup: RSI(2) < 10 on a completed 1-hour bar (pullback); ATR(14, 1h) sets the stop
  15m  entry refinement: a completed 15-minute bar closes above the previous 15-minute high while a
       1-hour setup from the last 4 hours is live
  5m   NOT used as a filter: execution is at the next real 1-minute open (finer than 5m)
Variants (`VARIANTS`):
  A_daily_only     single-timeframe baseline: daily RSI(2) < 10 in a daily uptrend, entry at the
                   next session's first RTH minute (08:30 CT)
  B_context_only   1d + 4h context, entry at a 1h close in RTH, no setup
  C_context_setup  1d + 4h + 1h setup, entry right after the setup bar closes
  D_full_mtf       C + 15m confirmation trigger
  E_moderate       1d context + 1h setup + 15m trigger (no 4h, no volatility filter)
  F_*              ablations of D (each timeframe / major feature removed in turn)
Identical exits for every variant (so only entry selection differs): stop 2.0 x ATR(1h,14),
target 1.5R, time stop at the last RTH minute (14:59 CT) of the second session after the entry
session. Stops/targets are resolved on 1-minute bars (stop first if both are inside one minute);
an open through the stop fills at that minute's open plus gap slippage.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from dataclasses import dataclass

import numpy as np
import pandas as pd

from swingtrader.contracts import SPECS, roll_dates
from swingtrader.costs import GAP_STOP, MARKET, STOP, CostModel
from swingtrader.indicators import atr, rsi, sma, trailing_percentile
from swingtrader.mtf.bars import asof, build_all

RTH_DECISION_FIRST = dt.time(8, 45)
RTH_DECISION_LAST = dt.time(14, 45)
POINT_VALUE = 5.0


@dataclass(frozen=True)
class Variant:
    name: str
    entry: str                    # daily_open | h1_close | m15_trigger
    use_daily: bool = True
    use_vol: bool = True
    use_h4: bool = True
    use_h1_setup: bool = True
    setup_window_h: int = 4
    side: str = "long"            # long | short (mirror: downtrends, RSI2 > 90, close below prior 15m low)
    stop_atr: float = 2.0
    target_r: float = 1.5


VARIANTS = {
    "A_daily_only": Variant("A_daily_only", "daily_open", use_h4=False, use_h1_setup=False, use_vol=False),
    "B_context_only": Variant("B_context_only", "h1_close", use_h1_setup=False),
    "C_context_setup": Variant("C_context_setup", "h1_close"),
    "D_full_mtf": Variant("D_full_mtf", "m15_trigger"),
    "E_moderate": Variant("E_moderate", "m15_trigger", use_h4=False, use_vol=False),
    "F_no_daily": Variant("F_no_daily", "m15_trigger", use_daily=False),
    "F_no_vol_filter": Variant("F_no_vol_filter", "m15_trigger", use_vol=False),
    "F_no_4h": Variant("F_no_4h", "m15_trigger", use_h4=False),
    "F_no_1h_setup": Variant("F_no_1h_setup", "m15_trigger", use_h1_setup=False),
    "F_no_15m_trigger": Variant("F_no_15m_trigger", "h1_close"),
    "E_moderate_setup8h": Variant("E_moderate_setup8h", "m15_trigger", use_h4=False, use_vol=False, setup_window_h=8),
}
VARIANTS.update({f"{k}_short": dataclasses.replace(v, name=f"{k}_short", side="short")
                 for k, v in list(VARIANTS.items()) if k[0] in "ABCDE"})


def features(bars: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    d = bars["1d"].copy()
    d["sma50"] = sma(d["close"], 50)
    d["up"] = (d["close"] > d["sma50"]) & (d["sma50"] > d["sma50"].shift(10))
    d["down"] = (d["close"] < d["sma50"]) & (d["sma50"] < d["sma50"].shift(10))
    d["atrp"] = atr(d, 14) / d["close"]
    d["atrp_rank"] = trailing_percentile(d["atrp"], 252) / 100
    d["calm"] = d["atrp_rank"] < 0.8
    d["rsi2"] = rsi(d["close"], 2)
    h4 = bars["4h"].copy()
    e20, e50 = h4["close"].ewm(span=20, adjust=False).mean(), h4["close"].ewm(span=50, adjust=False).mean()
    h4["up"], h4["down"] = e20 > e50, e20 < e50
    h1 = bars["1h"].copy()
    h1["rsi2"] = rsi(h1["close"], 2)
    h1["atr"] = atr(h1, 14)
    m15 = bars["15m"].copy()
    m15["trig"] = m15["close"] > m15["high"].shift(1)
    m15["trig_dn"] = m15["close"] < m15["low"].shift(1)
    return {"1d": d, "4h": h4, "1h": h1, "15m": m15}


def decision_frame(f: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """One row per completed 15-minute bar inside the RTH decision window, with every
    higher-timeframe value as of that moment (completed bars only)."""
    m15 = f["15m"]
    t = m15["available_at"]
    tt = t.dt.time
    t = t[(tt >= RTH_DECISION_FIRST) & (tt <= RTH_DECISION_LAST)]
    g = pd.DataFrame(index=pd.DatetimeIndex(t))
    g["m15_trig"] = m15.loc[t.index, "trig"].to_numpy()
    g["m15_trig_dn"] = m15.loc[t.index, "trig_dn"].to_numpy()
    for tf, cols, pre in (("1d", ["up", "down", "calm", "rsi2", "session"], "d_"), ("4h", ["up", "down"], "h4_"),
                          ("1h", ["rsi2", "atr"], "h1_")):
        a = asof(g.index, f[tf], cols, pre)
        for c in a.columns:
            g[c] = a[c].to_numpy()
    # most recent 1h setup bar (RSI2 < threshold) completed at or before t
    h1 = f["1h"]
    setup_times = h1.loc[h1["rsi2"] < 10.0, "available_at"]
    s = pd.merge_asof(pd.DataFrame({"t": g.index}), pd.DataFrame({"setup_at": setup_times.to_numpy()}),
                      left_on="t", right_on="setup_at", direction="backward", allow_exact_matches=True)
    g["h1_setup_at"] = s["setup_at"].to_numpy()
    short_times = h1.loc[h1["rsi2"] > 90.0, "available_at"]
    s = pd.merge_asof(pd.DataFrame({"t": g.index}), pd.DataFrame({"setup_at": short_times.to_numpy()}),
                      left_on="t", right_on="setup_at", direction="backward", allow_exact_matches=True)
    g["h1_setup_short_at"] = s["setup_at"].to_numpy()
    return g


def signals(g: pd.DataFrame, f: dict, v: Variant) -> tuple[pd.DataFrame, dict]:
    """Entry decision times for a variant + rejection diagnostics (counts per failed condition)."""
    ctx = pd.Series(True, index=g.index)
    diag = {}
    lg = v.side == "long"
    trend_d, trend_h4 = ("d_up", "h4_up") if lg else ("d_down", "h4_down")
    setup_col, trig_col = ("h1_setup_at", "m15_trig") if lg else ("h1_setup_short_at", "m15_trig_dn")
    if v.use_daily:
        ok = g[trend_d].fillna(False).astype(bool)
        diag["rejected_by_daily_trend"] = int((~ok).sum())
        ctx &= ok
    if v.use_vol:
        ok = g["d_calm"].fillna(False).astype(bool)
        diag["rejected_by_vol_regime"] = int((~ok).sum())
        ctx &= ok
    if v.use_h4:
        ok = g[trend_h4].fillna(False).astype(bool)
        diag["rejected_by_4h_trend"] = int((~ok).sum())
        ctx &= ok
    if v.entry == "daily_open":
        d = f["1d"]
        sig_sessions = d.index[((d["rsi2"] < 10) & d["up"].fillna(False).astype(bool)) if lg else
                               ((d["rsi2"] > 90) & d["down"].fillna(False).astype(bool))]
        nxt = g.index[(g.index.time == RTH_DECISION_FIRST)]
        # first RTH decision of the session AFTER each signal session (signal bar complete at 16:00)
        firsts = pd.Series(nxt, index=nxt)
        out = []
        for s in sig_sessions:
            cand = firsts[firsts.index > s]
            if len(cand):
                out.append(cand.iloc[0])
        times = pd.DatetimeIndex(sorted(set(out))) - pd.Timedelta(minutes=15)  # enter at 08:30 open
        return pd.DataFrame({"decision": times}), {"daily_signals": len(sig_sessions)}
    if v.use_h1_setup:
        live = (g.index - g[setup_col]) <= pd.Timedelta(hours=v.setup_window_h)
        live &= g[setup_col].notna()
        if v.entry == "h1_close":
            live &= g[setup_col] == g.index              # right after the setup bar completes
        diag["rejected_by_no_1h_setup"] = int((~live).sum())
        ctx &= live
    elif v.entry == "h1_close":
        ctx &= g.index.minute == 0                         # a 1h bar completes on the hour
    if v.entry == "m15_trigger":
        ok = g[trig_col].fillna(False).astype(bool)
        if v.use_h1_setup:
            ok &= g.index > g[setup_col]                   # trigger strictly after the setup bar
        diag["rejected_by_no_15m_trigger"] = int((~ok).sum())
        ctx &= ok
    return pd.DataFrame({"decision": g.index[ctx.to_numpy()]}), diag


@dataclass
class SimCfg:
    equity: float = 100_000.0
    risk_pct: float = 1.0
    max_contracts: int = 20
    cost_mult: float = 1.0
    entry_delay_min: int = 0


def simulate(m1: pd.DataFrame, f: dict, g: pd.DataFrame, entries: pd.DataFrame, v: Variant, costs_cfg: dict,
             sim: SimCfg, start, end) -> dict:
    spec = SPECS["MES"]
    cm = CostModel.from_config(spec, costs_cfg, multiplier=sim.cost_mult)
    ts = m1.index
    o, h, lo, c = (m1[k].to_numpy() for k in ("open", "high", "low", "close"))
    from swingtrader.data.sessions import session_dates
    sess = session_dates(ts)
    sess_vals = sess.to_numpy()
    mins = ts.hour * 60 + ts.minute
    is_last_rth = (mins == 14 * 60 + 59)
    rolls = set(roll_dates(dt.date(2019, 1, 1), dt.date(2027, 12, 31), spec))
    uniq_sessions = pd.DatetimeIndex(pd.unique(sess_vals))
    sess_pos = {d: i for i, d in enumerate(uniq_sessions)}
    idx = np.arange(len(ts))
    last_rth = pd.Series(idx[is_last_rth], index=sess[is_last_rth]).groupby(level=0).first()
    last_any = pd.Series(idx, index=sess).groupby(level=0).last()
    stop_idx = {d: int(last_rth.get(d, last_any[d])) for d in uniq_sessions}
    e = entries[(entries.decision >= pd.Timestamp(start)) & (entries.decision <= pd.Timestamp(end))]
    h1atr = g["h1_atr"].reindex(e.decision).to_numpy() if len(e) else np.array([])
    if v.entry == "daily_open" and len(e):
        a = asof(e.decision, f["1h"], ["atr"], "h1_")
        h1atr = a["h1_atr"].to_numpy()
    equity, trades = sim.equity, []
    busy_until = pd.Timestamp.min
    for dec, a_h1 in zip(e.decision, h1atr):
        if dec < busy_until or not np.isfinite(a_h1) or a_h1 <= 0:
            continue
        i = int(ts.searchsorted(dec + pd.Timedelta(minutes=sim.entry_delay_min)))
        if i >= len(ts) or (ts[i] - dec) > pd.Timedelta(minutes=30):
            continue                                        # no real minute soon after the decision
        stop_pts = v.stop_atr * a_h1
        risk_usd = sim.risk_pct / 100 * equity
        n = int(min(sim.max_contracts, risk_usd // (stop_pts * POINT_VALUE + cm.est_round_trip_per_contract())))
        if n <= 0:
            continue
        d = 1 if v.side == "long" else -1
        fill = cm.fill_price(o[i], d, MARKET)
        stop, target = fill - d * stop_pts, fill + d * v.target_r * stop_pts
        # time stop: last RTH minute of the second session after the entry session
        k0 = sess_pos[pd.Timestamp(sess_vals[i])]
        last_sess = uniq_sessions[min(k0 + 2, len(uniq_sessions) - 1)]
        T = max(stop_idx[last_sess], i)
        seg_l, seg_h, seg_o = lo[i:T + 1], h[i:T + 1], o[i:T + 1]
        adv, fav = (seg_l, seg_h) if d > 0 else (seg_h, seg_l)
        js = np.flatnonzero(d * (adv - stop) <= 0)
        jt = np.flatnonzero(d * (fav - target) >= 0)
        j_s = js[0] if len(js) else None
        j_t = jt[0] if len(jt) else None
        if j_s is not None and (j_t is None or j_s <= j_t):
            j = i + int(j_s)
            if j > i and d * (seg_o[j_s] - stop) <= 0:
                px, reason = cm.fill_price(o[j], -d, GAP_STOP), "stop_gap"
            else:
                px, reason = cm.fill_price(stop, -d, STOP), "stop"
        elif j_t is not None:
            j = i + int(j_t)
            px, reason = (o[j], "target_gap") if (j > i and d * (seg_o[j_t] - target) >= 0) else (target, "target")
        else:
            j, px, reason = T, cm.fill_price(c[T], -d, MARKET), "time"
        pnl = d * (px - fill) * POINT_VALUE * n - 2 * cm.fees(n)
        held_rolls = [r for r in rolls if pd.Timestamp(sess_vals[i]).date() < r <= pd.Timestamp(sess_vals[j]).date()]
        if held_rolls:
            pnl -= cm.roll_cost(n) * len(held_rolls)
        equity += pnl
        trades.append({"decision": dec, "entry_time": ts[i], "exit_time": ts[j], "contracts": n, "entry": fill,
                       "exit": px, "stop": stop, "target": target, "pnl": pnl,
                       "r": pnl / (stop_pts * POINT_VALUE * n), "reason": reason,
                       "sessions": int(sess_pos[pd.Timestamp(sess_vals[j])] - k0), "rolls": len(held_rolls),
                       "entry_session": pd.Timestamp(sess_vals[i]), "exit_session": pd.Timestamp(sess_vals[j]),
                       "dir": d})
        busy_until = ts[j] + pd.Timedelta(minutes=1)
    t = pd.DataFrame(trades)
    return {"trades": t, "equity": _session_equity(t, m1, sess, sim.equity, start, end)}


def _session_equity(t: pd.DataFrame, m1: pd.DataFrame, sess: pd.DatetimeIndex, eq0: float, start, end) -> pd.Series:
    """Mark-to-market equity at each session's last minute (unrealised P&L of an open trade
    uses that minute's close)."""
    closes = pd.Series(m1["close"].to_numpy(), index=sess).groupby(level=0).last()
    closes = closes[(closes.index >= pd.Timestamp(start).normalize()) & (closes.index <= pd.Timestamp(end))]
    eq = pd.Series(eq0, index=closes.index, dtype=float)
    if not len(t):
        return eq
    realized = t.groupby("exit_session")["pnl"].sum().reindex(closes.index, fill_value=0.0).cumsum()
    unreal = pd.Series(0.0, index=closes.index)
    for r in t.itertuples():
        open_days = closes.index[(closes.index >= r.entry_session) & (closes.index < r.exit_session)]
        unreal.loc[open_days] += r.dir * (closes.loc[open_days] - r.entry) * POINT_VALUE * r.contracts
    return eq0 + realized + unreal


def metrics(res: dict, eq0: float = 100_000.0) -> dict:
    t, eq = res["trades"], res["equity"]
    if not len(t):
        return {"trades": 0}
    years = max((eq.index[-1] - eq.index[0]).days / 365.25, 1e-9)
    total = eq.iloc[-1] / eq0 - 1
    rets = eq.pct_change().dropna()
    gl = -t.pnl[t.pnl < 0].sum()
    weeks = max(len(eq) / 5, 1)
    wk = t.groupby(t.entry_time.dt.to_period("W")).size()
    return {"trades": int(len(t)), "trades_per_week": round(len(t) / weeks, 2),
            "zero_trade_weeks_pct": round(100 * (1 - len(wk) / weeks), 1),
            "win_rate": round(float((t.pnl > 0).mean()), 3),
            "profit_factor": round(float(t.pnl[t.pnl > 0].sum() / gl), 3) if gl > 0 else None,
            "expectancy_r": round(float(t.r.mean()), 3), "expectancy_usd": round(float(t.pnl.mean()), 2),
            "total_return_pct": round(100 * total, 2),
            "cagr_pct": round(100 * ((1 + total) ** (1 / years) - 1), 2) if total > -1 else None,
            "geometric_monthly_pct": round(100 * ((1 + total) ** (1 / (12 * years)) - 1), 3) if total > -1 else None,
            "max_dd_pct": round(100 * float((eq / eq.cummax() - 1).min()), 2),
            "sharpe": round(float(rets.mean() / rets.std() * np.sqrt(252)), 2) if rets.std() > 0 else 0.0,
            "median_sessions": float(t.sessions.median()),
            "exit_reasons": {k: int(n) for k, n in t.reason.value_counts().items()},
            "reliability": "ok" if len(t) >= 100 else "unreliable (small sample)"}


def variant_with(v: Variant, **kw) -> Variant:
    return dataclasses.replace(v, **kw)

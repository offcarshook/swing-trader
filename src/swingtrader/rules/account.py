"""Generic, configurable HYPOTHETICAL account-rule replay (research / paper evaluation only).

This module does not model, connect to, or claim compatibility with any real firm, evaluation
or funded-account programme. It replays a chronological equity path against configurable
limits and reports the first event (target reached or rule breached) with its exact session and
reason. A simulated "target reached" is not an evaluation pass and not a forecast.

Inputs per session (index = session date, in the account's own calendar):
  balance       realised-only account balance at the session close
  equity        balance + unrealised P&L at the session close
  equity_worst  lowest intraday equity (daily data: bar lows for longs / highs for shorts)
  equity_best   highest intraday equity
  active        whether the account traded (opened or closed a position) that session

Rule semantics (every option is explicit; defaults are the conservative choice):
  daily loss    loss_today = reference - low, where reference = start-of-day equity
                (`daily_loss_reference: equity`) or start-of-day balance (`balance`), and
                low = equity_worst (`intraday`) or equity at the close (`eod`). The limit is
                `max_daily_loss_pct` of the starting balance (`daily_loss_limit_basis: starting`)
                or of the reference (`reference`). Breach when loss_today >= limit.
  total loss    static: floor = start * (1 - max_total_loss_pct).
                trailing: floor = peak - start * max_total_loss_pct, where peak is the running
                max of equity_best (`trailing_basis: intraday`), of close equity (`eod_equity`)
                or of balance (`eod_balance`). With `trailing_lock_at_start` the floor stops
                rising once it reaches the starting balance.
                Breach when the checked value (equity_worst for intraday checks, equity at the
                close for `eod` checks) <= floor.
  intrabar order daily data cannot order the high and low of a session. `conservative`
                updates the trailing peak with today's best BEFORE checking today's worst.
  target        equity (or balance with `target_basis: balance`) at a close >= start*(1+target),
                and at least `min_trading_days` active sessions, and, if set, no single
                session's gain above `consistency_max_day_share_pct` of total profit.
                Checked after the breach checks of the same session.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class AccountRules:
    name: str = "hypothetical"
    starting_balance: float = 100_000.0
    profit_target_pct: float | None = None
    max_daily_loss_pct: float | None = None
    daily_loss_reference: str = "equity"        # equity | balance
    daily_loss_limit_basis: str = "starting"    # starting | reference
    daily_loss_check: str = "intraday"          # intraday | eod
    max_total_loss_pct: float | None = None
    drawdown_type: str = "static"               # static | trailing
    trailing_basis: str = "intraday"            # intraday | eod_equity | eod_balance
    trailing_lock_at_start: bool = False
    total_loss_check: str = "intraday"          # intraday | eod
    intrabar_order: str = "conservative"
    target_basis: str = "equity"                # equity | balance
    min_trading_days: int = 0
    consistency_max_day_share_pct: float | None = None

    @classmethod
    def from_dict(cls, d: dict) -> AccountRules:
        names = {f.name for f in fields(cls)}
        unknown = set(d) - names
        if unknown:
            raise ValueError(f"unknown account-rule keys: {sorted(unknown)}")
        r = cls(**d)
        r.validate()
        return r

    def validate(self) -> None:
        choices = {"daily_loss_reference": ("equity", "balance"), "daily_loss_limit_basis": ("starting", "reference"),
                   "daily_loss_check": ("intraday", "eod"), "drawdown_type": ("static", "trailing"),
                   "trailing_basis": ("intraday", "eod_equity", "eod_balance"), "total_loss_check": ("intraday", "eod"),
                   "intrabar_order": ("conservative",), "target_basis": ("equity", "balance")}
        for k, ok in choices.items():
            if getattr(self, k) not in ok:
                raise ValueError(f"{k}={getattr(self, k)!r} not in {ok}")


@dataclass
class Replay:
    status: str                    # breached | target_reached | open (neither by the end)
    date: str | None
    reason: str | None
    sessions: int
    active_days: int
    final_equity: float
    max_dd_pct: float
    min_daily_headroom_usd: float | None
    min_total_headroom_usd: float | None
    detail: dict

    def to_dict(self) -> dict:
        return asdict(self)


def replay(path: pd.DataFrame, rules: AccountRules) -> Replay:
    """Walk the path session by session; stop at the first breach or target."""
    rules.validate()
    s0 = rules.starting_balance
    cols = {c: path[c].to_numpy(dtype=float) for c in ("balance", "equity", "equity_worst", "equity_best")}
    active = path["active"].to_numpy(dtype=bool) if "active" in path else np.ones(len(path), bool)
    peak = s0
    prev_eq, prev_bal = s0, s0
    day_gains, active_days = [], 0
    min_dh = min_th = None
    dates = path.index
    for i in range(len(path)):
        bal, eq, lo, hi = cols["balance"][i], cols["equity"][i], cols["equity_worst"][i], cols["equity_best"][i]
        active_days += int(active[i])
        # ---- daily loss
        if rules.max_daily_loss_pct is not None:
            ref = prev_eq if rules.daily_loss_reference == "equity" else prev_bal
            base = s0 if rules.daily_loss_limit_basis == "starting" else ref
            limit = base * rules.max_daily_loss_pct / 100
            low = lo if rules.daily_loss_check == "intraday" else eq
            headroom = limit - (ref - low)
            min_dh = headroom if min_dh is None else min(min_dh, headroom)
            if headroom <= 0:
                return _done("breached", dates[i], f"daily loss {ref - low:,.2f} >= limit {limit:,.2f} "
                             f"(reference {rules.daily_loss_reference} {ref:,.2f})", i, active_days, eq, path,
                             min_dh, min_th, rules)
        # ---- total loss
        if rules.max_total_loss_pct is not None:
            amt = s0 * rules.max_total_loss_pct / 100
            if rules.drawdown_type == "static":
                floor = s0 - amt
            else:
                cand = {"intraday": hi, "eod_equity": eq, "eod_balance": bal}[rules.trailing_basis]
                if rules.trailing_basis == "intraday":   # conservative: today's best counts before today's worst
                    peak = max(peak, cand)
                floor = peak - amt
                if rules.trailing_lock_at_start:
                    floor = min(floor, s0)
            chk = lo if rules.total_loss_check == "intraday" else eq
            headroom = chk - floor
            min_th = headroom if min_th is None else min(min_th, headroom)
            if headroom <= 0:
                return _done("breached", dates[i], f"total loss: equity {chk:,.2f} <= floor {floor:,.2f} "
                             f"({rules.drawdown_type})", i, active_days, eq, path, min_dh, min_th, rules)
            if rules.drawdown_type == "trailing" and rules.trailing_basis != "intraday":
                peak = max(peak, eq if rules.trailing_basis == "eod_equity" else bal)
        day_gains.append(eq - prev_eq)
        # ---- target
        if rules.profit_target_pct is not None:
            val = eq if rules.target_basis == "equity" else bal
            profit = val - s0
            if profit >= s0 * rules.profit_target_pct / 100 and active_days >= rules.min_trading_days:
                ok = True
                if rules.consistency_max_day_share_pct is not None and profit > 0:
                    ok = max(day_gains) <= profit * rules.consistency_max_day_share_pct / 100
                if ok:
                    return _done("target_reached", dates[i], f"{rules.target_basis} {val:,.2f} >= target", i,
                                 active_days, eq, path, min_dh, min_th, rules)
        prev_eq, prev_bal = eq, bal
    return _done("open", None, None, len(path) - 1, active_days, cols["equity"][-1] if len(path) else s0, path,
                 min_dh, min_th, rules)


def _done(status, date, reason, i, active_days, eq, path, min_dh, min_th, rules) -> Replay:
    e = path["equity"].iloc[: i + 1]
    dd = float((e / np.maximum.accumulate(np.r_[rules.starting_balance, e.to_numpy()])[1:] - 1).min()) if len(e) else 0.0
    return Replay(status, str(pd.Timestamp(date).date()) if date is not None else None, reason, i + 1, active_days,
                  round(float(eq), 2), round(100 * dd, 2),
                  None if min_dh is None else round(float(min_dh), 2), None if min_th is None else round(float(min_th), 2),
                  {"rules": asdict(rules)})


def path_from_result(res, start_balance: float, start=None, end=None) -> pd.DataFrame:
    """Build the replay path from an ETF engine Result, rescaled to `start_balance` at `start`.

    Position sizes are a fixed fraction of equity, so a path started later is approximately the
    original path rescaled; this is an approximation and is labelled as such in reports."""
    eq = res.equity.loc[start:end]
    if not len(eq):
        return pd.DataFrame(columns=["balance", "equity", "equity_worst", "equity_best", "active"])
    # the account starts flat at the previous close
    prev = res.equity.loc[: eq.index[0]].iloc[:-1]
    base = prev.iloc[-1] if len(prev) else res.equity.iloc[0]
    scale = start_balance / base
    t = res.trades
    realized = pd.Series(0.0, index=res.equity.index)
    if len(t):
        realized = t.groupby("exit_date")["pnl"].sum().reindex(res.equity.index, fill_value=0.0).cumsum()
    bal0 = realized.loc[: eq.index[0]].iloc[:-1]
    bal_base = bal0.iloc[-1] if len(bal0) else 0.0
    out = pd.DataFrame({
        "equity": eq * scale,
        "equity_worst": res.equity_worst.loc[eq.index] * scale,
        "equity_best": res.equity_best.loc[eq.index] * scale,
        "balance": start_balance + (realized.loc[eq.index] - bal_base) * scale,
    })
    act = pd.Series(False, index=res.equity.index)
    if len(t):
        days = set(t.entry_date) | set(t.exit_date)
        act = pd.Series(res.equity.index.isin(list(days)), index=res.equity.index)
    out["active"] = act.loc[eq.index].to_numpy()
    return out


def rolling_starts(res, rules: AccountRules, horizon_sessions: int, start=None, end=None, step: str = "MS") -> dict:
    """Start a fresh hypothetical account at the first session of every month in the window and
    replay at most `horizon_sessions` sessions. Overlapping windows are serially dependent: the
    report gives both all starts and the subset of non-overlapping starts."""
    eq = res.equity.loc[start:end]
    starts = sorted({eq.index[eq.index >= d][0] for d in pd.date_range(eq.index[0], eq.index[-1], freq=step)
                     if (eq.index >= d).any()})
    rows = []
    for s in starts:
        i = eq.index.get_loc(s)
        if i + horizon_sessions > len(eq):
            break
        seg = eq.index[i: i + horizon_sessions]
        r = replay(path_from_result(res, rules.starting_balance, seg[0], seg[-1]), rules)
        rows.append({"start": str(s.date()), "status": r.status, "event_date": r.date, "reason": r.reason,
                     "sessions_to_event": r.sessions})
    df = pd.DataFrame(rows)
    if df.empty:
        return {"starts": 0}
    non_overlap, last_end = [], None
    for _, row in df.iterrows():
        st = pd.Timestamp(row.start)
        if last_end is None or st > last_end:
            non_overlap.append(row)
            last_end = eq.index[min(eq.index.get_loc(st) + horizon_sessions - 1, len(eq) - 1)]
    no = pd.DataFrame(non_overlap)

    def freq(d):
        return {k: int(v) for k, v in d.status.value_counts().items()}
    return {"starts": int(len(df)), "horizon_sessions": horizon_sessions, "outcomes_all_starts": freq(df),
            "non_overlapping_starts": int(len(no)), "outcomes_non_overlapping": freq(no),
            "median_sessions_to_event": float(df.sessions_to_event.median()),
            "rows": df.to_dict("records"),
            "caveat": ("historical replay of one strategy path under hypothetical rules; overlapping starts are "
                       "serially dependent; not a pass-rate estimate for any real programme")}

"""Event-driven session backtester.

Timeline inside one session bar (all from data of that session only):

  A. pre-RTH segment   held positions: gap check at the session open, then the
                       resting stop vs pre_high/pre_low (overnight)
  B. RTH open          orders decided at the PREVIOUS close execute at rth_open
                       (+ adverse slippage); entries are sized here by RiskManager
  C. post-open segment resting stop vs post_high/post_low
  D. close             mark-to-market, drawdown halt check
  E. decision          strategy.decide() on the completed bar -> orders for the next RTH open

Stops are resting orders (filled at the stop, or at the open if price gaps
through it). A session-level "daily loss stop" is derived from the equity at the
start of the session so the daily loss limit is enforced intraday. There are no
profit targets, so there is no same-bar stop-vs-target ordering ambiguity.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from swingtrader.accounting import Ledger
from swingtrader.contracts import ContractSpec, roll_dates
from swingtrader.costs import GAP_STOP, MARKET, STOP, CostModel
from swingtrader.risk import RiskManager
from swingtrader.strategies.base import PositionView, Strategy

HOLE_DAYS = 4  # calendar gap that indicates missing sessions (long weekend = 3)


@dataclass
class OpenTrade:
    side: int
    contracts: int
    entry_date: pd.Timestamp
    entry_price: float
    initial_stop: float
    stop: float
    initial_risk: float
    entry_fees: float
    reason: str
    regime: str = ""
    bars_held: int = 0
    best_close: float = 0.0
    roll_costs: float = 0.0
    rolls: int = 0


@dataclass
class BacktestResult:
    label: str
    equity: pd.Series
    trades: pd.DataFrame
    events: pd.DataFrame
    in_market: pd.Series
    start_equity: float
    params: dict = field(default_factory=dict)
    halted: str | None = None


def _round_stop(spec: ContractSpec, price: float, side: int) -> float:
    # Long stops round down (further away), short stops round up.
    return spec.round_to_tick(price, "down" if side > 0 else "up")


def run_backtest(
    bars: pd.DataFrame,
    strategy: Strategy,
    spec: ContractSpec,
    costs: CostModel,
    risk: RiskManager,
    start: str | pd.Timestamp,
    end: str | pd.Timestamp | None,
    starting_equity: float,
    entry_filter=None,
    regimes: pd.Series | None = None,
    instrument: str = "MES",
) -> BacktestResult:
    """Run one strategy over [start, end]. `entry_filter(date, side, row) -> multiplier`
    is the (optional) research overlay hook; it can only scale size into [0, 1]."""
    feats = strategy.features(bars)
    start = pd.Timestamp(start)
    end = pd.Timestamp(end) if end is not None else bars.index[-1]
    # A strategy needs its warm-up history before the first decision.
    first_ok = bars.index[min(strategy.warmup, len(bars) - 1)]
    start = max(start, first_ok)
    win = bars.loc[start:end]
    if win.empty:
        raise ValueError("empty backtest window")
    feats = feats.loc[win.index]
    rows = list(feats.itertuples(index=False))
    short_flags = win["short_session"].to_numpy() if "short_session" in win else np.zeros(len(win), bool)

    ledger = Ledger(starting_equity, {instrument: spec.multiplier})
    rolls = set(roll_dates(win.index[0].date() - dt.timedelta(days=1), win.index[-1].date(), spec))
    trades: list[dict] = []
    events: list[dict] = []
    eq_curve, in_mkt = [], []
    pos: OpenTrade | None = None
    pending: dict | None = None
    peak = starting_equity
    prev_date = None
    ledger.mark(instrument, float(win["close"].iloc[0]))

    def close_trade(date, price_ref, kind, reason, thin=False):
        nonlocal pos
        fill = costs.fill_price(price_ref, -pos.side, kind, thin)
        fee = costs.fees(pos.contracts)
        realized = ledger.fill(instrument, -pos.side, pos.contracts, fill, fee, ts=date, tag=reason)
        net = realized - pos.entry_fees - fee - pos.roll_costs
        trades.append({
            "strategy": strategy.label, "side": pos.side, "contracts": pos.contracts,
            "entry_date": pos.entry_date, "entry_price": pos.entry_price, "initial_stop": pos.initial_stop,
            "exit_date": date, "exit_price": fill, "exit_reason": reason,
            "gross_pnl": realized, "fees": pos.entry_fees + fee, "roll_costs": pos.roll_costs, "rolls": pos.rolls,
            "net_pnl": net, "initial_risk": pos.initial_risk,
            "r_multiple": net / pos.initial_risk if pos.initial_risk else np.nan,
            "sessions_held": pos.bars_held, "calendar_days": (date - pos.entry_date).days,
            "entry_reason": pos.reason, "regime_at_entry": pos.regime,
        })
        pos = None

    for i, (date, bar) in enumerate(win.iterrows()):
        risk.start_session()
        thin = bool(short_flags[i])
        hole = prev_date is not None and (date - prev_date).days > HOLE_DAYS
        day_start_equity = ledger.equity()

        # ---- roll: held across a quarterly roll date -> pay two legs ----
        if pos is not None and prev_date is not None:
            due = [r for r in rolls if prev_date.date() < r <= date.date()]
            if due:
                c = costs.roll_cost(pos.contracts) * len(due)
                ledger.charge(c, "roll")
                pos.roll_costs += c
                pos.rolls += len(due)

        # ---- A. pre-RTH: gap at session open, then overnight range ----
        if pos is not None:
            dstop = risk.daily_stop_price(day_start_equity, ledger.equity(), ledger.marks[instrument],
                                          pos.side, pos.contracts)
            eff, why = _effective_stop(pos, dstop)
            o = bar["open"]
            if (o - eff) * pos.side <= 0:
                close_trade(date, o, GAP_STOP, f"{why}_gap", thin)
                if why == "daily_loss_stop":
                    risk.block_day()
            elif not math.isnan(bar.get("pre_low", np.nan)):
                extreme = bar["pre_low"] if pos.side > 0 else bar["pre_high"]
                if (extreme - eff) * pos.side <= 0:
                    close_trade(date, eff, STOP, why, thin)
                    if why == "daily_loss_stop":
                        risk.block_day()

        # ---- B. RTH open: execute orders decided at the previous close ----
        rth_open = bar["rth_open"]
        if pending is not None:
            if pending["type"] == "exit" and pos is not None:
                close_trade(date, rth_open, MARKET, pending["reason"], thin)
            elif pending["type"] == "entry" and pos is None:
                pos = _try_entry(pending, date, rth_open, thin, hole, ledger, costs, risk, spec, events,
                                 instrument, regimes)
            pending = None
        ledger.mark(instrument, rth_open)

        # ---- C. post-open: resting stop for the rest of the session ----
        if pos is not None:
            dstop = risk.daily_stop_price(day_start_equity, ledger.equity(), rth_open, pos.side, pos.contracts)
            eff, why = _effective_stop(pos, dstop)
            if (rth_open - eff) * pos.side <= 0 and pos.entry_date != date:
                close_trade(date, rth_open, GAP_STOP, f"{why}_gap", thin)
            else:
                extreme = bar["post_low"] if pos.side > 0 else bar["post_high"]
                if (extreme - eff) * pos.side <= 0:
                    close_trade(date, eff, STOP, why, thin)
            if pos is None and why == "daily_loss_stop":
                risk.block_day()

        # ---- D. close: mark, drawdown halt ----
        ledger.mark(instrument, bar["close"])
        equity = ledger.equity()
        peak = max(peak, equity)
        if not risk.halted and risk.drawdown_breached(peak, equity):
            risk.halt(f"max drawdown {risk.limits.max_drawdown_halt_pct}% breached on {date.date()}")
            events.append({"date": date, "event": "halt", "detail": risk.halt_reason})
            if pos is not None:
                pending = {"type": "exit", "reason": "drawdown_halt"}
        eq_curve.append((date, equity))
        in_mkt.append((date, pos is not None))

        # ---- E. decision on the completed bar ----
        if pos is not None:
            pos.bars_held += 1
            pos.best_close = max(pos.best_close, bar["close"]) if pos.side > 0 else min(pos.best_close, bar["close"])
        if pending is None and date < win.index[-1]:
            view = PositionView(pos.side, pos.entry_price, pos.stop, pos.bars_held, pos.best_close) if pos else PositionView()
            d = strategy.decide(rows[i], view)
            if pos is not None:
                if d.exit:
                    pending = {"type": "exit", "reason": d.reason or "signal_exit"}
                elif d.stop is not None and math.isfinite(d.stop):
                    new = _round_stop(spec, d.stop, pos.side)
                    pos.stop = max(pos.stop, new) if pos.side > 0 else min(pos.stop, new)
            elif d.entry_side != 0:
                if risk.halted:
                    events.append({"date": date, "event": "entry_blocked", "detail": "halted"})
                elif d.stop_distance is None or not math.isfinite(d.stop_distance) or d.stop_distance <= 0:
                    events.append({"date": date, "event": "entry_blocked", "detail": "invalid stop distance"})
                else:
                    mult = 1.0
                    if entry_filter is not None:
                        mult = float(entry_filter(date, d.entry_side, rows[i]))
                    pending = {"type": "entry", "side": d.entry_side, "stop_distance": d.stop_distance,
                               "reason": d.reason, "signal_date": date, "size_multiplier": mult}
            elif d.reason.startswith("no-trade"):
                events.append({"date": date, "event": "no_trade", "detail": d.reason})
        prev_date = date

    # ---- end of window: close anything open at the final close ----
    if pos is not None:
        close_trade(win.index[-1], win["close"].iloc[-1], MARKET, "end_of_test")
        eq_curve[-1] = (win.index[-1], ledger.equity())
    ledger.check_invariants()

    eq = pd.Series(dict(eq_curve), name="equity")
    tr = pd.DataFrame(trades)
    ev = pd.DataFrame(events)
    return BacktestResult(strategy.label, eq, tr, ev, pd.Series(dict(in_mkt)), starting_equity,
                          dict(strategy.params), risk.halt_reason)


def _effective_stop(pos: OpenTrade, daily_stop: float | None) -> tuple[float, str]:
    if daily_stop is None:
        return pos.stop, "stop"
    if pos.side > 0:
        return (daily_stop, "daily_loss_stop") if daily_stop > pos.stop else (pos.stop, "stop")
    return (daily_stop, "daily_loss_stop") if daily_stop < pos.stop else (pos.stop, "stop")


def _try_entry(pending, date, rth_open, thin, hole, ledger, costs, risk, spec, events, instrument,
               regimes) -> OpenTrade | None:
    side = pending["side"]
    ev = {"date": date, "event": "entry_signal", "side": side, "signal_date": pending["signal_date"],
          "size_multiplier": pending["size_multiplier"]}
    if hole:
        ev.update(event="entry_blocked", detail="data hole before this session")
        events.append(ev)
        return None
    fill = costs.fill_price(rth_open, side, MARKET, thin)
    stop = _round_stop(spec, fill - side * pending["stop_distance"], side)
    sz = risk.size_entry(ledger.equity(), fill, stop, side, size_multiplier=pending["size_multiplier"])
    if not sz.approved:
        ev.update(event="entry_rejected", detail=sz.rejected_reason)
        events.append(ev)
        return None
    fee = costs.fees(sz.contracts)
    ledger.fill(instrument, side, sz.contracts, fill, fee, ts=date, tag="entry")
    regime = ""
    if regimes is not None and pending["signal_date"] in regimes.index:
        regime = str(regimes.loc[pending["signal_date"]])
    trade = OpenTrade(side, sz.contracts, date, fill, stop, stop, sz.risk_dollars, fee, pending["reason"],
                      regime=regime, best_close=fill)
    ev.update(event="entry_filled", contracts=sz.contracts, price=fill, stop=stop, binding=sz.binding_limit)
    events.append(ev)
    return trade


def buy_and_hold(bars: pd.DataFrame, spec: ContractSpec, costs: CostModel, start, end,
                 starting_equity: float, leverage: float = 1.0, instrument: str = "MES") -> BacktestResult:
    """Long ~`leverage` x equity in notional, rebalanced at the first session of each
    month (at the RTH open), paying fees, slippage and quarterly roll costs."""
    win = bars.loc[pd.Timestamp(start): pd.Timestamp(end) if end else None]
    ledger = Ledger(starting_equity, {instrument: spec.multiplier})
    rolls = set(roll_dates(win.index[0].date(), win.index[-1].date(), spec))
    eq, prev, held = [], None, 0
    for date, bar in win.iterrows():
        if held and prev is not None and any(prev.date() < r <= date.date() for r in rolls):
            ledger.charge(costs.roll_cost(held), "roll")
        if prev is None or date.month != prev.month:
            ledger.mark(instrument, bar["rth_open"])
            target = max(int(ledger.equity() * leverage // (bar["rth_open"] * spec.multiplier)), 0)
            diff = target - held
            if diff:
                side = 1 if diff > 0 else -1
                fill = costs.fill_price(bar["rth_open"], side, MARKET)
                ledger.fill(instrument, side, abs(diff), fill, costs.fees(abs(diff)), ts=date)
                held = target
        ledger.mark(instrument, bar["close"])
        eq.append((date, ledger.equity()))
        prev = date
    s = pd.Series(dict(eq), name="equity")
    return BacktestResult(f"buy_hold_{leverage}x", s, pd.DataFrame(), pd.DataFrame(),
                          pd.Series(True, index=s.index), starting_equity, {"leverage": leverage})

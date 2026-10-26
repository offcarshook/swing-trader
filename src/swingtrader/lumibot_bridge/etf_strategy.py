"""Lumibot adapter for the ETF swing book (the ONLY component that submits ETF orders).

Responsibilities are split exactly as in docs/FRAMEWORK_INTEGRATION.md:
  * signals    -> swingtrader.etf.strategies (computed here from COMPLETED bars only),
  * research   -> optional `entry_filter` (TradingAgents records via agents/etf_research.py),
                  which may only scale an entry down or veto it,
  * risk       -> swingtrader.etf.risk.PortfolioRiskGate (final deterministic veto),
  * orders     -> this class, through OrderGuard (idempotent client ids) and the global
                  order-submission switch (safety.order_submission_enabled),
  * accounting -> Lumibot's broker (authoritative cash/positions); the adapter's own book is
                  reconciled against it every iteration and entries stop on any mismatch.

Verified Lumibot 4.6.30 timing (PandasDataBacktesting, daily bars stamped at the session date):
an order submitted in the iteration for session D fills at D's OPEN; get_historical_prices()
in that iteration already returns bar D, so `completed()` drops every bar >= D (look-ahead guard).
Consequences vs the reference engine (documented in docs/TAURIC_LUMIBOT_PARITY.md):
  * protective stop / target orders are placed in on_filled_order, so they first act on D+1;
  * the time stop is a market order at the open after session `max_hold` (no market-on-close);
  * dividends: in this PandasDataBacktesting daily path Lumibot 4.6.30 returns the ex-date dividend
    from get_yesterday_dividend() but never credits it to cash (verified with a minimal probe that
    held QQQ over the 2019-03-18 ex-date; dividend shifts of -1/0/+1/+2 sessions made no difference).
    The adapter therefore records each entitlement (holder of record at the previous close) as a
    `dividend_entitlement` ledger event; Lumibot's cash/equity exclude dividends and the parity
    report adds them back explicitly. A real paper broker credits dividends itself.
Supported families: close-decided market entries (dip, short, mr, mrshort, mom). Breakout
stop-entries, open-decided gap entries and the calendar family are rejected at start-up.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
from lumibot.entities import Asset
from lumibot.strategies import Strategy as LumiStrategy

import swingtrader
from swingtrader.etf.data import signal_view
from swingtrader.etf.engine import RiskCfg
from swingtrader.etf.risk import PortfolioRiskGate
from swingtrader.etf.strategies import Params, signals
from swingtrader.orders import DuplicateOrderError, OrderGuard, OrderIntent
from swingtrader.safety import order_submission_enabled

SUPPORTED_FAMILIES = {"dip", "short", "mr", "mrshort", "mom"}
HISTORY = 400


def lumibot_supported(params: list[dict]) -> tuple[list[dict], list[str]]:
    """Split a frozen book into the members this adapter can execute and the excluded ids."""
    keep = [d for d in params if d["family"] in SUPPORTED_FAMILIES]
    return keep, [d.get("id", d["family"]) for d in params if d["family"] not in SUPPORTED_FAMILIES]


def lumibot_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Executable daily bars for Lumibot (session date 00:00 New York) with the ex-date dividend."""
    out = pd.DataFrame({"open": df["open"], "high": df["high"], "low": df["low"], "close": df["close"],
                        "volume": df.get("volume", 0.0)})
    if "dividend" in df:
        out["dividend"] = df["dividend"].fillna(0.0)
    out.index = pd.DatetimeIndex(df.index).tz_localize("America/New_York")
    out.index.name = "datetime"
    return out


def completed(df: pd.DataFrame, now) -> pd.DataFrame:
    return df[df.index < pd.Timestamp(now).tz_localize(None).normalize()]


def next_session_signals(hist: pd.DataFrame, p: Params, next_day) -> list[dict]:
    """Signals decided on the last COMPLETED bar of `hist` for the session `next_day`.
    A placeholder row for next_day is appended so `signals()` can emit entry_i = len(hist);
    every indicator is causal, so the placeholder cannot influence the decision."""
    sv = signal_view(hist)
    nxt = pd.DataFrame(np.nan, index=[pd.Timestamp(next_day)], columns=sv.columns)
    ext = pd.concat([sv, nxt])
    sg = signals(ext, p)
    sg = sg[sg["entry_i"] == len(hist)]
    out = []
    fac = float(hist["adj_factor"].iloc[-1]) if "adj_factor" in hist else 1.0
    for _, r in sg.iterrows():
        if not math.isfinite(r["stop_dist"]):
            continue
        out.append({"dir": int(r["dir"]), "stop_dist": float(r["stop_dist"]) / fac,
                    "signal_date": str(hist.index[-1].date())})
    return out


class EtfSwingLumibot(LumiStrategy):
    parameters = {"params": None, "risk": None, "signal_bars": None, "ledger": None, "entry_filter": None,
                  "order_guard_file": None, "orders_switch_file": None, "kill_switch_file": None,
                  "kill_policy": "keep_protection", "state_file": None, "heartbeat_file": None,
                  "max_staleness_days": 4, "strategy_label": "etf_mr_book"}

    # ------------------------------------------------------------------ setup
    def initialize(self):
        self.sleeptime = "1D"
        p = self.parameters
        self.book_params = [Params(**{k: v for k, v in d.items() if k in Params.__dataclass_fields__})
                            for d in p["params"]]
        bad = [q.id for q in self.book_params if q.family not in SUPPORTED_FAMILIES]
        if bad:
            raise ValueError(f"Lumibot adapter does not support these families yet: {bad}")
        self.pmap = {q.id: q for q in self.book_params}
        self.risk = RiskCfg.from_dict(p["risk"])
        if self.risk.stack_symbols:
            raise ValueError("Lumibot adapter keeps one position per ETF (broker positions are per asset)")
        self.gate = PortfolioRiskGate(self.risk)
        self.bars = p["signal_bars"]
        self.assets = {s: Asset(s, asset_type=Asset.AssetType.STOCK) for s in self.bars}
        self.ledger = p["ledger"] if p["ledger"] is not None else []
        gf = p.get("order_guard_file")
        self.guard = OrderGuard(Path(gf) if gf else None, max_orders_per_session=200)
        self.book: dict[str, dict] = {}        # sym -> position state
        self.pending: dict[str, dict] = {}     # sym -> candidate waiting for its entry fill
        self.entries_blocked_reason = None
        self.dividends_receivable = 0.0   # entitlements Lumibot's backtest broker does not credit
        self.last_day = None
        self.recovered = False

    # --------------------------------------------------------------- helpers
    def _log(self, event: str, **kw):
        self.ledger.append({"ts": str(self.get_datetime()), "event": event, **kw})

    def _submit(self, sym: str, purpose: str, side: int, qty: int, order_type: str = "market", price=None):
        ok, why = order_submission_enabled(self.parameters.get("orders_switch_file"))
        if not ok:
            self._log("order_blocked", sym=sym, purpose=purpose, reason=why)
            return None
        assert swingtrader.LIVE_TRADING_ENABLED is False  # noqa: S101 - hard invariant
        day = str(pd.Timestamp(self.get_datetime()).date())
        intent = OrderIntent(self.parameters["strategy_label"], sym, day, purpose, side, int(qty), order_type,
                             stop_price=price)
        try:
            self.guard.check(intent, broker_is_paper=True)
        except DuplicateOrderError as exc:
            self._log("duplicate_blocked", sym=sym, purpose=purpose, reason=str(exc))
            return None
        kw = {}
        if order_type == "stop":
            kw["stop_price"] = float(price)
        elif order_type == "limit":
            kw["limit_price"] = float(price)
        o = self.create_order(self.assets[sym], int(qty), "buy" if side > 0 else "sell", order_type=order_type, **kw)
        o = self.submit_order(o)
        self.guard.record(intent)
        self._log("order_submitted", sym=sym, purpose=purpose, side=side, qty=int(qty), type=order_type,
                  price=price, client_id=intent.client_id)
        return o

    def _broker_qty(self, sym: str) -> int:
        pos = self.get_position(self.assets[sym])
        return int(pos.quantity) if pos is not None and pos.quantity else 0

    def _reconcile(self) -> bool:
        ok = True
        for s in self.bars:
            want = self.book[s]["dir"] * self.book[s]["shares"] if s in self.book else 0
            have = self._broker_qty(s)
            if want != have and s not in self.pending:
                ok = False
                self._log("reconcile_mismatch", sym=s, internal=want, broker=have)
        return ok

    def _persist(self):
        """Atomic snapshot of the adapter's own state (restart recovery); order objects excluded."""
        path = self.parameters.get("state_file")
        if not path:
            return
        import json
        from pathlib import Path
        snap = {"saved_at": str(self.get_datetime()), "book": {s: {k: v for k, v in st.items()
                                                                if not k.endswith("_order")}
                                                            for s, st in self.book.items()},
                "dividends_receivable": self.dividends_receivable,
                "gate": {"prev_equity": self.gate.prev_equity, "peak": self.gate.peak,
                         "halted_on": self.gate.halted_on}}
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(snap, indent=1, default=str))
        tmp.replace(p)

    def _recover(self):
        """On (re)start: reload the persisted book and gate state, then reconcile with the broker.
        Any disagreement blocks new entries until a human resolves it (exits still run)."""
        import json
        from pathlib import Path
        self.recovered = True
        path = self.parameters.get("state_file")
        if not path or not Path(path).exists():
            return
        snap = json.loads(Path(path).read_text())
        self.book = {s: st for s, st in snap.get("book", {}).items() if s in self.bars}
        self.dividends_receivable = float(snap.get("dividends_receivable", 0.0))
        g = snap.get("gate", {})
        self.gate.prev_equity = float(g.get("prev_equity", self.gate.prev_equity))
        self.gate.peak = float(g.get("peak", self.gate.peak))
        self.gate.halted_on = g.get("halted_on")
        self._log("state_recovered", positions=list(self.book), halted_on=self.gate.halted_on)

    def _cancel_protection(self, st: dict):
        for k in ("stop_order", "target_order"):
            o = st.get(k)
            if o is not None:
                self.cancel_order(o)
                st[k] = None

    # ------------------------------------------------------------ iteration
    def on_trading_iteration(self):
        now = self.get_datetime()
        day = pd.Timestamp(now).tz_localize(None).normalize()
        if not self.recovered:
            self._recover()
        hist = {s: completed(b, now).tail(HISTORY) for s, b in self.bars.items()}
        hb = self.parameters.get("heartbeat_file")
        if hb:
            from pathlib import Path
            Path(hb).parent.mkdir(parents=True, exist_ok=True)
            Path(hb).write_text(pd.Timestamp.now(tz="UTC").isoformat() + " strategy_clock=" + str(now))
        # Point-in-time equity: broker cash + broker positions marked at the last COMPLETED close.
        # get_portfolio_value() is NOT used for decisions: in a daily PandasDataBacktesting run it is
        # frequently marked at the current session's close, which is unknown at decision time.
        pit = float(self.get_cash()) + self.dividends_receivable + sum(
            self._broker_qty(s) * float(h["close"].iloc[-1]) for s, h in hist.items() if len(h))
        self._log("iteration", pit_equity=pit, lumibot_portfolio_value=float(self.get_portfolio_value()),
                  cash=float(self.get_cash()))
        if self.last_day is not None:
            self.gate.on_close(self.last_day, pit)
        self.last_day = day
        tradable = {s for s, b in self.bars.items() if day in b.index}
        reconciled = self._reconcile()

        # ---- dividend entitlements: positions in the book at this decision point were held at the
        # previous close, i.e. they are holders of record for an ex-date today
        for s, st in self.book.items():
            b = self.bars[s]
            if day in b.index and "dividend" in b and b.at[day, "dividend"] > 0:
                amt = st["dir"] * float(b.at[day, "dividend"]) * st["shares"]
                st["dividends"] = st.get("dividends", 0.0) + amt
                self.dividends_receivable += amt
                self._log("dividend_entitlement", sym=s, per_share=float(b.at[day, "dividend"]),
                          shares=st["shares"], amount=amt)

        # ---- exits (decided on completed bars, filled at today's open)
        for s, st in list(self.book.items()):
            if s not in tradable:
                continue
            st["held"] += 1
            q = self.pmap[st["pid"]]
            exit_reason = None
            if st["held"] > q.max_hold:
                exit_reason = "time"
            elif q.exit_sma and len(hist[s]) >= q.exit_sma:
                ac = signal_view(hist[s])["close"]
                if st["dir"] * (ac.iloc[-1] - ac.tail(q.exit_sma).mean()) > 0:
                    exit_reason = "sma_exit"
            if exit_reason:
                if self._broker_qty(s) != st["dir"] * st["shares"]:
                    # never send an exit the broker cannot match: on a real account it would open
                    # a position in the opposite direction. Leave it for a human to reconcile.
                    self._log("exit_skipped_mismatch", sym=s, internal=st["dir"] * st["shares"],
                              broker=self._broker_qty(s), reason=exit_reason)
                    continue
                self._cancel_protection(st)
                st["exit_reason"] = exit_reason
                self._submit(s, "exit", -st["dir"], st["shares"])

        # ---- account-level entry blocks (exits and protective orders above still run)
        from pathlib import Path
        stale = [s for s, h in hist.items() if s in tradable and
                 (not len(h) or (day - h.index[-1]).days > int(self.parameters.get("max_staleness_days", 4)))]
        kill = self.parameters.get("kill_switch_file")
        if kill and Path(kill).exists():
            self._log("entries_blocked", reason="kill switch file present")
            if self.parameters.get("kill_policy") == "flatten":
                for s, st in list(self.book.items()):
                    if "exit_reason" not in st and s in tradable and self._broker_qty(s) == st["dir"] * st["shares"]:
                        self._cancel_protection(st)
                        st["exit_reason"] = "kill_flatten"
                        self._submit(s, "exit", -st["dir"], st["shares"])
            self._persist()
            return
        if stale:
            self._log("entries_blocked", reason=f"stale data: {stale}")
            self._persist()
            return
        if not reconciled:
            self._log("entries_blocked", reason="reconciliation mismatch")
            self._persist()
            return
        positions = [{"sym": s, "pid": st["pid"], "dir": st["dir"], "shares": st["shares"],
                      "risk_usd": st["risk_usd"], "mark": float(hist[s]["close"].iloc[-1])}
                     for s, st in self.book.items() if "exit_reason" not in st]
        for rank, q in enumerate(self.book_params):
            for s in sorted(self.bars):
                if s not in tradable or len(hist[s]) < 250 or s in self.pending:
                    continue
                for sg in next_session_signals(hist[s], q, day):
                    ref = float(hist[s]["close"].iloc[-1])   # sizing estimate; stop re-anchored on the fill
                    cand = {"sym": s, "pid": q.id, "dir": sg["dir"], "stop_dist": sg["stop_dist"],
                            "signal_date": sg["signal_date"], "date": day, "rank": rank}
                    mult, why = 1.0, ""
                    if self.parameters.get("entry_filter") is not None:
                        mult, why = self.parameters["entry_filter"](cand)
                    dec = self.gate.check_entry(day=day, sym=s, pid=q.id, direction=sg["dir"], fill=ref,
                                                stop_dist=sg["stop_dist"], positions=positions, mult=mult)
                    self._log("signal", sym=s, pid=q.id, dir=sg["dir"], decision=dec.reason, shares=dec.shares,
                              overlay=why, signal_date=sg["signal_date"])
                    if not dec.approved:
                        continue
                    if self._submit(s, "entry", sg["dir"], dec.shares) is not None:
                        self.pending[s] = {**cand, "shares": dec.shares}
                        positions.append({"sym": s, "pid": q.id, "dir": sg["dir"], "shares": dec.shares,
                                          "risk_usd": dec.risk_usd, "mark": ref})
        self._persist()

    # ---------------------------------------------------------------- fills
    def on_filled_order(self, position, order, price, quantity, multiplier):
        sym = order.asset.symbol
        side = 1 if str(order.side).lower().endswith("buy") else -1
        price = float(price)
        self._log("fill", sym=sym, side=side, qty=float(quantity), price=price, type=str(order.order_type))
        if sym in self.pending and side == self.pending[sym]["dir"]:
            c = self.pending.pop(sym)
            q = self.pmap[c["pid"]]
            st = {"pid": c["pid"], "dir": c["dir"], "shares": int(quantity), "entry": price, "held": 0,
                  "stop": price - c["dir"] * c["stop_dist"], "risk_usd": int(quantity) * c["stop_dist"],
                  "entry_date": str(pd.Timestamp(self.get_datetime()).date()), "signal_date": c["signal_date"]}
            st["target"] = None if q.target_r is None else price + c["dir"] * q.target_r * c["stop_dist"]
            self.book[sym] = st
            st["stop_order"] = self._submit(sym, "stop", -c["dir"], st["shares"], "stop", st["stop"])
            if st["target"] is not None:
                st["target_order"] = self._submit(sym, "target", -c["dir"], st["shares"], "limit", st["target"])
            self._persist()
            return
        st = self.book.get(sym)
        if st is None or side != -st["dir"]:
            return
        typ = str(order.order_type).lower()
        reason = st.get("exit_reason") or ("stop" if "stop" in typ else "target" if "limit" in typ else "exit")
        self._cancel_protection(st)
        self._log("trade_closed", sym=sym, pid=st["pid"], dir=st["dir"], shares=st["shares"], entry=st["entry"],
                  exit=price, entry_date=st.get("entry_date"), exit_date=str(pd.Timestamp(self.get_datetime()).date()),
                  reason=reason, pnl_ex_costs=st["dir"] * (price - st["entry"]) * st["shares"],
                  dividends=st.get("dividends", 0.0))
        del self.book[sym]
        self._persist()

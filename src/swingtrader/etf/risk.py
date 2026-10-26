"""The single deterministic portfolio risk gate for ETF entries.

Used by the reference engine (etf/engine.py), the Lumibot strategy adapter and the paper runner,
so every execution path applies identical limits. Nothing upstream (strategy, research overlay,
LLM) can override it: an overlay multiplier is clamped to [0, 1] here, and lockouts are checked
before anything else.

State: the gate tracks the equity path it is told about (`on_close`) to run the daily-loss and
drawdown lockouts. A drawdown lockout is sticky: only a NEW gate (new simulation / paper session
after an explicit reset) clears it.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class Decision:
    shares: int
    risk_usd: float
    reason: str          # "accepted" or the rejection reason

    @property
    def approved(self) -> bool:
        return self.reason == "accepted"


class PortfolioRiskGate:
    def __init__(self, risk, start_equity: float | None = None):
        self.risk = risk
        self.prev_equity = start_equity if start_equity is not None else risk.equity
        self.peak = self.prev_equity
        self.daily_locked = False
        self.halted_on: str | None = None
        self.kill_from = pd.Timestamp(risk.kill_switch_from) if risk.kill_switch_from else None

    # ------------------------------------------------------------------ state
    def on_close(self, day, equity: float) -> None:
        r = self.risk
        self.daily_locked = (r.daily_loss_lockout_pct is not None
                             and equity / self.prev_equity - 1 <= -r.daily_loss_lockout_pct / 100)
        self.peak = max(self.peak, equity)
        if self.halted_on is None and r.max_dd_lockout_pct is not None \
                and equity / self.peak - 1 <= -r.max_dd_lockout_pct / 100:
            self.halted_on = str(pd.Timestamp(day).date())
        self.prev_equity = equity

    @property
    def halted(self) -> bool:
        return self.halted_on is not None

    def blocked(self, day) -> str | None:
        """Account-level reasons that block every new entry today."""
        if self.halted:
            return "dd_lockout"
        if self.kill_from is not None and pd.Timestamp(day) >= self.kill_from:
            return "kill_switch"
        if self.daily_locked:
            return "daily_loss_lockout"
        return None

    # ------------------------------------------------------------------ entry
    def check_entry(self, *, day, sym: str, pid: str, direction: int, fill: float, stop_dist: float,
                    positions: list[dict], equity: float | None = None, mult: float = 1.0) -> Decision:
        """positions: open positions as dicts with sym, pid, dir, shares, risk_usd and `mark`
        (latest executable price; entry price if never marked)."""
        r = self.risk
        eq = self.prev_equity if equity is None else equity
        why = self.blocked(day)
        if why:
            return Decision(0, 0.0, why)
        if any(p["sym"] == sym and (not r.stack_symbols or p["pid"] == pid) for p in positions):
            return Decision(0, 0.0, "same_symbol")
        mult = min(max(float(mult), 0.0), 1.0)
        if mult <= 0:
            return Decision(0, 0.0, "overlay_veto")
        shares = int(r.risk_pct / 100 * eq * mult // stop_dist) if stop_dist > 0 else 0
        if shares <= 0:
            return Decision(0, 0.0, "zero_size")
        risk_usd = shares * stop_dist
        if sum(p["risk_usd"] for p in positions) + risk_usd > r.max_open_risk_pct / 100 * eq + 1e-9:
            return Decision(0, 0.0, "open_risk_cap")
        clusters = r.clusters or {}
        cl = clusters.get(sym)
        if r.max_cluster_risk_pct is not None and cl is not None:
            cl_risk = sum(p["risk_usd"] for p in positions if clusters.get(p["sym"]) == cl)
            if cl_risk + risk_usd > r.max_cluster_risk_pct / 100 * eq + 1e-9:
                return Decision(0, 0.0, "cluster_risk_cap")
        if sum(p["shares"] * p["mark"] for p in positions) + shares * fill > r.max_gross * eq:
            return Decision(0, 0.0, "gross_cap")
        if r.max_net_exposure is not None:
            net = sum(p["dir"] * p["shares"] * p["mark"] for p in positions) + direction * shares * fill
            if abs(net) > r.max_net_exposure * eq:
                return Decision(0, 0.0, "net_cap")
        return Decision(shares, risk_usd, "accepted")

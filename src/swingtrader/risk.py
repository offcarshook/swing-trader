"""Deterministic risk controls. Nothing outside this module can size a position.

The AI research overlay may only pass a size multiplier in [0, 1] which is
applied BEFORE these limits; every limit here is then enforced regardless.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from swingtrader.contracts import ContractSpec
from swingtrader.costs import CostModel


@dataclass(frozen=True)
class RiskLimits:
    risk_per_trade_pct: float
    max_open_risk_pct: float
    max_notional_leverage: float
    max_margin_utilization: float
    initial_margin_per_contract: float
    max_contracts: int
    daily_loss_limit_pct: float
    max_drawdown_halt_pct: float
    min_stop_ticks: int

    @classmethod
    def from_config(cls, risk: dict) -> RiskLimits:
        return cls(**{k: risk[k] for k in cls.__dataclass_fields__})

    def __post_init__(self):
        if not 0 < self.risk_per_trade_pct <= 10:
            raise ValueError("risk_per_trade_pct must be in (0, 10]")
        if self.max_open_risk_pct < self.risk_per_trade_pct:
            raise ValueError("max_open_risk_pct must be >= risk_per_trade_pct")
        if not 0 < self.max_drawdown_halt_pct < 100 or not 0 < self.daily_loss_limit_pct < 100:
            raise ValueError("loss limits must be in (0, 100)")
        if self.max_contracts < 1 or self.min_stop_ticks < 1:
            raise ValueError("max_contracts and min_stop_ticks must be >= 1")


@dataclass
class SizingDecision:
    contracts: int
    risk_per_contract: float
    risk_dollars: float
    binding_limit: str
    rejected_reason: str | None = None
    caps: dict = field(default_factory=dict)

    @property
    def approved(self) -> bool:
        return self.contracts > 0 and self.rejected_reason is None


class RiskManager:
    """Stateful only for the halt / day-block flags; sizing itself is pure."""

    def __init__(self, limits: RiskLimits, spec: ContractSpec, costs: CostModel):
        self.limits = limits
        self.spec = spec
        self.costs = costs
        self.halted = False
        self.halt_reason: str | None = None
        self.day_blocked = False

    # ------------------------------------------------------------------ sizing
    def size_entry(
        self,
        equity: float,
        entry_price: float,
        stop_price: float,
        side: int,
        open_risk: float = 0.0,
        open_contracts: int = 0,
        size_multiplier: float = 1.0,
    ) -> SizingDecision:
        L, spec = self.limits, self.spec
        caps: dict = {}

        def reject(reason: str) -> SizingDecision:
            return SizingDecision(0, 0.0, 0.0, reason, rejected_reason=reason, caps=caps)

        if self.halted:
            return reject(f"halted: {self.halt_reason}")
        if self.day_blocked:
            return reject("daily loss limit hit this session")
        if equity <= 0 or not math.isfinite(equity):
            return reject("non-positive equity")
        if side not in (1, -1):
            return reject("invalid side")
        if not (math.isfinite(entry_price) and math.isfinite(stop_price)):
            return reject("non-finite price")
        stop_dist = (entry_price - stop_price) * side
        if stop_dist <= 0:
            return reject("stop on wrong side of entry")
        if stop_dist < L.min_stop_ticks * spec.tick_size:
            return reject("stop closer than min_stop_ticks")
        # The overlay can only shrink: clamp into [0, 1] no matter what it sent.
        mult = min(max(float(size_multiplier), 0.0), 1.0) if math.isfinite(size_multiplier) else 0.0
        if mult == 0.0:
            return reject("size multiplier is zero (vetoed)")

        per_contract = stop_dist * spec.multiplier + self.costs.est_round_trip_per_contract()
        caps["risk_per_trade"] = math.floor(equity * L.risk_per_trade_pct / 100 * mult / per_contract)
        caps["open_risk"] = math.floor(max(equity * L.max_open_risk_pct / 100 - open_risk, 0) / per_contract)
        notional = entry_price * spec.multiplier
        caps["notional"] = math.floor(equity * L.max_notional_leverage / notional) - abs(open_contracts)
        caps["margin"] = math.floor(equity * L.max_margin_utilization / L.initial_margin_per_contract) - abs(open_contracts)
        caps["max_contracts"] = L.max_contracts - abs(open_contracts)
        binding = min(caps, key=caps.get)
        n = max(int(caps[binding]), 0)
        if n < 1:
            return SizingDecision(0, per_contract, 0.0, binding,
                                  rejected_reason=f"limit '{binding}' allows < 1 contract", caps=caps)
        return SizingDecision(n, per_contract, n * per_contract, binding, caps=caps)

    # ------------------------------------------------------------- loss limits
    def daily_loss_breached(self, day_start_equity: float, equity: float) -> bool:
        return equity <= day_start_equity * (1 - self.limits.daily_loss_limit_pct / 100)

    def daily_stop_price(self, day_start_equity: float, equity_at_ref: float, ref_price: float,
                         side: int, contracts: int) -> float | None:
        """Price at which the open position would take the session's equity to the
        daily loss limit. Acts as an additional protective stop for the session."""
        if contracts == 0:
            return None
        floor_equity = day_start_equity * (1 - self.limits.daily_loss_limit_pct / 100)
        room = equity_at_ref - floor_equity
        if room <= 0:
            return ref_price
        move = room / (abs(contracts) * self.spec.multiplier)
        return ref_price - side * move

    def drawdown_breached(self, peak_equity: float, equity: float) -> bool:
        return equity <= peak_equity * (1 - self.limits.max_drawdown_halt_pct / 100)

    def halt(self, reason: str) -> None:
        self.halted = True
        self.halt_reason = reason

    def reset_halt(self, confirm: str) -> None:
        """Manual reset only; requires an explicit confirmation phrase."""
        if confirm != "I have reviewed the drawdown":
            raise PermissionError("halt reset requires explicit confirmation")
        self.halted = False
        self.halt_reason = None

    def start_session(self) -> None:
        self.day_blocked = False

    def block_day(self) -> None:
        self.day_blocked = True

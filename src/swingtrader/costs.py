"""Transaction-cost model: commissions, exchange fees, spread/slippage, gaps, rolls.

All prices move AGAINST the trader. Everything scales with `cost_multiplier`
so sensitivity runs (2x, 3x) stress fees and slippage together.
"""

from __future__ import annotations

from dataclasses import dataclass

from swingtrader.contracts import ContractSpec

MARKET = "market"
STOP = "stop"
GAP_STOP = "gap_stop"


@dataclass(frozen=True)
class CostModel:
    spec: ContractSpec
    commission_per_side: float
    exchange_fees_per_side: float
    market_slippage_ticks: float
    stop_slippage_ticks: float
    gap_extra_ticks: float
    roll_slippage_ticks: float
    cost_multiplier: float = 1.0

    @classmethod
    def from_config(cls, spec: ContractSpec, costs: dict, multiplier: float | None = None) -> CostModel:
        return cls(
            spec=spec,
            commission_per_side=costs["commission_per_side"],
            exchange_fees_per_side=costs["exchange_fees_per_side"],
            market_slippage_ticks=costs["market_slippage_ticks"],
            stop_slippage_ticks=costs["stop_slippage_ticks"],
            gap_extra_ticks=costs["gap_extra_ticks"],
            roll_slippage_ticks=costs["roll_slippage_ticks"],
            cost_multiplier=costs.get("cost_multiplier", 1.0) if multiplier is None else multiplier,
        )

    # ---- fees ($) ----
    def fees(self, contracts: int) -> float:
        per_side = self.commission_per_side + self.exchange_fees_per_side
        return abs(contracts) * per_side * self.cost_multiplier

    # ---- slippage (price) ----
    def slippage_ticks(self, kind: str, thin_session: bool = False) -> float:
        base = {
            MARKET: self.market_slippage_ticks,
            STOP: self.stop_slippage_ticks,
            GAP_STOP: self.market_slippage_ticks + self.gap_extra_ticks,
        }[kind]
        if thin_session:
            base *= 2.0
        return base * self.cost_multiplier

    def fill_price(self, ref_price: float, side: int, kind: str, thin_session: bool = False) -> float:
        """side=+1 buying, -1 selling. Buys fill higher, sells lower."""
        if side not in (1, -1):
            raise ValueError("side must be +1 or -1")
        slip = self.slippage_ticks(kind, thin_session) * self.spec.tick_size
        return ref_price + side * slip

    # ---- rolls ($) ----
    def roll_cost(self, contracts: int) -> float:
        """Closing the expiring and opening the next contract: 2 legs of fees + slippage.
        (Calendar-spread orders are usually cheaper; this is deliberately conservative.)"""
        legs = 2
        slip = legs * self.roll_slippage_ticks * self.cost_multiplier * self.spec.tick_value * abs(contracts)
        return legs * self.fees(contracts) + slip

    # ---- sizing helper ----
    def est_round_trip_per_contract(self) -> float:
        """Estimated $ cost of entering at market and leaving on a stop, per contract."""
        ticks = self.slippage_ticks(MARKET) + self.slippage_ticks(STOP)
        return 2 * self.fees(1) + ticks * self.spec.tick_value

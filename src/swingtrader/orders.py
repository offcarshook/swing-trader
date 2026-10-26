"""Order intents, idempotency and duplicate-order prevention.

Every order the system wants is first expressed as an OrderIntent whose
client_id is a deterministic hash of (strategy, instrument, session, purpose).
Re-running the same session (crash/restart, duplicate scheduler tick) therefore
produces the same id, and the OrderGuard refuses to submit it twice.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import swingtrader


@dataclass(frozen=True)
class OrderIntent:
    strategy: str
    instrument: str
    session: str          # YYYY-MM-DD the order is meant for
    purpose: str          # entry | exit | stop | roll_close | roll_open | flatten
    side: int             # +1 buy / -1 sell
    qty: int
    order_type: str       # market | stop
    stop_price: float | None = None

    @property
    def client_id(self) -> str:
        key = f"{self.strategy}|{self.instrument}|{self.session}|{self.purpose}|{self.side}"
        return "st-" + hashlib.sha256(key.encode()).hexdigest()[:16]

    def validate(self) -> None:
        if self.side not in (1, -1):
            raise ValueError("side must be +1/-1")
        if self.qty <= 0:
            raise ValueError("qty must be > 0")
        if self.order_type not in ("market", "stop"):
            raise ValueError("unsupported order type")
        if self.order_type == "stop" and not self.stop_price:
            raise ValueError("stop order needs stop_price")


class DuplicateOrderError(RuntimeError):
    pass


class LiveTradingDisabledError(RuntimeError):
    pass


class OrderGuard:
    """Remembers submitted client ids (optionally persisted to disk)."""

    def __init__(self, state_file: Path | None = None, max_orders_per_session: int = 6):
        self.state_file = state_file
        self.max_orders_per_session = max_orders_per_session
        self.submitted: dict[str, dict] = {}
        if state_file and state_file.exists():
            self.submitted = json.loads(state_file.read_text())

    def check(self, intent: OrderIntent, broker_is_paper: bool) -> None:
        intent.validate()
        if not broker_is_paper or swingtrader.LIVE_TRADING_ENABLED:
            # Defence in depth: LIVE_TRADING_ENABLED is a hard-coded False.
            raise LiveTradingDisabledError("live order execution is disabled in this project")
        if intent.client_id in self.submitted:
            raise DuplicateOrderError(f"duplicate order {intent.client_id} ({intent.purpose} {intent.session})")
        n_today = sum(1 for v in self.submitted.values() if v["session"] == intent.session)
        if n_today >= self.max_orders_per_session:
            raise DuplicateOrderError(f"order cap reached for session {intent.session}")

    def record(self, intent: OrderIntent) -> None:
        self.submitted[intent.client_id] = asdict(intent)
        if self.state_file:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.state_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.submitted, indent=1))
            tmp.replace(self.state_file)

    def submit(self, intent: OrderIntent, broker_is_paper: bool, send) -> object:
        """Check, send via callback, then record. If `send` raises, nothing is recorded."""
        self.check(intent, broker_is_paper)
        result = send(intent)
        self.record(intent)
        return result

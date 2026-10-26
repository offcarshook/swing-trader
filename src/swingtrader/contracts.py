"""Futures contract specifications and the quarterly roll calendar.

Specs are CME published values for the equity-index contracts considered in
docs/INSTRUMENT_SELECTION.md. Margins are broker-specific and change; the risk
config carries a conservative per-contract margin assumption instead.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass

QUARTERLY_MONTHS = (3, 6, 9, 12)
MONTH_CODES = {3: "H", 6: "M", 9: "U", 12: "Z"}


@dataclass(frozen=True)
class ContractSpec:
    root: str
    name: str
    exchange: str
    multiplier: float      # $ per 1.0 index point
    tick_size: float       # index points
    roll_days_before_expiry: int = 8   # CME equity-index roll convention (Thursday, 8 days prior)

    @property
    def tick_value(self) -> float:
        return self.multiplier * self.tick_size

    def points_to_dollars(self, points: float, contracts: float = 1.0) -> float:
        return points * self.multiplier * contracts

    def round_to_tick(self, price: float, direction: str = "nearest") -> float:
        """Round a price onto the tick grid. direction: nearest | up | down."""
        n = price / self.tick_size
        if direction == "up":
            n = math.ceil(n - 1e-9)
        elif direction == "down":
            n = math.floor(n + 1e-9)
        else:
            n = round(n)
        return round(n * self.tick_size, 10)


SPECS: dict[str, ContractSpec] = {
    "MES": ContractSpec("MES", "Micro E-mini S&P 500", "CME", 5.0, 0.25),
    "ES": ContractSpec("ES", "E-mini S&P 500", "CME", 50.0, 0.25),
    "MNQ": ContractSpec("MNQ", "Micro E-mini Nasdaq-100", "CME", 2.0, 0.25),
    "NQ": ContractSpec("NQ", "E-mini Nasdaq-100", "CME", 20.0, 0.25),
}


def third_friday(year: int, month: int) -> dt.date:
    d = dt.date(year, month, 1)
    first_friday = d + dt.timedelta(days=(4 - d.weekday()) % 7)
    return first_friday + dt.timedelta(days=14)


def expiries_between(start: dt.date, end: dt.date) -> list[dt.date]:
    out = []
    for y in range(start.year, end.year + 2):
        for m in QUARTERLY_MONTHS:
            e = third_friday(y, m)
            if start <= e <= end + dt.timedelta(days=120):
                out.append(e)
    return out


def roll_dates(start: dt.date, end: dt.date, spec: ContractSpec) -> list[dt.date]:
    """Dates on which a held position must be rolled to the next quarterly contract."""
    rolls = [e - dt.timedelta(days=spec.roll_days_before_expiry) for e in expiries_between(start, end)]
    return [r for r in rolls if start <= r <= end]


def contract_code(root: str, on: dt.date, spec: ContractSpec | None = None) -> str:
    """Front contract code (e.g. MESZ25) that should be held on date `on`."""
    spec = spec or SPECS[root]
    for y in (on.year, on.year + 1):
        for m in QUARTERLY_MONTHS:
            e = third_friday(y, m)
            if on < e - dt.timedelta(days=spec.roll_days_before_expiry):
                return f"{root}{MONTH_CODES[m]}{str(y)[-2:]}"
    raise AssertionError("unreachable")


def front_expiry(on: dt.date, spec: ContractSpec) -> dt.date:
    for y in (on.year, on.year + 1):
        for m in QUARTERLY_MONTHS:
            e = third_friday(y, m)
            if on < e - dt.timedelta(days=spec.roll_days_before_expiry):
                return e
    raise AssertionError("unreachable")

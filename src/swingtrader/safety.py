"""Operational safety: kill switch, data-freshness checks, safe shutdown."""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)


def kill_switch_active(path: Path) -> bool:
    """Touch the file to stop all new orders; exits/flatten remain allowed."""
    return path.exists()


@dataclass
class DataCheck:
    ok: bool
    reasons: list[str]


def check_latest_bar(sessions: pd.DataFrame, as_of: dt.date, max_staleness_days: int = 4,
                     min_rth_bars: int = 300) -> DataCheck:
    """Data-failure gate used before any new entry in paper trading.

    Fails when the latest session is stale, has too few RTH bars, contains
    non-finite prices, or violates OHLC consistency. On failure the runner only
    manages existing risk (stops/exits) and opens nothing new.
    """
    reasons: list[str] = []
    if sessions.empty:
        return DataCheck(False, ["no sessions"])
    last_day = sessions.index[-1].date()
    last = sessions.iloc[-1]
    if (as_of - last_day).days > max_staleness_days:
        reasons.append(f"stale data: last session {last_day}, as_of {as_of}")
    if last.get("n_rth_bars", min_rth_bars) < min_rth_bars:
        reasons.append(f"latest session has {last.get('n_rth_bars')} RTH bars")
    vals = last[["open", "high", "low", "close"]].astype(float)
    if not vals.notna().all() or (vals <= 0).any():
        reasons.append("non-finite or non-positive prices")
    elif not (last["low"] <= min(last["open"], last["close"]) and last["high"] >= max(last["open"], last["close"])):
        reasons.append("OHLC inconsistent")
    return DataCheck(not reasons, reasons)


def safe_shutdown(cancel_open_orders, persist_state, flatten=None, reason: str = "") -> None:
    """Ordered shutdown: cancel working orders, optionally flatten, persist state.
    Each step runs even if an earlier one fails; failures are logged and re-raised at the end."""
    errors = []
    for name, step in (("cancel", cancel_open_orders), ("flatten", flatten), ("persist", persist_state)):
        if step is None:
            continue
        try:
            step()
        except Exception as exc:  # noqa: BLE001 - we must attempt every step
            log.exception("safe_shutdown step %s failed", name)
            errors.append((name, exc))
    log.warning("safe shutdown complete (%s)", reason)
    if errors:
        raise RuntimeError(f"shutdown steps failed: {[n for n, _ in errors]}")

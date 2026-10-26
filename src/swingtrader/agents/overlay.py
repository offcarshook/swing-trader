"""The ONLY path by which AI research can touch a trade: an entry size multiplier in [0, 1].

Modes (config agents.mode):
  off       research is not run
  advisory  research is run and logged; multiplier is always 1.0      (default)
  veto      a usable thesis whose direction OPPOSES the signal returns 0.0

Never > 1.0, never opens/keeps/reverses a position, never touches stops, sizing
limits or exits. When research is unavailable or unparseable the multiplier is
1.0 (fail-open): the AI layer is unvalidated, so its absence must not change the
validated deterministic behaviour. RiskManager re-clamps the value anyway.
"""

from __future__ import annotations

from swingtrader.agents.schema import ThesisReport

MODES = ("off", "advisory", "veto")


def overlay_multiplier(signal_side: int, thesis: ThesisReport | None, mode: str) -> tuple[float, str]:
    if mode not in MODES:
        raise ValueError(f"unknown agents.mode {mode!r}")
    if mode in ("off", "advisory"):
        return 1.0, f"{mode}: no effect"
    if thesis is None or not thesis.usable:
        why = "no thesis" if thesis is None else f"thesis {thesis.status}/{thesis.rating}"
        return 1.0, f"veto mode, {why}: fail-open"
    if thesis.direction_bias == -signal_side:
        return 0.0, f"veto: research rating {thesis.rating} opposes signal {signal_side:+d}"
    return 1.0, f"research rating {thesis.rating} does not oppose signal"

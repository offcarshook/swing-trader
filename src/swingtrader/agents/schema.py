"""Structured research output shared by both environments (stdlib only).

TradingAgents returns free text plus a 5-tier rating. This module turns that
into a typed record. A rating is mapped to a direction bias deterministically;
nothing else from the text is ever used for trading decisions.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

RATING_BIAS = {"Buy": 1, "Overweight": 1, "Hold": 0, "Underweight": -1, "Sell": -1}

STATUS_OK = "ok"
STATUS_UNAVAILABLE = "unavailable"        # missing env / credentials / budget
STATUS_ERROR = "error"                    # the run itself failed
STATUS_PLUMBING = "fake_llm_plumbing_test"  # offline wiring test, NOT research


@dataclass
class ThesisReport:
    status: str
    as_of: str
    ticker: str
    rating: str | None = None
    direction_bias: int = 0
    bull_case: str = ""
    bear_case: str = ""
    research_plan: str = ""
    trader_plan: str = ""
    risk_debate: str = ""
    final_decision: str = ""
    market_report: str = ""
    news_report: str = ""
    candidate: dict | None = None          # the deterministic signal that was researched
    model_info: dict = field(default_factory=dict)
    tool_calls: list = field(default_factory=list)
    elapsed_s: float = 0.0
    reason: str | None = None

    @property
    def usable(self) -> bool:
        """Only real LLM research with a parseable rating may influence anything."""
        return self.status == STATUS_OK and self.rating in RATING_BIAS

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=1, default=str)

    @classmethod
    def from_dict(cls, d: dict) -> ThesisReport:
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        return cls(**known)


def bias_for(rating: str | None) -> int:
    return RATING_BIAS.get(rating or "", 0)


def from_final_state(state: dict, as_of: str, ticker: str, rating: str | None, status: str = STATUS_OK,
                     **extra) -> ThesisReport:
    """Map a TradingAgents final_state (v0.7.0 AgentState keys) to a ThesisReport."""
    inv = state.get("investment_debate_state") or {}
    risk = state.get("risk_debate_state") or {}
    return ThesisReport(
        status=status, as_of=as_of, ticker=ticker, rating=rating, direction_bias=bias_for(rating),
        bull_case=str(inv.get("bull_history", "")), bear_case=str(inv.get("bear_history", "")),
        research_plan=str(state.get("investment_plan", "")),
        trader_plan=str(state.get("trader_investment_plan", "")),
        risk_debate=str(risk.get("history", "")),
        final_decision=str(state.get("final_trade_decision", "")),
        market_report=str(state.get("market_report", "")),
        news_report=str(state.get("news_report", "")),
        **extra,
    )

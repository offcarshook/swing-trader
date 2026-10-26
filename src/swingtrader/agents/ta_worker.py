"""TradingAgents worker -- runs ONLY inside the agents environment (.venv-agents).

    .venv-agents/bin/python -m swingtrader.agents.ta_worker --request req.json --out out.json [--fake-llm]

Verified against TradingAgents v0.7.0 (commit e8f5503). Integration points used:
  * TradingAgentsGraph(selected_analysts, config).propagate(ticker, date)
        -> (final_state, rating in {Buy, Overweight, Hold, Underweight, Sell, REVIEW})
  * tradingagents.dataflows.router.VENDOR_METHODS -- a module-level registry. We add a
    "swingtrader_local" vendor so the agents read our validated, point-in-time
    session bars instead of yfinance (blocked here, and not point-in-time safe).
    This is an internal registry, not a public API: a version bump may break it,
    which is why the commit is pinned and tests check the registry shape.

--fake-llm swaps the LLM clients for a scripted local chat model. It exercises the
real graph, routing, tool calls and our vendor end-to-end WITHOUT any API call.
Its "opinions" are canned text: the output is labelled fake_llm_plumbing_test and
is never usable for trading (ThesisReport.usable is False).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path

import pandas as pd

from swingtrader.agents.schema import (STATUS_ERROR, STATUS_OK, STATUS_PLUMBING, STATUS_UNAVAILABLE,
                                       ThesisReport, from_final_state)

LOCAL_VENDOR = "swingtrader_local"
PROVIDER_KEYS = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "google": "GOOGLE_API_KEY"}
# (deep, quick) defaults per provider, taken from TradingAgents' own model catalog (v0.7.0).
# TradingAgents' global defaults are OpenAI model ids, which would fail on other providers.
PROVIDER_MODELS = {"anthropic": ("claude-opus-5-5", "claude-sonnet-5"),
                   "google": ("gemini-3.1-pro-preview", "gemini-3.8-flash")}


# --------------------------------------------------------------------------- data
def _load_bars(path: str, as_of: str) -> pd.DataFrame:
    df = pd.read_parquet(path)
    df = df[["open", "high", "low", "close"] + (["volume"] if "volume" in df else [])]
    return df[df.index <= pd.Timestamp(as_of)]  # hard point-in-time clamp, independent of TA's own


def register_local_vendor(bars_path: str, as_of: str, tool_log: list) -> None:
    from tradingagents.dataflows import router
    from tradingagents.dataflows.errors import NoMarketDataError

    def get_stock_data(symbol, start_date, end_date):
        tool_log.append({"tool": "get_stock_data", "start": start_date, "end": end_date})
        df = _load_bars(bars_path, min(end_date, as_of))
        df = df[df.index >= pd.Timestamp(start_date)]
        if df.empty:
            raise NoMarketDataError(symbol, symbol, f"no local sessions {start_date}..{end_date}")
        return (f"# {symbol} daily sessions (source: swingtrader validated data, point-in-time <= {as_of})\n"
                + df.round(2).to_csv())

    def get_indicators(symbol, indicator, curr_date, look_back_days=30):
        tool_log.append({"tool": "get_indicators", "indicator": indicator, "curr_date": curr_date})
        from stockstats import wrap
        df = _load_bars(bars_path, min(curr_date, as_of)).copy()
        if df.empty:
            raise NoMarketDataError(symbol, symbol, "no local sessions")
        ss = wrap(df.rename_axis("date").reset_index())  # stockstats moves `date` into the index
        try:
            values = ss[indicator]
        except Exception as exc:  # unknown indicator name from the model
            return f"Indicator {indicator!r} unavailable: {exc}"
        out = values.tail(int(look_back_days)).round(4).to_frame(indicator)
        return f"# {indicator} for {symbol}, last {look_back_days} sessions <= {curr_date}\n" + out.to_csv()

    for method, fn in (("get_stock_data", get_stock_data), ("get_indicators", get_indicators)):
        if method not in router.VENDOR_METHODS:
            raise RuntimeError(f"TradingAgents router has no {method}; API changed")
        router.VENDOR_METHODS[method][LOCAL_VENDOR] = fn


# -------------------------------------------------------------------- fake LLM
def install_fake_llm(as_of: str) -> None:
    """Replace LLM clients with a scripted model (offline wiring test only)."""
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AIMessage, ToolMessage
    from langchain_core.outputs import ChatGeneration, ChatResult
    from langchain_core.utils.function_calling import convert_to_openai_tool

    import tradingagents.graph.trading_graph as tg

    start = (pd.Timestamp(as_of) - pd.Timedelta(days=120)).strftime("%Y-%m-%d")

    class ScriptedChat(BaseChatModel):
        @property
        def _llm_type(self) -> str:
            return "scripted-fake"

        def bind_tools(self, tools, **kwargs):
            return self.bind(tools=[convert_to_openai_tool(t) for t in tools], **kwargs)

        def with_structured_output(self, *args, **kwargs):
            raise NotImplementedError("scripted model: free-text fallback")

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            tools = {t["function"]["name"] for t in kwargs.get("tools", [])}
            used = [m.name for m in messages if isinstance(m, ToolMessage)]
            if "get_stock_data" in tools and "get_stock_data" not in used:
                msg = AIMessage(content="", tool_calls=[{"name": "get_stock_data", "id": "c1",
                                "args": {"start_date": start, "end_date": as_of}}])
            elif "get_indicators" in tools and "get_indicators" not in used:
                msg = AIMessage(content="", tool_calls=[{"name": "get_indicators", "id": "c2",
                                "args": {"indicator": "rsi", "curr_date": as_of, "look_back_days": 10}}])
            else:
                msg = AIMessage(content=("[FAKE LLM - plumbing test, not research]\n"
                                         "Rating: Hold\nThis text is canned and carries no opinion."))
            return ChatResult(generations=[ChatGeneration(message=msg)])

    class FakeClient:
        def get_llm(self):
            return ScriptedChat()

    tg.create_tier_client = lambda config, tier, **extra: FakeClient()


# ------------------------------------------------------------------------- run
def run(req: dict, fake_llm: bool) -> ThesisReport:
    as_of, ticker = req["as_of"], req["ticker"]
    base = ThesisReport(status=STATUS_UNAVAILABLE, as_of=as_of, ticker=ticker, candidate=req.get("candidate"))
    try:
        import tradingagents
        from tradingagents.default_config import build_default_config
        from tradingagents.graph.trading_graph import TradingAgentsGraph
    except Exception as exc:  # noqa: BLE001
        base.reason = f"tradingagents not importable in this env: {exc}"
        return base

    cfg = build_default_config()
    home = Path(req["work_dir"])
    cfg.update({
        "results_dir": str(home / "logs"), "data_cache_dir": str(home / "cache"),
        "memory_log_path": str(home / "memory" / "trading_memory.md"),
        "max_debate_rounds": int(req.get("max_debate_rounds", 1)),
        "max_risk_discuss_rounds": int(req.get("max_risk_rounds", 1)),
        "checkpoint_enabled": False, "output_language": "English",
    })
    cfg["data_vendors"] = {**cfg["data_vendors"], "core_stock_apis": LOCAL_VENDOR,
                           "technical_indicators": LOCAL_VENDOR}
    provider = req.get("provider") or cfg["llm_provider"]
    if not fake_llm:
        key = PROVIDER_KEYS.get(provider)
        if key and not os.environ.get(key):
            base.reason = f"no {key} in environment for provider {provider!r}"
            return base
        cfg["llm_provider"] = provider
        defaults = PROVIDER_MODELS.get(provider)
        for i, (k, env) in enumerate((("deep_think_llm", "TRADINGAGENTS_DEEP_THINK_LLM"),
                                      ("quick_think_llm", "TRADINGAGENTS_QUICK_THINK_LLM"))):
            if req.get(k):
                cfg[k] = req[k]
            elif defaults and not os.environ.get(env):
                cfg[k] = defaults[i]

    tool_log: list = []
    register_local_vendor(req["bars_path"], as_of, tool_log)
    if fake_llm:
        install_fake_llm(as_of)

    t0 = time.time()
    try:
        graph = TradingAgentsGraph(selected_analysts=tuple(req.get("analysts", ["market"])), config=cfg)
        final_state, rating = graph.propagate(ticker, as_of)
    except Exception as exc:  # noqa: BLE001
        base.status, base.reason = STATUS_ERROR, f"{type(exc).__name__}: {exc}"
        base.model_info = {"traceback": traceback.format_exc()[-3000:]}
        base.tool_calls = tool_log
        return base
    status = STATUS_PLUMBING if fake_llm else STATUS_OK
    rep = from_final_state(final_state, as_of, ticker, rating, status=status, candidate=req.get("candidate"),
                           tool_calls=tool_log, elapsed_s=round(time.time() - t0, 2),
                           model_info={"tradingagents": tradingagents.__version__, "provider": "fake" if fake_llm else provider,
                                       "deep": None if fake_llm else cfg["deep_think_llm"],
                                       "quick": None if fake_llm else cfg["quick_think_llm"]})
    if fake_llm:
        rep.reason = "scripted local model: wiring test only, not research"
    return rep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--request", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--fake-llm", action="store_true")
    a = ap.parse_args(argv)
    req = json.loads(Path(a.request).read_text())
    rep = run(req, a.fake_llm)
    Path(a.out).write_text(rep.to_json())
    return 0 if rep.status in (STATUS_OK, STATUS_PLUMBING) else 2


if __name__ == "__main__":
    sys.exit(main())

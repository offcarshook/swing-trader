# TradingAgents integration notes (verified against v0.7.0, commit e8f5503, 2026-10-16)

## Verified API
* Not on PyPI; installed from the pinned git commit into `.venv-agents`.
* `TradingAgentsGraph(selected_analysts=("market",), config=cfg).propagate(ticker, "YYYY-MM-DD")`
  returns `(final_state, rating)`; rating ∈ {Buy, Overweight, Hold, Underweight, Sell} or `REVIEW`.
* `final_state` keys used: `market_report`, `investment_debate_state.{bull_history,bear_history}`,
  `investment_plan`, `trader_investment_plan`, `risk_debate_state.history`, `final_trade_decision`.
* Providers: openai (default), anthropic, google, azure, bedrock… keys via `OPENAI_API_KEY`,
  `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`; models via `TRADINGAGENTS_DEEP_THINK_LLM` / `..._QUICK_...`.
* Asset types: `stock` and `crypto` only. An index future is analysed as the S&P 500 (`^GSPC`).
* Tools clamp dates to the run date (`as_of_window`); data vendors are looked up in the
  module-level `tradingagents.dataflows.router.VENDOR_METHODS`.

## Incompatibility with LumiBot
`pandas>=3.0.6` (TradingAgents) vs `pandas<3` (LumiBot via llama-index-readers-file) → two
environments and a JSON/subprocess boundary (`agents/adapter.py` ↔ `agents/ta_worker.py`).

## What the adapter adds
* **Local point-in-time vendor** `swingtrader_local` for `get_stock_data` / `get_indicators`
  (registered into `VENDOR_METHODS`): agents read our validated S&P 500 sessions, hard-clamped to
  the as-of date, instead of yfinance (blocked here). Integration test asserts no row after as-of.
  This uses an internal registry, hence the pinned commit and a registry-shape check.
* **Structured output** `ThesisReport` (rating → direction bias deterministically; bull/bear cases,
  research/trader plans, risk debate, final decision, tool calls, model ids, elapsed time).
* **Cost guards**: called only when the deterministic strategy has an entry signal; on-disk cache
  per (date, candidate, settings); per-day call budget (`agents.max_calls_per_day`, default 2);
  1-round debates; market analyst only (no fundamentals for an index future; news vendors blocked).
* **Overlay policy** (`agents/overlay.py`): `advisory` (default, logged only) or `veto` (a usable
  thesis opposing the signal → multiplier 0). Never > 1, never touches exits/stops/limits, fail-open
  when research is unavailable. `RiskManager` re-clamps any multiplier to [0, 1].

## Verified offline
`--fake-llm` replaces the LLM clients with a scripted local chat model and runs the **real**
graph: market analyst → `get_stock_data` + `get_indicators` tool calls through our vendor → bull
and bear researchers → research manager → trader → aggressive/conservative/neutral risk debate →
portfolio manager → rating parsed by TradingAgents' own parser. Output status is
`fake_llm_plumbing_test` and can never influence a trade. Real research needs an API key (blocked).

## Why there is no "AI-filtered backtest"
An LLM asked about 2018 already "knows" 2019–2026. Any historical AI-filtered P&L would be
contaminated, so none is reported. The only honest evaluation is forward: log every thesis in
paper trading and later compare vetoed vs accepted signals.

## Running with real research (when credentials exist)
```bash
export ANTHROPIC_API_KEY=...            # or OPENAI_API_KEY / GOOGLE_API_KEY
export TRADINGAGENTS_DEEP_THINK_LLM=claude-opus-5-5 TRADINGAGENTS_QUICK_THINK_LLM=claude-sonnet-5
.venv/bin/python -m swingtrader agent-research --date 2025-11-14
```

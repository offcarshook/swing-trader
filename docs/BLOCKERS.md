# Blockers and what was done instead

Everything below was hit in the build environment (a sandboxed cloud container). Nothing in the
results was faked to work around them.

| # | Blocker | Evidence | Impact | Workaround / status | To unblock |
|---|---|---|---|---|---|
| 1 | Market-data vendors blocked by network policy | proxy `403` for query1/2.finance.yahoo.com, stooq.com, cmegroup.com, api.databento.com, api.polygon.io, alphavantage.co, data.nasdaq.com, api.tiingo.com, fred.stlouisfed.org, data.alpaca.markets | no official/vendor futures history; no live feed | used pinned Hugging Face files, validated against two independent series (see INSTRUMENT_SELECTION.md) | allow a vendor host (e.g. Databento) in the environment's network settings and add an API key; `data/sources.py` is the single place to add a source |
| 2 | Data provenance | MES/SPX files come from an anonymous HF uploader with no licence card | legal/quality uncertainty | cross-checked (corr 0.99998 vs unadjusted ES, 0.999 vs SPX); pinned by SHA-256 | re-run the pipeline on licensed data before any real-money decision |
| 3 | No LLM credentials | no `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GOOGLE_API_KEY`; `api.openai.com` blocked | no real TradingAgents research could be produced | adapter verified end-to-end offline with a scripted model (`--fake-llm`), output labelled as not research | export a provider key; `swingtrader agent-research --date …` |
| 4 | TradingAgents data/news tools use yfinance | Yahoo blocked | news/sentiment analysts cannot run | local point-in-time price vendor; only the market analyst is enabled | allow Yahoo or configure Alpha Vantage key in TradingAgents |
| 5 | LumiBot ↔ TradingAgents dependency conflict | pandas<3 vs pandas>=3.0.6 | cannot share an environment | two venvs + JSON/subprocess boundary | none needed |
| 6 | No paper-broker credentials / broker hosts | no Tradovate/IB settings; broker APIs unreachable | LumiBot paper trading not exercised | local deterministic paper book (`swingtrader paper`) with the same strategy, risk and order guard | Tradovate demo (`TRADOVATE_IS_PAPER=true`) or IB paper gateway (7497/4002), then `swingtrader paper --mode lumibot` |
| 7 | No live data feed | see 1 | paper runner consumes files; its data gate currently blocks entries because the newest bar (2026-10-20) is > 4 days old | intended behaviour of the data-failure control | refresh `data/processed` daily from a real feed |
| 8 | Statistical power | one instrument, swing horizon → 100 training trades, 25 holdout trades | wide confidence intervals | SPX proxy added to training (Amendment 1) | more instruments (only after data is available) and months of forward paper results |
| 9 | Historical bid/ask unavailable | — | spreads are assumptions | 1-tick spread + stress at 2×, 3×, +2 ticks | tick/quote data from a vendor |

Live order execution is not implemented: `swingtrader.LIVE_TRADING_ENABLED = False` is a code
constant checked by `OrderGuard`, the paper runner and the LumiBot launcher, and there is no
configuration switch for it.

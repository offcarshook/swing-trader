# Framework integration: Tauric Research TradingAgents + Lumibot

## Versions (pinned, verified 2026-10-26)
| Framework | Version | Source | Licence | Python | Environment |
|---|---|---|---|---|---|
| **Lumibot** | **4.6.30** (latest on PyPI on 2026-10-26) | PyPI `lumibot==4.6.30` | GPL-3.0 | ≥3.10 | `.venv` (pandas 2.3.3, numpy 2.4.6) |
| **TradingAgents** | **0.7.0**, commit `e8f5503e9b86d5c2710b0c76b1f686703968c9df` (= upstream `HEAD` and tag `v0.7.0` on 2026-10-26, checked with `git ls-remote`) | `git+https://github.com/TauricResearch/TradingAgents@e8f5503` (not on PyPI) | Apache-2.0 | ≥3.11 | `.venv-agents` (pandas 3.1.0, langgraph 1.2.18, langchain-core 1.7.0) |

Licence note: Lumibot is GPL-3.0. The project imports it as a library; anyone redistributing a combined
work must respect the GPL. TradingAgents (Apache-2.0) runs in a separate process.

## Dependency conflict and the boundary
`lumibot==4.6.30` resolves to `pandas<3` (through `llama-index-readers-file`), while TradingAgents 0.7.0
requires `pandas>=3.0.6`. They cannot share one interpreter, so:
* `.venv` runs the core, the reference engine and Lumibot;
* `.venv-agents` runs `swingtrader.agents.ta_worker` (the only module that imports `tradingagents`);
* they talk through a JSON request/response file pair and a subprocess with a timeout
  (`agents/etf_research.py: run_plumbing`, `agents/adapter.py` for the MES path).
The core package imports cleanly under both pandas versions (both test suites pass).

```bash
scripts/setup_envs.sh          # creates .venv (Lumibot) and .venv-agents (TradingAgents) with uv or pip
```
Import smoke test (2026-10-26): `.venv` → `lumibot 4.6.30`; `.venv-agents` → `tradingagents 0.7.0`.

## Architecture (one ledger, one order path)
```
point-in-time data (etf/data.py: executable OHLC + adj_factor + dividend; completed bars only)
        │
        ▼
deterministic signals (etf/strategies.py)  ──►  TradingAgents research record (optional)
        │                                        agents/etf_research.py → ta_worker (.venv-agents)
        │                                        validated ResearchRecord, cached, PIT-checked
        ▼                                                  │ entry_filter: multiplier in [0,1]
PortfolioRiskGate (etf/risk.py)  ◄──────────────────────────┘   (clamped; can only shrink/veto)
  lockouts · kill switch · per-trade risk · open-risk cap · cluster/gross/net caps · one position per ETF
        │ approved size
        ▼
Lumibot strategy adapter (lumibot_bridge/etf_strategy.py: EtfSwingLumibot)
  OrderGuard (idempotent client ids, persisted) · global order switch · reconciliation · state file
        │ market / stop / limit orders
        ▼
Lumibot broker: PandasDataBacktesting (backtests, dry run) or a PAPER broker (Alpaca paper, IB paper)
```
* Lumibot owns the strategy lifecycle, order objects and the broker-side cash/positions. The adapter's
  own book is reconciled against the broker every iteration; on any mismatch new entries stop and no exit
  is sent for a position the broker does not hold.
* The reference engine (`etf/engine.py`) is an **independent** implementation used for research and for
  parity checks; it never submits orders. The only component that submits ETF orders is the Lumibot
  adapter; `SWINGTRADER_DISABLE_ORDERS=1` (or the configured switch file) blocks every order it would send.
* TradingAgents never submits orders, never sizes up, never touches exits or limits.

## Lumibot: verified behaviour this integration depends on (4.6.30, `PandasDataBacktesting`, daily bars)
| Behaviour | Evidence | Handling |
|---|---|---|
| An order submitted in the iteration for session D fills at D's **open**; the fill is reported with the clock of the **next** iteration | parity ledger (fills at D's open price, timestamp D+1) | parity maps fills back to the bar that priced them |
| `get_historical_prices()` in iteration D already contains bar D (close not yet known) | phase-1 notes, re-verified | `completed()` drops every bar ≥ D before signals |
| `get_portfolio_value()` in iteration D is frequently marked at **D's close** | probe: 2019-02-19 value 99,940.88 = reference D-close equity | sizing uses point-in-time equity = broker cash + positions × last completed close (now equal to the reference engine's previous-close equity to the cent) |
| `get_yesterday_dividend()` reads the current clock's bar; the backtest broker **does not credit** dividends to cash in this path | probe: QQQ held over 2019-03-18 ex-date, cash unchanged for shifts −1/0/+1/+2 | adapter logs `dividend_entitlement` events (holders of record) and includes them in point-in-time equity; parity adds them back |
| `TradingFee(per_contract_fee=…)` is charged per share for stocks; `percent_fee` on notional | source `calculate_trade_cost` | commission → per_contract_fee, slippage → percent_fee; extra stop slippage cannot be expressed |
| Stop / limit orders act from the next bar; gaps fill at the open | parity | reference engine `exec_style="lumibot"` mirrors this for parity |
| No market-on-close in daily backtests | — | time stop = market order at the next open in the adapter |
| No clock at the open in daily backtests | — | open-decided members (gap-and-go) and stop-entry breakouts are excluded from the Lumibot book and reported as excluded |

## TradingAgents: what is used and what is disabled
* API used: `TradingAgentsGraph(selected_analysts=("market",), config).propagate(ticker, date)` →
  `(final_state, rating)`; ratings Buy / Overweight / Hold / Underweight / Sell.
* Data: our own point-in-time vendor `swingtrader_local` is registered into the internal
  `tradingagents.dataflows.router.VENDOR_METHODS` registry (internal API, hence the pinned commit and a
  registry-shape check in the worker). For ETF decisions the worker receives a parquet cut to sessions
  **strictly before** the decision date, because the vendor's own clamp is `<= as_of` (which would expose
  the decision day's close).
* Disabled inputs (recorded in every record's `disabled_inputs`): news, social sentiment, fundamentals,
  macro — no point-in-time dated archive exists in this project, and upstream vendors return today's data.
* Record schema (`ResearchRecord`, `etf-research-record/1`): instrument, decision_ts, data_cutoff,
  generated_at, status, timeframes_assessed, rating, direction_bias, confidence (null: v0.7.0 produces no
  calibrated confidence), thesis, counter_thesis, risks, invalidation_conditions, source_timestamps, model,
  provider, temperature, seed, prompt_config_version, schema_version, run_id, data_fingerprint, candidate.
* Validation rejects: missing/unknown fields, non-research status (scripted-model plumbing runs),
  invalid or contradictory rating/bias, confidence outside [0,1], missing thesis or counter-thesis,
  `data_cutoff` or any source timestamp after the decision, and any record **generated later than the
  decision deadline** (hindsight-contaminated).
* `ResearchService`: cache-first (key = instrument, decision time, candidate, config, data fingerprint,
  prompt version); `replay` mode never calls a model; `forward` mode refuses fresh calls for decisions not
  within `max_latency_s` of the wall clock; call budget, timeout and retries; atomic cache writes.
* Policies (`entry_filter_from`): `off` (deterministic baseline), `advisory` (logged, no effect), `gate`
  (agent-assisted variant: needs a valid non-opposing record, otherwise **fails closed** = no entry).
  The phase-1 MES overlay's `veto` mode was changed from fail-open to fail-closed for consistency.

## Blockers (exact)
1. **No LLM credentials.** No `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GOOGLE_API_KEY` exists in this
   environment (the coding session's own endpoint is not used for the trading system). Real TradingAgents
   research, its incremental value versus the deterministic baseline, and run-to-run variability could
   therefore not be measured. What was verified: the real v0.7.0 graph end to end with the scripted local
   model (market analyst → our PIT vendor → bull/bear debate → trader → risk debate → portfolio manager →
   rating), and the full adapter with recorded fixtures.
2. **Historical evaluation of an LLM is not point-in-time safe** even with credentials: a model asked
   about 2019 has seen 2020–2026. Only research records generated at decision time (forward paper
   trading) can be evaluated; the adapter enforces this.
3. **No paper-broker credentials** (Alpaca connector failed to connect; no IB/Tradovate settings). The
   paper runner refuses anything that is not a paper account and otherwise runs a clearly labelled
   simulated-broker dry run.

## Setup for real research / paper trading (when credentials exist)
```bash
export ANTHROPIC_API_KEY=...            # or OPENAI_API_KEY / GOOGLE_API_KEY (never commit them)
export ALPACA_API_KEY=... ALPACA_API_SECRET=... ALPACA_IS_PAPER=true
.venv/bin/python -m swingtrader etf-paper --broker      # PAPER account only; refuses otherwise
```

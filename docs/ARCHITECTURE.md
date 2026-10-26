# Architecture

```
                 pinned HF files (sha256)                      data/raw/  (git-ignored)
                          │
              swingtrader.data  ── loaders → drop out-of-hours bars → session bars (17:00–16:00 CT)
                          │        quality report + independent cross-checks (ES unadjusted, SPX)
                          ▼
                 data/processed/*.parquet  ──────────────┐
                          │                              │ (point-in-time, clamped to as-of)
          ┌───────────────┴──────────────┐               ▼
          │ deterministic core (Python)  │      .venv-agents  (pandas 3.x)
          │  strategies → Decision       │      swingtrader.agents.ta_worker
          │  RiskManager (sizing/limits) │◄──── TradingAgents v0.7.0 graph
          │  CostModel, Ledger, OrderGuard│  JSON ThesisReport → overlay multiplier ∈ [0,1]
          └───────┬───────────┬──────────┘      (subprocess boundary, cached, budgeted)
                  │           │
   internal engine│           │LumiBot bridge (.venv, pandas 2.x)
   (research,     │           │ PandasDataBacktesting replay + paper broker launcher
    selection,    │           │
    holdout)      ▼           ▼
            results/*.json, *.md        paper runner (local replay book / LumiBot paper)
```

## Separation of concerns

| Layer | Owns | Never does |
|---|---|---|
| `strategies/*` | exact entry/exit/stop rules on completed session bars | sizing, fills, P&L |
| `risk.RiskManager` | contracts from stop distance × tick value; per-trade, open-risk, notional, margin, contract caps; daily-loss stop; drawdown halt | trust an external multiplier > 1 |
| `costs.CostModel` | commissions, exchange fees, slippage by order type, gaps, thin sessions, rolls | — |
| `accounting.Ledger` | realized/unrealized P&L, fees, charges, invariant checks | — |
| `orders.OrderGuard` | deterministic client ids, duplicate prevention (persisted), per-session cap, live-trading refusal | — |
| `safety` | kill-switch file, latest-bar data checks, ordered safe shutdown | — |
| `backtest.engine` | the session timeline (pre-RTH → RTH open → post-open → close → decision) | look at future bars |
| `agents.*` | research theses, structured output, veto-only overlay | size up, open, hold or reverse positions |
| `lumibot_bridge.*` | independent replay in LumiBot; paper-broker launcher | live trading |

## Two environments (verified incompatibility)

`lumibot==4.6.30` resolves `pandas==2.3.3` (its dependency `llama-index-readers-file` pins `pandas<3`).
TradingAgents v0.7.0 declares `pandas>=3.0.6`. They cannot be installed into one environment, so:

* `.venv` — core + LumiBot (pandas 2.x)
* `.venv-agents` — core + TradingAgents pinned to commit `e8f5503` (pandas 3.x)

The core package imports under both (the unit-test suite runs green in both envs). The only
coupling is a JSON request/response pair (`ThesisReport`) exchanged through a subprocess with a
timeout, an on-disk cache and a per-day call budget.

## Why AI can only veto

LLM agents cannot be backtested honestly: the models were trained on text written after most
historical dates, so a "2018 thesis" leaks 2019+ knowledge. Their value is therefore unknown, and
the overlay is restricted to the one action that cannot add risk — declining an entry — and
defaults to `advisory` (logged, no effect). Evaluation of the agents can only happen forward, in
paper trading, by comparing logged vetoes with what the vetoed trades would have done.

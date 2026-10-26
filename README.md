# swingtrader — AI-assisted futures swing-trading research & paper-trading system

A new, self-contained project (no code from any earlier bot). Deterministic Python owns data
validation, signals, sizing, risk and accounting; **LumiBot** independently replays backtests and
provides the paper-broker runtime; **Tauric Research TradingAgents** produces structured bull/bear
research that can, at most, veto an entry. **Live order execution does not exist in this codebase.**

> **Headline (actual results, see [docs/RESULTS.md](docs/RESULTS.md))**
> Instrument: MES. Selected on training data only: a pullback-in-uptrend strategy (S&P 500 proxy
> 2008-19 + MES 2019-23). On the untouched MES holdout (2024-01 → 2026-10): **+4.45% total,
> 0.13% per month, max drawdown 0.56%, 25 trades, PF 4.8, Sharpe 1.33**, robust to 3× costs, beats
> 100% of random-entry runs — and far below buy-and-hold's +34.9%. The ambitious **5–8% per month
> target is not supported**: even at 8% risk per trade the strategy averaged < 1%/month on training
> data. Paper trading is unlocked by the promotion gates; nothing here promises returns.

> **ETF 1–3 day phase ([docs/ETF_RESULTS.md](docs/ETF_RESULTS.md))** — the 15-ETF basket could not be
> tested (free Alpha Vantage key: 100 sessions/ETF, 25 calls/day). On a SPY proxy, 4 of 5 families passed
> training, but the fresh 2021–26 test made only +12.3% (PF 1.15, max DD −13.9%) vs +104.9% buy-and-hold.

## Quick start

```bash
# 1. environments (two, because LumiBot pins pandas<3 and TradingAgents needs pandas>=3)
scripts/setup_envs.sh

# 2. data: pinned, sha256-verified downloads -> session bars -> quality report
.venv/bin/python -m swingtrader download
.venv/bin/python -m swingtrader data              # results/DATA_QUALITY.md

# 3. research (training windows only) -> one selected candidate
.venv/bin/python -m swingtrader select            # results/TRAIN_REPORT.md (~5 min)

# 4. one-shot holdout evaluation + promotion gates (registered in results/holdout_registry.json)
.venv/bin/python -m swingtrader holdout           # results/HOLDOUT_REPORT.md, results/promotion.json

# 5. independent replay in LumiBot (train window default; holdout only after step 4)
.venv/bin/python -m swingtrader lumibot-backtest
.venv/bin/python -m swingtrader lumibot-backtest --start 2024-01-02

# 6. TradingAgents research for a session (real run needs an LLM key; --dry-run = offline wiring test)
.venv/bin/python -m swingtrader agent-research --date 2025-11-14 --dry-run

# 7. paper trading (requires a passed promotion; local deterministic paper book)
.venv/bin/python -m swingtrader paper --dry-run
.venv/bin/python -m swingtrader paper             # writes state/paper/{status.json,journal.jsonl,orders.json}
.venv/bin/python -m swingtrader paper --mode lumibot   # Tradovate demo / IB paper only (needs creds)
touch KILL_SWITCH                                 # blocks all new entries; exits still processed

# regenerate markdown from saved results (no re-runs)
.venv/bin/python -m swingtrader report

# tests
.venv/bin/python -m pytest -q                     # 72 unit tests
.venv/bin/python -m pytest -q -m integration      # 4 integration tests (data, LumiBot, TradingAgents graph)
.venv-agents/bin/python -m pytest -q              # core suite under pandas 3
```

## How it works

1. **Data** (`swingtrader/data`): pinned Hugging Face files (the environment blocks Yahoo/CME/
   Databento/Polygon…). 1-min bars → CME sessions (17:00–16:00 CT) with RTH open/close and
   pre/post-open ranges. Invalid bars are dropped and counted, never repaired. MES is cross-checked
   against unadjusted ES (corr 0.99998) and the S&P 500 index (corr 0.999).
2. **Regimes & strategies** (`regime.py`, `strategies/`): explicit, testable rules for trend
   continuation, momentum breakout and pullback entries plus baselines; shared no-trade
   conditions (extreme volatility, data holes, kill switch, halts).
3. **Research overlay** (`agents/`): TradingAgents runs only for a deterministic entry signal, in
   its own environment, reading our point-in-time data; output is a typed `ThesisReport`. Mode
   `advisory` (default) logs it; mode `veto` can only cancel an entry.
4. **Risk** (`risk.py`, `costs.py`, `accounting.py`, `orders.py`, `safety.py`): sizing by stop
   distance × $1.25 tick value; per-trade, open-risk, notional, margin and contract caps; 3% daily
   loss stop; 20% drawdown halt with manual reset; commissions, fees, slippage, gaps, rolls;
   futures ledger with invariants; idempotent order ids and duplicate prevention; kill switch;
   data-failure gate; ordered safe shutdown.
5. **Backtests** (`backtest/`): event-driven session engine (orders at the next RTH open, resting
   stops intraday, gap fills), plus a LumiBot replay (`lumibot_bridge/`) for independent confirmation.
6. **Validation** (`research/`): pre-registered splits and gates, 8-fold walk-forward, random-entry
   Monte Carlo, anchored walk-forward of the selection rule, cost stress, holdout guard, append-only
   experiment log including failed experiments and every protocol amendment.
7. **Paper trading** (`paper/`): gated by the promotion file, deterministic replay book, OrderGuard.

## Project structure

```
config/default.yaml          all assumptions, grids, gates, splits (pre-registered)
data/                        raw/ + processed/ are git-ignored; provenance pinned in code
docs/                        ARCHITECTURE, INSTRUMENT_SELECTION, STRATEGY_SPECS, VALIDATION_PROTOCOL,
                             COSTS, LUMIBOT_NOTES, TRADINGAGENTS_NOTES, RESULTS, BLOCKERS
results/                     generated reports, JSON results, trade/equity CSVs, experiment log
scripts/setup_envs.sh        creates .venv (LumiBot) and .venv-agents (TradingAgents)
src/swingtrader/
  cli.py                     `python -m swingtrader <command>`
  config.py contracts.py costs.py risk.py accounting.py orders.py safety.py indicators.py regime.py
  data/        sources.py loaders.py sessions.py quality.py pipeline.py
  strategies/  base.py trend.py breakout.py pullback.py baselines.py
  backtest/    engine.py metrics.py runner.py
  research/    selection.py holdout.py experiments.py report.py
  agents/      schema.py overlay.py adapter.py ta_worker.py
  lumibot_bridge/  strategy.py run_backtest.py paper.py
  paper/       runner.py
tests/                       unit tests + integration tests (-m integration)
```

## Blockers (details in [docs/BLOCKERS.md](docs/BLOCKERS.md))
* Market-data vendors, Yahoo, OpenAI and broker hosts are blocked by the environment's network
  policy → third-party HF data (validated, pinned), no live feed.
* No LLM API key → TradingAgents verified end-to-end only with an offline scripted model; no real
  AI theses were generated.
* No paper-broker credentials → LumiBot paper launcher implemented but not exercised.

## Safety
`LIVE_TRADING_ENABLED = False` is a code constant (no config switch) checked by every order path.
AI output can only shrink an entry to zero. The holdout cannot be silently re-used for a different
candidate. This is research software, not investment advice.

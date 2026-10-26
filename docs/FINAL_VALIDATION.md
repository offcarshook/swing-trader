# Final validation (2026-10-26)

## Bottom line
* **No strategy has a demonstrated, defensible edge.** The best candidate — a US-equity short-term
  mean-reversion book on SPY/QQQ — is positive after 3× costs in training, but its deflated Sharpe
  probability is 0.48, the selection procedure produced +1.05 % over 2013–2020 in walk-forward, it fails on
  every non-equity ETF, and buy & hold beat it on every window.
* **Multi-timeframe confirmation (MES, real 1-minute data) adds no value** and loses after costs.
* **Both frameworks are genuinely integrated**: Lumibot runs the book with exact zero-cost parity and is
  the only order path; TradingAgents' real graph runs behind a validated, point-in-time, fail-closed adapter.
  Real LLM research and real paper brokers are blocked by missing credentials.
* The system is suitable for **continued historical and forward paper research**, not for capital.

## Test results (actually run)
| Environment | Command | Result |
|---|---|---|
| core (system Python 3.13, pandas 3.0.5) | `python -m pytest -q` | **157 passed**, 2 skipped (Lumibot-only modules), 4 deselected (integration) |
| `.venv` (Lumibot 4.6.30, pandas 2.3.3) | `.venv/bin/python -m pytest -q` | **166 passed**, 4 deselected |
| `.venv` integration | `.venv/bin/python -m pytest -q -m integration` | **4 passed** |
| `.venv-agents` (TradingAgents 0.7.0, pandas 3.1.0) | `.venv-agents/bin/python -m pytest -q` | **157 passed**, 2 skipped |
| `.venv-agents` integration | `.venv-agents/bin/python -m pytest -q -m integration` | **3 passed**, 2 skipped (need Lumibot) |
Baseline before the audit: 106 passed, 1 skipped. New suites: `test_etf_basis_risk.py` (14),
`test_account_rules.py` (10), `test_etf_research_adapter.py` (21), `test_mtf.py` (7),
`test_lumibot_etf.py` (8). No assertion was weakened; three test expectations I had written wrongly were
corrected with the arithmetic shown in the test, and two pre-existing tests were changed because the
specification changed (adjusted-price loader → executable prices; veto fail-open → fail-closed).

## Validation methodology
* Chronological splits, pre-registered in config before running: ETF train 2008–2020 / previously viewed
  2021+; MES train 2019-11→2022, validation 2023, viewed 2024+.
* Training-only selection with gates at 2× costs (≥30 trades, PF ≥ 1.2, positive expectancy, ≥60 %
  positive yearly folds, above the 90th percentile of random-entry runs with the same exits).
* Anchored walk-forward of the full selection procedure (re-selected every year, 2013–2026).
* Holdout registry: every evaluation of a viewed window is logged with an override reason
  (`results/etf/holdout_registry_full2etf.json`: 4 entries). Viewed windows are never relabelled as fresh.
* Multiple-testing audit: deflated Sharpe ratio with ~260 trials (52 candidates × 5 selection rounds on
  related data).
* Stress: 0×/1×/2×/3× costs, 1-session entry delay, 10 %/25 % missed fills, parameter perturbations,
  leave-one-member-out, per-instrument and per-year splits, block bootstrap (10-day blocks).
* Experiment log: `results/etf/experiment_log.jsonl`, `results/experiment_log.jsonl`; config snapshot and
  data provenance inside `results/etf/study/study.json`; input fingerprints `data/meta/input_fingerprints.json`.

## Performance summary (net, exact windows)
| Test | Window | Trades | Trades/wk | 0-trade weeks | PF 1× | PF 3× | Net return | CAGR | Max DD | Sharpe | Benchmark |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ETF book, train | 2008-01-02→2020-12-31 | 763 | 1.12 | 40 % | 1.28 | 1.14 | +62.2 % | 3.8 % | −13.0 % | 0.58 | — |
| ETF book, common (viewed) | 2021-01-04→2025-09-11 | 267 | 1.09 | 41 % | 1.49 | 1.38 | +33.0 % (gross +37.8 %) | 6.3 % | −9.4 % | 0.94 | SPY +86.6 %, QQQ +90.5 % |
| SPY only (viewed) | 2021-01-04→2025-09-11 | 140 | 0.57 | 51 % | 1.34 | 1.23 | +11.5 % | 2.4 % | −8.2 % | 0.60 | +86.6 % |
| QQQ only (viewed) | 2021-01-04→2026-09-29 | 157 | 0.52 | 54 % | 1.29 | 1.21 | +12.0 % | 2.0 % | −9.0 % | 0.56 | +142.1 % |
| MES D full MTF, train | 2019-11-01→2022-12-31 | 218 | 1.33 | 49 % | 1.05 | exp R −0.094 | +5.4 % | 1.7 % | −8.1 % | 0.22 | — |
| MES D full MTF, viewed | 2024-01-02→2026-10-20 | 225 | 1.55 | — | 0.79 | — | −26.4 % | — | −28.4 % | — | — |
Geometric monthly equivalents: ETF train 0.31 %, ETF common 0.51 %. These are not targets and are not
extrapolated.

## Status by requirement
| Requirement | Status |
|---|---|
| Reproduce reported results | done (exact) — then shown invalid (price basis, slot look-ahead, window labels) |
| SPY-only / QQQ-only / common-window tests | done, exact dates |
| Price-basis integrity | fixed; executable fills, dividends, borrow; QQQ rebuilt and validated |
| Lumibot integration (backtest, parity, paper) | done; paper = simulated-broker dry run (no paper credentials) |
| TradingAgents integration | done (adapter, schema, PIT, cache, fail-closed, real graph offline); real research blocked (no LLM key) |
| Multi-timeframe engine | done on MES 1-min; ETF intraday blocked (daily data) |
| Multi-market | ETF matrix (17 ETFs), MES futures; stocks / FX / spot gold blocked (data) |
| Account-rule simulator | done (configurable, exact breach dates, 10 boundary tests, rolling replays) |
| Risk controls & stacking at equal risk | done (gate, lockouts, caps; stacking ablation train + viewed) |
| Walk-forward, untouched holdout | walk-forward done; **no untouched holdout remains** |
| Trade frequency 1–5/week | not reachable with a defensible edge (1.1/week; relaxing filters dilutes expectancy) |

## What cannot be concluded
* Whether the SPY/QQQ effect persists: no untouched data remains; forward paper records are the next test.
* Whether TradingAgents adds value: no credentials, and historical LLM use is not point-in-time safe.
* Anything about intraday ETF behaviour, single stocks, FX or spot gold.
* Whether controlled stacking is genuinely better (measured post hoc, sensitive to engine details).

## Reproduce everything
```bash
scripts/setup_envs.sh                                     # .venv (Lumibot) + .venv-agents (TradingAgents)
.venv/bin/python -m swingtrader download                  # pinned MES/SPX files (sha256-verified)
python scripts/rebuild_qqq_raw.py                         # needs the user QQQ upload in data/raw/etf_user/
python scripts/import_kaggle_etfs.py <unzipped_kaggle_dir>  # optional: market matrix ETFs
python -m swingtrader etf-study --reselect                # ETF selection + study (~40 min with walk-forward)
python scripts/etf_market_matrix.py                       # per-ETF matrix + stacking on the training window
python -m swingtrader mtf-study                           # MES multi-timeframe study (~2 min)
.venv/bin/python -m swingtrader lumibot-etf --full        # Lumibot backtest + parity report
.venv/bin/python -m swingtrader etf-paper --sessions 120  # paper mode: simulated-broker dry run
.venv/bin/python -m swingtrader etf-paper --broker        # PAPER broker only (credentials required)
python -m pytest -q && .venv/bin/python -m pytest -q && .venv-agents/bin/python -m pytest -q
```
Kill switches: create `state/etf_paper/KILL_SWITCH` (no new entries) or set `SWINGTRADER_DISABLE_ORDERS=1`
/ create `state/etf_paper/DISABLE_ORDERS` (no orders of any kind). Live trading does not exist in this
codebase.

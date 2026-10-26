# Project audit (2026-10-26)

Branch `claude/youthful-hopper-e6kuzz` (built on `claude/admiring-johnson-nch2lh`). Baseline before the
audit: 106 tests passing (1 skipped: Lumibot not installed in the default interpreter); after: 157 core,
166 in the Lumibot environment (+4 integration), 157 in the TradingAgents environment — all passing.

## Architecture (after the audit)
| Layer | Module | Role |
|---|---|---|
| Data | `etf/data.py`, `data/` (MES pipeline), `mtf/bars.py` | provenance, price-basis contract, completed bars, coverage/windows |
| Signals | `etf/strategies.py` (52-candidate grid), `mtf/engine.py` (MTF variants), `strategies/` (phase-1 MES daily) | deterministic, causal |
| Risk | `etf/risk.py` `PortfolioRiskGate`; `risk.py` (phase-1 MES) | final deterministic veto; lockouts; caps |
| Reference simulators | `etf/engine.py`, `mtf/engine.py`, `backtest/engine.py` | research + parity reference; never submit orders |
| Research / selection | `etf/research.py`, `etf/study.py`, `mtf/study.py`, `research/` | training-only selection, holdout guard, walk-forward, stress |
| Analytics | `etf/analytics.py` | net metrics, geometric monthly, exposure, costs, concentration, opportunities |
| Account rules | `rules/account.py` | hypothetical rule replay with exact breach dates |
| Research overlay | `agents/etf_research.py`, `agents/ta_worker.py` (.venv-agents) | TradingAgents records, PIT validation, fail-closed gate |
| Execution | `lumibot_bridge/etf_strategy.py`, `etf_backtest.py`, `etf_parity.py`, `etf_paper.py` | the only ETF order path (Lumibot) |
| Safety | `safety.py`, `orders.py` | global order switch, kill switch, OrderGuard idempotency, `LIVE_TRADING_ENABLED = False` |

## What already existed and worked
Phase 1 (MES daily): pinned sha256-verified data, session builder, causal indicators, deterministic risk
core, backtester, training selection + holdout guard, Lumibot backtest replay for MES, TradingAgents
worker with a point-in-time local vendor and a scripted offline model, local paper runner with
OrderGuard. ETF phase (rounds 1–4): daily ETF engine, 52-candidate grid, gates, holdout registry.

## Confirmed bugs (all fixed, each with a regression test)
| # | Severity | Bug | Effect | Fix / test |
|---|---|---|---|---|
| 1 | high | ETF loader scaled OHLC by `Adj Close / Close` | every fill, stop, target and mark of rounds 1–4 at prices that never traded; dividends never modelled explicitly | executable OHLC + `adj_factor` + `dividend`; signals on the adjusted view; dividend cash and short borrow (`test_parse_csv_keeps_executable_prices_and_audit`, `test_fills_use_raw_prices_and_dividends_are_credited`, `test_short_pays_dividend_and_borrow`, `test_ex_dividend_drop_is_not_a_gap_signal`) |
| 2 | high | reference engine freed a position's slot/risk budget for an entry at the session open although the position only exited later that session | look-ahead; materially changed training results and selection | `occupied_at_open` (`test_intraday_exit_does_not_free_the_slot_for_the_same_open`) |
| 3 | high (reporting) | round 3 labelled a SPY+QQQ test "2021–2026" although SPY ends 2025-09-11; buy & hold compared on different windows | misleading comparison | `coverage()`, `common_window()`, `buy_hold()` with exact dates; per-instrument + common-window reports (`test_windows_and_buy_hold_report_exact_dates`) |
| 4 | medium | a position in an instrument whose data ends stayed "open" with stale marks | latent risk-budget leak | close at the instrument's last close (`test_position_closed_when_instrument_data_ends`) |
| 5 | medium | turn-of-month feature used the length of the (incomplete) last month | calendar signals at the data end | NaN for the incomplete month (caught by `test_calendar_signal_enters_last_session_of_month`) |
| 6 | high (Lumibot) | sizing from `get_portfolio_value()`, which Lumibot marks at the current session's close | look-ahead in live/backtest sizing | point-in-time equity from broker cash + completed closes |
| 7 | medium (Lumibot) | dividends silently not credited by Lumibot's backtest broker | equity understated vs reality | entitlement ledger events; parity to the cent |
| 8 | high (safety) | a recovered book entry the broker did not hold triggered a SELL | unintended short on a real account | exits require a matching broker position (`test_no_exit_order_for_a_position_the_broker_does_not_hold`) |
| 9 | medium | agent research worker clamps data with `<= as_of`; a pre-open decision on day D could see D's close | look-ahead for ETF research | parquet cut to sessions < D; record's data_cutoff = last served session |
| 10 | medium (policy) | phase-1 overlay `veto` mode failed **open** | unvalidated AI absence changed nothing, contrary to spec | fail-closed for agent-assisted entries (test updated: documented requirement change) |
| 11 | low (data) | Kaggle `liewyousheng` file misses QQQ's 2020-09-21 dividend | 0.14 % adjustment error before 2020-09 | documented; QQQ rebuilt from Alpha Vantage dividends instead |

## Stacking audit (the round-2 question)
Round 2's +63.3 % stacked SPY-proxy result came from holding up to four correlated long index bets at
once in a bull market (proxy data, now superseded). With the corrected engine on real SPY+QQQ and
compared at **equal average exposure**, controlled stacking improved risk-adjusted results modestly in
both training and the viewed window (`docs/MARKET_RESULTS.md`) — the opposite of the pre-fix measurement.
Stacking was not pre-registered; it stays a hypothesis.

## Unresolved limitations
* No untouched holdout remains for SPY/QQQ daily (2021+ viewed 4×) or MES (2024+ viewed in phase 1).
* No LLM credentials: TradingAgents research quality / incremental value / variability unmeasured.
* No paper-broker credentials: paper mode verified only as a simulated-broker dry run.
* ETF intraday multi-timeframe research blocked (daily data only).
* Single stocks (survivorship), FX and spot gold (no bid/ask data) blocked.
* Lumibot daily backtests cannot execute open-decided entries; such members run only in the reference engine.
* Quality of the free Kaggle ETF files is mixed (one missing dividend found; TLT unadjusted).

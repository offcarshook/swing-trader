# TradingAgents + Lumibot: end-to-end pipeline, parity and paper-mode evidence

Reproduce: `.venv/bin/python -m swingtrader lumibot-etf --full` → `results/parity/parity.json`,
`*_trades.csv` (trade-by-trade comparison), `*_lumibot_ledger.csv` (every signal, order, fill,
dividend entitlement, reconciliation event). Tests: `.venv/bin/python -m pytest tests/test_lumibot_etf.py`.

## End-to-end pipeline (tested in `test_end_to_end_research_gate_risk_lumibot_ledger`)
1. Point-in-time data: executable SPY/QQQ bars; the adapter only sees sessions before the decision.
2. Deterministic candidate from the frozen book (`etf/strategies.py`).
3. Research record: recorded `ResearchRecord`s (generated at decision time, Buy SPY / Sell QQQ) read by
   `ResearchService` in replay mode; `gate` policy.
4. Deterministic veto/approval: `PortfolioRiskGate` (multiplier clamped to [0,1]).
5. Lumibot simulated order (market entry; stop and limit protection after the fill).
6. Reconciled ledger: every QQQ long and SPY short candidate is logged `overlay_veto`, no such order is
   submitted, the closed-trade count plus open positions equals the submitted entries, no
   `reconcile_mismatch`, and the reference engine with the same filter produces the same trades.

## Parity: reference engine vs Lumibot 4.6.30
Frozen book members run in Lumibot: `mr_long_bb_low`, `mr_long_low7`, `mr_long_wr-90`, `mr_long_key_rev`,
`mr_long_mon_down`, `mrshort_short_up3`. **Excluded:** `gap_long_go1` (decided at the open; Lumibot daily
backtests have no clock at the open). The reference engine runs with `exec_style="lumibot"` (protection
from the session after entry, time stop at the next open) so that only implementation differences remain.

| Run | Window | Ref trades | Lumibot trades | Matched | Same shares | Same entry / exit price | Same exit session | P&L before fees ref / Lumibot | Dividends ref / Lumibot ledger |
|---|---|---|---|---|---|---|---|---|---|
| Fixture, zero costs | 2019-01-02 → 2019-12-31 | 67 | 65 | **65** | **65** | **65 / 65** | **65** | **$5,450.13 / $5,450.13** | $0 / $0 |
| Fixture, 1× costs | 2019 | 68 | 65 | 65 | 28 | 0 / 0 (by design) | 64 | $4,882.54 / $5,409.42 | $0 / $0 |
| Production window, 1× costs | 2021-01-04 → 2025-09-11 | 254 | 253 | **253** | 211 | 0 / 0 (by design) | 251 | $36,347.44 / $38,758.74 | **$503.89 / $503.89** |

Final equity, production window: Lumibot $136,055.60 (+$503.89 dividend entitlements it does not credit =
$136,559.49) vs reference (Lumibot timing) $135,237.41 → +0.98 %. Reference with its own timing (same 6
members): $134,732.31.

### Explained differences
* **Unmatched reference trades** are entries on the last session of the window (Lumibot ends before the
  fill) — 2 in each fixture — plus one 2019 and one 2025 SPY entry whose sizing differed after cost-driven
  equity divergence.
* **Prices with costs:** the reference engine puts slippage into the fill price (1 bp, +2 bp on stops);
  Lumibot fills at the bar price and charges `percent_fee` on notional; the extra stop slippage has no
  Lumibot equivalent. Same exposure, different bookkeeping → entry/exit prices never equal, P&L "before
  fees" differs by construction, and the slightly lower Lumibot cost causes the +0.98 % final difference.
* **Shares with costs:** each engine's equity differs by the cost bookkeeping, so the 1 %-risk share
  count differs by ±1 share on some trades (zero-cost: identical).
* **Daily equity correlation ≈ 0.65–0.69:** Lumibot's own daily `portfolio_value` snapshot is marked at a
  different moment than the reference session close (see the look-ahead note below); end-to-end P&L agrees.

### Defects found while building parity (all fixed, with regression tests)
1. **Reference engine slot look-ahead:** a position that would be stopped *during* session D freed its
   symbol slot and risk budget for an entry at D's *open*. Fixed; training selection and the study were
   rerun (`test_intraday_exit_does_not_free_the_slot_for_the_same_open`).
2. **Lumibot valuation look-ahead:** `get_portfolio_value()` inside the iteration for session D is often
   marked at D's close. The adapter sizes from point-in-time equity instead (probe: identical to the
   reference previous-close equity on every session checked).
3. **Lumibot dividends:** the backtest broker never credited the `dividend` column to cash in this path
   (probe with four alignments). The adapter records entitlements; parity matches to the cent.
4. **Unsafe exit after recovery:** a recovered book entry that the broker did not hold triggered a time-stop
   SELL (on a real account: an unintended short). Exits now require a matching broker position
   (`test_no_exit_order_for_a_position_the_broker_does_not_hold`).

## Paper-mode evidence (no broker connected)
* `--broker` without paper credentials → `{"status": "blocked"}`; IB on the live port 7496 or Alpaca with
  `ALPACA_IS_PAPER != true` → refused (`test_paper_broker_mode_refuses_without_paper_credentials`).
* Simulated-broker dry run (`.venv/bin/python -m swingtrader etf-paper --sessions 120`): window
  2025-03-21 → 2025-09-11, 119 iterations, 75 orders submitted, 50 fills, 25 closed trades, no open
  positions, `live_trading_enabled: false`; state in `state/etf_paper/` (orders.json, book.json,
  heartbeat.txt, journal.jsonl with UTC and New York timestamps).
* Restart: rerunning the same window on the same state → `state_recovered`, 29 orders blocked as
  duplicates for sessions already handled.
* Recovery mismatch → `reconcile_mismatch`, entries blocked; kill-switch file → entries blocked (policy
  `flatten` exits only positions the broker holds); `SWINGTRADER_DISABLE_ORDERS=1` → zero orders of any
  kind (`test_global_order_switch_blocks_every_order`).
* Hard-risk supremacy in Lumibot: kill switch active + an "LLM" returning multiplier 10 → every signal
  `kill_switch`, zero orders (`test_kill_switch_beats_an_eager_llm_in_lumibot`).

## TradingAgents evidence
* Real v0.7.0 graph run offline with the scripted local model on point-in-time SPY bars for a
  2024-03-05 decision (`results/agents/plumbing_SPY_2024-03-05/`): market analyst tool calls requested data
  up to 2024-03-05, the local vendor served only ≤ 2024-03-04; the record maps to the schema and is
  **rejected** by validation (status `plumbing_test`, generated after the decision deadline).
* Adapter contract tests (`tests/test_etf_research_adapter.py`, 21): schema round trip; look-ahead,
  late/hindsight, contradictory, unknown-field, missing-field and malformed records rejected; replay never
  calls a model; forward mode refuses past decisions and fails closed without credentials (budget counted,
  retries); data-fingerprint-keyed cache; gate policy fails closed and vetoes opposition; an LLM
  "recommendation" cannot bypass daily-loss, drawdown, kill-switch, open-risk or gross limits.
* Not measured (blocked: no LLM credentials): real research quality, incremental value over the
  deterministic baseline, run-to-run variability. Historical LLM evaluation is not point-in-time safe in
  any case; forward paper logging is the only valid path.

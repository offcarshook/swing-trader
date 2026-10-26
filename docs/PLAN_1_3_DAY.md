# Research plan: 1–3 day futures swing trading (phase 2)

Status: **audit + plan only**. Implementation waits on multi-market data (see §1).
Nothing here reuses Kronos code; it extends the existing `swingtrader` core.

## 1. Data audit (what is genuinely available today)

| Source | Instruments | Intervals derivable | Span | Usable for 1–3 day research? |
|---|---|---|---|---|
| Pinned HF MES file (validated) | MES | 1m → 15m / 30m / 1h / session | 2019-05 → 2026-10 | **yes** (single market) |
| Pinned HF SPX file | S&P 500 cash index | 1m → intraday, RTH only | 2008 → 2026-10 | proxy only (no overnight, not tradable) |
| Pinned HF MNQ file | MNQ | 1m | 2022-01 → 2025-09 | doubtful: 43,701 duplicate timestamps, no volume |
| Pinned HF ES file | ES | 1m | 2020-11 → 2024-07, large holes | cross-check only |
| **Databento** | all CME/CBOT/NYMEX/COMEX futures | 1m / 1h / 1d OHLCV, definitions | 2010+ | **needed** for multiple markets |

Blocker on 2026-10-26: `hist.databento.com` is reachable, but **`DATABENTO_API_KEY` is not
present in this session's environment** (secrets reach new sessions only). Yahoo is only partly
allowed and rate-limited.

## 2. Candidate universe (to be confirmed by a per-market data audit)

Selected for liquidity in micro/mini size, distinct drivers and 23-hour Globex sessions:

| Sector | Markets | Tick value (micro) |
|---|---|---|
| Equity index | MES, MNQ, M2K, MYM | $1.25, $0.50, $0.50, $0.50 |
| Rates | ZN, ZF (or 10Y micro yield) | $15.625, $7.8125 |
| Metals | MGC, SIL | $1.00, $5.00 |
| Energy | MCL | $1.00 |
| FX | M6E, M6A / 6J | $1.25, $1.00 / $6.25 |
| Ags (only if costs allow) | ZC, ZS | $12.50 |

Inclusion rules: complete data with ≤ 1% missing RTH bars per year, ≥ 8 years history, and a
round-trip cost of at most 10% of the median 1-day ATR in dollars. Markets that fail stay out,
whatever this does to the trade count.

## 3. Holding-time definition (exact)

* **Holding period = elapsed exchange trading time between fill and exit**, measured in Globex
  session-hours from the market's own calendar. Weekend and holiday closures do not count.
* Target: one to three **sessions** ("1–3 days"). Hard time stop: exit at the first RTH close
  after **3 completed sessions** (a Friday entry exits by Wednesday at the latest).
* Calendar days are reported alongside, so weekend holds are visible.
* Minimum hold: no exit before the next session's open (no intraday round trips).

## 4. Strategy families (redesigned for 1–3 day holds, not shortened 10-day rules)

Decision bars: 15m, 30m, 1h, evaluated on closed bars only; daily bars give context.
Each family has ≤ 4 parameter sets per bar size. Every parameter set is run long-only,
short-only and both, and a side is kept only if it passes on its own.

1. **Trend pullback (1–3 days):** daily trend filter (e.g. 50-day slope); entry on an hourly
   pullback into a VWAP/EMA band followed by a reclaim; stop below the swing low in ATR units;
   exit at a 1–1.5 R target, on a trailing stop, or at the 3-session time stop.
2. **Breakout with filters:** prior-day high/low or overnight-range break on 30m/1h closes,
   only when volatility is compressed (NR4/NR7 or a low ATR percentile) and the daily regime
   agrees; failed-breakout exit.
3. **Regime-gated mean reversion:** RSI/z-score extremes on 1h bars, only when the market is
   range-bound (low ADX, flat 20-day trend); exit at the mean or the time stop.
4. **Portfolio layer:** combine the surviving families across markets. Measure signal overlap
   and the correlation of open positions; apply sector caps (e.g. at most 2% open risk in
   equity index) and a portfolio cap of 5–6% total open risk.

## 5. Execution realism additions

* Fills at the next bar's open plus a slippage term per market; stop fills at the stop or
  through the gap; worse fills overnight and in thin hours.
* Overnight/weekend gap stress: replay the worst 1% of gaps across the whole book at once.
* Per-market roll calendars from Databento definitions; margin from current exchange
  schedules (stored in config).

## 6. Validation

* **Rolling walk-forward:** 3-year train, 1-year test; parameters chosen only on the train part.
* **Fresh untouched final test:** the most recent ~18 months for every market, guarded by
  `HoldoutGuard` (the earlier MES holdout is spent).
* **Gates:** positive net expectancy at 2× costs, profit factor ≥ 1.2, positive in at least 70%
  of walk-forward folds, positive in most markets (not just one), beats a random-entry
  baseline with the same holding time, maximum portfolio drawdown ≤ 20%.
* **Report:** trades per month (histogram, never forced), holding-time distribution,
  expectancy, profit factor, win rate, return, drawdown, costs, results per market, per regime
  and per side, correlated-loss days.
* The 5–8% per month figure is treated as a hypothesis and reported only as it comes out.

## 7. Fallback if Databento stays unavailable
Run the whole plan on MES alone (1m data → 15m/30m/1h). The trade-frequency target will be
reported as probably unreachable with one market rather than met by loosening rules.

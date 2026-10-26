# Per-market, per-instrument and per-strategy results

All figures net of modelled costs at 1× unless stated. "Viewed" = a window that has already been
evaluated in an earlier round and therefore cannot serve as an untouched holdout.

## Markets actually tested
| Group | What was tested | Data | Result |
|---|---|---|---|
| A — US ETFs | frozen SPY/QQQ book; per-instrument matrix on 17 ETFs | daily | modest edge on US equity ETFs, none elsewhere |
| A — proxy | S&P 500 cash index (rounds 1–2) | 1-min → daily | misleading (stale opens); proxy-only, superseded |
| B — single stocks | not tested | — | blocked: no survivorship-free universe |
| C — index futures | MES multi-timeframe study | 1-min | no edge after costs (`docs/MTF_RESULTS.md`) |
| D — FX / spot gold | not tested | — | blocked: no bid/ask history |

## The frozen ETF book (training-only selection on SPY+QQQ 2008–2020, corrected engine)
Members (`results/etf/study/train_selection_corrected.json`, hash `4a875e67a82950ec`):
`gap_long_go1` (gap-and-go ≥ 1 ATR), `mr_long_bb_low` (close below lower Bollinger band, SMA5 exit),
`mr_long_low7` (close at a 7-day low), `mr_long_wr-90` (Williams %R < −90), `mr_long_key_rev`
(key reversal), `mr_long_mon_down` (down Monday), `mrshort_short_up3` (3 up closes in a downtrend, short).

### Per instrument — frozen book applied to each ETF alone (`scripts/etf_market_matrix.py`)
| ETF | Data | Train trades | Train PF | PF @2× | Train return | Train max DD | Buy & hold (train) | 2021+ trades | 2021+ PF | 2021+ return |
|---|---|---|---|---|---|---|---|---|---|---|
| SPY | 1993-02-01→2025-09-11 | 396 | 1.22 | 1.15 | +23.5 % | −12.7 % | +232.6 % | 140 | 1.34 | +11.5 % |
| QQQ | 1999-03-10→2026-09-29 | 371 | 1.34 | 1.25 | +31.0 % | −4.5 % | +589.6 % | 157 | 1.29 | +12.0 % |
| IWM | →2020-04-01 | 333 | 1.15 | 1.10 | +11.7 % | −8.0 % | +66.7 % | – | – | – |
| DIA | →2022-08-08 | 374 | 1.08 | 1.04 | +8.8 % | −17.7 % | +216.0 % | 47 | 0.98 | −0.3 % |
| XLF | →2022-08-08 | 342 | 1.22 | 1.09 | +20.9 % | −7.6 % | +61.9 % | 49 | 1.39 | +4.1 % |
| XLK | →2022-08-08 | 385 | 1.17 | 1.06 | +16.4 % | −10.5 % | +498.3 % | 46 | 1.46 | +4.9 % |
| SMH | →2022-08-08 | 370 | 1.19 | 1.07 | +15.4 % | −9.5 % | +672.4 % | 48 | 1.00 | −0.0 % |
| XLV | →2022-08-08 | 375 | 1.20 | 1.12 | +18.4 % | −8.9 % | +301.9 % | 46 | 0.86 | −1.6 % |
| GLD | →2022-08-08 | 344 | 1.23 | 1.15 | +22.8 % | −18.9 % | +113.5 % | 24 | 0.54 | −3.8 % |
| SLV | →2020-04-01 | 298 | 1.05 | 0.94 | +4.6 % | −14.1 % | −12.4 % | – | – | – |
| TLT | →2024-08-19 (unadjusted) | 356 | 0.89 | 0.83 | −11.6 % | −22.6 % | +70.0 % | 60 | 0.68 | −5.9 % |
| IEF | →2020-04-01 | 354 | 0.89 | 0.78 | −11.1 % | −20.7 % | +88.3 % | – | – | – |
| USO | →2020-04-01 | 263 | 0.78 | 0.70 | −15.4 % | −18.1 % | −94.3 % | – | – | – |
| XLE | →2022-08-08 | 295 | 0.83 | 0.75 | −11.4 % | −13.9 % | −31.3 % | 51 | 1.52 | +5.8 % |
| EFA | →2020-04-01 | 337 | 0.92 | 0.86 | −9.3 % | −17.1 % | −7.2 % | – | – | – |
| EEM | →2020-04-01 | 289 | 0.94 | 0.84 | −5.0 % | −14.5 % | −16.8 % | – | – | – |
| DBC | →2022-08-08 | 287 | 0.70 | 0.62 | −25.4 % | −27.7 % | −52.1 % | 60 | 1.79 | +12.5 % |

Reading: the effect is a **US-equity short-term mean-reversion effect**. It does not transfer to rates,
oil, broad commodities, energy or international equity (PF < 1 in training for TLT, IEF, USO, XLE, EFA,
EEM, DBC). US equity ETFs other than SPY/QQQ are highly correlated with them and add exposure, not
independent evidence. The book is not deployed beyond SPY/QQQ.

### Per strategy member — common window 2021-01-04→2025-09-11 (viewed), SPY+QQQ, 1×
| Member | Trades | P&L |
|---|---|---|
| mr_long_low7 (7-day low) | 96 | +$18,741 |
| mr_long_mon_down (down Monday) | 81 | +$8,536 |
| mr_long_key_rev (key reversal) | 32 | +$4,716 |
| mr_long_bb_low (Bollinger) | 21 | +$2,914 |
| mrshort_short_up3 (short) | 24 | +$1,225 |
| mr_long_wr-90 (Williams %R) | 1 | −$1,067 |
| gap_long_go1 (gap-and-go) | 12 | −$2,113 |
By direction: longs 243 trades +$31,727; shorts 24 trades +$1,225. On QQQ alone the gap-and-go member
lost $6,816 (11 trades) and the short lost $1,128.

### Exact windows (date integrity)
| Test | Window | Sessions | Trades | PF | Net return | Max DD | Benchmark (total return, same dates) |
|---|---|---|---|---|---|---|---|
| SPY only | 2021-01-04 → 2025-09-11 | 1,178 | 140 | 1.34 | +11.5 % | −8.2 % | SPY +86.6 % (max DD −24.5 %) |
| QQQ only | 2021-01-04 → 2026-09-29 | 1,441 | 157 | 1.29 | +12.0 % | −9.0 % | QQQ +142.1 % (max DD −35.1 %) |
| Common portfolio | 2021-01-04 → 2025-09-11 | 1,178 | 267 | 1.49 | +33.0 % | −9.4 % | SPY +86.6 %, QQQ +90.5 %, 50/50 +88.6 % |
The often-quoted "QQQ +142 %" is QQQ's own longer window to 2026-09-29; on the common window ending
2025-09-11 QQQ returned +90.5 %. The earlier "2021–2026 SPY+QQQ" label was wrong: SPY data ends 2025-09-11.

## Stacking at comparable risk (SPY+QQQ)
| Variant | Train 2008–2020 CAGR | Train max DD | Train Sharpe | Avg gross exposure | CAGR per 100 % gross | Viewed 2021–25 CAGR / DD / Sharpe |
|---|---|---|---|---|---|---|
| One position per ETF (primary) | 3.79 % | −13.0 % | 0.58 | 22.7 % | 16.7 | 6.27 % / −9.4 % / 0.94 |
| Stacked, same 1 % per trade | 6.58 % | −14.0 % | 0.71 | 29.2 % | 22.5 | 9.37 % / −10.8 % / 1.00 |
| Stacked, **equal exposure** (0.78 % / 0.75 % per trade) | 6.38 % | −10.5 % | 0.76 | 25.6 % | 24.9 | 8.32 % / −9.3 % / 1.00 |
| Stacked, 2R cluster cap on US equity | 5.25 % | −10.0 % | 0.79 | 22.5 % | 23.3 | 5.81 % / −9.8 % / 0.85 |
With the corrected engine, controlled stacking improved risk-adjusted results at equal exposure in both
windows. Before the slot-accounting fix the opposite was measured (stacking ≈ just more exposure); the
reversal shows how sensitive this conclusion is. Stacking was not part of the pre-registered selection,
so it is a hypothesis for forward paper validation, not an adopted change. The Lumibot adapter keeps one
position per ETF (broker positions are per asset).

## Trade frequency
Common window: 1.09 completed trades/week, 41 % of weeks with zero trades, 601 opportunities detected,
267 accepted, 334 rejected (all because the ETF already had a position; 173 were same-symbol same-day
duplicates from different members). Holding time: 8 trades closed in the entry session (stops),
104 after 1 session, 55 after 2, 100 after 3. Filter relaxation (single IBS rule, SPY+QQQ, 2× costs;
train 2008–2016 / validation 2017–2020): threshold 0.10 → 0.35 raises frequency from 0.44 to 1.17
trades/week in training but drives train expectancy from +0.068 R to −0.001 R (validation: +0.111 R →
+0.058 R). Williams %R −97.5 → −75: 0.11 → 0.49 trades/week, train expectancy +0.282 R → +0.103 R.
More trades diluted the edge. The 1–5 setups/week target is not reachable with a defensible edge on the
data available.

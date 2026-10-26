# ETF 1–3 day swing phase — results

> **AUDIT CORRECTION (2026-10-26, round 5). Rounds 1–4 below are kept for the record but several of their
> numbers and labels are superseded:**
> * Every round 1–4 fill, stop and target used **dividend-adjusted prices** that never traded (loader bug).
> * The reference engine let a position stopped out *during* a session free its slot for an entry at that
>   session's *open* (look-ahead in slot/risk accounting).
> * Round 3's "2021-01 → 2026-09 SPY+QQQ" label was wrong: SPY data ends **2025-09-11**; after that the
>   "portfolio" was QQQ alone. Its buy & hold figures (+86.6 % SPY, +142.1 % QQQ) were on **different**
>   windows (SPY to 2025-09-11, QQQ to 2026-09-29).
> * The round-1/2 proxy results (S&P cash index) are proxy research only; the index's stale opens made gap
>   and narrow-range patterns look better than they trade.
> * Round 4's 15-ETF result used the buggy engine and mixed data sources (see `docs/DATA_AUDIT.md`).
> * The 2021+ window has now been looked at **four times** (`results/etf/holdout_registry_full2etf.json`);
>   it is permanently "previously viewed". **No untouched ETF holdout remains.**
>
> Current, audited results: **Round 5** at the end of this file, `docs/MARKET_RESULTS.md`,
> `docs/FINAL_VALIDATION.md`.

## TL;DR
* **The 15-ETF basket test could not be run**: the Alpha Vantage key in this session is a free key.
  `outputsize=full` is premium, so each ETF returns only the latest **100 sessions**, and the
  quota is **25 calls/day** (5 ETFs fetched before it ran out: SPY QQQ IWM DIA TLT, 2026-06-03 → 2026-10-23).
  100 bars is not enough to warm up a 200-day trend filter, let alone train and test.
* Everything is built and tested so the basket run is one command once full-history CSVs exist
  (`data/raw/etf_full/<SYM>.csv`, any `date,open,high,low,close[,adj close],volume` file).
* To get *some* real evidence, the full protocol ran on **one market**: daily bars built from the
  pinned S&P 500 1-min file as a **SPY proxy** (index, no dividends, RTH open/close).
* Result on that proxy: 4 of 5 families passed training; on the fresh final window
  (2021-01 → 2026-10) the combined book made **+12.3% total (≈2.0%/yr, 0.17%/month), PF 1.15,
  max drawdown −13.9%**, vs **+104.9% buy-and-hold**. At 3× costs PF falls to 1.04. **Not tradable
  as is.** Only the NR7 breakout held up out of sample.

## Protocol (pre-registered in `config/etf.yaml`)
* 28 candidates (`swingtrader/etf/strategies.py:grid`), ≤ 8 per family, written before any run.
* Train 2008-01 → 2020-12 only. Gates at **2× costs**: ≥ 30 trades, PF ≥ 1.2, positive expectancy,
  positive in ≥ 60% of yearly folds, above the 90th percentile of 100 random-entry runs with the same exits.
* Best train Sharpe per family is kept; kept candidates run together under **1% risk per trade,
  4% max open risk, 2× gross**, one position per ETF.
* Selection committed (`4252edf`) **before** the final window was touched; the final run is
  registered in `results/etf/holdout_registry_spx-proxy.json` (evaluation #1, no override).
* Caveat: S&P data after 2024-01 was already seen in phase 1 (MES holdout, different strategies),
  so the final window is "fresh for these rules", not pristine.

## Execution model
Signals decided at the close fill at the next open; gap signals are decided at the open and fill at it;
breakouts are buy/sell-stops at the setup bar's high/low. Stops gapped through fill at the open; stop wins
when stop and target share a bar; breakout trades can't hit target on the entry bar. Time stop = MOC on
session 3 (gap: 1–2). Costs: $0.005/share + 1 bp (3 bp SLV/USO/XLE/SMH/EEM) per side, +2 bp on stops.

## The five families on training (2× costs) — see `results/etf/TRAIN_spx-proxy.md`
| family | best candidate | passed? | train trades | PF@2× |
|---|---|---|---|---|
| 1. dip-buy in uptrend (RSI2) | rsi2<10, exit > SMA5 | **no** — PF 1.09 | 111 | 1.09 |
| 2. NR4/NR7/inside breakout | NR7 long, 1R target | yes (6 of 8 variants) | 181 | 1.56 |
| 3. gap fade / gap-and-go | go, gap ≥ 0.5 ATR | yes (fades all failed) | 64 | 1.90 |
| 4. calendar (turn of month) | after a down week, no trend filter | yes | 65 | 1.64 |
| 5. downtrend shorts (RSI2 > 90) | exit < SMA5 | yes, barely (30 trades) | 30 | 2.12 |
Combined train book: 316 trades (0.49/week), PF 1.78, +96.9%, max DD −5.1%.

## Final test (2021-01 → 2026-10, run once) — `results/etf/FINAL_spx-proxy.md`
| costs | trades | /week | PF | exp R | total | %/month | max DD |
|---|---|---|---|---|---|---|---|
| 1× | 191 | 0.66 | 1.15 | +0.07 | +12.3% | 0.17 | −13.9% |
| 2× | 191 | 0.66 | 1.11 | +0.05 | +9.0% | 0.13 | −15.4% |
| 3× | 190 | 0.66 | 1.04 | +0.02 | +3.8% | 0.05 | −16.7% |

By family: NR7 breakout +$13.5k (89 trades, avg +0.15R), calendar +$2.5k (21), gap-and-go −$2.2k (70),
shorts −$1.5k (11). 2025 and 2026 YTD were losing years (−$4.5k, −$5.6k).
Holding time: 17 trades closed on the entry day (stops), 39 after 1 session, 74 after 2, 61 after 3.

## Frequency target (1–5 setups/week across the basket)
One market gives 0.66 trades/week; 48.5% of weeks had none. Across 15 ETFs, ~5–10× more signals would
be expected, but equity ETFs are highly correlated, so many would be blocked by the 4% open-risk cap or
duplicate each other. **The target is plausible with the full basket but unverified.**

## What it takes to finish the basket test
1. Full daily history for the 15 ETFs (Alpha Vantage premium, or any vendor CSVs) in `data/raw/etf_full/`.
2. `python -m swingtrader etf audit --source full` → `etf select --source full` → commit → `etf final --source full`.
   That final run would be the basket's first and only look at 2021+.

## Round 2 (same day): 12 more setups + "stacking" for more trades/week
**Read this first:** the grid v2 candidates and the stacking option were added *after* the v1
final test had been run, so the 2021+ results below are a **second look at a window that was already used**.
Both runs are in `results/etf/holdout_registry_spx-proxy.json` with an override reason. Treat
them as a hint, not as out-of-sample evidence. The first clean test will be the full ETF basket.

New setups (`strategies.py:grid_v2`, 24 candidates, committed before running): IBS < 0.2, 3 down closes,
close below the lower Bollinger band, close at a 7-day low, Williams %R < −90, weak outside day, key reversal,
down Monday (all long, in an uptrend), the short mirrors IBS > 0.8 / 3 up closes / above the upper band
(in a downtrend), and 10-day-high momentum.

Passed training (2× costs, same gates): **Williams %R, weak outside day, IBS, 3 down closes**.
Failed: Bollinger, 7-day low, key reversal, down Monday (on the random-entry check), every short
mirror, and momentum (PF 0.91).

`--stack` lets *different* strategies hold the same ETF at once (still 1% per trade, 4% open-risk cap).

| run (2021-01 → 2026-10, 1× costs) | trades/wk | PF | total | %/mo | max DD | PF @3× |
|---|---|---|---|---|---|---|
| v1 only (clean test) | 0.66 | 1.15 | +12.3% | 0.17 | −13.9% | 1.04 |
| v1 + v2 | 1.09 | 1.09 | +10.7% | 0.15 | −10.8% | 0.98 |
| v1 + v2, stacked | **1.71** | **1.33** | **+63.3%** | 0.72 | −11.2% | 1.21 |
| buy & hold | – | – | +104.9% | – | ~−25% | – |

Caveats on the stacked run: on one market, stacking just means holding up to four long SPY bets
at once in a strong bull market, so part of the gain is extra market exposure, not extra edge.
Gap-and-go and downtrend shorts lost money again. Mean reversion (+$54k) and NR7 (+$11k) did the work.

## Round 3: real SPY + QQQ daily data (2 of the 15 ETFs)
Data supplied by the user: SPY 1993-02 → 2025-09-11 (dividend-adjusted via `Adj Close`) and QQQ
1999-03 → 2026-09-29 (already adjusted). Both pass the audit (one float-rounding row in QQQ is snapped).
The full grid (v1 + v2, 52 candidates) was selected on 2008–2020 only, committed, then run once on 2021+.
Caveats: SPY's 2021+ path was already seen through the S&P proxy. QQQ's had not been.

**Key finding: the S&P cash-index proxy was misleading.** A cash index's daily "open" is stale (it is
mostly built from the prior close), so on the index gaps and narrow-range bars were partly artefacts.
On the tradable ETFs, gap-and-go (PF 0.90), NR7 (PF 1.06), turn-of-month and RSI2 dip-buying all
**failed training**. Only short-term mean reversion survived: IBS < 0.2, close below the lower
Bollinger band, Williams %R < −90, down Monday.

| final 2021-01 → 2026-09 | trades/wk | PF | total | %/mo | max DD | PF @3× |
|---|---|---|---|---|---|---|
| mean-reversion book (primary) | 1.23 | **1.37** | **+29.5%** | 0.38 | −10.8% | 1.26 |
| same, stacked (secondary) | 1.64 | 1.28 | +36.5% | 0.45 | −15.1% | 1.19 |
| buy & hold SPY / QQQ | – | – | +86.6% / +142.1% | – | – | – |

The final test did *better* than training (train PF 1.13 at 1× costs), so treat it as luck plus a
friendlier regime, not as an edge that improved. 2022 lost money (few signals, because the uptrend
filter was off most of the year). The 1–5 setups/week target was met in only ~50% of weeks with
2 ETFs. The other 13 ETFs (bonds, metals, energy, international) are what would spread the signals out.

## Round 4: all 15 ETFs (Kaggle sources) — the strategies don't generalise
Sources (`scripts/import_kaggle_etfs.py`, provenance in `data/raw/etf_full/provenance.json`, not committed):
SPY/QQQ user uploads; DIA GLD XLE XLF XLK SMH from `liewyousheng/historical-etf` (ends 2022-08-08);
IEF SLV USO EFA EEM IWM from `jacksoncrow/stock-market-dataset` (ends 2020-04-01, so **training only**);
TLT from `kornilovag94/etfs-bonds-market-dataset` (unadjusted, ends 2024-08-19). The 2-ETF results
from round 3 were renamed `*full2etf*`.

**Training (2008–2020, all 52 candidates, 2× costs): only turn-of-month (after a down week, no trend
filter) passed** (498 trades, PF 1.33, 77% positive years, above 100% of random runs). Every mean-reversion
setup that worked on SPY+QQQ **failed on the basket**. IBS < 0.2, for example, lost money on 10 of 15
ETFs (SLV, IEF, EEM, USO, IWM, XLF, DIA, XLE …). The edge belongs to US large-cap equity indexes, not
to "ETFs".

**Final test 2021+ (run once; a crash in the buy-and-hold line forced one rerun of the same frozen
candidate, logged as evaluation #2):** 85 trades, PF **0.93**, **−2.1%**, max DD −12.6%. 0.29 trades/week.
It fails. Only 9 ETFs have post-2021 data, and most of those stop in 2022-08, so the window is thin.

### What the whole phase says
1. Short-term mean reversion on **SPY/QQQ** is the only thing that survived a clean out-of-sample test
   (round 3: PF 1.37, +29.5%, robust at 3× costs). It is not a basket-wide edge.
2. Gap, NR7, RSI2-dip and downtrend-short families did not hold up on tradable data.
3. 1–5 setups/week cannot be reached honestly: the rules that work fire ~1.2×/week on two correlated ETFs,
   and spreading them to other ETFs adds losing trades, not edge.


## Round 5 (audit, 2026-10-26): corrected engine, exact windows, frozen re-selection
Reproduce: `python -m swingtrader etf-study --reselect` → `results/etf/study/` (study.json, trades,
equity, opportunity logs, selection). Same pre-registered grid (52 candidates) and gates, training only
(2008–2020), SPY+QQQ executable prices with dividends, corrected slot accounting.

### Reproduction first
Round 3's numbers reproduce exactly from the old code and data: 355 trades, PF 1.37, +29.52 %, max DD
−10.84 % (stacked: 472, 1.28, +36.49 %, −15.13 %; 3× costs PF 1.26 / 1.19). They are not valid results
because of the defects listed in the banner.

### Training (2008–2020) — the only clean evidence
Frozen book (7 members, 10 of 52 candidates passed): see `docs/MARKET_RESULTS.md`. Training portfolio:
763 trades (1.12/week), PF 1.28, +62.2 % over 13 years (CAGR 3.8 %), max DD −13.0 %, Sharpe 0.58.
At 3× costs: PF 1.14, +29.3 %. Deflated Sharpe probability 0.48 for ~260 trials (52 candidates × 5
selection rounds) — **not statistically significant**.

### Walk-forward of the whole selection procedure (anchored, re-selected every year)
| Years | Chained return | Positive years | Selected beats the average candidate |
|---|---|---|---|
| 2013–2020 (out-of-sample within research data) | **+1.05 %** | 5 / 8 | 4 / 8 |
| 2021–2026 (viewed) | +27.5 % | 3 / 6 | 3 / 6 |
The selection procedure shows **no out-of-sample skill** in 2013–2020.

### 2021+ (previously viewed, reported with exact windows)
| Test | Window | Trades | PF 1× / 3× | Net return | Max DD | Benchmark (same dates) |
|---|---|---|---|---|---|---|
| SPY only | 2021-01-04 → 2025-09-11 | 140 | 1.34 / 1.23 | +11.5 % | −8.2 % | +86.6 % |
| QQQ only | 2021-01-04 → 2026-09-29 | 157 | 1.29 / 1.21 | +12.0 % | −9.0 % | +142.1 % |
| Common SPY+QQQ | 2021-01-04 → 2025-09-11 | 267 | 1.49 / 1.38 | +33.0 % | −9.4 % | 50/50 +88.6 % |
Gross (0× costs) common: +37.8 %. Costs at 1×: $293 commission, $3,095 slippage, +$787 dividends,
−$13 borrow. Five largest trades = 26.5 % of net profit (SPY alone: 61 %). 2022 lost money (−$5,820).
Block bootstrap (2,000 samples, 10-day blocks) of the common path: total return p5 / p50 / p95 =
+3.4 % / +32.7 % / +68.5 %, max DD p5 / p50 / p95 = −16.1 % / −8.9 % / −5.4 %.

### Conclusion
A small positive effect on US equity ETFs survives costs in training, but its significance does not
survive the multiple-testing correction, the selection procedure has no demonstrated out-of-sample
skill, the effect does not transfer to non-equity ETFs, and buy & hold beat it by a wide margin on every
window. No untouched holdout remains; the only valid next evidence is forward paper trading.

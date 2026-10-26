# ETF 1–3 day swing phase — results (2026-10-26)

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

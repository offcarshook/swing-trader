# Multi-timeframe results (MES, genuine 1-minute data)

**Verdict: multi-timeframe confirmation did not add value.** Under the pre-registered rule
(`config/mtf.yaml`: a multi-timeframe variant must beat both the single-timeframe baseline A and the
context-only variant B on net expectancy at 2× costs in train AND validation, with ≥100 train trades),
no long or short variant qualified. On the previously viewed 2024+ window every multi-timeframe long
variant lost 17–28 %.

Reproduce: `python -m swingtrader mtf-study` → `results/mtf/mtf_study.json` + per-variant trade CSVs.

## Why MES, and why not the ETFs
The SPY/QQQ files are daily. Resampling daily candles into 5m/15m/1h/4h bars would fabricate data, so
ETF intraday MTF tests are **blocked**. MES has 2.63 M genuine 1-minute bars (2019-05-05 → 2026-10-20).

## Engine (`swingtrader/mtf/`)
* `bars.py`: 15m / 1h / 4h buckets anchored to the 17:00 CT session start, daily = full Globex session.
  Each bar is stamped `available_at` = the moment it is complete (bucket end, capped at the 16:00 session
  end; early-close days keep the nominal, later time). Empty buckets are never created.
* `asof()` joins by timestamp (`merge_asof` on `available_at`), never by row position, so a lower
  timeframe only sees higher-timeframe bars that have completed.
* Decisions: every completed 15-minute bar with a close between 08:45 and 14:45 CT. Fill: open of the next
  real 1-minute bar (+1 tick). Exits are identical for every variant (stop 2.0 × ATR(1h,14), target 1.5 R,
  time stop at 14:59 CT of the second session after entry). Stops and targets are resolved on 1-minute
  bars, stop first when both are inside one minute; an open through the stop fills at that open + gap
  slippage. Roll costs are charged when a hold spans a CME roll date. Equity is marked at every session
  close. Risk: 1 % of equity per trade, max 20 contracts.
* Tests (`tests/test_mtf.py`, 7): session anchoring and completion stamps, an incomplete 4-hour bar is
  invisible at 10:15 and visible exactly at 13:00, identical decision rows when all data after a cut is
  removed (no look-ahead), DST weeks have 23 hourly buckets per session, missing minutes never create a
  bar, early close keeps the conservative completion time, real-data fills never precede decisions.

## Variants
| | Daily context | Vol regime | 4h trend | 1h setup (RSI2) | 15m trigger | Entry |
|---|---|---|---|---|---|---|
| A daily only (baseline) | trend + daily RSI2<10 | – | – | – | – | 08:30 CT next session |
| B context only | ✓ | ✓ | ✓ | – | – | each 1h close in RTH |
| C context + setup | ✓ | ✓ | ✓ | ✓ | – | right after setup bar |
| D full MTF | ✓ | ✓ | ✓ | ✓ | ✓ | after 15m trigger |
| E moderate | ✓ | – | – | ✓ | ✓ | after 15m trigger |
| F_* ablations of D | one component removed each | | | | | |
Shorts mirror everything (downtrends, RSI2 > 90, close below the prior 15m low).

## Results (net of costs; train 2019-11-01→2022-12-31, validation 2023, final 2024-01-02→2026-10-20 = viewed)

| Variant | Train trades | Train PF | Train exp R (1× / 2× / 3×) | Val trades | Val exp R 2× | Final (viewed) trades | Final PF | Final return | Final max DD |
|---|---|---|---|---|---|---|---|---|---|
| A daily only | 26 | 1.20 | 0.121 / 0.088 / 0.055 | 7 | −0.001 | 23 | 1.81 | +7.9 % | −2.8 % |
| B context only | 444 | 0.94 | −0.028 / −0.080 / −0.145 | 177 | −0.053 | 500 | 0.86 | −36.7 % | −41.9 % |
| C context + setup | 184 | 0.93 | −0.030 / −0.097 / −0.152 | 55 | +0.084 | 193 | 0.73 | −27.6 % | −30.6 % |
| **D full MTF** | 218 | 1.05 | +0.041 / −0.009 / −0.094 | 75 | −0.021 | 225 | 0.79 | −26.4 % | −28.4 % |
| E moderate | 290 | 0.98 | −0.003 / −0.060 / −0.132 | 89 | +0.012 | 298 | 0.90 | −17.7 % | −26.4 % |
| E moderate, 8h setup window | 378 | 0.95 | −0.027 / −0.082 / −0.146 | 125 | +0.007 | 395 | 0.97 | −7.1 % | −27.9 % |
| F no daily | 238 | 1.02 | +0.025 / −0.023 | 101 | +0.081 | 238 | 0.77 | −29.5 % | −31.5 % |
| F no vol filter | 230 | 1.04 | +0.036 / −0.013 | 75 | −0.021 | 240 | 0.79 | −27.6 % | −29.6 % |
| F no 4h | 277 | 0.98 | −0.007 / −0.065 | 89 | +0.012 | 279 | 0.89 | −17.1 % | −25.0 % |
| F no 1h setup | 416 | 1.00 | +0.005 / −0.052 | 170 | −0.100 | 442 | 0.89 | −26.1 % | −29.7 % |
| F no 15m trigger (= C) | 184 | 0.93 | −0.030 / −0.097 | 55 | +0.084 | 193 | 0.73 | −27.6 % | −30.6 % |
| D short | 7 | 0.59 | −0.248 / −0.268 | 13 | −0.490 | 17 | 1.25 | +2.1 % | −2.9 % |
| E short | 106 | 0.85 | −0.081 / −0.099 | 20 | −0.444 | 60 | 0.86 | −4.4 % | −9.0 % |
| E short, 8h window | 139 | 1.11 | +0.064 / +0.047 | 28 | −0.172 | 77 | 0.85 | −6.2 % | −11.5 % |

Trade frequency: D ≈ 1.3–1.6 trades/week, E ≈ 1.7–2.1, B ≈ 2.7–3.5 — the extra trades **diluted**
expectancy (B, F-no-setup) rather than adding edge. The median hold is 1 session; most exits are stops
(D final: 142 stops, 79 targets, 2 time exits), i.e. the 1-hour-ATR stop is tight relative to a 1–3 day
horizon. A 5-minute entry delay leaves the conclusions unchanged (`*_delay5min` rows in the JSON).

## Ablation reading
* Removing the volatility filter changes almost nothing (it rarely binds in 2023) — it can be dropped.
* Removing the 4-hour filter or the daily filter does not hurt train expectancy materially; neither
  timeframe adds measurable value here.
* Removing the 1-hour setup doubles trade count and turns validation expectancy clearly negative: the
  setup is the only component that carries information, and it is not enough after costs.
* The 15-minute trigger improves train expectancy slightly vs C but worsens validation; inconclusive.

## What cannot be concluded
* Only one instrument and ~7 years; no untouched holdout (MES 2024+ was the phase-1 holdout).
* The daily baseline A looks best but has 26 train trades — statistically unreliable.
* Results are specific to this feature set (kept deliberately small); they do not prove that no MTF
  design works, only that this controlled one does not add value after costs.

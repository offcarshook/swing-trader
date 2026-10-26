# Training-period selection report
Protocol: docs/VALIDATION_PROTOCOL.md (with Amendment 1). Training windows: `{'spx': ['2008-01-02', '2019-04-30'], 'mes': ['2019-05-06', '2023-12-31']}`. No holdout data is used anywhere in this report.
## All candidates (failed experiments included)
| id | passed | trades | profit_factor | expectancy_usd | expectancy_r | max_dd_pct | median_fold_sharpe | positive_folds | random_pctile | spx_net_return_pct | mes_net_return_pct | failures |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| trend[allow_short=False,fast=50,slow=100,stop_atr=2.5,trail_atr=3.0] | False | 74 | 1.84 | 220.87 | 0.22 | 5.49 | 0.62 | 5 | 86.00 | 14.02 | 2.32 | positive folds 5 < 6 |
| trend[allow_short=False,fast=20,slow=100,stop_atr=2.5,trail_atr=3.0] | True | 83 | 2.02 | 287.28 | 0.30 | 5.31 | 0.56 | 6 | 95.00 | 22.27 | 1.57 | - |
| trend[allow_short=False,fast=50,slow=100,stop_atr=3.0,trail_atr=4.0] | False | 60 | 2.47 | 324.62 | 0.35 | 5.07 | 0.80 | 5 | 96.00 | 16.64 | 2.84 | positive folds 5 < 6 |
| trend[allow_short=True,fast=50,slow=100,stop_atr=2.5,trail_atr=3.0] | False | 98 | 1.47 | 122.57 | 0.13 | 6.63 | 0.41 | 5 | 87.00 | 10.76 | 1.25 | positive folds 5 < 6 |
| breakout[allow_short=False,entry_lookback=55,exit_lookback=20,stop_atr=2.0] | True | 44 | 2.73 | 550.76 | 0.61 | 5.90 | 0.72 | 6 | 97.00 | 18.56 | 5.68 | - |
| breakout[allow_short=False,entry_lookback=20,exit_lookback=10,stop_atr=2.0] | True | 84 | 2.13 | 286.03 | 0.33 | 4.34 | 0.39 | 6 | 92.00 | 19.81 | 4.22 | - |
| breakout[allow_short=True,entry_lookback=55,exit_lookback=20,stop_atr=2.0] | True | 64 | 1.89 | 341.60 | 0.40 | 9.15 | 0.53 | 6 | 93.00 | 14.80 | 7.06 | - |
| breakout[allow_short=False,entry_lookback=40,exit_lookback=15,stop_atr=2.5] | False | 57 | 2.32 | 285.22 | 0.30 | 3.99 | 0.31 | 5 | 82.00 | 15.12 | 1.14 | positive folds 5 < 6 |
| pullback[exit_ma=5,max_hold=10,rsi_entry=15,rsi_len=3,stop_atr=2.5,trend_len=100] | True | 64 | 1.64 | 83.98 | 0.11 | 2.95 | 0.49 | 6 | 94.00 | 3.06 | 2.31 | - |
| pullback[exit_ma=5,max_hold=10,rsi_entry=10,rsi_len=2,stop_atr=2.5,trend_len=100] | True | 100 | 1.48 | 72.71 | 0.09 | 5.86 | 1.03 | 7 | 99.00 | 3.28 | 3.99 | - |
| pullback[exit_ma=5,max_hold=8,rsi_entry=20,rsi_len=3,stop_atr=2.5,trend_len=50] | True | 69 | 2.36 | 147.87 | 0.17 | 3.05 | 1.00 | 7 | 100.00 | 6.43 | 3.78 | - |
| pullback[exit_ma=10,max_hold=15,rsi_entry=15,rsi_len=3,stop_atr=3.0,trend_len=100] | True | 59 | 1.59 | 91.69 | 0.09 | 3.05 | 0.52 | 6 | 96.00 | 4.02 | 1.39 | - |

**Selected:** `pullback[exit_ma=5,max_hold=10,rsi_entry=10,rsi_len=2,stop_atr=2.5,trend_len=100]`

Best per family: trend: `trend[allow_short=False,fast=20,slow=100,stop_atr=2.5,trail_atr=3.0]` (pass), breakout: `breakout[allow_short=False,entry_lookback=55,exit_lookback=20,stop_atr=2.0]` (pass), pullback: `pullback[exit_ma=5,max_hold=10,rsi_entry=10,rsi_len=2,stop_atr=2.5,trend_len=100]` (pass)

## Top candidate detail: `pullback[exit_ma=5,max_hold=10,rsi_entry=10,rsi_len=2,stop_atr=2.5,trend_len=100]`

### Walk-forward folds (one continuous run per source)
| source | fold | net_pnl | return_pct | sharpe | trades |
|---|---|---|---|---|---|
| spx | 2008-01-02..2010-12-31 | 2,440.55 | 2.44 | 1.12 | 10 |
| spx | 2011-01-01..2013-12-31 | 3,754.65 | 3.67 | 0.95 | 20 |
| spx | 2014-01-01..2016-12-31 | -3,777.15 | -3.56 | -0.74 | 22 |
| spx | 2017-01-01..2019-04-30 | 858.85 | 0.84 | 0.29 | 16 |
| mes | 2019-05-06..2020-12-31 | 96.00 | 0.10 | 0.07 | 8 |
| mes | 2021-01-01..2021-12-31 | 1,834.00 | 1.83 | 1.33 | 11 |
| mes | 2022-01-01..2022-12-31 | 922.00 | 0.90 | 1.12 | 4 |
| mes | 2023-01-01..2023-12-31 | 1,142.00 | 1.11 | 1.34 | 9 |

### Per-source metrics vs baselines
| metric | pullback spx | pullback mes | buy_hold_1x_spx | ma_cross_spx | buy_hold_1x_mes | ma_cross_mes |
|---|---|---|---|---|---|---|
| net_return_pct | 3.28 | 3.99 | 95.18 | 18.37 | 44.45 | 5.84 |
| cagr_pct | 0.30 | 0.94 | 6.08 | 1.61 | 8.23 | 1.48 |
| avg_monthly_return_pct | 0.03 | 0.08 | 0.63 | 0.14 | 0.82 | 0.15 |
| median_monthly_return_pct | 0.00 | 0.00 | 1.07 | 0.14 | 1.46 | 0.00 |
| pct_positive_months | 26.40 | 40.00 | 64.40 | 55.60 | 60.00 | 41.30 |
| worst_month_pct | -1.24 | -0.98 | -15.71 | -2.49 | -10.18 | -1.33 |
| months_ge_5pct | 0 | 0 | 15 | 0 | 8 | 0 |
| max_drawdown_pct | 5.86 | 1.38 | 52.49 | 4.58 | 25.90 | 3.66 |
| sharpe | 0.24 | 0.84 | 0.41 | 0.55 | 0.57 | 0.59 |
| trades | 68 | 32 | 0 | 10 | 0 | 7 |
| win_rate_pct | 63.20 | 71.90 | 0.00 | 50.00 | 0.00 | 28.60 |
| profit_factor | 1.27 | 2.30 | 0.00 | 5.77 | 0.00 | 2.63 |
| expectancy_usd | 48.19 | 124.81 | 0.00 | 1,836.57 | 0.00 | 834.14 |
| expectancy_r | 0.05 | 0.17 | 0.00 | 2.15 | 0.00 | 0.66 |
| avg_sessions_held | 2.78 | 2.44 | 0.00 | 205.20 | 0.00 | 93.29 |
| avg_calendar_days_held | 4.09 | 3.25 | 0.00 | 298.10 | 0.00 | 132.00 |
| exposure_pct | 6.90 | 7.30 | 100.00 | 77.40 | 100.00 | 65.30 |
| total_fees_usd | 628.00 | 76.00 | 0.00 | 56.00 | 0.00 | 14.00 |
| total_roll_costs_usd | 45.00 | 0.00 | 0.00 | 436.50 | 0.00 | 49.50 |

### Yearly returns (%)
| year | spx | mes |
|---|---|---|
| 2009 | 2.08 |  |
| 2010 | 0.35 |  |
| 2011 | 0.81 |  |
| 2012 | 1.82 |  |
| 2013 | 1.00 |  |
| 2014 | -2.38 |  |
| 2015 | -2.58 |  |
| 2016 | 1.41 |  |
| 2017 | 3.20 |  |
| 2018 | -2.49 |  |
| 2019 | 0.21 |  |
| 2020 |  | -0.69 |
| 2021 |  | 1.83 |
| 2022 |  | 0.90 |
| 2023 |  | 1.11 |

### Random-entry baseline
100 seeds, matched entry rate, side mix, stop and holding time. Candidate total net P&L $7,271 vs random median $920 (p90 $4,264) -> beats **99.0%** of random runs.

### Cost sensitivity (training)
| costs | total_net_pnl | profit_factor | expectancy_usd | spx_net_return_pct | mes_net_return_pct |
|---|---|---|---|---|---|
| 1x | 7,270.90 | 1.48 | 72.71 | 3.28 | 3.99 |
| 2x | 5,458.20 | 1.36 | 54.58 | 1.64 | 3.82 |
| 3x | 3,793.55 | 1.25 | 37.94 | -0.10 | 3.90 |

## Anchored walk-forward of the SELECTION PROCESS
At each fold, pick the candidate with the best median Sharpe over earlier folds, then record its next fold.

| fold | chosen | chosen_return_pct | chosen_sharpe | avg_all_candidates_return_pct |
|---|---|---|---|---|
| spx 2011-01-01..2013-12-31 | pullback[exit_ma=5,max_hold=10,rsi_entry=15,rsi_len=3,stop_atr=2.5,trend_len=100] | 1.31 | 0.51 | 3.31 |
| spx 2014-01-01..2016-12-31 | pullback[exit_ma=5,max_hold=8,rsi_entry=20,rsi_len=3,stop_atr=2.5,trend_len=50] | 0.06 | 0.02 | -2.10 |
| spx 2017-01-01..2019-04-30 | pullback[exit_ma=5,max_hold=8,rsi_entry=20,rsi_len=3,stop_atr=2.5,trend_len=50] | -0.22 | -0.10 | 7.47 |
| mes 2019-05-06..2020-12-31 | trend[allow_short=False,fast=50,slow=100,stop_atr=3.0,trail_atr=4.0] | 2.96 | 2.13 | 2.06 |
| mes 2021-01-01..2021-12-31 | pullback[exit_ma=5,max_hold=8,rsi_entry=20,rsi_len=3,stop_atr=2.5,trend_len=50] | 0.89 | 0.72 | 1.13 |
| mes 2022-01-01..2022-12-31 | pullback[exit_ma=5,max_hold=8,rsi_entry=20,rsi_len=3,stop_atr=2.5,trend_len=50] | 0.88 | 1.13 | -0.89 |
| mes 2023-01-01..2023-12-31 | pullback[exit_ma=5,max_hold=8,rsi_entry=20,rsi_len=3,stop_atr=2.5,trend_len=50] | 0.52 | 0.88 | 0.84 |

Mean next-fold return of the chosen candidate: 0.914% vs 1.689% for the average candidate.

## Can 5-8% per month be reached by scaling risk? (training data, top candidate)
Risk limits loosened only for this experiment (leverage cap 15x, DD halt 90%).

| risk_per_trade_pct | source | avg_monthly_return_pct | cagr_pct | max_drawdown_pct | worst_month_pct | months_ge_5pct | avg_contracts |
|---|---|---|---|---|---|---|---|
| 1.00 | spx | 0.03 | 0.30 | 5.86 | -1.24 | 0 | 4.62 |
| 1.00 | mes | 0.08 | 0.94 | 1.38 | -0.98 | 0 | 1.19 |
| 2.00 | spx | 0.06 | 0.63 | 11.79 | -2.36 | 0 | 9.94 |
| 2.00 | mes | 0.21 | 2.49 | 2.82 | -1.94 | 0 | 2.94 |
| 3.00 | spx | 0.08 | 0.85 | 17.85 | -3.77 | 0 | 15.81 |
| 3.00 | mes | 0.30 | 3.57 | 4.22 | -2.88 | 0 | 4.59 |
| 5.00 | spx | 0.14 | 1.41 | 28.48 | -6.43 | 5 | 28.68 |
| 5.00 | mes | 0.51 | 6.10 | 6.91 | -4.70 | 0 | 8.56 |
| 8.00 | spx | 0.15 | 1.28 | 40.37 | -10.57 | 7 | 43.51 |
| 8.00 | mes | 0.85 | 10.14 | 11.16 | -7.76 | 6 | 15.03 |

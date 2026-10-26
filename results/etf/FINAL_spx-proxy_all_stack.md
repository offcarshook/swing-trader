# ETF phase - final test (spx-proxy_all_stack)

Window 2021-01-01 -> 2026-12-31, run once after training selection (registry: results/etf/holdout_registry_spx-proxy_all_stack.json).

Portfolio: nrb_long_nr70_s1_1R_h3, gap_long_go0.5_s1_1.5R_h2, calendar_long_tom1_s2_none_h3_notrend, short_short_rsi2>90_s2_none_h3_x5, mr_long_ibs0.2_s2_none_h3_x5, mr_long_down30_s1.5_1R_h3, mr_long_wr-90_s2_none_h3_x5, mr_long_outside_weak0_s2_none_h3_x5

| costs | trades | /week | win | PF | exp R | sessions | total % | %/month | max DD % | Sharpe |
|---|---|---|---|---|---|---|---|---|---|---|
| 1x | 494 | 1.71 | 0.623 | 1.33 | 0.108 | 1.86 | 63.27 | 0.715 | -11.19 | 0.96 |
| 2x | 497 | 1.72 | 0.62 | 1.28 | 0.094 | 1.86 | 53.31 | 0.623 | -11.59 | 0.84 |
| 3x | 497 | 1.72 | 0.604 | 1.21 | 0.074 | 1.85 | 39.21 | 0.482 | -12.29 | 0.66 |

Buy & hold over the same window: {'SPY': 104.87}
Skipped by risk layer: {'open_risk_cap': 2, 'same_symbol': 110, 'gross_cap': 39, 'not_triggered': 54, 'zero_size': 0}
Weeks with zero setups: 28.4%, weeks with 1-5 setups: 70.3%
Holding sessions histogram: {0: 28, 1: 162, 2: 153, 3: 151}

## By family

| family | trades | P&L $ | win | avg R |
|---|---|---|---|---|
| calendar | 23 | 3283 | 0.52 | 0.10 |
| gap | 74 | -3206 | 0.49 | -0.02 |
| mr | 296 | 54318 | 0.68 | 0.14 |
| nrb | 90 | 11214 | 0.61 | 0.13 |
| short | 11 | -2335 | 0.46 | -0.14 |

## By year (entry year)

| year | trades | P&L $ |
|---|---|---|
| 2021 | 106 | 23737 |
| 2022 | 22 | -7895 |
| 2023 | 84 | 8754 |
| 2024 | 113 | 30833 |
| 2025 | 92 | 9584 |
| 2026 | 77 | -1740 |

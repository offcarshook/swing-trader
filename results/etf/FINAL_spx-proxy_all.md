# ETF phase - final test (spx-proxy_all)

Window 2021-01-01 -> 2026-12-31, run once after training selection (registry: results/etf/holdout_registry_spx-proxy_all.json).

Portfolio: nrb_long_nr70_s1_1R_h3, gap_long_go0.5_s1_1.5R_h2, calendar_long_tom1_s2_none_h3_notrend, short_short_rsi2>90_s2_none_h3_x5, mr_long_ibs0.2_s2_none_h3_x5, mr_long_down30_s1.5_1R_h3, mr_long_wr-90_s2_none_h3_x5, mr_long_outside_weak0_s2_none_h3_x5

| costs | trades | /week | win | PF | exp R | sessions | total % | %/month | max DD % | Sharpe |
|---|---|---|---|---|---|---|---|---|---|---|
| 1x | 316 | 1.09 | 0.579 | 1.09 | 0.037 | 1.9 | 10.66 | 0.147 | -10.81 | 0.31 |
| 2x | 316 | 1.09 | 0.573 | 1.05 | 0.022 | 1.9 | 5.31 | 0.075 | -12.23 | 0.17 |
| 3x | 315 | 1.09 | 0.565 | 0.98 | -0.001 | 1.9 | -1.81 | -0.027 | -14.98 | -0.02 |

Buy & hold over the same window: {'SPY': 104.87}
Skipped by risk layer: {'open_risk_cap': 0, 'same_symbol': 335, 'gross_cap': 0, 'not_triggered': 48, 'zero_size': 0}
Weeks with zero setups: 30.0%, weeks with 1-5 setups: 70.0%
Holding sessions histogram: {0: 23, 1: 93, 2: 93, 3: 107}

## By family

| family | trades | P&L $ | win | avg R |
|---|---|---|---|---|
| calendar | 19 | 2344 | 0.53 | 0.13 |
| gap | 52 | -12960 | 0.40 | -0.22 |
| mr | 148 | 11324 | 0.63 | 0.07 |
| nrb | 86 | 11533 | 0.63 | 0.14 |
| short | 11 | -1578 | 0.46 | -0.14 |

## By year (entry year)

| year | trades | P&L $ |
|---|---|---|
| 2021 | 68 | 7141 |
| 2022 | 17 | -3516 |
| 2023 | 48 | 1196 |
| 2024 | 71 | 13698 |
| 2025 | 64 | -3768 |
| 2026 | 48 | -4087 |

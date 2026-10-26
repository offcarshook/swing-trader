# ETF phase - final test (spx-proxy)

Window 2021-01-01 -> 2026-12-31, run once after training selection (registry: results/etf/holdout_registry_spx-proxy.json).

Portfolio: nrb_long_nr70_s1_1R_h3, gap_long_go0.5_s1_1.5R_h2, calendar_long_tom1_s2_none_h3_notrend, short_short_rsi2>90_s2_none_h3_x5

| costs | trades | /week | win | PF | exp R | sessions | total % | %/month | max DD % | Sharpe |
|---|---|---|---|---|---|---|---|---|---|---|
| 1x | 191 | 0.66 | 0.56 | 1.15 | 0.068 | 1.94 | 12.27 | 0.168 | -13.88 | 0.4 |
| 2x | 191 | 0.66 | 0.555 | 1.11 | 0.05 | 1.93 | 8.99 | 0.125 | -15.38 | 0.3 |
| 3x | 190 | 0.66 | 0.547 | 1.04 | 0.024 | 1.94 | 3.75 | 0.053 | -16.68 | 0.15 |

Buy & hold over the same window: {'SPY': 104.87}
Skipped by risk layer: {'open_risk_cap': 0, 'same_symbol': 60, 'gross_cap': 0, 'not_triggered': 49, 'zero_size': 0}
Weeks with zero setups: 48.5%, weeks with 1-5 setups: 51.5%
Holding sessions histogram: {'0': 17, '1': 39, '2': 74, '3': 61}

## By family

| family | trades | P&L $ | win | avg R |
|---|---|---|---|---|
| calendar | 21 | 2460 | 0.52 | 0.13 |
| gap | 70 | -2205 | 0.50 | -0.02 |
| nrb | 89 | 13500 | 0.63 | 0.15 |
| short | 11 | -1485 | 0.46 | -0.14 |

## By year (entry year)

| year | trades | P&L $ |
|---|---|---|
| 2021 | 31 | 6463 |
| 2022 | 12 | -656 |
| 2023 | 26 | 5625 |
| 2024 | 44 | 10884 |
| 2025 | 48 | -4462 |
| 2026 | 30 | -5585 |

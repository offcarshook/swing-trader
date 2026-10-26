# ETF phase - final test (full_all_stack)

Window 2021-01-01 -> 2026-12-31, run once after training selection (registry: results/etf/holdout_registry_full_all_stack.json).

Portfolio: mr_long_ibs0.2_s2_none_h3_x5, mr_long_bb_low0_s1.5_1R_h3, mr_long_wr-90_s1.5_1R_h3, mr_long_mon_down0_s2_none_h3_x5

| costs | trades | /week | win | PF | exp R | sessions | total % | %/month | max DD % | Sharpe |
|---|---|---|---|---|---|---|---|---|---|---|
| 1x | 472 | 1.64 | 0.625 | 1.28 | 0.072 | 1.76 | 36.49 | 0.454 | -15.13 | 0.6 |
| 2x | 471 | 1.63 | 0.616 | 1.23 | 0.061 | 1.76 | 29.52 | 0.378 | -15.55 | 0.5 |
| 3x | 472 | 1.64 | 0.608 | 1.19 | 0.052 | 1.76 | 24.36 | 0.318 | -16.64 | 0.43 |

Buy & hold over the same window: {'SPY': 86.64, 'QQQ': 142.14}
Skipped by risk layer: {'open_risk_cap': 58, 'same_symbol': 79, 'gross_cap': 14, 'not_triggered': 0, 'zero_size': 0}
Weeks with zero setups: 47.0%, weeks with 1-5 setups: 48.7%
Holding sessions histogram: {0: 11, 1: 226, 2: 101, 3: 134}

## By family

| family | trades | P&L $ | win | avg R |
|---|---|---|---|---|
| mr | 472 | 36485 | 0.62 | 0.07 |

## By year (entry year)

| year | trades | P&L $ |
|---|---|---|
| 2021 | 127 | 17763 |
| 2022 | 14 | -10677 |
| 2023 | 95 | 2454 |
| 2024 | 140 | 24102 |
| 2025 | 69 | 6440 |
| 2026 | 27 | -3597 |

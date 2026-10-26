# ETF phase - final test (full_all)

Window 2021-01-01 -> 2026-12-31, run once after training selection (registry: results/etf/holdout_registry_full_all.json).

Portfolio: mr_long_ibs0.2_s2_none_h3_x5, mr_long_bb_low0_s1.5_1R_h3, mr_long_wr-90_s1.5_1R_h3, mr_long_mon_down0_s2_none_h3_x5

| costs | trades | /week | win | PF | exp R | sessions | total % | %/month | max DD % | Sharpe |
|---|---|---|---|---|---|---|---|---|---|---|
| 1x | 355 | 1.23 | 0.634 | 1.37 | 0.076 | 1.73 | 29.52 | 0.378 | -10.84 | 0.75 |
| 2x | 355 | 1.23 | 0.623 | 1.31 | 0.066 | 1.73 | 25.04 | 0.326 | -11.42 | 0.65 |
| 3x | 355 | 1.23 | 0.614 | 1.26 | 0.056 | 1.73 | 20.73 | 0.275 | -11.97 | 0.56 |

Buy & hold over the same window: {'SPY': 86.64, 'QQQ': 142.14}
Skipped by risk layer: {'open_risk_cap': 0, 'same_symbol': 268, 'gross_cap': 0, 'not_triggered': 0, 'zero_size': 0}
Weeks with zero setups: 47.3%, weeks with 1-5 setups: 52.0%
Holding sessions histogram: {0: 6, 1: 178, 2: 77, 3: 94}

## By family

| family | trades | P&L $ | win | avg R |
|---|---|---|---|---|
| mr | 355 | 29519 | 0.63 | 0.08 |

## By year (entry year)

| year | trades | P&L $ |
|---|---|---|
| 2021 | 98 | 10821 |
| 2022 | 7 | -3964 |
| 2023 | 75 | 3539 |
| 2024 | 105 | 16399 |
| 2025 | 52 | 4311 |
| 2026 | 18 | -1586 |

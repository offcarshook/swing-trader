# ETF phase - final test (full_all)

Window 2021-01-01 -> 2026-12-31, run once after training selection (registry: results/etf/holdout_registry_full_all.json).

Portfolio: calendar_long_tom1_s2_none_h3_notrend

| costs | trades | /week | win | PF | exp R | sessions | total % | %/month | max DD % | Sharpe |
|---|---|---|---|---|---|---|---|---|---|---|
| 1x | 85 | 0.29 | 0.459 | 0.93 | -0.019 | 2.67 | -2.12 | -0.03 | -12.55 | -0.07 |
| 2x | 85 | 0.29 | 0.459 | 0.9 | -0.029 | 2.67 | -2.95 | -0.043 | -12.84 | -0.1 |
| 3x | 85 | 0.29 | 0.459 | 0.87 | -0.04 | 2.67 | -3.82 | -0.055 | -13.12 | -0.14 |

Buy & hold over the same window: {'SPY': 86.64, 'QQQ': 142.14, 'DIA': 10.03, 'TLT': -37.83, 'GLD': -8.4, 'XLE': 104.74, 'XLF': 16.87, 'XLK': 12.9, 'SMH': 9.13}
Skipped by risk layer: {'open_risk_cap': 14, 'same_symbol': 0, 'gross_cap': 0, 'not_triggered': 0, 'zero_size': 0}
Weeks with zero setups: 86.7%, weeks with 1-5 setups: 13.3%
Holding sessions histogram: {0: 1, 1: 9, 2: 7, 3: 68}

## By family

| family | trades | P&L $ | win | avg R |
|---|---|---|---|---|
| calendar | 85 | -2121 | 0.46 | -0.02 |

## By year (entry year)

| year | trades | P&L $ |
|---|---|---|
| 2021 | 27 | -2542 |
| 2022 | 24 | -3313 |
| 2023 | 14 | 2523 |
| 2024 | 10 | 1397 |
| 2025 | 7 | -2000 |
| 2026 | 3 | 1813 |

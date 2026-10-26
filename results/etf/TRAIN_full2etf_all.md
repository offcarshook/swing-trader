# ETF phase - training selection (full_all)

Symbols: QQQ, SPY. Train window 2008-01-01 -> 2020-12-31 only.
Gates at 2x costs: {'min_trades': 30, 'min_pf': 1.2, 'min_fold_share': 0.6, 'random_pctile': 90, 'random_seeds': 100}.

**Selected:** mr_long_ibs0.2_s2_none_h3_x5, mr_long_bb_low0_s1.5_1R_h3, mr_long_wr-90_s1.5_1R_h3, mr_long_mon_down0_s2_none_h3_x5

## All candidates (2x costs)

| candidate | pass | trades | /week | win | PF | exp R | sessions | total % | %/month | max DD % | Sharpe | folds+ | rand pct | failures |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| mr_long_wr-90_s1.5_1R_h3 | yes | 182 | 0.28 | 0.577 | 1.34 | 0.136 | 1.99 | 26.42 | 0.15 | -10.37 | 0.4 | 67% of 12 | 96.0 |  |
| mr_long_ibs0.2_s2_none_h3_x5 | yes | 579 | 0.88 | 0.644 | 1.23 | 0.048 | 1.87 | 29.79 | 0.167 | -11.48 | 0.39 | 62% of 13 | 98.0 |  |
| mr_long_mon_down0_s2_none_h3_x5 | yes | 343 | 0.52 | 0.589 | 1.24 | 0.046 | 1.77 | 16.18 | 0.096 | -7.29 | 0.32 | 69% of 13 | 94.0 |  |
| mr_long_bb_low0_s1.5_1R_h3 | yes | 119 | 0.18 | 0.571 | 1.33 | 0.121 | 1.84 | 14.68 | 0.088 | -9.12 | 0.3 | 64% of 11 | 91.0 |  |
| calendar_long_tom1_s2_none_h3_notrend | no | 127 | 0.19 | 0.575 | 1.38 | 0.116 | 2.7 | 14.9 | 0.089 | -6.18 | 0.34 | 54% of 13 | - | positive folds 54% < 60% |
| calendar_long_tom0_s2_none_h3_notrend | no | 312 | 0.48 | 0.545 | 1.17 | 0.05 | 2.78 | 15.11 | 0.09 | -12.54 | 0.24 | 46% of 13 | - | PF@2x 1.17 < 1.2; positive folds 46% < 60% |
| calendar_long_tom1_s2_none_h3 | no | 95 | 0.15 | 0.579 | 1.18 | 0.06 | 2.64 | 5.3 | 0.033 | -7.48 | 0.16 | 58% of 12 | - | PF@2x 1.18 < 1.2; positive folds 58% < 60% |
| calendar_long_tom0_s2_none_h3 | no | 221 | 0.34 | 0.543 | 1.04 | 0.016 | 2.72 | 2.58 | 0.016 | -14.72 | 0.07 | 50% of 12 | - | PF@2x 1.04 < 1.2; positive folds 50% < 60% |
| dip_long_rsi2<10_s2_1R_h3 | no | 242 | 0.37 | 0.521 | 1.05 | 0.021 | 2.47 | 4.01 | 0.025 | -16.68 | 0.09 | 50% of 12 | - | PF@2x 1.05 < 1.2; positive folds 50% < 60% |
| dip_long_rsi2<5_s2_1R_h3 | no | 117 | 0.18 | 0.53 | 1.07 | 0.028 | 2.37 | 2.77 | 0.018 | -8.69 | 0.08 | 67% of 12 | - | PF@2x 1.07 < 1.2 |
| dip_long_rsi2<10_s2_none_h3_x5 | no | 241 | 0.37 | 0.589 | 1.03 | 0.012 | 2.24 | 2.02 | 0.013 | -17.9 | 0.06 | 50% of 12 | - | PF@2x 1.03 < 1.2; positive folds 50% < 60% |
| dip_long_rsi2<5_s2_none_h3_x5 | no | 116 | 0.18 | 0.56 | 1.0 | 0.003 | 2.21 | -0.14 | -0.001 | -11.96 | 0.01 | 67% of 12 | - | PF@2x 1.0 < 1.2 |
| gap_short_fade1_s1_1R_h1 | no | 12 | 0.02 | 0.75 | 2.99 | 0.45 | 0.42 | 5.44 | 0.034 | -1.35 | 0.39 | 100% of 3 | - | trades 12 < 30 |
| gap_long_go1_s1_1.5R_h2 | no | 41 | 0.06 | 0.512 | 1.44 | 0.174 | 1.41 | 7.13 | 0.044 | -3.63 | 0.27 | 75% of 8 | 75.0 | random-entry percentile 75 < 90 |
| gap_long_fade1_s1_1R_h1 | no | 80 | 0.12 | 0.575 | 1.27 | 0.112 | 0.4 | 8.89 | 0.055 | -6.91 | 0.25 | 55% of 11 | - | positive folds 55% < 60% |
| gap_long_fade0.5_s1_1R_h1 | no | 373 | 0.57 | 0.534 | 1.02 | 0.013 | 0.61 | 2.48 | 0.016 | -20.75 | 0.06 | 58% of 12 | - | PF@2x 1.02 < 1.2; positive folds 58% < 60% |
| gap_long_fade1_s1.5_none_h3_x5 | no | 84 | 0.13 | 0.476 | 0.87 | -0.059 | 2.17 | -5.36 | -0.035 | -14.63 | -0.1 | 45% of 11 | - | PF@2x 0.87 < 1.2; expectancy@2x <= 0; positive folds 45% < 60% |
| gap_long_fade0.5_s1.5_none_h3_x5 | no | 382 | 0.58 | 0.542 | 0.91 | -0.03 | 1.87 | -12.83 | -0.088 | -21.58 | -0.13 | 33% of 12 | - | PF@2x 0.91 < 1.2; expectancy@2x <= 0; positive folds 33% < 60% |
| gap_long_go0.5_s1_1.5R_h2 | no | 398 | 0.61 | 0.51 | 0.9 | -0.041 | 1.56 | -17.22 | -0.121 | -35.08 | -0.19 | 42% of 12 | - | PF@2x 0.9 < 1.2; expectancy@2x <= 0; positive folds 42% < 60% |
| gap_short_fade0.5_s1_1R_h1 | no | 123 | 0.19 | 0.455 | 0.74 | -0.106 | 0.72 | -12.89 | -0.089 | -18.62 | -0.31 | 30% of 10 | - | PF@2x 0.74 < 1.2; expectancy@2x <= 0; positive folds 30% < 60% |
| mom_long_high100_s1_1R_h2 | no | 832 | 1.27 | 0.569 | 1.06 | 0.026 | 1.47 | 18.29 | 0.108 | -29.67 | 0.19 | 62% of 13 | - | PF@2x 1.06 < 1.2 |
| mom_long_high100_s1.5_1.5R_h3 | no | 669 | 1.02 | 0.544 | 0.95 | -0.01 | 2.64 | -10.07 | -0.068 | -27.15 | -0.07 | 54% of 13 | - | PF@2x 0.95 < 1.2; expectancy@2x <= 0; positive folds 54% < 60% |
| mr_long_wr-90_s2_none_h3_x5 | no | 176 | 0.27 | 0.676 | 1.66 | 0.154 | 2.3 | 30.23 | 0.17 | -6.98 | 0.57 | 58% of 12 | - | positive folds 58% < 60% |
| mr_long_key_rev0_s1.5_1R_h3 | no | 161 | 0.25 | 0.615 | 1.39 | 0.117 | 2.41 | 19.85 | 0.116 | -5.92 | 0.43 | 58% of 12 | - | positive folds 58% < 60% |
| mr_long_bb_low0_s2_none_h3_x5 | no | 105 | 0.16 | 0.648 | 1.46 | 0.123 | 2.16 | 13.3 | 0.08 | -6.34 | 0.32 | 55% of 11 | - | positive folds 55% < 60% |
| mr_long_outside_weak0_s2_none_h3_x5 | no | 133 | 0.2 | 0.677 | 1.35 | 0.065 | 1.82 | 8.76 | 0.054 | -6.29 | 0.32 | 42% of 12 | - | positive folds 42% < 60% |
| mr_long_mon_down0_s1.5_1R_h3 | no | 339 | 0.52 | 0.569 | 1.19 | 0.064 | 2.33 | 21.91 | 0.127 | -13.91 | 0.31 | 77% of 13 | - | PF@2x 1.19 < 1.2 |
| mr_long_outside_weak0_s1.5_1R_h3 | no | 133 | 0.2 | 0.579 | 1.24 | 0.084 | 2.25 | 11.0 | 0.067 | -9.72 | 0.28 | 42% of 12 | - | positive folds 42% < 60% |
| mr_long_down30_s2_none_h3_x5 | no | 218 | 0.33 | 0.638 | 1.17 | 0.05 | 2.02 | 10.75 | 0.065 | -12.77 | 0.23 | 50% of 12 | - | PF@2x 1.17 < 1.2; positive folds 50% < 60% |
| mr_long_low70_s2_none_h3_x5 | no | 421 | 0.64 | 0.618 | 1.09 | 0.031 | 2.1 | 11.6 | 0.07 | -18.99 | 0.17 | 58% of 12 | - | PF@2x 1.09 < 1.2; positive folds 58% < 60% |
| mr_long_down30_s1.5_1R_h3 | no | 235 | 0.36 | 0.54 | 1.1 | 0.044 | 2.1 | 9.4 | 0.058 | -14.63 | 0.16 | 42% of 12 | - | PF@2x 1.1 < 1.2; positive folds 42% < 60% |
| mr_long_key_rev0_s2_none_h3_x5 | no | 165 | 0.25 | 0.558 | 1.07 | 0.013 | 1.41 | 1.93 | 0.012 | -8.21 | 0.08 | 50% of 12 | - | PF@2x 1.07 < 1.2; positive folds 50% < 60% |
| mr_long_ibs0.2_s1.5_1R_h3 | no | 569 | 0.87 | 0.536 | 0.99 | 0.005 | 2.15 | -1.13 | -0.007 | -24.91 | 0.03 | 54% of 13 | - | PF@2x 0.99 < 1.2; positive folds 54% < 60% |
| mr_long_low70_s1.5_1R_h3 | no | 466 | 0.71 | 0.526 | 1.0 | 0.006 | 1.93 | -0.4 | -0.003 | -21.29 | 0.03 | 54% of 13 | - | PF@2x 1.0 < 1.2; positive folds 54% < 60% |
| mrshort_short_up30_s2_none_h3_x5 | no | 69 | 0.11 | 0.609 | 1.62 | 0.095 | 2.48 | 6.57 | 0.041 | -4.44 | 0.36 | 56% of 9 | - | positive folds 56% < 60% |
| mrshort_short_up30_s1.5_1R_h3 | no | 69 | 0.11 | 0.536 | 1.18 | 0.059 | 2.65 | 3.83 | 0.024 | -6.79 | 0.15 | 56% of 9 | - | PF@2x 1.18 < 1.2; positive folds 56% < 60% |
| mrshort_short_ibs_hi0.8_s2_none_h3_x5 | no | 210 | 0.32 | 0.505 | 1.07 | 0.017 | 2.12 | 3.14 | 0.02 | -10.11 | 0.11 | 40% of 10 | - | PF@2x 1.07 < 1.2; positive folds 40% < 60% |
| mrshort_short_bb_high0_s2_none_h3_x5 | no | 8 | 0.01 | 0.5 | 1.12 | 0.014 | 3.0 | 0.11 | 0.001 | -1.22 | 0.02 | 50% of 2 | - | trades 8 < 30; PF@2x 1.12 < 1.2; positive folds 50% < 60% |
| mrshort_short_bb_high0_s1.5_1R_h3 | no | 8 | 0.01 | 0.5 | 0.42 | -0.095 | 2.88 | -0.76 | -0.005 | -1.85 | -0.1 | 50% of 2 | - | trades 8 < 30; PF@2x 0.42 < 1.2; expectancy@2x <= 0; positive folds 50% < 60% |
| mrshort_short_ibs_hi0.8_s1.5_1R_h3 | no | 205 | 0.31 | 0.459 | 0.83 | -0.063 | 2.6 | -12.93 | -0.089 | -27.58 | -0.25 | 30% of 10 | - | PF@2x 0.83 < 1.2; expectancy@2x <= 0; positive folds 30% < 60% |
| nrb_long_nr70_s1_1R_h3 | no | 357 | 0.55 | 0.563 | 1.06 | 0.031 | 1.97 | 9.3 | 0.057 | -19.72 | 0.15 | 67% of 12 | - | PF@2x 1.06 < 1.2 |
| nrb_long_nr70_s1_1.5R_h3 | no | 346 | 0.53 | 0.532 | 1.04 | 0.023 | 2.24 | 5.71 | 0.036 | -22.0 | 0.1 | 58% of 12 | - | PF@2x 1.04 < 1.2; positive folds 58% < 60% |
| nrb_long_nr40_s1_1R_h3 | no | 563 | 0.86 | 0.54 | 1.01 | 0.012 | 1.87 | 3.01 | 0.019 | -29.09 | 0.07 | 46% of 13 | - | PF@2x 1.01 < 1.2; positive folds 46% < 60% |
| nrb_long_nr40_s1_1.5R_h3 | no | 532 | 0.81 | 0.509 | 1.02 | 0.015 | 2.18 | 3.61 | 0.023 | -33.9 | 0.07 | 46% of 13 | - | PF@2x 1.02 < 1.2; positive folds 46% < 60% |
| nrb_short_nr70_s1_1R_h3 | no | 75 | 0.11 | 0.507 | 1.04 | 0.023 | 1.81 | 1.23 | 0.008 | -8.73 | 0.05 | 62% of 8 | - | PF@2x 1.04 < 1.2 |
| nrb_short_inside0_s1_1R_h3 | no | 54 | 0.08 | 0.481 | 0.91 | -0.04 | 1.76 | -2.44 | -0.016 | -7.86 | -0.07 | 57% of 7 | - | PF@2x 0.91 < 1.2; expectancy@2x <= 0; positive folds 57% < 60% |
| nrb_long_inside0_s1_1.5R_h3 | no | 262 | 0.4 | 0.466 | 0.85 | -0.065 | 2.15 | -17.07 | -0.12 | -29.46 | -0.24 | 33% of 12 | - | PF@2x 0.85 < 1.2; expectancy@2x <= 0; positive folds 33% < 60% |
| nrb_long_inside0_s1_1R_h3 | no | 265 | 0.4 | 0.483 | 0.79 | -0.095 | 1.89 | -23.39 | -0.171 | -30.95 | -0.38 | 33% of 12 | - | PF@2x 0.79 < 1.2; expectancy@2x <= 0; positive folds 33% < 60% |
| short_short_rsi2>90_s2_none_h3_x5 | no | 56 | 0.09 | 0.643 | 1.62 | 0.088 | 2.55 | 4.95 | 0.031 | -2.86 | 0.31 | 50% of 8 | - | positive folds 50% < 60% |
| short_short_rsi2>90_s2_1R_h3 | no | 56 | 0.09 | 0.607 | 1.53 | 0.094 | 2.96 | 5.25 | 0.033 | -4.41 | 0.29 | 50% of 8 | - | positive folds 50% < 60% |
| short_short_rsi2>95_s2_none_h3_x5 | no | 23 | 0.04 | 0.522 | 1.02 | 0.004 | 2.39 | 0.06 | 0.0 | -3.26 | 0.01 | 50% of 4 | - | trades 23 < 30; PF@2x 1.02 < 1.2; positive folds 50% < 60% |
| short_short_rsi2>95_s2_1R_h3 | no | 23 | 0.04 | 0.435 | 0.89 | -0.024 | 2.91 | -0.58 | -0.004 | -5.17 | -0.05 | 25% of 4 | - | trades 23 < 30; PF@2x 0.89 < 1.2; expectancy@2x <= 0; positive folds 25% < 60% |

## Combined train portfolio (shared 1% risk / 4% open-risk cap)

| trades | /week | win | PF | exp R | sessions | total % | %/month | max DD % | Sharpe |
|---|---|---|---|---|---|---|---|---|---|
| 791 | 1.21 | 0.611 | 1.13 | 0.031 | 1.79 | 24.16 | 0.139 | -13.83 | 0.27 |  (1x costs)
| 791 | 1.21 | 0.607 | 1.06 | 0.017 | 1.79 | 11.4 | 0.069 | -15.08 | 0.15 |  (2x costs)

Signals skipped by the risk layer: {'open_risk_cap': 0, 'same_symbol': 604, 'gross_cap': 0, 'not_triggered': 0, 'zero_size': 0}

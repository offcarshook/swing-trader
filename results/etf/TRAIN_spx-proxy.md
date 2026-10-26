# ETF phase - training selection (spx-proxy)

Symbols: SPY. Train window 2008-01-01 -> 2020-12-31 only.
Gates at 2x costs: {'min_trades': 30, 'min_pf': 1.2, 'min_fold_share': 0.6, 'random_pctile': 90, 'random_seeds': 100}.

**Selected:** nrb_long_nr70_s1_1R_h3, gap_long_go0.5_s1_1.5R_h2, calendar_long_tom1_s2_none_h3_notrend, short_short_rsi2>90_s2_none_h3_x5

## All candidates (2x costs)

| candidate | pass | trades | /week | win | PF | exp R | sessions | total % | %/month | max DD % | Sharpe | folds+ | rand pct | failures |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| calendar_long_tom1_s2_none_h3_notrend | yes | 65 | 0.1 | 0.631 | 1.64 | 0.185 | 2.66 | 12.28 | 0.075 | -3.18 | 0.5 | 64% of 11 | 98.0 |  |
| gap_long_go0.5_s1_1.5R_h2 | yes | 64 | 0.1 | 0.609 | 1.9 | 0.259 | 1.7 | 17.5 | 0.104 | -3.54 | 0.56 | 100% of 4 | 96.0 |  |
| nrb_long_nr70_s1_1R_h3 | yes | 181 | 0.28 | 0.641 | 1.56 | 0.194 | 1.93 | 40.55 | 0.22 | -6.03 | 0.75 | 75% of 12 | 100.0 |  |
| nrb_long_nr40_s1_1R_h3 | yes | 302 | 0.47 | 0.603 | 1.38 | 0.143 | 1.83 | 51.21 | 0.268 | -6.21 | 0.69 | 92% of 12 | 100.0 |  |
| nrb_long_nr70_s1_1.5R_h3 | yes | 170 | 0.26 | 0.6 | 1.5 | 0.191 | 2.25 | 36.58 | 0.202 | -6.6 | 0.63 | 75% of 12 | 95.0 |  |
| nrb_long_inside0_s1_1R_h3 | yes | 153 | 0.24 | 0.595 | 1.47 | 0.186 | 1.83 | 31.67 | 0.178 | -6.45 | 0.6 | 67% of 12 | 98.0 |  |
| nrb_long_nr40_s1_1.5R_h3 | yes | 285 | 0.44 | 0.544 | 1.31 | 0.133 | 2.19 | 42.93 | 0.231 | -9.5 | 0.55 | 92% of 12 | 100.0 |  |
| nrb_long_inside0_s1_1.5R_h3 | yes | 151 | 0.23 | 0.55 | 1.42 | 0.194 | 2.22 | 32.41 | 0.182 | -9.23 | 0.55 | 67% of 12 | 97.0 |  |
| short_short_rsi2>90_s2_none_h3_x5 | yes | 30 | 0.05 | 0.7 | 2.12 | 0.126 | 2.47 | 3.65 | 0.023 | -1.4 | 0.33 | 86% of 7 | 95.0 |  |
| calendar_long_tom0_s2_none_h3_notrend | no | 147 | 0.23 | 0.578 | 1.27 | 0.077 | 2.71 | 11.41 | 0.07 | -5.86 | 0.34 | 62% of 13 | 78.0 | random-entry percentile 78 < 90 |
| calendar_long_tom1_s2_none_h3 | no | 45 | 0.07 | 0.622 | 1.5 | 0.147 | 2.64 | 6.28 | 0.039 | -3.29 | 0.33 | 70% of 10 | 83.0 | random-entry percentile 83 < 90 |
| calendar_long_tom0_s2_none_h3 | no | 105 | 0.16 | 0.571 | 1.16 | 0.049 | 2.69 | 4.73 | 0.03 | -7.03 | 0.17 | 50% of 12 | - | PF@2x 1.16 < 1.2; positive folds 50% < 60% |
| dip_long_rsi2<10_s2_none_h3_x5 | no | 111 | 0.17 | 0.586 | 1.09 | 0.03 | 2.1 | 3.1 | 0.02 | -13.32 | 0.11 | 75% of 12 | - | PF@2x 1.09 < 1.2 |
| dip_long_rsi2<10_s2_1R_h3 | no | 111 | 0.17 | 0.514 | 1.08 | 0.03 | 2.48 | 2.96 | 0.019 | -12.31 | 0.1 | 58% of 12 | - | PF@2x 1.08 < 1.2; positive folds 58% < 60% |
| dip_long_rsi2<5_s2_1R_h3 | no | 56 | 0.09 | 0.536 | 1.02 | 0.011 | 2.36 | 0.45 | 0.003 | -8.21 | 0.03 | 60% of 10 | - | PF@2x 1.02 < 1.2 |
| dip_long_rsi2<5_s2_none_h3_x5 | no | 56 | 0.09 | 0.607 | 0.97 | -0.005 | 2.2 | -0.45 | -0.003 | -8.97 | -0.01 | 60% of 10 | - | PF@2x 0.97 < 1.2; expectancy@2x <= 0 |
| gap_long_go1_s1_1.5R_h2 | no | 4 | 0.01 | 1.0 | inf | 1.297 | 1.25 | 5.23 | 0.033 | -0.3 | 0.64 | 0% of 0 | - | trades 4 < 30; positive folds 0% < 60% |
| gap_long_fade1_s1_1R_h1 | no | 15 | 0.02 | 0.533 | 1.02 | 0.004 | 0.47 | 0.11 | 0.001 | -3.78 | 0.01 | 0% of 2 | - | trades 15 < 30; PF@2x 1.02 < 1.2; positive folds 0% < 60% |
| gap_short_fade0.5_s1_1R_h1 | no | 11 | 0.02 | 0.455 | 0.76 | -0.114 | 0.73 | -1.03 | -0.007 | -3.83 | -0.09 | 50% of 2 | - | trades 11 < 30; PF@2x 0.76 < 1.2; expectancy@2x <= 0; positive folds 50% < 60% |
| gap_long_fade1_s1.5_none_h3_x5 | no | 15 | 0.02 | 0.4 | 0.64 | -0.21 | 1.8 | -3.07 | -0.02 | -4.66 | -0.18 | 0% of 2 | - | trades 15 < 30; PF@2x 0.64 < 1.2; expectancy@2x <= 0; positive folds 0% < 60% |
| gap_long_fade0.5_s1_1R_h1 | no | 58 | 0.09 | 0.448 | 0.7 | -0.157 | 0.5 | -8.85 | -0.06 | -14.02 | -0.32 | 25% of 4 | - | PF@2x 0.7 < 1.2; expectancy@2x <= 0; positive folds 25% < 60% |
| gap_long_fade0.5_s1.5_none_h3_x5 | no | 59 | 0.09 | 0.458 | 0.66 | -0.169 | 1.63 | -9.47 | -0.064 | -12.88 | -0.32 | 0% of 4 | - | PF@2x 0.66 < 1.2; expectancy@2x <= 0; positive folds 0% < 60% |
| gap_short_fade1_s1_1R_h1 | no | 0 | 0.0 |  |  |  |  | 0.0 |  | 0.0 |  | 0% of 0 | - | trades 0 < 30; PF@2x None < 1.2; expectancy@2x <= 0; positive folds 0% < 60% |
| nrb_short_nr70_s1_1R_h3 | no | 34 | 0.05 | 0.441 | 0.82 | -0.095 | 1.85 | -3.1 | -0.02 | -9.23 | -0.15 | 43% of 7 | - | PF@2x 0.82 < 1.2; expectancy@2x <= 0; positive folds 43% < 60% |
| nrb_short_inside0_s1_1R_h3 | no | 22 | 0.03 | 0.409 | 0.71 | -0.155 | 2.05 | -3.37 | -0.022 | -4.56 | -0.18 | 50% of 4 | - | trades 22 < 30; PF@2x 0.71 < 1.2; expectancy@2x <= 0; positive folds 50% < 60% |
| short_short_rsi2>90_s2_1R_h3 | no | 30 | 0.05 | 0.567 | 1.57 | 0.098 | 3.0 | 2.84 | 0.018 | -2.96 | 0.22 | 57% of 7 | - | positive folds 57% < 60% |
| short_short_rsi2>95_s2_none_h3_x5 | no | 11 | 0.02 | 0.636 | 1.22 | 0.039 | 2.36 | 0.4 | 0.003 | -1.18 | 0.07 | 100% of 2 | - | trades 11 < 30 |
| short_short_rsi2>95_s2_1R_h3 | no | 11 | 0.02 | 0.364 | 0.43 | -0.163 | 3.0 | -1.74 | -0.011 | -3.08 | -0.24 | 0% of 2 | - | trades 11 < 30; PF@2x 0.43 < 1.2; expectancy@2x <= 0; positive folds 0% < 60% |

## Combined train portfolio (shared 1% risk / 4% open-risk cap)

| trades | /week | win | PF | exp R | sessions | total % | %/month | max DD % | Sharpe |
|---|---|---|---|---|---|---|---|---|---|
| 316 | 0.49 | 0.646 | 1.78 | 0.221 | 2.04 | 96.85 | 0.439 | -5.12 | 1.15 |  (1x costs)
| 315 | 0.49 | 0.644 | 1.67 | 0.198 | 2.07 | 83.03 | 0.392 | -6.37 | 1.03 |  (2x costs)

Signals skipped by the risk layer: {'open_risk_cap': 0, 'same_symbol': 90, 'gross_cap': 10, 'not_triggered': 90, 'zero_size': 0}

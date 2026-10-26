# ETF phase - training selection (full_all_stack)

Symbols: DIA, EEM, EFA, GLD, IEF, IWM, QQQ, SLV, SMH, SPY, TLT, USO, XLE, XLF, XLK. Train window 2008-01-01 -> 2020-12-31 only.
Gates at 2x costs: {'min_trades': 30, 'min_pf': 1.2, 'min_fold_share': 0.6, 'random_pctile': 90, 'random_seeds': 100}.

**Selected:** calendar_long_tom1_s2_none_h3_notrend

## All candidates (2x costs)

| candidate | pass | trades | /week | win | PF | exp R | sessions | total % | %/month | max DD % | Sharpe | folds+ | rand pct | failures |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| calendar_long_tom1_s2_none_h3_notrend | yes | 498 | 0.73 | 0.546 | 1.33 | 0.096 | 2.79 | 55.56 | 0.274 | -13.86 | 0.49 | 77% of 13 | 100.0 |  |
| calendar_long_tom1_s2_none_h3 | yes | 354 | 0.52 | 0.548 | 1.24 | 0.073 | 2.78 | 25.89 | 0.143 | -13.12 | 0.3 | 62% of 13 | 100.0 |  |
| calendar_long_tom0_s2_none_h3_notrend | no | 587 | 0.87 | 0.532 | 1.1 | 0.035 | 2.79 | 18.62 | 0.106 | -26.6 | 0.21 | 54% of 13 | - | PF@2x 1.1 < 1.2; positive folds 54% < 60% |
| calendar_long_tom0_s2_none_h3 | no | 536 | 0.79 | 0.532 | 1.02 | 0.012 | 2.77 | 3.22 | 0.02 | -27.15 | 0.07 | 46% of 13 | - | PF@2x 1.02 < 1.2; positive folds 46% < 60% |
| dip_long_rsi2<10_s2_1R_h3 | no | 1049 | 1.55 | 0.516 | 0.97 | -0.006 | 2.55 | -12.17 | -0.08 | -39.89 | -0.03 | 54% of 13 | - | PF@2x 0.97 < 1.2; expectancy@2x <= 0; positive folds 54% < 60% |
| dip_long_rsi2<5_s2_1R_h3 | no | 554 | 0.82 | 0.502 | 0.96 | -0.009 | 2.49 | -8.24 | -0.053 | -25.29 | -0.04 | 54% of 13 | - | PF@2x 0.96 < 1.2; expectancy@2x <= 0; positive folds 54% < 60% |
| dip_long_rsi2<5_s2_none_h3_x5 | no | 536 | 0.79 | 0.552 | 0.92 | -0.021 | 2.3 | -12.88 | -0.085 | -28.81 | -0.1 | 46% of 13 | - | PF@2x 0.92 < 1.2; expectancy@2x <= 0; positive folds 46% < 60% |
| dip_long_rsi2<10_s2_none_h3_x5 | no | 1031 | 1.52 | 0.549 | 0.94 | -0.016 | 2.31 | -20.18 | -0.139 | -40.65 | -0.12 | 54% of 13 | - | PF@2x 0.94 < 1.2; expectancy@2x <= 0; positive folds 54% < 60% |
| gap_short_fade1_s1_1R_h1 | no | 281 | 0.41 | 0.505 | 0.92 | -0.023 | 0.72 | -8.3 | -0.054 | -21.58 | -0.09 | 38% of 13 | - | PF@2x 0.92 < 1.2; expectancy@2x <= 0; positive folds 38% < 60% |
| gap_long_fade1_s1_1R_h1 | no | 562 | 0.83 | 0.512 | 0.86 | -0.058 | 0.62 | -31.99 | -0.238 | -42.35 | -0.26 | 31% of 13 | - | PF@2x 0.86 < 1.2; expectancy@2x <= 0; positive folds 31% < 60% |
| gap_long_go1_s1_1.5R_h2 | no | 420 | 0.62 | 0.44 | 0.85 | -0.078 | 1.35 | -30.3 | -0.223 | -43.4 | -0.34 | 23% of 13 | - | PF@2x 0.85 < 1.2; expectancy@2x <= 0; positive folds 23% < 60% |
| gap_short_fade0.5_s1_1R_h1 | no | 1400 | 2.06 | 0.459 | 0.82 | -0.08 | 0.82 | -71.09 | -0.765 | -80.01 | -0.62 | 15% of 13 | - | PF@2x 0.82 < 1.2; expectancy@2x <= 0; positive folds 15% < 60% |
| gap_long_fade1_s1.5_none_h3_x5 | no | 549 | 0.81 | 0.437 | 0.7 | -0.157 | 2.17 | -59.88 | -0.564 | -64.75 | -0.7 | 23% of 13 | - | PF@2x 0.7 < 1.2; expectancy@2x <= 0; positive folds 23% < 60% |
| gap_long_go0.5_s1_1.5R_h2 | no | 1689 | 2.49 | 0.448 | 0.79 | -0.1 | 1.48 | -84.16 | -1.134 | -86.35 | -0.81 | 8% of 13 | - | PF@2x 0.79 < 1.2; expectancy@2x <= 0; positive folds 8% < 60% |
| gap_long_fade0.5_s1_1R_h1 | no | 1938 | 2.86 | 0.482 | 0.78 | -0.108 | 0.7 | -90.1 | -1.421 | -92.4 | -0.86 | 15% of 13 | - | PF@2x 0.78 < 1.2; expectancy@2x <= 0; positive folds 15% < 60% |
| gap_long_fade0.5_s1.5_none_h3_x5 | no | 1764 | 2.6 | 0.496 | 0.77 | -0.1 | 1.95 | -85.18 | -1.175 | -86.9 | -0.87 | 23% of 13 | - | PF@2x 0.77 < 1.2; expectancy@2x <= 0; positive folds 23% < 60% |
| mom_long_high100_s1.5_1.5R_h3 | no | 2144 | 3.16 | 0.492 | 0.88 | -0.038 | 2.5 | -63.75 | -0.626 | -71.9 | -0.37 | 23% of 13 | - | PF@2x 0.88 < 1.2; expectancy@2x <= 0; positive folds 23% < 60% |
| mom_long_high100_s1_1R_h2 | no | 2558 | 3.77 | 0.491 | 0.79 | -0.09 | 1.29 | -92.37 | -1.58 | -93.74 | -0.86 | 8% of 13 | - | PF@2x 0.79 < 1.2; expectancy@2x <= 0; positive folds 8% < 60% |
| mr_long_wr-90_s2_none_h3_x5 | no | 899 | 1.32 | 0.586 | 1.05 | 0.02 | 2.32 | 14.61 | 0.084 | -26.92 | 0.16 | 69% of 13 | - | PF@2x 1.05 < 1.2 |
| mr_long_bb_low0_s1.5_1R_h3 | no | 519 | 0.76 | 0.52 | 1.03 | 0.022 | 1.91 | 6.34 | 0.038 | -27.51 | 0.1 | 54% of 13 | - | PF@2x 1.03 < 1.2; positive folds 54% < 60% |
| mr_long_bb_low0_s2_none_h3_x5 | no | 463 | 0.68 | 0.592 | 1.03 | 0.014 | 2.29 | 4.17 | 0.025 | -19.74 | 0.08 | 69% of 13 | - | PF@2x 1.03 < 1.2 |
| mr_long_key_rev0_s1.5_1R_h3 | no | 704 | 1.04 | 0.534 | 1.02 | 0.011 | 2.44 | 3.65 | 0.022 | -25.95 | 0.07 | 62% of 13 | - | PF@2x 1.02 < 1.2 |
| mr_long_outside_weak0_s2_none_h3_x5 | no | 658 | 0.97 | 0.573 | 1.01 | 0.004 | 1.93 | 0.84 | 0.005 | -19.37 | 0.04 | 46% of 13 | - | PF@2x 1.01 < 1.2; positive folds 46% < 60% |
| mr_long_key_rev0_s2_none_h3_x5 | no | 791 | 1.17 | 0.556 | 0.97 | -0.002 | 1.57 | -3.28 | -0.021 | -23.26 | -0.02 | 46% of 13 | - | PF@2x 0.97 < 1.2; expectancy@2x <= 0; positive folds 46% < 60% |
| mr_long_wr-90_s1.5_1R_h3 | no | 914 | 1.35 | 0.503 | 0.95 | -0.013 | 2.21 | -17.96 | -0.122 | -39.52 | -0.06 | 46% of 13 | - | PF@2x 0.95 < 1.2; expectancy@2x <= 0; positive folds 46% < 60% |
| mr_long_mon_down0_s2_none_h3_x5 | no | 1391 | 2.05 | 0.561 | 0.95 | -0.007 | 1.77 | -12.98 | -0.086 | -33.53 | -0.09 | 38% of 13 | - | PF@2x 0.95 < 1.2; expectancy@2x <= 0; positive folds 38% < 60% |
| mr_long_down30_s2_none_h3_x5 | no | 1009 | 1.49 | 0.575 | 0.94 | -0.014 | 2.22 | -16.86 | -0.114 | -41.16 | -0.11 | 54% of 13 | - | PF@2x 0.94 < 1.2; expectancy@2x <= 0; positive folds 54% < 60% |
| mr_long_outside_weak0_s1.5_1R_h3 | no | 617 | 0.91 | 0.514 | 0.92 | -0.021 | 2.32 | -15.76 | -0.106 | -37.52 | -0.12 | 46% of 13 | - | PF@2x 0.92 < 1.2; expectancy@2x <= 0; positive folds 46% < 60% |
| mr_long_down30_s1.5_1R_h3 | no | 1035 | 1.53 | 0.501 | 0.94 | -0.024 | 2.23 | -28.16 | -0.205 | -53.14 | -0.14 | 46% of 13 | - | PF@2x 0.94 < 1.2; expectancy@2x <= 0; positive folds 46% < 60% |
| mr_long_mon_down0_s1.5_1R_h3 | no | 1257 | 1.85 | 0.496 | 0.84 | -0.048 | 2.3 | -49.77 | -0.425 | -66.39 | -0.36 | 31% of 13 | - | PF@2x 0.84 < 1.2; expectancy@2x <= 0; positive folds 31% < 60% |
| mr_long_low70_s2_none_h3_x5 | no | 1762 | 2.6 | 0.553 | 0.86 | -0.039 | 2.2 | -54.71 | -0.489 | -60.91 | -0.38 | 23% of 13 | - | PF@2x 0.86 < 1.2; expectancy@2x <= 0; positive folds 23% < 60% |
| mr_long_ibs0.2_s2_none_h3_x5 | no | 2589 | 3.82 | 0.552 | 0.86 | -0.026 | 1.85 | -54.65 | -0.488 | -66.17 | -0.4 | 38% of 13 | - | PF@2x 0.86 < 1.2; expectancy@2x <= 0; positive folds 38% < 60% |
| mr_long_low70_s1.5_1R_h3 | no | 1794 | 2.64 | 0.49 | 0.84 | -0.065 | 2.13 | -74.23 | -0.836 | -77.1 | -0.49 | 8% of 13 | - | PF@2x 0.84 < 1.2; expectancy@2x <= 0; positive folds 8% < 60% |
| mr_long_ibs0.2_s1.5_1R_h3 | no | 2222 | 3.27 | 0.489 | 0.77 | -0.076 | 2.21 | -84.81 | -1.16 | -88.5 | -0.71 | 23% of 13 | - | PF@2x 0.77 < 1.2; expectancy@2x <= 0; positive folds 23% < 60% |
| mrshort_short_bb_high0_s2_none_h3_x5 | no | 154 | 0.23 | 0.481 | 0.85 | -0.033 | 2.62 | -5.34 | -0.034 | -9.69 | -0.15 | 31% of 13 | - | PF@2x 0.85 < 1.2; expectancy@2x <= 0; positive folds 31% < 60% |
| mrshort_short_bb_high0_s1.5_1R_h3 | no | 151 | 0.22 | 0.45 | 0.81 | -0.057 | 2.57 | -8.8 | -0.057 | -14.64 | -0.2 | 38% of 13 | - | PF@2x 0.81 < 1.2; expectancy@2x <= 0; positive folds 38% < 60% |
| mrshort_short_up30_s2_none_h3_x5 | no | 616 | 0.91 | 0.516 | 0.86 | -0.031 | 2.45 | -18.75 | -0.128 | -35.52 | -0.26 | 38% of 13 | - | PF@2x 0.86 < 1.2; expectancy@2x <= 0; positive folds 38% < 60% |
| mrshort_short_ibs_hi0.8_s1.5_1R_h3 | no | 1494 | 2.2 | 0.476 | 0.91 | -0.038 | 2.41 | -50.16 | -0.43 | -74.02 | -0.32 | 31% of 13 | - | PF@2x 0.91 < 1.2; expectancy@2x <= 0; positive folds 31% < 60% |
| mrshort_short_ibs_hi0.8_s2_none_h3_x5 | no | 1636 | 2.41 | 0.496 | 0.89 | -0.025 | 1.98 | -37.01 | -0.286 | -56.15 | -0.34 | 23% of 13 | - | PF@2x 0.89 < 1.2; expectancy@2x <= 0; positive folds 23% < 60% |
| mrshort_short_up30_s1.5_1R_h3 | no | 621 | 0.92 | 0.448 | 0.82 | -0.068 | 2.58 | -36.76 | -0.283 | -52.41 | -0.41 | 31% of 13 | - | PF@2x 0.82 < 1.2; expectancy@2x <= 0; positive folds 31% < 60% |
| nrb_short_nr70_s1_1R_h3 | no | 791 | 1.17 | 0.482 | 0.92 | -0.041 | 1.82 | -33.25 | -0.25 | -55.99 | -0.22 | 23% of 13 | - | PF@2x 0.92 < 1.2; expectancy@2x <= 0; positive folds 23% < 60% |
| nrb_short_inside0_s1_1R_h3 | no | 573 | 0.84 | 0.452 | 0.84 | -0.083 | 1.69 | -41.48 | -0.331 | -49.91 | -0.37 | 46% of 13 | - | PF@2x 0.84 < 1.2; expectancy@2x <= 0; positive folds 46% < 60% |
| nrb_long_inside0_s1_1.5R_h3 | no | 987 | 1.45 | 0.459 | 0.83 | -0.068 | 2.03 | -53.2 | -0.469 | -67.02 | -0.43 | 31% of 13 | - | PF@2x 0.83 < 1.2; expectancy@2x <= 0; positive folds 31% < 60% |
| nrb_long_inside0_s1_1R_h3 | no | 1025 | 1.51 | 0.5 | 0.83 | -0.064 | 1.76 | -52.1 | -0.455 | -64.03 | -0.45 | 38% of 13 | - | PF@2x 0.83 < 1.2; expectancy@2x <= 0; positive folds 38% < 60% |
| nrb_long_nr70_s1_1.5R_h3 | no | 1173 | 1.73 | 0.462 | 0.85 | -0.072 | 2.12 | -61.44 | -0.588 | -65.6 | -0.5 | 15% of 13 | - | PF@2x 0.85 < 1.2; expectancy@2x <= 0; positive folds 15% < 60% |
| nrb_long_nr70_s1_1R_h3 | no | 1276 | 1.88 | 0.498 | 0.85 | -0.066 | 1.83 | -61.18 | -0.584 | -64.89 | -0.51 | 31% of 13 | - | PF@2x 0.85 < 1.2; expectancy@2x <= 0; positive folds 31% < 60% |
| nrb_long_nr40_s1_1.5R_h3 | no | 1653 | 2.44 | 0.445 | 0.78 | -0.108 | 2.03 | -85.99 | -1.209 | -88.81 | -0.84 | 15% of 13 | - | PF@2x 0.78 < 1.2; expectancy@2x <= 0; positive folds 15% < 60% |
| nrb_long_nr40_s1_1R_h3 | no | 1805 | 2.66 | 0.479 | 0.8 | -0.099 | 1.76 | -85.97 | -1.208 | -88.73 | -0.86 | 23% of 13 | - | PF@2x 0.8 < 1.2; expectancy@2x <= 0; positive folds 23% < 60% |
| short_short_rsi2>90_s2_none_h3_x5 | no | 584 | 0.86 | 0.526 | 0.9 | -0.023 | 2.47 | -14.22 | -0.095 | -29.85 | -0.18 | 46% of 13 | - | PF@2x 0.9 < 1.2; expectancy@2x <= 0; positive folds 46% < 60% |
| short_short_rsi2>90_s2_1R_h3 | no | 585 | 0.86 | 0.446 | 0.84 | -0.044 | 2.82 | -24.16 | -0.171 | -36.31 | -0.31 | 38% of 13 | - | PF@2x 0.84 < 1.2; expectancy@2x <= 0; positive folds 38% < 60% |
| short_short_rsi2>95_s2_none_h3_x5 | no | 285 | 0.42 | 0.505 | 0.74 | -0.064 | 2.52 | -17.29 | -0.117 | -24.62 | -0.39 | 31% of 13 | - | PF@2x 0.74 < 1.2; expectancy@2x <= 0; positive folds 31% < 60% |
| short_short_rsi2>95_s2_1R_h3 | no | 284 | 0.42 | 0.426 | 0.69 | -0.086 | 2.83 | -22.36 | -0.156 | -30.19 | -0.47 | 23% of 13 | - | PF@2x 0.69 < 1.2; expectancy@2x <= 0; positive folds 23% < 60% |

## Combined train portfolio (shared 1% risk / 4% open-risk cap)

| trades | /week | win | PF | exp R | sessions | total % | %/month | max DD % | Sharpe |
|---|---|---|---|---|---|---|---|---|---|
| 498 | 0.73 | 0.562 | 1.44 | 0.119 | 2.79 | 74.34 | 0.345 | -13.53 | 0.61 |  (1x costs)
| 498 | 0.73 | 0.546 | 1.33 | 0.096 | 2.79 | 55.56 | 0.274 | -13.86 | 0.49 |  (2x costs)

Signals skipped by the risk layer: {'open_risk_cap': 385, 'same_symbol': 0, 'gross_cap': 109, 'not_triggered': 0, 'zero_size': 0}

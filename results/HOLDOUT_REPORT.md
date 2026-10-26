# Holdout report (MES, unseen data)
Candidate `pullback[exit_ma=5,max_hold=10,rsi_entry=10,rsi_len=2,stop_atr=2.5,trend_len=100]` evaluated on 2024-01-01 .. 2026-10-20. Holdout evaluation #2 (registry: results/holdout_registry.json).

## Metrics vs baselines
| metric | candidate | buy_hold_1x | ma_cross_50_200 |
|---|---|---|---|
| net_return_pct | 4.45 | 34.87 | -1.67 |
| cagr_pct | 1.57 | 11.28 | -0.60 |
| avg_monthly_return_pct | 0.13 | 0.92 | -0.04 |
| median_monthly_return_pct | 0.00 | 1.18 | 0.00 |
| pct_positive_months | 41.20 | 61.80 | 41.20 |
| worst_month_pct | -0.27 | -4.82 | -3.39 |
| months_ge_5pct | 0 | 1 | 0 |
| max_drawdown_pct | 0.56 | 15.53 | 6.95 |
| sharpe | 1.33 | 0.94 | -0.16 |
| trades | 25 | 0 | 2 |
| win_rate_pct | 80.00 | 0.00 | 0.00 |
| profit_factor | 4.80 | 0.00 | 0.00 |
| expectancy_usd | 177.80 | 0.00 | -834.38 |
| expectancy_r | 0.23 | 0.00 | -1.02 |
| avg_sessions_held | 2.48 | 0.00 | 248.50 |
| avg_calendar_days_held | 3.72 | 0.00 | 354.00 |
| exposure_pct | 8.60 | 100.00 | 68.80 |
| total_fees_usd | 50.00 | 0.00 | 4.00 |
| total_roll_costs_usd | 0.00 | 0.00 | 36.00 |

## Cost / slippage stress
| scenario | net_return_pct | profit_factor | expectancy_usd | max_drawdown_pct |
|---|---|---|---|---|
| 1x | 4.45 | 4.80 | 177.80 | 0.56 |
| 2x | 4.33 | 4.63 | 173.25 | 0.56 |
| 3x | 4.22 | 4.47 | 168.70 | 0.56 |
| +2 ticks slippage | 4.32 | 4.61 | 172.70 | 0.56 |

## Random-entry baseline
Beats 100.0% of 200 matched random runs (random median $275, candidate $4,445).

## Yearly returns (%)
| year | return_pct |
|---|---|
| 2024 | 2.06 |
| 2025 | 1.23 |
| 2026 | 1.09 |

## Losing periods
### Worst drawdowns
| depth_pct | dd_start | trough | recovered |
|---|---|---|---|
| -0.56 | 2024-09-06 | 2024-09-06 | 2024-11-05 |
| -0.51 | 2024-04-16 | 2024-04-19 | 2024-06-25 |
| -0.43 | 2024-07-23 | 2024-07-25 | 2024-07-31 |

### Losing months
2024-04 -0.088%, 2024-09 -0.27%, 2024-10 -0.029%, 2025-02 -0.246%

### Losing trades (5)
| entry_date | exit_date | contracts | entry_price | exit_price | exit_reason | net_pnl |
|---|---|---|---|---|---|---|
| 2024-04-16 | 2024-04-22 | 1 | 5,706.50 | 5,629.50 | trend invalidated | -387.00 |
| 2024-07-22 | 2024-07-24 | 1 | 6,128.50 | 6,083.00 | reverted above exit MA | -229.50 |
| 2024-09-06 | 2024-09-09 | 1 | 6,050.25 | 5,996.25 | trend invalidated | -272.00 |
| 2024-10-24 | 2024-10-29 | 1 | 6,330.25 | 6,324.75 | reverted above exit MA | -29.50 |
| 2025-02-24 | 2025-02-25 | 1 | 6,452.25 | 6,402.25 | trend invalidated | -252.00 |

## Monthly returns (%)
| month | return_pct |
|---|---|
| 2024-01-31 | 0.21 |
| 2024-02-29 | 0.00 |
| 2024-03-31 | 0.00 |
| 2024-04-30 | -0.09 |
| 2024-05-31 | 0.32 |
| 2024-06-30 | 0.11 |
| 2024-07-31 | 0.26 |
| 2024-08-31 | 0.04 |
| 2024-09-30 | -0.27 |
| 2024-10-31 | -0.03 |
| 2024-11-30 | 1.21 |
| 2024-12-31 | 0.28 |
| 2025-01-31 | 0.31 |
| 2025-02-28 | -0.25 |
| 2025-03-31 | 0.00 |
| 2025-04-30 | 0.00 |
| 2025-05-31 | 0.00 |
| 2025-06-30 | 0.00 |
| 2025-07-31 | 0.00 |
| 2025-08-31 | 0.65 |
| 2025-09-30 | 0.00 |
| 2025-10-31 | 0.29 |
| 2025-11-30 | 0.21 |
| 2025-12-31 | 0.00 |
| 2026-01-31 | 0.39 |
| 2026-02-28 | 0.00 |
| 2026-03-31 | 0.00 |
| 2026-04-30 | 0.00 |
| 2026-05-31 | 0.00 |
| 2026-06-30 | 0.00 |
| 2026-07-31 | 0.00 |
| 2026-08-31 | 0.00 |
| 2026-09-30 | 0.47 |
| 2026-10-31 | 0.23 |

## Promotion to paper trading: **PASSED**

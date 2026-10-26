# Results (actual runs, nothing hand-edited)

Generated artefacts: `results/TRAIN_REPORT.md`, `results/HOLDOUT_REPORT.md`,
`results/DATA_QUALITY.md`, `results/lumibot_backtest_<start>_<end>.json`,
`results/experiment_log.jsonl`. Account $100,000, 1% risk per trade, base costs unless stated.

## 1. Training (S&P 500 proxy 2008-2019 + MES 2019-2023): all 12 candidates

| Candidate | Gates | Trades | PF | Max DD | Median fold Sharpe | +folds | Beats random | SPX net | MES net |
|---|---|---|---|---|---|---|---|---|---|
| trend 50/100 trail3 stop2.5 | **fail** (5/8 folds) | 74 | 1.84 | 5.5% | 0.62 | 5 | 86% | +14.0% | +2.3% |
| trend 20/100 trail3 stop2.5 | pass | 83 | 2.02 | 5.3% | 0.56 | 6 | 95% | +22.3% | +1.6% |
| trend 50/100 trail4 stop3 | **fail** (5/8 folds) | 60 | 2.47 | 5.1% | 0.80 | 5 | 96% | +16.6% | +2.8% |
| trend 50/100 long+short | **fail** (5/8 folds) | 98 | 1.47 | 6.6% | 0.41 | 5 | 87% | +10.8% | +1.2% |
| breakout 55/20 | pass | 44 | 2.73 | 5.9% | 0.72 | 6 | 97% | +18.6% | +5.7% |
| breakout 20/10 | pass | 84 | 2.13 | 4.3% | 0.39 | 6 | 92% | +19.8% | +4.2% |
| breakout 55/20 long+short | pass | 64 | 1.89 | 9.2% | 0.53 | 6 | 93% | +14.8% | +7.1% |
| breakout 40/15 stop2.5 | **fail** (5/8 folds) | 57 | 2.32 | 4.0% | 0.31 | 5 | 82% | +15.1% | +1.1% |
| pullback SMA100 RSI3<15 | pass | 64 | 1.64 | 3.0% | 0.49 | 6 | 94% | +3.1% | +2.3% |
| **pullback SMA100 RSI2<10 (selected)** | pass | 100 | 1.48 | 5.9% | **1.03** | 7 | 99% | +3.3% | +4.0% |
| pullback SMA50 RSI3<20 | pass | 69 | 2.36 | 3.0% | 1.00 | 7 | 100% | +6.4% | +3.8% |
| pullback SMA100 RSI3<15 exit10 | pass | 59 | 1.59 | 3.0% | 0.52 | 6 | 96% | +4.0% | +1.4% |

Failed experiments: 4 of 12 (all on fold consistency). Adding short-side rules made both the trend
and breakout families *worse* (lower PF, deeper drawdown) — the equity-index short side did not
pay over 2008-2023. Note the ranking rule (median fold Sharpe) picked the candidate with the
smallest absolute return; trend/breakout earned 4–7× more on the SPX proxy at similar drawdowns.

**Selected candidate, training detail:** SPX proxy +3.28% over 11 years (CAGR 0.30%, Sharpe 0.24,
PF 1.27, max DD 5.86%); MES 2019-2023 +3.99% (CAGR 0.94%, Sharpe 0.84, PF 2.30, max DD 1.38%).
Losing training years: 2014 (−2.38%), 2015 (−2.58%), 2018 (−2.49%), 2020 (−0.69%); losing fold
SPX 2014-2016 (−3.56%). **The SPX-proxy drawdown that began in June 2014 (−5.86% at its May-2016
trough) had not recovered when the proxy period ended in April 2019 — almost five years
underwater.** On MES the worst episode was −1.38% (Jan–Jun 2020, recovered May 2021). Cost stress (train): PF 1.48 → 1.36 (2×) → 1.25 (3×); the SPX part turns
negative at 3× costs (−0.10%).

**Selection-process check (anchored walk-forward):** choosing the best-so-far candidate at each
fold produced a mean next-fold return of 0.91% versus 1.69% for the average candidate — the
selection rule itself showed **no** out-of-sample skill on training folds.

## 2. Holdout (MES 2024-01-02 → 2026-10-20, unseen, evaluated once + one identical reproduction)

| Metric | Selected pullback | Buy & hold 1× | MA cross 50/200 |
|---|---|---|---|
| Net return | **+4.45%** | +34.87% | −1.67% |
| CAGR | 1.57% | 11.28% | −0.60% |
| Average monthly return | **0.13%** | 0.92% | −0.04% |
| Positive months | 41% (most months flat) | 61% | 39% |
| Worst month | −0.27% | −4.82% | −3.39% |
| Max drawdown | **0.56%** | 15.53% | 6.95% |
| Sharpe (daily) | 1.33 | 0.94 | −0.16 |
| Trades | 25 | — | 2 |
| Win rate | 80% | — | 0% |
| Profit factor | 4.80 | — | 0 |
| Expectancy / trade | $177.80 (0.23 R) | — | −$834 |
| Avg holding | 2.5 sessions (3.7 calendar days) | — | — |
| Exposure | 8.6% of sessions | 100% | 69% |
| Yearly | 2024 +2.06%, 2025 +1.23%, 2026 YTD +1.09% | | |

Cost sensitivity: 1× +4.45% · 2× +4.33% · 3× +4.22% · +2 ticks slippage +4.32% (PF ≥ 4.47 in all).
Random-entry baseline: beats 100% of 200 matched random runs (random median +$275, candidate +$4,445).
Losing periods: worst drawdowns −0.56% (Sep 2024), −0.51% (Apr 2024), −0.43% (Jul 2024); losing
months 2024-04, 2024-09, 2024-10, 2025-02; 5 losing trades (largest −$387). No trades at all from
March to July 2025 (the April 2025 sell-off pushed price below the 100-day trend filter / vol filter).

**Promotion gates: passed** (≥ 15 trades, PF ≥ 1.1, DD ≤ 25%, profitable at 2× costs) → paper
trading is unlocked for this candidate. Independent LumiBot replay: 25/25 identical entry
sessions, final equity within $27 of the internal engine.

## 3. The 5–8% per month question
* At the pre-registered 1% risk, the validated edge produced **0.13% per month** on unseen data.
* Scaling risk on training data (limits loosened only for that experiment):

| Risk / trade | MES avg monthly | MES max DD | SPX-proxy avg monthly | SPX-proxy max DD |
|---|---|---|---|---|
| 1% | 0.08% | 1.4% | 0.03% | 5.9% |
| 3% | 0.30% | 4.2% | 0.08% | 17.9% |
| 5% | 0.51% | 6.9% | 0.14% | 28.5% |
| 8% | 0.85% | 11.2% | 0.15% | 40.4% |

Even at 8% risk per trade (a level no professional risk framework would accept) the strategy
averaged under 1% per month, with drawdowns growing far faster than returns on the longer sample.
**Conclusion: 5–8% average monthly returns are not supported by any evidence produced here.** The
binding constraint is opportunity: a selective swing strategy on one index future is in the market
~7–9% of the time. Higher returns would need more independent opportunities (more instruments /
strategies, validated the same way) — not more leverage.

## 4. What this does and does not show
* It shows a small, cost-robust, low-drawdown edge for buying short-term oversold dips in an
  established S&P 500 uptrend, consistent across the proxy, MES training and MES holdout periods,
  and clearly better than random timing with identical risk management.
* It does not show a return level that beats simply holding the index; at 1% risk it delivered
  roughly 1/7 of buy-and-hold's holdout return with 1/28 of its drawdown.
* 25 holdout trades is a small sample; the holdout PF of 4.8 is far above the training PF of 1.48
  and should be expected to regress.

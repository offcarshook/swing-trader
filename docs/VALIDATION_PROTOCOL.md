# Validation protocol (pre-registered, with disclosed amendments)

The append-only log `results/experiment_log.jsonl` (timestamp, git commit, config hash) is the
primary record. `results/holdout_registry.json` records every holdout evaluation.

## 1. Pre-registration (written before any backtest)
`config/default.yaml` fixed, before any strategy result existed: instrument, cost and risk
assumptions, the three strategy families with **4 parameter sets each (12 candidates)**, the
selection gates and ranking rule, the promotion gates and the chronological split:

| Period | Data | Role |
|---|---|---|
| 2019-05-06 → 2023-12-31 | MES | training |
| **2024-01-01 → 2026-10-20** | MES | **holdout — touched once, after selection** |
| 2008-01-02 → 2019-04-30 | S&P 500 cash index | originally "second unseen test" → training (Amendment 1) |

## 2. Look-ahead / leakage controls
* Signals use completed session bars only; fills at the next session's RTH open.
* Indicators are causal; unit tests mutate future bars and assert identical past trades/equity.
* Warm-up history before a window is used for indicators only (it was known at the time).
* LumiBot's daily pandas path returns the in-progress bar to the strategy; the bridge drops it
  (`completed_bars`, unit-tested). Holdout replays in LumiBot are refused until the one-shot
  holdout evaluation has been registered.
* LLM research is excluded from every backtest (models know the future of historical dates).
* Random-entry seeds are deterministic (no Python `hash()` salt).

## 3. Selection on training data only
Gates (all must pass): ≥ 30 trades; profit factor ≥ 1.15; max drawdown ≤ 25% (worst source);
≥ 6 of 8 walk-forward folds with positive P&L; beat ≥ 80% of matched random-entry runs.
Survivors ranked by **median fold Sharpe** (robustness over peak result). One candidate selected.
An anchored walk-forward of the *selection procedure itself* is also reported.

## 4. Holdout and promotion
The selected candidate (only) is evaluated on the holdout at 1×, 2×, 3× costs and +2 ticks
slippage, against buy & hold, MA-cross and 200 random-entry runs. Paper trading unlocks only if:
≥ 15 trades, PF ≥ 1.1, max DD ≤ 25%, profitable at 2× costs. `HoldoutGuard` raises if a
*different* candidate/config is evaluated after the holdout has been touched.

## Amendments and disclosures (chronological)
1. **Smoke-run disclosure.** While testing the engine, the first parameter set of each family
   was run on the MES *training* window (results logged verbatim). They showed 12–22 trades each.
2. **Amendment 1** (logged before any proxy or holdout run): 12–22 trades cannot satisfy the
   30-trade gate and would make selection statistically meaningless. The S&P 500 2008-2019
   proxy was moved into training; folds extended to 8 (4 SPX + 4 MES) and the fold gate scaled
   from 3/4 to 6/8 (same 75%). Cost of the amendment: the protocol lost its second unseen period;
   the MES holdout (2.8 years) is now the only genuinely unseen data.
3. **Bug-fix disclosure** (after holdout evaluation #1): monthly/yearly return tables dropped the
   first period. No selection or promotion input used those numbers. Fixed with a regression
   test; training selection re-run (deterministic, asserted identical) and the holdout re-run for
   the *same* candidate (registry evaluation #2, identical trades, PF, drawdown).
4. Reports were later regenerated with additional losing-period tables via a third deterministic
   selection re-run (asserted identical) and `swingtrader report` (no holdout re-run).

## Known residual biases
* **Researcher knowledge:** the strategy families are textbook ideas chosen by someone who knows
  2008–2026 market history. Small grids and train-only selection limit, but cannot remove, this.
* **Multiple testing:** 12 candidates; the winner's training Sharpe is optimistic. The anchored
  walk-forward shows the "pick the best so far" rule did *worse* than the average candidate
  (0.91% vs 1.69% mean next-fold return).
* **Small samples:** 25 holdout trades. Confidence intervals on PF/expectancy are wide.
* **Data provenance:** anonymous third-party files, validated by cross-checks but not exchange-certified.

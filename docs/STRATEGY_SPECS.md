# Strategy specifications (exact, reproducible)

All rules run on **completed session bars** (17:00–16:00 CT Globex session; OHLC of the whole
session, `close` = last trade before 16:00 CT). Decisions made after the close of session *t*
execute at the **RTH open (08:30 CT) of session t+1**. Indicators are causal (row *t* uses rows ≤ *t*);
`tests/test_engine.py::test_no_lookahead_*` and `tests/test_indicators_sessions.py::test_indicators_are_causal`
mutate future bars and assert past decisions do not change.

Common definitions: `ATR` = Wilder ATR(20); `vol_rank` = percentile of ATR/close within the
trailing 252 sessions; **no-trade (all strategies)** when `vol_rank > 95`.

## S1 Trend continuation (`strategies/trend.py`)
* `up(t)` = close > SMA(slow) ∧ SMA(fast) > SMA(slow) ∧ SMA(slow) > SMA(slow)[t−20]
* **Entry long**: flat ∧ up(t) ∧ (¬up(t−1) ∨ close crosses above SMA(fast)) ∧ no no-trade flag
* **Initial stop**: fill − `stop_atr`·ATR(t) (resting, rounded to tick away from price)
* **Trailing stop**: highest close since entry − `trail_atr`·ATR(t) (tighten only)
* **Exit**: close < SMA(slow) → market at next RTH open
* **Short**: exact mirror when `allow_short`
* Grid: (50/100, trail 3, stop 2.5), (20/100, 3, 2.5), (50/100, 4, 3), (50/100, 3, 2.5, short)

## S2 Momentum breakout (`strategies/breakout.py`)
* **Entry long**: flat ∧ close > highest high of the prior N sessions ∧ no no-trade flag
* **Initial stop**: fill − `stop_atr`·ATR(t)
* **Resting stop**: max(initial, lowest low of the last M sessions) — tighten only; it is the exit
* **Short** mirror when allowed
* Grid: (55/20, 2.0), (20/10, 2.0), (55/20, 2.0, short), (40/15, 2.5)

## S3 Pullback in uptrend, long only (`strategies/pullback.py`)
* **Entry**: flat ∧ close > SMA(trend_len) ∧ RSI(rsi_len) < rsi_entry ∧ no no-trade flag
* **Initial stop**: fill − `stop_atr`·ATR(t) (resting)
* **Exit at next RTH open** when: close > SMA(exit_ma) | sessions held ≥ max_hold | close < SMA(trend_len)
* Grid: (100, RSI3<15, exit SMA5, 10d, 2.5), (100, RSI2<10, 5, 10d, 2.5), (50, RSI3<20, 5, 8d, 2.5), (100, RSI3<15, 10, 15d, 3.0)

**Selected on training data:** S3 with trend_len 100, RSI(2) < 10, exit SMA(5), max 10 sessions, 2.5 ATR stop.

## Baselines (`strategies/baselines.py`, `backtest/engine.py::buy_and_hold`)
* **Buy & hold 1×**: long `floor(equity / notional)` contracts, rebalanced monthly at the RTH open, roll costs paid
* **MA cross**: long while SMA(50) > SMA(200), 3-ATR initial stop, same risk sizing
* **Random entry**: Monte-Carlo (100 seeds train / 200 holdout) entering at the candidate's own
  entry rate, side mix, stop and holding-time distribution with identical sizing and costs

## Position sizing and risk (`risk.py`) — identical for every strategy
```
per_contract_risk = |fill − stop| × $5 + est. round trip (2 × fees + (1 + 2) ticks × $1.25)
contracts = min( floor(1%·equity / per_contract_risk),                 # risk per trade
                 floor((2%·equity − open_risk) / per_contract_risk),   # total open risk
                 floor(3·equity / (price × $5)),                        # notional leverage
                 floor(0.5·equity / $2,500 margin),                    # margin utilisation
                 20 )                                                   # hard cap
reject if < 1, stop on wrong side, stop < 8 ticks, halted, or day blocked
```
* **Daily loss limit 3%**: a session "daily-loss stop" price is derived from the session's starting
  equity; touching it flattens and blocks new entries for the session.
* **Drawdown halt 20%** from peak: flatten at next open, no entries until a manual, explicit reset.
* **Data failures**: entries are blocked after a data hole (> 4 calendar days) and, in paper
  trading, whenever `safety.check_latest_bar` fails (stale, too few RTH bars, bad OHLC).
* **Thin sessions** (holiday/half day, < 300 RTH minutes): slippage doubled.
* **Rolls**: a position held across a roll date (8 days before quarterly expiry) pays 2 legs of fees + slippage.

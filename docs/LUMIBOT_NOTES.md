# LumiBot integration notes (verified against lumibot 4.6.30, 2026-10-24 release)

Verified by reading the installed source and by probe backtests, not assumed.

## What works
* `PandasDataBacktesting` with our own daily frame (`Data(asset, df, timestep="day")`), futures
  asset `Asset("MES", FUTURE, expiration=…, multiplier=5)`, `TradingFee(per_contract_fee=…)`.
* Futures accounting: margin deducted on open (LumiBot's `TYPICAL_FUTURES_MARGINS`), P&L realised
  per contract × multiplier on close, portfolio value = cash + margin + unrealised (checked by hand
  in the probe: 2 MES bought at 4862, marked at 4802.5 → −$595, cash 97,398, value 99,403).
* Stop orders: gap → filled at the bar open; otherwise at the stop price when the bar's range
  touches it (`BacktestingBroker.stop_order`).
* `benchmark_asset=None, risk_free_rate=0.0` avoid Yahoo calls (blocked here).

## Look-ahead hazard found (and guarded)
With daily bars stamped at the session date, an order submitted at iteration *D* fills at the
**open of the bar stamped D**, but `get_historical_prices()` at iteration *D* **already returns
bar D including its close**. A naive strategy would buy at today's open knowing today's close.
`lumibot_bridge.strategy.completed_bars()` drops every bar with index ≥ the iteration date, so a
decision at *D* uses sessions ≤ *D−1* and fills at session *D*'s RTH open (we feed `open = rth_open`),
which is exactly the internal engine's timing. Unit-tested.

## Parity with the internal engine (selected pullback candidate)
| Window | Entries internal / LumiBot / same session | Final equity internal | LumiBot | Δ |
|---|---|---|---|---|
| Train 2019-11-22 → 2023-12-31 | 32 / 32 / 32 | $103,994.00 | $103,945.25 | −$48.75 |
| Holdout 2024-01-02 → 2026-10-20 | 25 / 25 / 25 | $104,445.00 | $104,417.88 | −$27.12 |

Differences come from the fee/slippage approximation (see COSTS.md) and from the entry-day stop:
in LumiBot the protective stop is submitted in `on_filled_order`, so it is first evaluated on the
session *after* entry (the internal engine protects the entry session after the RTH open). Daily
equity snapshots correlate only ~0.4–0.6 because LumiBot's daily mark timing differs; the
end-to-end P&L agrees within $50.

## Limitations
* Rolls are emulated in the bridge (close + reopen market orders on the roll date) because the
  continuous back-adjusted series is modelled as one long-dated contract; the selected strategy
  holds ~2.5 sessions, so no roll occurred in either replay.
* Paper trading via LumiBot (`swingtrader paper --mode lumibot`) needs a Tradovate demo
  (`TRADOVATE_IS_PAPER=true`) or IB paper gateway (port 7497/4002); none available here → blocked.
  The launcher refuses non-paper configurations. It has **not** been exercised against a broker.

# Cost and execution assumptions

All values live in `config/default.yaml → costs` and scale together with `cost_multiplier`.
No historical bid/ask data could be obtained, so spreads are assumptions and are stress-tested.

| Item | Base assumption (per MES contract, per side) | Rationale |
|---|---|---|
| Broker commission | $0.62 | typical retail futures broker for micros ($0.25–$0.85 range) |
| Exchange + clearing + NFA | $0.38 | CME micro E-mini non-member exchange fee + clearing + NFA, approx. |
| **All-in fees** | **$1.00 / side** ($2.00 round trip) | 2× and 3× stresses cover $2–$3/side |
| Market order at RTH open | 1 tick ($1.25) adverse vs the 1-min bar open | MES RTH spread is normally 1 tick; the bar open is a trade price, so a full tick is conservative |
| Stop order | 2 ticks adverse vs the stop price | stops trigger into momentum |
| Gap through a stop | fill at the gap open − (1 + 1) ticks | no fill at the stop price when price jumps over it |
| Holiday / half-day session | slippage × 2 | thinner books |
| Quarterly roll | 2 legs × (fees + 1 tick) | conservative vs a calendar-spread order |
| Margin | $2,500 per contract for limits | broker-specific; LumiBot uses its own table ($1,300 MES) for cash accounting |

Sensitivity reported for every final number: 1×, 2×, 3× costs and +2 ticks on every fill.

## LumiBot run
LumiBot 4.6.30 applies `TradingSlippage` only to SMART_LIMIT orders, so for market/stop orders the
bridge folds a blended slippage (1.5 ticks) into a per-contract fee: $1.00 + 1.5 × $1.25 =
**$2.875 per side**. This is why LumiBot and the internal engine differ by tens of dollars.

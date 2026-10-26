# Instrument selection: MES (Micro E-mini S&P 500)

Selection was made from what could actually be obtained and validated in this environment,
not from preference. Numbers below come from `results/data_quality.json` (`swingtrader data`).

## What data was reachable

The environment's network policy blocks Yahoo, Stooq, CME, Databento, Polygon, Alpha Vantage,
Tiingo, FRED, Nasdaq Data Link and broker APIs (all answered `403` at the proxy). Hugging Face
was reachable. Every candidate dataset found there was downloaded, pinned (revision + SHA-256)
and audited:

| Candidate | Source file | Span | Quality findings | Verdict |
|---|---|---|---|---|
| **MES** continuous, additive back-adjusted, 1-min, ETH+RTH | `thillsss/SPX-MES-VIX-data` | 2019-05-06 → 2026-10-20, 1,923 sessions, 2.63 M bars | 0 OHLC violations, 0 off-tick prices, 0 duplicates; 1 stray Saturday bar dropped; 3 missing quarterly-expiry Fridays (2023-09-15, 2023-12-15, 2024-03-15) plus Good Fridays; volume present | **selected** |
| ES front month, unadjusted, 1-min | `Khanhpham1992/es-futures-1m` (Databento-style ids) | 2020-11-17 → 2024-07-19, 473 sessions | holes of 166, 41, 40 and 25 days; inconsistent `adj_*` columns | cross-check only |
| MNQ continuous 1-min | `thillsss/SPX-MES-VIX-data` | 2022-01-03 → 2025-09-03, 942 sessions | **43,701 duplicate timestamps**, no volume column, short | rejected |
| NQ | none found | — | — | unavailable |
| S&P 500 cash index 1-min | `thillsss/SPX-MES-VIX-data` | 2008-01-02 → 2026-10-20, 4,730 sessions | matches NYSE calendar exactly; no volume; stale 08:30 opening print | training proxy (Amendment 1) |
| Commodity samples (GC/KC/PL/FCPO) | `lynx1231/...-data-sample` | ≤ 3 years per contract, no continuous series | too short for swing validation | rejected |
| `paperswithbacktest/*` | gated (subscription) | — | could not download | unavailable |

## Independent validation of the MES file (anonymous uploader, no licence card)

Because the MES file has unknown provenance, it was checked against two independent series:

* **vs unadjusted ES (different vendor/format):** daily RTH-close changes over 419 consecutive
  common sessions (roll days excluded): correlation **0.99998**, mean absolute difference
  **0.20 points**, max 1.5 points. The offset `MES_adj − ES` is constant within a contract on
  95.8% of days (IQR ≤ 1 tick) and steps only at quarterly rolls by amounts consistent with the
  ES calendar spread (≈ −52 … −65 points in 2023-24 when rates were ~5%). This confirms the
  series is additively back-adjusted, rolled on the Monday of expiry week.
* **vs the S&P 500 cash index:** daily changes over 1,822 sessions: correlation **0.9990**,
  mean absolute difference **0.036%** of index level.

Conclusion: price changes in the MES file are trustworthy for daily swing research. Absolute
levels are back-adjusted (earlier prices are shifted up), which is exact for point-based P&L and
stops, but means quoted prices are not the historical contract prices.

## Why MES over ES / MNQ / NQ

| Criterion | MES | Notes |
|---|---|---|
| Data | longest validated futures history available here (7.4 yrs, 1-min, with volume) | ES file has large holes; MNQ file is duplicated and volume-less |
| Contract | $5 × index, tick 0.25 = **$1.25** | ES is 10× larger ($12.50/tick): at $100k and 1% risk a 2.5-ATR ES stop would usually allow 0 contracts |
| Sizing granularity | 1-contract steps of ~$300–$900 of stop risk | makes the risk-based sizing rule actually bind |
| Liquidity | median session volume 0.75 M (2021) → 1.1 M contracts (2025) in this data; spread ≈ 1 tick in RTH | positions here are 1–20 contracts |
| Spread estimate | no historical bid/ask available; 1-tick spread assumed (a public cost table, paperswithbacktest's README, reports ES front-month spread ≈ 1.04 ticks 2017-2026) | stress-tested at 2× and 3× |
| Expiry/roll | quarterly H/M/U/Z, 3rd Friday; roll 8 days before expiry modelled explicitly with costs | `contracts.py` |
| Framework compatibility | LumiBot: `Asset(... FUTURE, multiplier=5)`, built-in MES margin table entry; verified in a real LumiBot backtest | TradingAgents: equity-index thesis via `^GSPC` context |
| Overnight exposure | 23-hour Globex session lets resting stops act overnight; the data include the overnight bars so gap risk is simulated | |

## Limitations carried forward

* Single instrument → few trades per year; statistical power is the binding constraint.
* The SPX proxy has no overnight session, roll or carry; it is used only for training.
* No real-time feed is reachable here, so paper trading can only consume files.

# Data audit (2026-10-26)

Every number below was produced by code in this repository from the files listed. Input files are
fingerprinted (sha256) in `data/meta/input_fingerprints.json`; downloaded/uploaded data stays out of git
(`data/raw/` is ignored) and is rebuilt by the scripts named here.

## 1. Instrument × data availability matrix

| Group | Instrument | Source | First | Last | Sessions / rows | Resolution | Price basis | Status |
|---|---|---|---|---|---|---|---|---|
| A ETF | **SPY** | user upload `spy-historical.csv` | 1993-02-01 | **2025-09-11** | 8,210 | daily | raw OHLC + dividend column (131 ex-dates); total-return factor rebuilt from dividends | **used** |
| A ETF | **QQQ** | user upload `qqq_daily_clean.csv` (adjusted only) + Alpha Vantage DIVIDENDS | 1999-03-10 | **2026-09-29** | 6,932 | daily | executable prices **rebuilt** from adjusted file + 89 ex-dates (`scripts/rebuild_qqq_raw.py`) | **used** |
| A ETF | DIA, GLD, XLE, XLF, XLK, SMH, XLV, DBC | Kaggle `liewyousheng/historical-etf` | 1998–2006 | 2022-08-08 | 2,999–6,179 | daily | raw OHLC + Adj Close (dividends inferred from factor jumps) | research only (market matrix) |
| A ETF | VOO, IVV | same Kaggle set | 2000/2010 | 2022-08-08 | | daily | | not used: duplicate SPY exposure |
| A ETF | IWM, IEF, SLV, USO, EFA, EEM | Kaggle `jacksoncrow/stock-market-dataset` | 2000–2006 | **2020-04-01** | | daily | raw OHLC + Adj Close | training-period only |
| A ETF | TLT | Kaggle `kornilovag94/etfs-bonds-market-dataset` | 2007-04-11 | 2024-08-19 | 4,529 | daily | **unadjusted, no dividends** (total return understated) | research only |
| A ETF | SPY, QQQ, IWM, DIA, TLT | Alpha Vantage free key (compact) | 2026-06-03 | 2026-10-23 | 100 each | daily | raw, no dividends | validation of rebuilt QQQ prices only |
| A ETF | QQQM, XLI, SHY | — | | | | | | **not available** (not in any accessible source) |
| A proxy | S&P 500 cash index | pinned HF `SPX_full_1min_CT.txt` | 2008-01-02 | 2026-10-20 | 1-min RTH | 1-min | index, **stale opens** | **PROXY only**, never treated as SPY |
| B stocks | — | — | | | | | | **blocked**: no survivorship-free universe with corporate actions |
| C futures | **MES** | pinned HF `MES_full_1min_continuous_absolute_adjusted_*` | 2019-05-05 17:00 | 2026-10-20 20:44 | 2,627,538 minutes | **1-min** | continuous, additive back-adjusted; rolls emulated | **used (MTF study)** |
| C futures | MNQ | pinned HF | 2022-01 | 2025-09 | | 1-min | 43,701 duplicate timestamps, no volume | not used |
| C futures | ES (Databento-style) | pinned HF | 2020-11 | 2024-07 | | 1-min | unadjusted, large holes | cross-check only |
| D FX / gold | EURUSD etc., XAUUSD spot | — | | | | | | **blocked**: no bid/ask history; GLD (ETF) ≠ spot gold ≠ gold futures |

## 2. Genuine timeframe availability

| Instrument | 5m | 15m | 1h | 4h | daily | weekly |
|---|---|---|---|---|---|---|
| SPY, QQQ and the other ETFs | **blocked** | **blocked** | **blocked** | **blocked** | yes | derivable (completed weeks only) |
| MES | yes | yes | yes | yes | yes | yes |

Daily ETF candles are **never** resampled into intraday observations. Intraday multi-timeframe research
is therefore done on MES only (`docs/MTF_RESULTS.md`). ETF intraday MTF work stays blocked until genuine
intraday ETF data (with executable prices) is supplied.

## 3. Price-basis contract (ETFs)

`swingtrader/etf/data.py`:

* `open/high/low/close` are **executable** prices (split-adjusted share units, never dividend-adjusted).
  Every fill, stop, target and mark uses them.
* `adj_factor` = total-return factor; `signal_view()` multiplies OHLC by it for indicators/signals only,
  so ex-dividend drops are not mistaken for price moves (`test_ex_dividend_drop_is_not_a_gap_signal`).
* `dividend` = cash per share on the ex-date: credited to longs and debited to shorts held over the previous
  close (`test_fills_use_raw_prices_and_dividends_are_credited`, `test_short_pays_dividend_and_borrow`).
* Signal distances (ATR stops, breakout levels) are converted from adjusted to raw units with the factor of
  the signal session.

### Audit findings on the inputs
* **Bug fixed:** the previous loader multiplied OHLC by `Adj Close / Close`, so every fill, stop and target
  of rounds 1–4 happened at dividend-adjusted prices that never traded.
* SPY's `Adj Close` has 2 decimals; the factor derived from it carries ±4·10⁻⁴ noise (799 spurious "jumps").
  The factor is rebuilt exactly from the dividend column; the largest relative difference to the file's
  own Adj Close is 0.30 % (early 1990s, cumulative rounding).
* QQQ's upload contains adjusted prices only. Executable prices were rebuilt from the dividend history
  (Alpha Vantage DIVIDENDS, saved in `data/meta/QQQ_dividends_alphavantage.json`). Check against
  independent raw quotes: **max error 0.00013 %** over 82 sessions (Alpha Vantage, 2026-06-03 → 09-29);
  exact against the Kaggle raw closes for 2021–2022.
* **Kaggle defect found:** `liewyousheng/historical-etf` is missing QQQ's 2020-09-21 dividend (0.388),
  so its adjusted series is off by ~0.14 % before that date. Its other files may carry similar gaps.
* TLT (Kaggle bonds set) has no adjustment and no dividends: its total return is understated by roughly
  the coupon yield; it is used for the market matrix only.

## 4. MES 1-minute data (intraday MTF)

* Timestamps: naive US/Central, bar start; sessions 17:00 CT → 16:00 CT, daily maintenance break 16:00–17:00.
* Daylight saving: switches happen at 02:00 on Sundays while CME is closed — no duplicated or missing
  minutes around 2019–2026 DST dates (checked; `test_dst_weeks_have_regular_sessions`).
* No duplicate timestamps. Holidays/early closes appear as missing or short sessions (e.g. Thanksgiving
  2023 closes 12:14 CT, Christmas 2023 reopens 17:00 CT); the bar builder never fabricates a bucket.
* Phase-1 quality report: `results/DATA_QUALITY.md` (pinned sha256, sessions, holes, roll inference).

## 5. Cost assumptions (visible, unchanged during the audit)

| Market | Commission | Slippage | Stops | Other |
|---|---|---|---|---|
| ETFs (`config/etf.yaml`) | $0.005/share | 1 bp per side (3 bp SLV/USO/XLE/SMH/EEM) | +2 bp | borrow 30 bp/yr on shorts; dividends paid on shorts |
| MES (`config/default.yaml`) | $0.62 + $0.38 fees per side | 1 tick market | 2 ticks | +1 tick on gaps; roll = 2 legs fees + 1 tick each |

Stress multiples 2× and 3× scale every cost line.

## 6. Commands

```bash
python scripts/rebuild_qqq_raw.py                      # executable QQQ from the adjusted upload
python scripts/import_kaggle_etfs.py <unzipped_dir>    # Kaggle ETFs -> data/raw/etf_full
.venv/bin/python -m swingtrader download && .venv/bin/python -m swingtrader data   # pinned files + phase-1 report (use .venv: needs the calendar library)
python -m swingtrader etf audit --source full          # results/etf/audit_full.json
```

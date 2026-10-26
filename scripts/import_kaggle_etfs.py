"""Convert the Kaggle ETF downloads into data/raw/etf_full/<SYM>.csv (+ provenance.json).

Sources (downloaded 2026-10-26, unzipped by hand into one directory passed as argv[1]):
  liewyousheng/historical-etf      etf/<SYM>.csv   Yahoo OHLC + Adj Close, ends 2022-08-08
  jacksoncrow/stock-market-dataset etfs/<SYM>.csv  Yahoo OHLC + Adj Close, ends 2020-04-01
  kornilovag94/etfs-bonds-market-dataset TLT_data.csv  Bloomberg PX_*, UNADJUSTED, ends 2024-08-19
SPY and QQQ come from the user's own uploads and are never overwritten here.
"""

import json
import sys
from pathlib import Path

import pandas as pd

SRC = Path(sys.argv[1])
OUT = Path("data/raw/etf_full")
LIEW = ["DIA", "GLD", "XLE", "XLF", "XLK", "SMH"]
JACK = ["IEF", "SLV", "USO", "EFA", "EEM", "IWM"]
prov = json.loads((OUT / "provenance.json").read_text()) if (OUT / "provenance.json").exists() else {}
prov.setdefault("SPY", "user upload spy-historical.csv (dividend-adjusted via Adj Close)")
prov.setdefault("QQQ", "user upload qqq_daily_clean.csv (adjusted)")

for s in LIEW:
    pd.read_csv(SRC / "etf" / f"{s}.csv").dropna().to_csv(OUT / f"{s}.csv", index=False)
    prov[s] = "kaggle liewyousheng/historical-etf (Adj Close), ends 2022-08-08"
for s in JACK:
    pd.read_csv(SRC / "etfs" / f"{s}.csv").dropna().to_csv(OUT / f"{s}.csv", index=False)
    prov[s] = "kaggle jacksoncrow/stock-market-dataset (Adj Close), ends 2020-04-01: TRAIN ONLY"
t = pd.read_csv(SRC / "TLT_data.csv", sep=";", decimal=",", na_values=["#N/A N/A"]).dropna(subset=["Date"])
t = pd.DataFrame({"date": pd.to_datetime(t["Date"], format="%d.%m.%Y"), "open": t["PX_OPEN"], "high": t["PX_HIGH"],
                  "low": t["PX_LOW"], "close": t["PX_LAST"], "volume": t["PX_VOLUME"]}).dropna()
t.to_csv(OUT / "TLT.csv", index=False)
prov["TLT"] = "kaggle kornilovag94/etfs-bonds-market-dataset, UNADJUSTED (monthly dividends show as small gaps), ends 2024-08-19"
(OUT / "provenance.json").write_text(json.dumps(prov, indent=1))
print(json.dumps(prov, indent=1))

"""Rebuild executable (unadjusted) QQQ prices from the user's dividend-adjusted file.

    python scripts/rebuild_qqq_raw.py

Inputs : data/raw/etf_user/QQQ_user_adjusted.csv           (user upload, adjusted OHLC)
         data/meta/QQQ_dividends_alphavantage.json  (Alpha Vantage DIVIDENDS, 2026-10-26)
Output : data/raw/etf_full/QQQ.csv  (open/high/low/close raw, adj close, dividend, volume)
Checks : printed max error vs Alpha Vantage raw closes (data/raw/etf_av/QQQ.csv) when present.
"""

import json
from pathlib import Path

import pandas as pd

from swingtrader.etf.data import raw_from_adjusted

adj = pd.read_csv("data/raw/etf_user/QQQ_user_adjusted.csv", parse_dates=["date"]).set_index("date")
d = pd.DataFrame(json.loads(Path("data/meta/QQQ_dividends_alphavantage.json").read_text())["data"])
div = pd.Series(d["amount"].astype(float).to_numpy(), index=pd.to_datetime(d["ex_dividend_date"])).sort_index()
raw = raw_from_adjusted(adj, div)
raw.index.name = "date"
raw.to_csv("data/raw/etf_full/QQQ.csv")
av = Path("data/raw/etf_av/QQQ.csv")
if av.exists():
    a = pd.read_csv(av, parse_dates=["date"]).set_index("date")["close"]
    j = pd.concat([raw["close"], a], axis=1, keys=["rebuilt", "av"]).dropna()
    print(f"vs Alpha Vantage raw closes: {len(j)} sessions, max |err| {100 * (j.rebuilt / j.av - 1).abs().max():.5f}%")
print(f"wrote data/raw/etf_full/QQQ.csv ({len(raw)} sessions, {int((raw.dividend > 0).sum())} ex-dates)")

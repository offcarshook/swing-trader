"""ETF daily bars: Alpha Vantage fetcher, CSV cache, coverage audit, SPX daily proxy.

Alpha Vantage free keys return only the latest ~100 sessions (`outputsize=full` is a
premium feature) and allow ~25 requests/day at <=1 request/second. The fetcher records
exactly what it got; nothing downstream pretends a 100-bar file is a 20-year history.
"""

from __future__ import annotations

import io
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

BASKET = ["SPY", "QQQ", "IWM", "DIA", "TLT", "IEF", "GLD", "SLV", "USO",
          "XLE", "XLF", "XLK", "SMH", "EFA", "EEM"]
AV_URL = "https://www.alphavantage.co/query"
COLS = ["open", "high", "low", "close", "volume"]


def fetch_alphavantage(symbol: str, outputsize: str = "compact", timeout: int = 30) -> tuple[pd.DataFrame, str]:
    """Return (bars, note). bars is empty when the API answered with a message instead of data."""
    # The session proxy injects the real key; the env var is used when it is set.
    key = os.environ.get("ALPHAVANTAGE_API_KEY") or "INJECTED_BY_PROXY"
    q = urllib.parse.urlencode({"function": "TIME_SERIES_DAILY", "symbol": symbol,
                                "outputsize": outputsize, "datatype": "csv", "apikey": key})
    with urllib.request.urlopen(f"{AV_URL}?{q}", timeout=timeout) as r:
        body = r.read().decode()
    if not body.startswith("timestamp"):
        try:
            msg = next(iter(json.loads(body).values()))
        except Exception:  # noqa: BLE001
            msg = body[:200]
        return pd.DataFrame(columns=COLS), str(msg)
    df = parse_csv(io.StringIO(body))
    return df, "ok" if len(df) else "empty (rate limited?)"


def parse_csv(src) -> pd.DataFrame:
    df = pd.read_csv(src)
    df.columns = [c.strip().lower() for c in df.columns]
    date_col = next(c for c in ("timestamp", "date", "datetime") if c in df.columns)
    df.index = pd.to_datetime(df.pop(date_col)).dt.tz_localize(None).dt.normalize()
    df.index.name = "date"
    if "adjusted close" in df.columns or "adj close" in df.columns:
        # scale OHLC by the adjustment ratio so splits/dividends don't create fake gaps
        adj = df.get("adjusted close", df.get("adj close"))
        ratio = adj / df["close"]
        for c in ("open", "high", "low", "close"):
            df[c] = df[c] * ratio
    if "volume" not in df.columns:
        df["volume"] = 0
    df = df[COLS].astype(float).sort_index()[lambda d: ~d.index.duplicated()]
    # snap float-rounding noise (adjusted prices) so high/low always contain open/close
    oc_max, oc_min = df[["open", "close"]].max(axis=1), df[["open", "close"]].min(axis=1)
    tiny = 1e-6 * df["close"].abs()
    df.loc[(df["high"] < oc_max) & (oc_max - df["high"] <= tiny), "high"] = oc_max
    df.loc[(df["low"] > oc_min) & (df["low"] - oc_min <= tiny), "low"] = oc_min
    return df


def fetch_basket(out_dir: Path, symbols=BASKET, outputsize: str = "compact", pause: float = 2.0,
                 skip_existing: bool = True) -> dict:
    """Fetch each ETF once; files already on disk are kept (the free quota is ~25 calls/day)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / "fetch_log.json"
    log = json.loads(log_path.read_text()) if log_path.exists() else {}
    first = True
    for s in symbols:
        if skip_existing and (out_dir / f"{s}.csv").exists():
            continue
        if not first:
            time.sleep(pause)
        first = False
        df, note = fetch_alphavantage(s, outputsize)
        if len(df):
            df.to_csv(out_dir / f"{s}.csv")
        log[s] = {"rows": len(df), "first": str(df.index.min().date()) if len(df) else None,
                  "last": str(df.index.max().date()) if len(df) else None, "note": note}
    log_path.write_text(json.dumps(log, indent=1))
    return log


def load_basket(data_dir: Path, symbols=BASKET) -> dict[str, pd.DataFrame]:
    """Load whatever CSVs exist (Alpha Vantage format or any date/OHLCV CSV)."""
    return {s: parse_csv(data_dir / f"{s}.csv") for s in symbols if (data_dir / f"{s}.csv").exists()}


def audit(basket: dict[str, pd.DataFrame], min_years: float = 8.0) -> dict:
    """Per-symbol coverage; `usable` means enough history for train + final test."""
    out = {}
    for s, df in basket.items():
        bad = int(((df["high"] < df[["open", "close"]].max(axis=1)) |
                   (df["low"] > df[["open", "close"]].min(axis=1)) | (df[COLS[:4]] <= 0).any(axis=1)).sum())
        gaps = df.index.to_series().diff().dt.days
        years = (df.index.max() - df.index.min()).days / 365.25 if len(df) else 0.0
        out[s] = {"rows": len(df), "first": str(df.index.min().date()), "last": str(df.index.max().date()),
                  "years": round(years, 2), "bad_ohlc_rows": bad,
                  "max_calendar_gap_days": int(gaps.max()) if len(df) > 1 else None,
                  "usable": years >= min_years and bad == 0}
    return out


def spx_daily_proxy(raw_dir: Path) -> pd.DataFrame:
    """Daily RTH OHLC of the S&P 500 cash index from the pinned 1-min file (SPY proxy:
    no dividends, no tradable instrument, so results are indicative only)."""
    from swingtrader.data.loaders import load_spx_1m
    m = load_spx_1m(raw_dir)
    idx = m.index.tz_localize(None) if m.index.tz is not None else m.index
    g = m.groupby(idx.normalize())
    d = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                      "close": g["close"].last(), "volume": 0.0, "bars": g.size()})
    d = d[d["bars"] >= 300].drop(columns="bars")  # drop half days / holes, same rule as the core pipeline
    d.index.name = "date"
    return d

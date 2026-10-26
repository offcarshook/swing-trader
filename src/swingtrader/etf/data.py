"""ETF daily bars: Alpha Vantage fetcher, CSV cache, coverage audit, SPX daily proxy.

Alpha Vantage free keys return only the latest ~100 sessions (`outputsize=full` is a
premium feature) and allow ~25 requests/day at <=1 request/second. The fetcher records
exactly what it got; nothing downstream pretends a 100-bar file is a 20-year history.

Price-basis contract (docs/DATA_AUDIT.md):
  open/high/low/close  EXECUTABLE prices (split-adjusted share units, NOT dividend-adjusted).
                       Every fill, stop, target and mark uses these.
  adj_factor           total-return factor, adj_close / close (1.0 = no dividend adjustment).
                       Signals/indicators use open/high/low/close * adj_factor (`signal_view`)
                       so ex-dividend drops do not look like price moves.
  dividend             cash per share on the ex-date (credited to longs, debited to shorts).
A file with an `Adj Close` but no dividend column has its dividends inferred from the factor
jumps; a file with neither is flagged `unadjusted` (its total return is understated).
"""

from __future__ import annotations

import io
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

BASKET = ["SPY", "QQQ", "IWM", "DIA", "TLT", "IEF", "GLD", "SLV", "USO",
          "XLE", "XLF", "XLK", "SMH", "EFA", "EEM"]
AV_URL = "https://www.alphavantage.co/query"
COLS = ["open", "high", "low", "close", "volume"]
OUT_COLS = COLS + ["adj_factor", "dividend"]
FACTOR_JUMP = 1e-4  # relative factor change treated as an ex-dividend event (rounding noise is ~1e-6)


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
    """Read any date/OHLC[V] CSV into the price-basis contract above (index = session date)."""
    df = pd.read_csv(src)
    df.columns = [c.strip().lower() for c in df.columns]
    date_col = next(c for c in ("timestamp", "date", "datetime") if c in df.columns)
    df.index = pd.to_datetime(df.pop(date_col)).dt.tz_localize(None).dt.normalize()
    df.index.name = "date"
    df = df.sort_index()[lambda d: ~d.index.duplicated()]
    if "volume" not in df.columns:
        df["volume"] = 0
    adj = df.get("adjusted close", df.get("adj close"))
    if adj is not None:
        df["adj_factor"] = (adj / df["close"]).astype(float)
        basis = "raw OHLC + adj close"
    else:
        df["adj_factor"] = 1.0
        basis = "unadjusted (no dividend information)"
    if "dividend" in df.columns:
        df["dividend"] = df["dividend"].fillna(0.0).astype(float)
        exact = factor_from_dividends(df["close"].astype(float), df["dividend"])
        if adj is not None:
            df.attrs["adj_close_vs_dividend_factor_max_rel_diff"] = float((df["adj_factor"] / exact - 1).abs().max())
        df["adj_factor"] = exact  # exact factor; a 2-decimal Adj Close carries ~4e-4 rounding noise
        basis = "raw OHLC + dividend column (factor rebuilt from dividends)"
    elif adj is not None:
        f = df["adj_factor"]
        ratio = (f.shift(1) / f).fillna(1.0)          # = 1 - D / close_prev on an ex-date
        df["dividend"] = (df["close"].shift(1) * (1 - ratio)).where((ratio - 1).abs() > FACTOR_JUMP, 0.0).fillna(0.0)
        basis += " (dividends inferred from factor jumps)"
    else:
        df["dividend"] = 0.0
    df = df[OUT_COLS].astype(float)
    df.attrs["price_basis"] = basis
    # snap float-rounding noise so high/low always contain open/close
    oc_max, oc_min = df[["open", "close"]].max(axis=1), df[["open", "close"]].min(axis=1)
    tiny = 1e-6 * df["close"].abs()
    df.loc[(df["high"] < oc_max) & (oc_max - df["high"] <= tiny), "high"] = oc_max
    df.loc[(df["low"] > oc_min) & (df["low"] - oc_min <= tiny), "low"] = oc_min
    return df


def factor_from_dividends(close: pd.Series, dividend: pd.Series) -> pd.Series:
    """CRSP/Yahoo-style total-return factor: every session before an ex-date is multiplied by
    (1 - D / close of the session before the ex-date). Latest session has factor 1."""
    c, d = close.to_numpy(), dividend.to_numpy()
    f = np.ones(len(c))
    cur = 1.0
    for i in range(len(c) - 1, 0, -1):
        f[i] = cur
        if d[i] > 0 and c[i - 1] > 0:
            cur *= 1 - d[i] / c[i - 1]
    if len(c):
        f[0] = cur
    return pd.Series(f, index=close.index)


def raw_from_adjusted(adj: pd.DataFrame, dividends: pd.Series) -> pd.DataFrame:
    """Invert a total-return-adjusted OHLC file back to executable prices using the dividend
    history (inverse of `factor_from_dividends`, walked backwards from the last session).
    `dividends` is indexed by ex-date; ex-dates outside the file are ignored."""
    idx = adj.index
    pos = {d: i for i, d in enumerate(idx)}
    dmap = dividends[dividends.index.isin(idx)]
    f = np.ones(len(idx))
    cur, last = 1.0, len(idx)
    for e in sorted((pos[d] for d in dmap.index), reverse=True):
        f[e:last] = cur
        raw_prev = adj["close"].iloc[e - 1] / cur + float(dmap.loc[idx[e]])
        cur *= 1 - float(dmap.loc[idx[e]]) / raw_prev
        last = e
    f[:last] = cur
    out = adj[["open", "high", "low", "close"]].div(f, axis=0)
    out["adj close"] = adj["close"]
    out["volume"] = adj["volume"] if "volume" in adj else 0
    div = pd.Series(0.0, index=idx)
    div.loc[dmap.index] = dmap.to_numpy(dtype=float)
    out["dividend"] = div
    return out


def signal_view(df: pd.DataFrame) -> pd.DataFrame:
    """Total-return-adjusted OHLC for indicators/signals (never for fills)."""
    if "adj_factor" not in df.columns:
        return df
    f = df["adj_factor"]
    out = df.copy()
    for c in ("open", "high", "low", "close"):
        out[c] = df[c] * f
    return out


def coverage(bars: dict[str, pd.DataFrame], start=None, end=None) -> dict:
    """Exact per-instrument sample: first/last session and count inside [start, end]."""
    out = {}
    for s, b in bars.items():
        w = b.loc[pd.Timestamp(start) if start else None:pd.Timestamp(end) if end else None]
        out[s] = {"first": str(w.index.min().date()) if len(w) else None,
                  "last": str(w.index.max().date()) if len(w) else None, "sessions": int(len(w))}
    return out


def common_window(bars: dict[str, pd.DataFrame], start, end) -> tuple[str, str]:
    """Largest [start, end] sub-window in which EVERY instrument has data."""
    s = max([pd.Timestamp(start)] + [b.index.min() for b in bars.values()])
    e = min([pd.Timestamp(end)] + [b.index.max() for b in bars.values()])
    return str(s.date()), str(e.date())


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
        rec = {"rows": len(df), "first": str(df.index.min().date()), "last": str(df.index.max().date()),
               "years": round(years, 2), "bad_ohlc_rows": bad,
               "max_calendar_gap_days": int(gaps.max()) if len(df) > 1 else None,
               "price_basis": df.attrs.get("price_basis", "unknown"),
               "is_proxy": bool(df.attrs.get("proxy", False)),
               "usable": years >= min_years and bad == 0 and not df.attrs.get("proxy", False)}
        if "dividend" in df.columns:
            d = df["dividend"]
            rec["dividend_events"] = int((d > 0).sum())
            # consistency: an ex-date in the dividend column must coincide with a factor jump
            f = df["adj_factor"]
            jump = ((f.shift(1) / f) - 1).abs() > FACTOR_JUMP
            rec["dividends_without_factor_jump"] = int(((d > 0) & ~jump).sum())
            rec["factor_jumps_without_dividend"] = int((jump & ~(d > 0)).sum())
        out[s] = rec
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
    d["adj_factor"], d["dividend"] = 1.0, 0.0
    d.attrs["price_basis"] = "S&P 500 cash index (PROXY, not tradable, stale opens)"
    d.attrs["proxy"] = True
    return d

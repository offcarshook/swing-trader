"""End-to-end data build: raw pinned files -> validated session bars + quality report."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from swingtrader.config import resolve
from swingtrader.contracts import SPECS, roll_dates
from swingtrader.data import loaders, quality
from swingtrader.data.sessions import build_sessions
from swingtrader.data.sources import SOURCES, local_path, sha256_of


def processed_path(cfg: dict, name: str) -> Path:
    return resolve(cfg["data"]["processed_dir"]) / f"{name}.parquet"


def load_sessions(cfg: dict, name: str = "mes_sessions") -> pd.DataFrame:
    p = processed_path(cfg, name)
    if not p.exists():
        raise FileNotFoundError(f"{p} missing - run `swingtrader data` first")
    return pd.read_parquet(p)


def build_all(cfg: dict) -> dict:
    raw = resolve(cfg["data"]["raw_dir"])
    out_dir = resolve(cfg["data"]["processed_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    spec = SPECS["MES"]
    report: dict = {"sources": {}}

    for key, src in SOURCES.items():
        p = local_path(raw, src)
        report["sources"][key] = {
            "repo": src.repo, "revision": src.revision, "file": src.filename,
            "present": p.exists(),
            "sha256": sha256_of(p) if p.exists() else None,
            "pinned_sha256": src.sha256, "caveats": src.caveats,
        }

    # ---- MES (primary instrument) ----
    mes_raw = loaders.load_mes_1m(raw)
    mes, dropped = quality.drop_out_of_hours(mes_raw)
    report["mes_minute"] = quality.minute_report(mes, spec.tick_size)
    report["mes_minute"]["out_of_hours"] = dropped
    sess = build_sessions(mes)
    sess["short_session"] = sess["n_rth_bars"] < cfg["data"]["min_session_minutes"]
    report["mes_sessions"] = quality.session_report(sess, cfg["data"]["min_session_minutes"])
    sess.to_parquet(processed_path(cfg, "mes_sessions"))

    # ---- independent cross-check 1: unadjusted ES (different vendor format) ----
    es = loaders.load_es_databento_1m(raw)
    es, es_drop = quality.drop_out_of_hours(es)
    offsets = quality.infer_roll_offsets(mes, es)
    audit = quality.roll_audit(offsets, spec.tick_size)
    calendar = roll_dates(offsets.index.min().date(), offsets.index.max().date(), spec)
    audit["calendar_roll_dates_in_window"] = [str(d) for d in calendar]
    report["roll_audit_vs_es"] = audit
    es_sess = build_sessions(es[["open", "high", "low", "close", "volume"]])
    change_days = pd.DatetimeIndex([pd.Timestamp(c["date"]) for c in audit["offset_changes"]])
    # exclude the day of and after each offset change (one of the two series rolled)
    excl = change_days.union(change_days + pd.offsets.BDay(1))
    da, db = quality.aligned_changes(sess["rth_close"], es_sess["rth_close"], sess.index)
    report["crosscheck_mes_vs_es_points"] = quality.return_crosscheck(
        da, db, "daily RTH-close change, points (consecutive sessions only, roll days excluded)", excl)

    # ---- independent cross-check 2: S&P 500 cash index ----
    spx_raw = loaders.load_spx_1m(raw)
    report["spx_minute"] = quality.minute_report(spx_raw, 0.01)
    spx = build_sessions(spx_raw, rth_only_source=True)
    report["spx_sessions"] = quality.session_report(spx, 300, calendar="NYSE")
    spx.to_parquet(processed_path(cfg, "spx_sessions"))
    da, db = quality.aligned_changes(sess["rth_close"], spx["close"], sess.index, pct_of=spx["close"])
    report["crosscheck_mes_vs_spx_pct"] = quality.return_crosscheck(
        da, db, "daily RTH-close change, % of SPX level (consecutive sessions only)")

    # ---- VIX (regime context only) ----
    vix = loaders.load_vix_daily(raw)
    vix.to_parquet(processed_path(cfg, "vix_daily"))
    report["vix"] = {"rows": int(len(vix)), "first": str(vix.index.min().date()), "last": str(vix.index.max().date())}

    # ---- MNQ (instrument audit only) ----
    mnq = loaders.load_mnq_1m(raw)
    mnq, _ = quality.drop_out_of_hours(mnq)
    mnq_sess = build_sessions(mnq)
    report["mnq_audit"] = {
        **quality.minute_report(mnq, 0.25),
        "has_volume": "volume" in mnq.columns,
        "sessions": int(len(mnq_sess)),
        "first": str(mnq_sess.index.min().date()),
        "last": str(mnq_sess.index.max().date()),
        "median_bars_per_session": float(mnq_sess["n_bars"].median()),
    }
    report["es_audit"] = {
        **quality.minute_report(es, 0.25),
        "sessions": int(len(es_sess)),
        "first": str(es_sess.index.min().date()),
        "last": str(es_sess.index.max().date()),
        "largest_calendar_holes_days": _largest_holes(es_sess.index),
        "out_of_hours": es_drop,
    }
    report["mes_audit"] = {"largest_calendar_holes_days": _largest_holes(sess.index)}

    res = resolve("results")
    res.mkdir(exist_ok=True)
    (res / "data_quality.json").write_text(json.dumps(report, indent=2, default=str))
    return report


def _largest_holes(idx: pd.DatetimeIndex, n: int = 6) -> list[dict]:
    gaps = pd.Series(idx[1:] - idx[:-1], index=idx[1:]).dt.days
    top = gaps.sort_values(ascending=False).head(n)
    return [{"after": str((d - pd.Timedelta(days=int(g))).date()), "resume": str(d.date()), "days": int(g)}
            for d, g in top.items()]

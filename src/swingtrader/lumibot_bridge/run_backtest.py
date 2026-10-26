"""Run a candidate through LumiBot's PandasDataBacktesting and compare with the internal engine."""

from __future__ import annotations

import json
import logging
import os

import pandas as pd

from swingtrader.backtest.metrics import summarize
from swingtrader.backtest.runner import run_candidate
from swingtrader.config import resolve
from swingtrader.data.pipeline import load_sessions


def lumibot_frame(sessions: pd.DataFrame) -> pd.DataFrame:
    """Daily bars for LumiBot: stamped at the session date (00:00 New York), open = RTH open."""
    df = pd.DataFrame({"open": sessions["rth_open"], "high": sessions["high"], "low": sessions["low"],
                       "close": sessions["close"], "volume": sessions.get("volume", 0)})
    df.index = pd.DatetimeIndex(sessions.index).tz_localize("America/New_York")
    df.index.name = "datetime"
    return df


def lumibot_fee_per_contract(cfg: dict) -> float:
    c, tick_value = cfg["costs"], 1.25
    slip_ticks = (c["market_slippage_ticks"] + c["stop_slippage_ticks"]) / 2  # blended market/stop
    return (c["commission_per_side"] + c["exchange_fees_per_side"] + slip_ticks * tick_value) * c.get("cost_multiplier", 1.0)


def _candidate(cfg, family, params_json):
    if family and params_json:
        return family, json.loads(params_json)
    for name in ("promotion.json", "train_selection.json"):
        p = resolve("results") / name
        if p.exists():
            d = json.loads(p.read_text())
            if name == "promotion.json":
                return d["family"], d["params"]
            c = d.get("selected") or d.get("top_ranked_if_none_passed")
            return c["family"], c["params"]
    raise SystemExit("no candidate: run `swingtrader select` or pass --family/--params")


def run_lumibot_backtest(cfg: dict, start=None, end=None, family=None, params_json=None) -> dict:
    os.environ.setdefault("IS_BACKTESTING", "True")
    from lumibot.backtesting import PandasDataBacktesting
    from lumibot.entities import Data, TradingFee

    from swingtrader.lumibot_bridge.strategy import SwingFuturesLumibot, mes_asset

    logging.getLogger("lumibot").setLevel(logging.ERROR)
    family, params = _candidate(cfg, family, params_json)
    sessions = load_sessions(cfg)
    # Default = MES training window. The holdout may only be replayed in LumiBot AFTER
    # the one-shot holdout evaluation has been registered (no peeking via a second engine).
    if start is None:
        start = pd.Timestamp(cfg["splits"]["train_start"]) + pd.Timedelta(days=200)  # after warm-up
        end = end or cfg["splits"]["train_end"]
    start = pd.Timestamp(start)
    end = pd.Timestamp(end) if end else sessions.index[-1]
    if end >= pd.Timestamp(cfg["splits"]["holdout_start"]):
        from swingtrader.research.experiments import HoldoutGuard
        if not HoldoutGuard().history():
            raise SystemExit("refusing to run LumiBot on holdout dates before `swingtrader holdout` has run")
    asset = mes_asset()
    data = {asset: Data(asset, lumibot_frame(sessions), timestep="day")}
    fee = TradingFee(per_contract_fee=lumibot_fee_per_contract(cfg))
    log_rows: list[dict] = []
    log_dir = resolve("results/lumibot_logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    cwd = os.getcwd()
    os.chdir(log_dir)  # LumiBot writes its own artefacts into ./logs
    try:
        result, strat = SwingFuturesLumibot.run_backtest(
            PandasDataBacktesting, start.to_pydatetime(), end.to_pydatetime(), pandas_data=data,
            budget=cfg["account"]["starting_equity"], benchmark_asset=None, risk_free_rate=0.0,
            buy_trading_fees=[fee], sell_trading_fees=[fee],
            parameters={"cfg": cfg, "family": family, "params": params, "asset": asset, "trade_log": log_rows},
            show_plot=False, show_tearsheet=False, save_tearsheet=False, show_indicators=False,
            show_progress_bar=False, save_logfile=False, quiet_logs=True, save_stats_file=False)
    finally:
        os.chdir(cwd)

    lb_equity = None
    df = getattr(strat, "_strategy_returns_df", None)
    if isinstance(df, pd.DataFrame) and "portfolio_value" in df:
        lb_equity = df["portfolio_value"].astype(float)
        lb_equity.index = pd.DatetimeIndex(lb_equity.index).tz_localize(None).normalize()
        lb_equity = lb_equity.groupby(level=0).last()

    internal = run_candidate(cfg, sessions, family, params, start, end)
    ilog = pd.DataFrame(log_rows)
    fills = ilog[ilog["event"] == "fill"] if not ilog.empty else ilog
    entries_lb = ilog[ilog["event"] == "entry_signal"] if not ilog.empty else ilog
    out = {
        "candidate": {"family": family, "params": params},
        "window": [str(start.date()), str(end.date())],
        "lumibot_version": __import__("lumibot").__version__,
        "lumibot_fee_per_contract_side": round(lumibot_fee_per_contract(cfg), 4),
        "lumibot": {
            "final_equity": float(lb_equity.iloc[-1]) if lb_equity is not None else None,
            "net_return_pct": round((float(lb_equity.iloc[-1]) / cfg["account"]["starting_equity"] - 1) * 100, 2)
            if lb_equity is not None else None,
            "max_drawdown_pct": round(float(-(lb_equity / lb_equity.cummax() - 1).min() * 100), 2)
            if lb_equity is not None else None,
            "entry_signals": int(len(entries_lb)),
            "fills": int(len(fills)),
            "rolls": int((ilog["event"] == "roll").sum()) if not ilog.empty else 0,
            "lumibot_reported": {k: (float(v) if isinstance(v, (int, float)) else str(v))
                                 for k, v in (result or {}).items()} if isinstance(result, dict) else str(result),
        },
        "internal_engine": {k: v for k, v in summarize(internal.equity, internal.trades, internal.start_equity,
                                                       internal.in_market).items() if k != "exit_reasons"},
    }
    if not internal.trades.empty and not entries_lb.empty:
        # LumiBot logs the iteration date D at which it decides with bars < D; its order
        # fills at D's RTH open -- the same session the internal engine records as entry_date.
        ie = set(pd.to_datetime(internal.trades["entry_date"]).dt.date)
        le = set(pd.to_datetime(entries_lb["date"]).dt.date)
        out["parity"] = {
            "internal_entries": len(ie), "lumibot_entries": len(le),
            "matching_entry_sessions": len(ie & le),
            "only_internal": sorted(map(str, ie - le))[:20], "only_lumibot": sorted(map(str, le - ie))[:20],
        }
    if lb_equity is not None:
        j = pd.concat({"lumibot": lb_equity, "internal": internal.equity}, axis=1).dropna()
        if not j.empty:
            out["parity_equity"] = {"days_compared": int(len(j)),
                                    "corr_daily_changes": round(float(j.diff().corr().iloc[0, 1]), 4),
                                    # LumiBot's daily snapshot can lag the session close by one bar
                                    "corr_daily_changes_lb_lag1": round(float(
                                        j["lumibot"].diff().shift(-1).corr(j["internal"].diff())), 4),
                                    "final_diff_usd": round(float(j["lumibot"].iloc[-1] - j["internal"].iloc[-1]), 2)}
    res_dir = resolve("results")
    tag = f"{start.date()}_{end.date()}"
    (res_dir / f"lumibot_backtest_{tag}.json").write_text(json.dumps(out, indent=1, default=str))
    if not ilog.empty:
        ilog.to_csv(res_dir / f"lumibot_events_{tag}.csv", index=False)
    out["written"] = f"results/lumibot_backtest_{tag}.json"
    return out

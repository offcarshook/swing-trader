"""Run the ETF book through Lumibot's PandasDataBacktesting and compare with the reference engine.

    .venv/bin/python -m swingtrader lumibot-etf --start 2021-01-04 --end 2025-09-11

Lumibot owns order handling and accounting in this run; the reference engine (etf/engine.py) is
the independent implementation it is compared with (exec_style="lumibot" mirrors Lumibot's order
timing, exec_style="reference" is the research engine's own timing).
"""

from __future__ import annotations

import logging
import os

import pandas as pd


def run_etf_lumibot(bars: dict[str, pd.DataFrame], params: list[dict], risk: dict, start, end,
                    cost_mult: float = 1.0, entry_filter=None, log_dir: str | None = None,
                    orders_switch_file: str | None = None, extra_parameters: dict | None = None) -> dict:
    os.environ.setdefault("IS_BACKTESTING", "True")
    from lumibot.backtesting import PandasDataBacktesting
    from lumibot.entities import Asset, Data, TradingFee

    from swingtrader.lumibot_bridge.etf_strategy import EtfSwingLumibot, lumibot_frame

    logging.getLogger("lumibot").setLevel(logging.ERROR)
    data = {}
    for s, b in bars.items():
        a = Asset(s, asset_type=Asset.AssetType.STOCK)
        data[a] = Data(a, lumibot_frame(b), timestep="day")
    fee = TradingFee(percent_fee=risk.get("slip_bps", 0.0) * cost_mult / 1e4,
                     per_contract_fee=risk.get("commission_per_share", 0.0) * cost_mult)
    ledger: list[dict] = []
    cwd = os.getcwd()
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
        os.chdir(log_dir)
    try:
        result, strat = EtfSwingLumibot.run_backtest(
            PandasDataBacktesting, pd.Timestamp(start).to_pydatetime(), pd.Timestamp(end).to_pydatetime(),
            pandas_data=data, budget=risk.get("equity", 100_000.0), benchmark_asset=None, risk_free_rate=0.0,
            buy_trading_fees=[fee], sell_trading_fees=[fee],
            parameters={"params": params, "risk": risk, "signal_bars": bars, "ledger": ledger,
                        "entry_filter": entry_filter, "orders_switch_file": orders_switch_file,
                        **(extra_parameters or {})},
            show_plot=False, show_tearsheet=False, save_tearsheet=False, show_indicators=False,
            show_progress_bar=False, save_logfile=False, quiet_logs=True, save_stats_file=False)
    finally:
        os.chdir(cwd)
    eq = None
    df = getattr(strat, "_strategy_returns_df", None)
    if isinstance(df, pd.DataFrame) and "portfolio_value" in df:
        eq = df["portfolio_value"].astype(float)
        eq.index = pd.DatetimeIndex(eq.index).tz_localize(None).normalize()
        eq = eq.groupby(level=0).last()
    led = pd.DataFrame(ledger)
    trades = led[led.event == "trade_closed"].copy() if len(led) else pd.DataFrame()
    import lumibot
    return {"lumibot_version": lumibot.__version__, "ledger": led, "trades": trades, "equity": eq,
            "final_value": float(eq.iloc[-1]) if eq is not None and len(eq) else None,
            "cash": float(strat.get_cash()), "book_open": dict(strat.book)}

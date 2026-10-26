"""Paper trading for the ETF book through Lumibot (paper / simulated brokers ONLY).

    .venv/bin/python -m swingtrader etf-paper --dry-run [--sessions 120]   # simulated broker, offline
    .venv/bin/python -m swingtrader etf-paper --broker                     # needs PAPER credentials

* `--broker` connects Lumibot to a PAPER account only: Alpaca with ALPACA_IS_PAPER=true, or an
  Interactive Brokers paper gateway (ports 7497 / 4002). Anything else is refused. Live trading
  does not exist in this project (swingtrader.LIVE_TRADING_ENABLED is a hard-coded False).
* `--dry-run` runs the SAME strategy class, risk gate, order guard, state file, heartbeat, kill
  switch and global order switch against Lumibot's simulated broker over the most recent common
  window of real data. It is labelled SIMULATED BROKER DRY RUN everywhere: no broker is contacted.
State lives in state/etf_paper/ (gitignored): orders.json (OrderGuard), book.json (restart
recovery), heartbeat.txt, journal.jsonl (UTC + America/New_York timestamps).
"""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

import pandas as pd

import swingtrader
from swingtrader.config import load_config, resolve

STATE = "state/etf_paper"


def paper_broker_from_env() -> tuple[str | None, str]:
    if os.environ.get("ALPACA_API_KEY") and os.environ.get("ALPACA_API_SECRET"):
        if os.environ.get("ALPACA_IS_PAPER", "").lower() != "true":
            return None, "ALPACA_IS_PAPER is not 'true' - refusing (live trading is disabled)"
        return "alpaca", "Alpaca paper"
    if os.environ.get("INTERACTIVE_BROKERS_PORT"):
        port = int(os.environ["INTERACTIVE_BROKERS_PORT"])
        if port not in (7497, 4002):
            return None, f"IB port {port} is not a paper port (7497/4002) - refusing"
        return "ib", "Interactive Brokers paper"
    return None, ("no paper-broker credentials (ALPACA_API_KEY/ALPACA_API_SECRET with ALPACA_IS_PAPER=true, "
                  "or an IB paper gateway on port 7497/4002)")


def _book() -> tuple[dict, list[dict], dict]:
    from swingtrader.etf.data import load_basket
    from swingtrader.lumibot_bridge.etf_strategy import lumibot_supported
    ecfg = load_config(resolve("config/etf.yaml"))
    sel = json.loads((resolve("results/etf/study") / "train_selection_corrected.json").read_text())
    params, _ = lumibot_supported(sel["selected_params"])
    bars = load_basket(resolve(ecfg["data"]["full_dir"]), ["SPY", "QQQ"])
    return bars, params, {**ecfg["risk"], **ecfg["costs"]}


def _journal(state: Path, rec: dict) -> None:
    now = pd.Timestamp.now(tz="UTC")
    rec = {"ts_utc": now.isoformat(), "ts_new_york": now.tz_convert("America/New_York").isoformat(), **rec}
    with open(state / "journal.jsonl", "a") as fh:
        fh.write(json.dumps(rec, default=str) + "\n")


def run_etf_paper(dry_run: bool = True, sessions: int = 120, state_dir: str | None = None,
                  entry_filter=None) -> dict:
    assert swingtrader.LIVE_TRADING_ENABLED is False  # noqa: S101 - hard invariant
    state = resolve(state_dir or STATE)
    state.mkdir(parents=True, exist_ok=True)
    files = {"order_guard_file": state / "orders.json", "state_file": state / "book.json",
             "heartbeat_file": state / "heartbeat.txt", "kill_switch_file": state / "KILL_SWITCH",
             "orders_switch_file": state / "DISABLE_ORDERS"}
    bars, params, risk = _book()
    if not dry_run:
        name, reason = paper_broker_from_env()
        if name is None:
            out = {"status": "blocked", "mode": "paper-broker", "reason": reason}
            _journal(state, out)
            return out
        return _run_with_paper_broker(name, bars, params, risk, files)   # pragma: no cover - needs credentials
    from swingtrader.lumibot_bridge.etf_backtest import run_etf_lumibot
    end = min(b.index.max() for b in bars.values())
    cal = sorted(set().union(*[b.loc[:end].index for b in bars.values()]))
    start = cal[-sessions]
    res = run_etf_lumibot(bars, params, risk, start, end, entry_filter=entry_filter, log_dir=str(state / "lumibot"),
                          orders_switch_file=str(files["orders_switch_file"]),
                          extra_parameters={k: str(v) for k, v in files.items() if k != "orders_switch_file"})
    led = res["ledger"]
    led.to_csv(state / "ledger_last_dry_run.csv", index=False)
    ev = led.event.value_counts().to_dict() if len(led) else {}
    out = {"status": "ok", "mode": "SIMULATED BROKER DRY RUN (Lumibot backtesting broker; no broker contacted)",
           "window": [str(pd.Timestamp(start).date()), str(pd.Timestamp(end).date())],
           "lumibot_version": res["lumibot_version"], "events": ev,
           "closed_trades": int((led.event == "trade_closed").sum()) if len(led) else 0,
           "open_positions_at_end": list(res["book_open"]), "final_value": res["final_value"],
           "live_trading_enabled": swingtrader.LIVE_TRADING_ENABLED,
           "state_files": {k: str(v) for k, v in files.items()}}
    _journal(state, out)
    return out


def _run_with_paper_broker(name, bars, params, risk, files):   # pragma: no cover - needs credentials
    from lumibot.traders import Trader

    from swingtrader.lumibot_bridge.etf_strategy import EtfSwingLumibot
    if name == "alpaca":
        from lumibot.brokers import Alpaca
        broker = Alpaca({"API_KEY": os.environ["ALPACA_API_KEY"], "API_SECRET": os.environ["ALPACA_API_SECRET"],
                         "PAPER": True})
    else:
        from lumibot.brokers import InteractiveBrokers
        from lumibot.credentials import INTERACTIVE_BROKERS_CONFIG
        broker = InteractiveBrokers(INTERACTIVE_BROKERS_CONFIG)
    strat = EtfSwingLumibot(broker=broker, parameters={"params": params, "risk": risk, "signal_bars": bars,
                                                       "ledger": [], **{k: str(v) for k, v in files.items()}})
    trader = Trader()
    trader.add_strategy(strat)
    trader.run_all()
    return {"status": "stopped", "broker": name, "stopped_at": dt.datetime.now(dt.timezone.utc).isoformat()}

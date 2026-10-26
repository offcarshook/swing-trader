"""LumiBot paper-trading launcher (paper/demo accounts ONLY).

Not exercised in this repository's environment: no broker credentials exist and
the network policy blocks broker hosts. The function validates configuration and
refuses to start rather than pretending to trade. See docs/BLOCKERS.md.
"""

from __future__ import annotations

import os

import swingtrader


def paper_broker_from_env() -> tuple[str | None, str]:
    """Pick a supported paper broker from env; return (name, reason)."""
    if os.environ.get("TRADOVATE_USERNAME"):
        if os.environ.get("TRADOVATE_IS_PAPER", "true").lower() != "true":
            return None, "TRADOVATE_IS_PAPER is not 'true' - refusing (live trading is disabled)"
        return "tradovate", "Tradovate demo"
    if os.environ.get("INTERACTIVE_BROKERS_PORT"):
        port = int(os.environ["INTERACTIVE_BROKERS_PORT"])
        if port not in (7497, 4002):  # TWS paper / IB Gateway paper default ports
            return None, f"IB port {port} is not a paper port (7497/4002) - refusing"
        return "ib", "Interactive Brokers paper"
    return None, ("no paper-broker credentials (set TRADOVATE_* with TRADOVATE_IS_PAPER=true, or an IB paper "
                  "gateway on port 7497/4002)")


def run_lumibot_paper(cfg: dict, promo: dict) -> dict:
    if swingtrader.LIVE_TRADING_ENABLED:
        raise RuntimeError("invariant violated")
    name, reason = paper_broker_from_env()
    if name is None:
        return {"status": "blocked", "reason": reason}
    # Credentials exist: build the LumiBot runtime. Imports are deferred so the rest
    # of the project never needs broker SDKs.
    from lumibot.entities import Asset
    from lumibot.traders import Trader

    from swingtrader.lumibot_bridge.strategy import SwingFuturesLumibot
    if name == "tradovate":
        from lumibot.brokers import Tradovate
        from lumibot.credentials import TRADOVATE_CONFIG
        if not TRADOVATE_CONFIG.get("IS_PAPER", False):
            return {"status": "blocked", "reason": "Tradovate config not paper"}
        broker = Tradovate(TRADOVATE_CONFIG)
    else:
        from lumibot.brokers import InteractiveBrokers
        from lumibot.credentials import INTERACTIVE_BROKERS_CONFIG
        broker = InteractiveBrokers(INTERACTIVE_BROKERS_CONFIG)
    asset = Asset("MES", asset_type=Asset.AssetType.FUTURE, auto_expiry=Asset.AutoExpiry.FRONT_MONTH)
    strat = SwingFuturesLumibot(broker=broker, parameters={"cfg": cfg, "family": promo["family"],
                                                           "params": promo["params"], "asset": asset,
                                                           "trade_log": []})
    trader = Trader()
    trader.add_strategy(strat)
    trader.run_all()  # blocks; Ctrl+C -> LumiBot graceful shutdown
    return {"status": "stopped", "broker": reason}

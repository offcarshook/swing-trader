"""swingtrader: research-first, AI-assisted futures swing-trading system.

Deterministic Python owns data validation, signals, sizing, risk and accounting.
LumiBot is used for an independent backtest and the paper-trading runtime.
TradingAgents (separate environment) produces structured research that can at
most veto an entry -- it can never create, enlarge or keep open a position.
"""

__version__ = "0.1.0"

# Live order execution is not implemented and must stay off. Every order path
# checks this constant; there is deliberately no config switch that flips it.
LIVE_TRADING_ENABLED = False

"""LumiBot adapter: runs the SAME deterministic strategy + RiskManager inside LumiBot.

Verified LumiBot 4.6.30 behaviour this adapter depends on (see docs/LUMIBOT_NOTES.md):

* PandasDataBacktesting with daily bars stamped at the session date (00:00 NY):
  an order submitted during the iteration at date D is filled at the OPEN of the
  bar stamped D when the clock reaches D+1; stop orders are checked against that
  bar's open/high/low (gap -> fill at open).
* get_historical_prices() at iteration D ALSO returns the bar stamped D, i.e. a
  bar whose close is not yet known at the fill time. Using it would be a
  look-ahead. This adapter therefore drops every bar with index >= the current
  iteration date before computing signals (`completed_bars`).
* The bar fed to LumiBot uses `open = rth_open`, so market orders fill at the RTH
  open like the internal engine.
* Market/stop slippage is not modelled by LumiBot (its TradingSlippage applies to
  SMART_LIMIT only); it is folded into the per-contract fee instead.

The AI overlay is not consulted in backtests (LLM knowledge would leak the future).
"""

from __future__ import annotations

import datetime as dt
import math

import pandas as pd
from lumibot.entities import Asset
from lumibot.strategies import Strategy as LumiStrategy

from swingtrader.backtest.runner import components
from swingtrader.contracts import roll_dates
from swingtrader.strategies import make_strategy
from swingtrader.strategies.base import PositionView

HISTORY_BARS = 650  # >= vol lookback (252) + longest MA (200) + ATR seed decay


def completed_bars(df: pd.DataFrame, now) -> pd.DataFrame:
    """Only sessions that ended before the current iteration date (look-ahead guard)."""
    cutoff = pd.Timestamp(now)
    if df.index.tz is not None and cutoff.tz is None:
        cutoff = cutoff.tz_localize(df.index.tz)
    elif df.index.tz is not None:
        cutoff = cutoff.tz_convert(df.index.tz)
    return df[df.index < cutoff.normalize()]


def mes_asset() -> Asset:
    # Back-adjusted continuous series modelled as one long-dated contract; rolls are
    # emulated explicitly (close + reopen at the RTH open of the roll date).
    return Asset("MES", asset_type=Asset.AssetType.FUTURE, expiration=dt.date(2099, 12, 18), multiplier=5)


class SwingFuturesLumibot(LumiStrategy):
    parameters = {"cfg": None, "family": None, "params": None, "asset": None, "trade_log": None}

    def initialize(self):
        self.sleeptime = "1D"
        p = self.parameters
        self.cfg = p["cfg"]
        self.asset = p["asset"]
        self.core = make_strategy(p["family"], p["params"], self.cfg)
        self.spec, self.costs, self.risk = components(self.cfg)
        self.log_rows = p["trade_log"] if p["trade_log"] is not None else []
        self.state = None            # dict(side, entry_price, stop, bars_held, best_close, distance)
        self.stop_order = None
        self.pending_entry = None
        self.last_iter_date = None
        self.rolls = set()

    # ------------------------------------------------------------- helpers
    def _position_qty(self) -> int:
        pos = self.get_position(self.asset)
        return int(pos.quantity) if pos is not None and pos.quantity else 0

    def _submit_stop(self, qty: int, side: int, price: float):
        if self.stop_order is not None:
            self.cancel_order(self.stop_order)
        o = self.create_order(self.asset, abs(qty), "sell" if side > 0 else "buy", order_type="stop",
                              stop_price=float(price))
        self.stop_order = self.submit_order(o)

    # ---------------------------------------------------------- lifecycle
    def on_trading_iteration(self):
        now = self.get_datetime()
        today = pd.Timestamp(now).date()
        bars = self.get_historical_prices(self.asset, HISTORY_BARS, "day")
        if bars is None or bars.df is None or bars.df.empty:
            return  # data failure: do nothing new
        hist = completed_bars(bars.df, now)
        if len(hist) < self.core.warmup:
            return
        qty = self._position_qty()
        if qty == 0 and self.state is not None:
            self.state = None  # stopped out since last iteration
            self.stop_order = None

        # Emulate the quarterly roll: held across a roll date -> close and reopen.
        if qty != 0 and self.last_iter_date is not None:
            due = [r for r in self._roll_dates() if self.last_iter_date < r <= today]
            if due:
                side = 1 if qty > 0 else -1
                self.submit_order(self.create_order(self.asset, abs(qty), "sell" if side > 0 else "buy"))
                self.submit_order(self.create_order(self.asset, abs(qty), "buy" if side > 0 else "sell"))
                self.log_rows.append({"date": today, "event": "roll", "qty": qty})
        self.last_iter_date = today

        feats = self.core.features(hist)
        row = next(feats.iloc[[-1]].itertuples(index=False))
        if self.state is not None:
            s = self.state
            s["bars_held"] += 1
            last_close = float(hist["close"].iloc[-1])
            s["best_close"] = max(s["best_close"], last_close) if s["side"] > 0 else min(s["best_close"], last_close)
            view = PositionView(s["side"], s["entry_price"], s["stop"], s["bars_held"], s["best_close"])
            d = self.core.decide(row, view)
            if d.exit:
                if self.stop_order is not None:
                    self.cancel_order(self.stop_order)
                    self.stop_order = None
                self.submit_order(self.create_order(self.asset, abs(qty), "sell" if s["side"] > 0 else "buy"))
                self.log_rows.append({"date": today, "event": "exit_signal", "reason": d.reason})
            elif d.stop is not None and math.isfinite(d.stop):
                new = self.spec.round_to_tick(d.stop, "down" if s["side"] > 0 else "up")
                tighter = new > s["stop"] if s["side"] > 0 else new < s["stop"]
                if tighter:
                    s["stop"] = new
                    self._submit_stop(qty, s["side"], new)
        else:
            d = self.core.decide(row, PositionView())
            if d.entry_side != 0 and d.stop_distance and math.isfinite(d.stop_distance):
                ref = float(hist["close"].iloc[-1])  # estimate; stop is re-anchored on the actual fill
                stop = ref - d.entry_side * d.stop_distance
                sz = self.risk.size_entry(float(self.get_portfolio_value()), ref, stop, d.entry_side)
                if sz.approved:
                    self.pending_entry = {"side": d.entry_side, "distance": d.stop_distance, "reason": d.reason}
                    self.submit_order(self.create_order(self.asset, sz.contracts,
                                                        "buy" if d.entry_side > 0 else "sell"))
                    self.log_rows.append({"date": today, "event": "entry_signal", "contracts": sz.contracts,
                                          "reason": d.reason})

    def on_filled_order(self, position, order, price, quantity, multiplier):
        price = float(price)
        side = 1 if str(order.side).lower().endswith("buy") else -1
        self.log_rows.append({"date": pd.Timestamp(self.get_datetime()).date(), "event": "fill",
                              "side": side, "qty": float(quantity), "price": price,
                              "type": str(order.order_type)})
        if self.pending_entry is not None and side == self.pending_entry["side"] and self.state is None:
            pe = self.pending_entry
            stop = self.spec.round_to_tick(price - pe["side"] * pe["distance"], "down" if pe["side"] > 0 else "up")
            self.state = {"side": pe["side"], "entry_price": price, "stop": stop, "bars_held": 0,
                          "best_close": price}
            self.pending_entry = None
            self._submit_stop(int(quantity), pe["side"], stop)
        elif self.state is not None and str(order.order_type).lower().endswith("market") and side == self.state["side"]:
            # roll re-open leg: keep protection on the new contract
            self._submit_stop(self._position_qty(), self.state["side"], self.state["stop"])

    def _roll_dates(self):
        if not self.rolls:
            self.rolls = set(roll_dates(dt.date(2008, 1, 1), dt.date(2030, 12, 31), self.spec))
        return self.rolls

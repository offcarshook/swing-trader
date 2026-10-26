"""Paper-trading runner. Live order execution does not exist in this project.

local mode (default, works offline)
    Deterministic replay: the promoted strategy is re-run through the backtest
    engine from the paper start date to the latest validated session with the
    position left open. History is therefore crash-safe and reproducible; only
    the orders for the NEXT session are new. Each order goes through OrderGuard
    (idempotent client ids, so re-running a day cannot duplicate it) into a
    simulated paper book + journal.

lumibot mode
    Hands the same LumiBot strategy used in backtests to a LumiBot paper broker
    (Tradovate demo / IBKR paper / ProjectX sim). Requires credentials; refuses
    anything that is not explicitly a paper/demo account.

Gates applied before any NEW entry: promotion passed, kill switch absent, latest
data passes check_latest_bar, risk not halted. Exits/stops are always processed.
"""

from __future__ import annotations

import datetime as dt
import json

import pandas as pd

import swingtrader
from swingtrader.agents.adapter import research
from swingtrader.agents.overlay import overlay_multiplier
from swingtrader.backtest.engine import run_backtest
from swingtrader.backtest.runner import components, regimes_for
from swingtrader.config import resolve
from swingtrader.data.pipeline import load_sessions
from swingtrader.orders import DuplicateOrderError, OrderGuard, OrderIntent
from swingtrader.safety import check_latest_bar, kill_switch_active
from swingtrader.strategies import make_strategy


class PromotionRequired(RuntimeError):
    pass


def load_promotion() -> dict:
    p = resolve("results") / "promotion.json"
    if not p.exists():
        raise PromotionRequired("no results/promotion.json: run `swingtrader select` and `swingtrader holdout`")
    d = json.loads(p.read_text())
    if not d.get("passed"):
        raise PromotionRequired(f"candidate {d.get('candidate')} did not pass promotion gates: {d.get('failures')}")
    return d


def run_paper(cfg: dict, as_of: str | None = None, dry_run: bool = False, mode: str = "local",
              start: str | None = None) -> dict:
    assert swingtrader.LIVE_TRADING_ENABLED is False  # noqa: S101 - hard invariant
    promo = load_promotion()
    if mode == "lumibot":
        from swingtrader.lumibot_bridge.paper import run_lumibot_paper
        return run_lumibot_paper(cfg, promo)

    state_dir = resolve(cfg["paper"]["state_dir"])
    state_dir.mkdir(parents=True, exist_ok=True)
    meta_p = state_dir / "meta.json"
    bars = load_sessions(cfg)
    if as_of:
        bars = bars[bars.index <= pd.Timestamp(as_of)]
    if meta_p.exists():
        meta = json.loads(meta_p.read_text())
        if meta["candidate_hash"] != promo["hash"]:
            raise RuntimeError("paper book belongs to a different candidate; archive state/paper first")
    else:
        # Paper trading starts from the next unseen session (default: latest available).
        meta = {"candidate": promo["candidate"], "candidate_hash": promo["hash"],
                "paper_start": start or str(bars.index[-1].date()),
                "created": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
        if not dry_run:
            meta_p.write_text(json.dumps(meta, indent=1))

    today = (pd.Timestamp(as_of).date() if as_of else dt.date.today())
    gates = []
    if kill_switch_active(resolve(cfg["paper"]["kill_switch_file"])):
        gates.append("kill switch active")
    dc = check_latest_bar(bars, today if as_of is None else bars.index[-1].date())
    if not dc.ok:
        gates.append("data check failed: " + "; ".join(dc.reasons))

    theses = []

    def entry_filter(date, side, row):
        if gates:
            return 0.0  # entries blocked; exits still flow
        if cfg["agents"]["mode"] == "off":
            return 1.0
        rep = research(cfg, str(date.date()), {"family": promo["family"], "side": side})
        mult, why = overlay_multiplier(side, rep, cfg["agents"]["mode"])
        theses.append({"date": str(date.date()), "status": rep.status, "rating": rep.rating, "mult": mult,
                       "why": why})
        return mult

    spec, costs, risk = components(cfg)
    strat = make_strategy(promo["family"], promo["params"], cfg)
    begin = pd.Timestamp(meta["paper_start"])
    if begin > bars.index[-1]:
        return {"status": "waiting", "detail": f"no session after paper start {begin.date()} yet"}
    res = run_backtest(bars, strat, spec, costs, risk, begin, bars.index[-1], cfg["account"]["starting_equity"],
                       entry_filter=entry_filter, regimes=regimes_for(bars), instrument=cfg["instrument"],
                       close_at_end=False)
    fs = res.final_state
    guard = OrderGuard(None if dry_run else state_dir / "orders.json")
    session_key = f"after:{fs['last_session']}"
    intents = []
    nxt = fs["next_session_order"]
    pos = fs["position"]
    if nxt and nxt["type"] == "exit" and pos:
        intents.append(OrderIntent(strat.label, cfg["instrument"], session_key, "exit", -pos["side"],
                                   pos["contracts"], "market"))
    elif nxt and nxt["type"] == "entry" and not gates:
        intents.append(OrderIntent(strat.label, cfg["instrument"], session_key, "entry", nxt["side"], 1, "market"))
    if pos and not (nxt and nxt["type"] == "exit"):
        intents.append(OrderIntent(strat.label, cfg["instrument"], session_key, "stop", -pos["side"],
                                   pos["contracts"], "stop", stop_price=pos["stop"]))
    journal = []
    for it in intents:
        rec = {"client_id": it.client_id, **it.__dict__}
        try:
            if dry_run:
                guard.check(it, broker_is_paper=True)
                rec["result"] = "dry-run (not recorded)"
            else:
                guard.submit(it, broker_is_paper=True, send=lambda i: "accepted by local paper book")
                rec["result"] = "accepted by local paper book"
        except DuplicateOrderError as exc:
            rec["result"] = f"skipped duplicate: {exc}"
        journal.append(rec)
    status = {
        "mode": "local-paper", "dry_run": dry_run, "candidate": promo["candidate"],
        "paper_start": meta["paper_start"], "last_session": fs["last_session"],
        "equity": round(fs["equity"], 2), "position": pos, "next_session_orders": journal,
        "entry_gates_blocking": gates, "halted": fs["halted"], "closed_trades": int(len(res.trades)),
        "agent_theses": theses, "live_trading_enabled": swingtrader.LIVE_TRADING_ENABLED,
        "note": "entry quantity is finalised by RiskManager at the next RTH open (shown as 1 placeholder)",
    }
    if not dry_run:
        (state_dir / "status.json").write_text(json.dumps(status, indent=1, default=str))
        with open(state_dir / "journal.jsonl", "a") as fh:
            fh.write(json.dumps({"ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                                 **status}, default=str) + "\n")
    return status

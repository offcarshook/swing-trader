"""Lumibot ETF adapter acceptance tests (run in .venv, which has lumibot==4.6.30)."""

import json
import os
from pathlib import Path

import pandas as pd
import pytest

lumibot = pytest.importorskip("lumibot")

from swingtrader.agents.etf_research import ResearchRecord, ResearchService, cache_key, entry_filter_from  # noqa: E402
from swingtrader.config import resolve  # noqa: E402
from swingtrader.etf.data import load_basket  # noqa: E402
from swingtrader.etf.engine import RiskCfg, build_signals, simulate  # noqa: E402
from swingtrader.etf.strategies import Params  # noqa: E402
from swingtrader.lumibot_bridge.etf_backtest import run_etf_lumibot  # noqa: E402

DATA = resolve("data/raw/etf_full")
SEL = resolve("results/etf/study/train_selection_corrected.json")
pytestmark = pytest.mark.skipif(not (DATA / "SPY.csv").exists() or not SEL.exists(),
                                reason="needs the real SPY/QQQ files and the frozen selection")
ZERO = dict(equity=100000.0, risk_pct=1.0, max_open_risk_pct=4.0, max_gross=2.0, commission_per_share=0.0,
            slip_bps=0.0, slip_bps_wide=0.0, stop_extra_bps=0.0, borrow_bps_annual=0.0)
W = ("2019-01-02", "2019-04-30")


@pytest.fixture(scope="module")
def setup():
    sel = json.loads(SEL.read_text())
    bars = {s: b.loc[:"2019-12-31"] for s, b in load_basket(DATA, ["SPY", "QQQ"]).items()}
    from swingtrader.lumibot_bridge.etf_strategy import lumibot_supported
    params, _ = lumibot_supported(sel["selected_params"])
    ps = [Params(**{k: v for k, v in d.items() if k in Params.__dataclass_fields__}) for d in params]
    return bars, params, ps


def _prev(cal, d):
    return cal[cal.searchsorted(pd.Timestamp(d)) - 1]


def test_smoke_and_exact_zero_cost_parity(setup, tmp_path):
    bars, params, ps = setup
    lb = run_etf_lumibot(bars, params, ZERO, *W, log_dir=str(tmp_path))
    ref = simulate(bars, ps, *W, RiskCfg.from_dict(ZERO), exec_style="lumibot")
    cal = pd.DatetimeIndex(sorted(set().union(*[b.index for b in bars.values()])))
    lt = lb["trades"]
    assert len(lt) > 5 and lb["lumibot_version"] == "4.6.30"
    got = sorted((r.sym, _prev(cal, r.entry_date), int(r.shares), round(r.entry, 6), round(r.exit, 6))
                 for r in lt.itertuples())
    rt = ref.trades[ref.trades.reason != "end_of_window"]
    want = sorted((r.sym, r.entry_date, int(r.shares), round(r.entry, 6), round(r.exit, 6))
                  for r in rt.itertuples() if r.entry_date in {g[1] for g in got})
    assert got == want


def test_global_order_switch_blocks_every_order(setup, tmp_path, monkeypatch):
    bars, params, _ = setup
    monkeypatch.setenv("SWINGTRADER_DISABLE_ORDERS", "1")
    lb = run_etf_lumibot(bars, params, ZERO, *W, log_dir=str(tmp_path))
    ev = lb["ledger"].event.value_counts()
    assert ev.get("order_submitted", 0) == 0 and ev.get("fill", 0) == 0 and ev.get("order_blocked", 0) > 0


def test_end_to_end_research_gate_risk_lumibot_ledger(setup, tmp_path):
    """point-in-time data -> deterministic candidate -> recorded research record -> gate policy ->
    PortfolioRiskGate -> Lumibot simulated order -> reconciled ledger."""
    bars, params, ps = setup
    svc = ResearchService(tmp_path / "cache", mode="replay")
    sigs = build_signals(bars, ps)
    sigs = sigs[(sigs.entry_date >= W[0]) & (sigs.entry_date <= W[1])]
    for r in sigs.itertuples():          # fixture: records "logged at decision time" (Buy SPY / Sell QQQ)
        dec = f"{r.entry_date.date()}T13:25:00+00:00"
        rating = "Buy" if r.sym == "SPY" else "Sell"
        rec = ResearchRecord(instrument=r.sym, decision_ts=dec, data_cutoff=f"{r.signal_date.date()}T21:00:00+00:00",
                             generated_at=f"{r.entry_date.date()}T13:15:00+00:00", status="research",
                             timeframes_assessed=["1d"], rating=rating, direction_bias=1 if rating == "Buy" else -1,
                             confidence=None, thesis="fixture", counter_thesis="fixture", risks="fixture",
                             invalidation_conditions=[], source_timestamps=[], model="fixture", provider="fixture")
        svc.store(rec, cache_key(r.sym, dec, {"sym": r.sym, "pid": r.pid, "dir": int(r.dir)}, svc.config, "fx"))
    gate = entry_filter_from(svc, "gate", lambda s, d: "fx")
    lb = run_etf_lumibot(bars, params, ZERO, *W, entry_filter=gate, log_dir=str(tmp_path / "lb"))
    led = lb["ledger"]
    sub = led[(led.event == "order_submitted") & (led.purpose == "entry")]
    # research says Sell QQQ / Buy SPY: every QQQ LONG and every SPY SHORT entry is vetoed,
    # QQQ shorts and SPY longs (agreeing with the record) may pass
    assert not ((sub.sym == "QQQ") & (sub.side == 1)).any() and not ((sub.sym == "SPY") & (sub.side == -1)).any()
    sig = led[led.event == "signal"]
    opp = ((sig.sym == "QQQ") & (sig.dir == 1)) | ((sig.sym == "SPY") & (sig.dir == -1))
    assert opp.any() and (sig[opp].decision == "overlay_veto").all()
    # reconciliation: fills = submitted entries + their exits; no unreconciled positions remain
    assert "reconcile_mismatch" not in set(led.event)
    closed = led[led.event == "trade_closed"]
    assert len(closed) + len(lb["book_open"]) == len(sub)
    # the same filter through the reference engine gives the same SPY entries
    ref = simulate(bars, ps, *W, RiskCfg.from_dict(ZERO), exec_style="lumibot",
                   entry_filter=entry_filter_from(svc, "gate", lambda s, d: "fx"))
    rt = ref.trades[ref.trades.reason != "end_of_window"]
    assert not ((rt.sym == "QQQ") & (rt.dir == 1)).any() and len(rt) == len(closed)


def test_kill_switch_beats_an_eager_llm_in_lumibot(setup, tmp_path):
    bars, params, _ = setup
    risk = {**ZERO, "kill_switch_from": W[0]}
    lb = run_etf_lumibot(bars, params, risk, *W, entry_filter=lambda c: (10.0, "LLM says all-in"),
                         log_dir=str(tmp_path))
    led = lb["ledger"]
    assert (led[led.event == "signal"].decision == "kill_switch").all()
    assert len(led[led.event == "order_submitted"]) == 0


def test_restart_recovery_mismatch_blocks_entries(setup, tmp_path):
    bars, params, _ = setup
    state = tmp_path / "book.json"
    state.write_text(json.dumps({"book": {"SPY": {"pid": params[0]["id"], "dir": 1, "shares": 10, "entry": 250.0,
                                                   "held": 0, "stop": 240.0, "risk_usd": 100.0, "target": None}},
                                 "gate": {"prev_equity": 100000.0, "peak": 100000.0, "halted_on": None}}))
    lb = run_etf_lumibot(bars, params, ZERO, *W, log_dir=str(tmp_path / "lb"),
                         extra_parameters={"state_file": str(state), "heartbeat_file": str(tmp_path / "hb.txt")})
    led = lb["ledger"]
    assert "state_recovered" in set(led.event) and "reconcile_mismatch" in set(led.event)
    first_block = led[led.event == "entries_blocked"].index.min()
    assert pd.notna(first_block)
    assert (tmp_path / "hb.txt").exists()


def test_kill_switch_file_blocks_entries_and_flattens(setup, tmp_path):
    bars, params, _ = setup
    kill = tmp_path / "KILL_SWITCH"
    kill.write_text("stop")
    lb = run_etf_lumibot(bars, params, ZERO, *W, log_dir=str(tmp_path / "lb"),
                         extra_parameters={"kill_switch_file": str(kill), "kill_policy": "flatten"})
    led = lb["ledger"]
    assert len(led[(led.event == "order_submitted")]) == 0 and (led.event == "entries_blocked").any()


def test_paper_broker_mode_refuses_without_paper_credentials(monkeypatch, tmp_path):
    from swingtrader.lumibot_bridge.etf_paper import paper_broker_from_env
    for k in ("ALPACA_API_KEY", "ALPACA_API_SECRET", "ALPACA_IS_PAPER", "INTERACTIVE_BROKERS_PORT"):
        monkeypatch.delenv(k, raising=False)
    assert paper_broker_from_env()[0] is None
    monkeypatch.setenv("INTERACTIVE_BROKERS_PORT", "7496")          # live TWS port
    assert paper_broker_from_env()[0] is None
    monkeypatch.setenv("ALPACA_API_KEY", "x")
    monkeypatch.setenv("ALPACA_API_SECRET", "y")
    monkeypatch.setenv("ALPACA_IS_PAPER", "false")
    assert paper_broker_from_env()[0] is None
    monkeypatch.setenv("ALPACA_IS_PAPER", "true")
    assert paper_broker_from_env()[0] == "alpaca"


def test_no_exit_order_for_a_position_the_broker_does_not_hold(setup, tmp_path):
    # Regression: a recovered (stale) book entry used to trigger a time-stop SELL although the broker
    # held nothing -> on a real account that sell would open an unintended short.
    bars, params, _ = setup
    state = tmp_path / "book.json"
    state.write_text(json.dumps({"book": {"SPY": {"pid": params[0]["id"], "dir": 1, "shares": 10, "entry": 250.0,
                                                   "held": 9, "stop": 240.0, "risk_usd": 100.0, "target": None}}}))
    lb = run_etf_lumibot(bars, params, ZERO, *W, log_dir=str(tmp_path / "lb"),
                         extra_parameters={"state_file": str(state)})
    led = lb["ledger"]
    assert "exit_skipped_mismatch" in set(led.event)
    sub = led[led.event == "order_submitted"]
    assert len(sub) == 0 or not ((sub.sym == "SPY") & (sub.get("purpose") == "exit")).any()

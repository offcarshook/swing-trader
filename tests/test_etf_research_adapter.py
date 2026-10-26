"""TradingAgents adapter contract: schema, cache, fail-closed, point-in-time, hard-risk supremacy."""

import datetime as dt
import json

import numpy as np
import pandas as pd
import pytest

from swingtrader.agents.etf_research import (STATUS_PLUMBING, STATUS_RESEARCH, ResearchRecord, ResearchService,
                                             cache_key, entry_filter_from, validate)
from swingtrader.etf.engine import RiskCfg, simulate
from swingtrader.etf.strategies import Params

DEC = "2024-03-05T13:25:00+00:00"


def rec(**over):
    d = ResearchRecord(instrument="SPY", decision_ts=DEC, data_cutoff="2024-03-04T21:00:00+00:00",
                       generated_at="2024-03-05T13:10:00+00:00", status=STATUS_RESEARCH,
                       timeframes_assessed=["1d"], rating="Buy", direction_bias=1, confidence=None,
                       thesis="trend intact", counter_thesis="breadth weak", risks="CPI on Thursday",
                       invalidation_conditions=["close below 500"], source_timestamps=["2024-03-04T21:00:00+00:00"],
                       model="m", provider="p").to_dict()
    d.update(over)
    return d


def test_valid_record_passes_and_round_trips():
    d = rec()
    assert validate(d, DEC) == []
    assert ResearchRecord(**json.loads(json.dumps(d))).to_dict() == d


@pytest.mark.parametrize("over,needle", [
    ({"data_cutoff": "2024-03-05T15:00:00+00:00"}, "look-ahead"),
    ({"source_timestamps": ["2024-03-06T00:00:00+00:00"]}, "after decision"),
    ({"generated_at": "2026-10-26T12:00:00+00:00"}, "hindsight"),
    ({"rating": "Strong Buy"}, "rating"),
    ({"direction_bias": -1}, "contradicts"),
    ({"status": STATUS_PLUMBING}, "not research"),
    ({"counter_thesis": ""}, "counter-thesis"),
    ({"confidence": 1.7}, "confidence"),
    ({"surprise": 1}, "unknown fields"),
])
def test_invalid_or_leaky_records_rejected(over, needle):
    assert any(needle in e for e in validate(rec(**over), DEC))


def test_missing_fields_rejected():
    d = rec()
    del d["thesis"]
    assert validate(d, DEC) == ["missing field thesis"]


def _service(tmp_path, mode="replay", now=None):
    return ResearchService(tmp_path, mode=mode, now=(lambda: now) if now else None)


def test_replay_reads_cache_and_never_calls_a_model(tmp_path):
    svc = _service(tmp_path)
    cand = {"sym": "SPY", "pid": "x", "dir": 1}
    d, errs = svc.get("SPY", DEC, cand, "fp")
    assert d is None and "replay never calls a model" in errs[0] and svc.calls_made == 0
    svc.store(ResearchRecord(**rec()), cache_key("SPY", DEC, cand, svc.config, "fp"))
    d, errs = svc.get("SPY", DEC, cand, "fp")
    assert d["run_id"] and errs == []
    # a different data fingerprint is a different cache entry (data changed -> no stale reuse)
    assert svc.get("SPY", DEC, cand, "other")[0] is None


def test_forward_mode_refuses_fresh_calls_for_past_decisions(tmp_path):
    now = dt.datetime(2026, 10, 26, 14, 0, tzinfo=dt.timezone.utc)
    svc = _service(tmp_path, "forward", now)
    d, errs = svc.get("SPY", DEC, {"sym": "SPY"}, "fp")
    assert d is None and "hindsight" in errs[0] and svc.calls_made == 0


def test_forward_mode_without_credentials_fails_closed_and_counts_budget(tmp_path):
    now = dt.datetime(2024, 3, 5, 13, 25, tzinfo=dt.timezone.utc)
    svc = ResearchService(tmp_path, mode="forward", now=lambda: now, retries=1, max_calls_per_day=5)
    d, errs = svc.get("SPY", DEC, {"sym": "SPY"}, "fp")
    assert d is None and svc.calls_made == 2 and "not available" in errs[0]


def test_malformed_cache_file_fails_closed(tmp_path):
    svc = _service(tmp_path)
    cand = {"sym": "SPY"}
    k = cache_key("SPY", DEC, cand, svc.config, "fp")
    (tmp_path / f"{k}.json").write_text("{not json")
    d, errs = svc.get("SPY", DEC, cand, "fp")
    assert d is None and "malformed" in errs[0]


def test_gate_policy_fails_closed_and_vetoes_opposition(tmp_path):
    svc = _service(tmp_path)
    f = entry_filter_from(svc, "gate", lambda s, d: "fp")
    cand = {"sym": "SPY", "pid": "p", "dir": 1, "date": pd.Timestamp("2024-03-05")}
    assert f(cand)[0] == 0.0                                   # nothing cached -> no agent-assisted entry
    key = cache_key("SPY", DEC, {"sym": "SPY", "pid": "p", "dir": 1}, svc.config, "fp")
    svc.store(ResearchRecord(**rec(rating="Sell", direction_bias=-1)), key)
    m, why = f(cand)
    assert m == 0.0 and "veto" in why
    svc.store(ResearchRecord(**rec()), key)
    assert f(cand)[0] == 1.0
    assert entry_filter_from(svc, "advisory", lambda s, d: "fp")({**cand, "dir": -1})[0] == 1.0
    assert entry_filter_from(svc, "off", lambda s, d: "fp")(cand) == (1.0, "agents off")


def _bars(n=400, seed=0):
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.01, n)))
    o = c * (1 + rng.normal(0, 0.003, n))
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) * 1.004, "low": np.minimum(o, c) * 0.996, "close": c,
                         "volume": 1e6, "adj_factor": 1.0, "dividend": 0.0}, index=pd.bdate_range("2015-01-01", periods=n))


@pytest.mark.parametrize("risk_over,blocked_reason", [
    ({"daily_loss_lockout_pct": 0.5}, "daily_loss_lockout"),
    ({"max_dd_lockout_pct": 0.5}, "dd_lockout"),
    ({"kill_switch_from": "2016-02-24"}, "kill_switch"),
    ({"max_open_risk_pct": 0.5}, "open_risk_cap"),
    ({"max_gross": 0.01}, "gross_cap"),
])
def test_llm_recommendation_cannot_bypass_hard_limits(risk_over, blocked_reason):
    df = _bars()
    k = 300
    df.iloc[k, df.columns.get_loc("low")] = df.open.iloc[k] - 50          # first trade: large loss on entry day
    P = Params("dip", "long", "rsi2<", 10, 2.0, None, 3)
    s = pd.DataFrame([{"sym": "X", "rank": 0, "pid": P.id, "entry_date": df.index[i], "dir": 1, "stop_dist": dist,
                       "entry_level": np.nan, "signal_date": df.index[i - 1], "regime": "up"}
                      for i, dist in ((k, 1.0), (k + 1, 1.0))])
    eager = lambda c: (10.0, "LLM: STRONG BUY, size up, ignore limits")  # noqa: E731
    base = dict(commission_per_share=0, slip_bps=0, slip_bps_wide=0, stop_extra_bps=0, risk_pct=1.0)
    r = simulate({"X": df}, [P], df.index[0], df.index[-1], RiskCfg(**base, **risk_over), sigs=s, entry_filter=eager)
    plain = simulate({"X": df}, [P], df.index[0], df.index[-1], RiskCfg(**base, **risk_over), sigs=s)
    assert r.skipped[blocked_reason] >= 1
    assert len(r.trades) == len(plain.trades)                              # the "recommendation" changed nothing
    if len(r.trades):
        assert (r.trades.shares.to_numpy() == plain.trades.shares.to_numpy()).all()

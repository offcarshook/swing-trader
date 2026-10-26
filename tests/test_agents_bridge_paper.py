import json

import numpy as np
import pandas as pd
import pytest

from swingtrader.agents import adapter
from swingtrader.agents.overlay import overlay_multiplier
from swingtrader.agents.schema import (STATUS_OK, STATUS_PLUMBING, STATUS_UNAVAILABLE, ThesisReport, bias_for,
                                       from_final_state)
from swingtrader.backtest.engine import run_backtest
from swingtrader.risk import RiskManager
from swingtrader.strategies import TrendPullback

from conftest import make_bars


def thesis(rating, status=STATUS_OK):
    return ThesisReport(status=status, as_of="2024-01-02", ticker="^GSPC", rating=rating,
                        direction_bias=bias_for(rating))


def test_rating_bias_mapping():
    assert [bias_for(r) for r in ("Buy", "Overweight", "Hold", "Underweight", "Sell", "REVIEW", None)] == \
        [1, 1, 0, -1, -1, 0, 0]


def test_final_state_mapping():
    st = {"investment_debate_state": {"bull_history": "B", "bear_history": "R"},
          "risk_debate_state": {"history": "risk"}, "final_trade_decision": "Rating: Sell",
          "investment_plan": "plan", "trader_investment_plan": "tp", "market_report": "mkt"}
    rep = from_final_state(st, "2024-01-02", "^GSPC", "Sell")
    assert rep.bull_case == "B" and rep.bear_case == "R" and rep.direction_bias == -1 and rep.usable
    assert ThesisReport.from_dict(json.loads(rep.to_json())) == rep


@pytest.mark.parametrize("mode", ["off", "advisory"])
def test_overlay_non_veto_modes_never_change_size(mode):
    for r in ("Buy", "Sell", "Hold", None):
        assert overlay_multiplier(1, thesis(r), mode)[0] == 1.0


def test_overlay_veto_mode():
    assert overlay_multiplier(1, thesis("Sell"), "veto")[0] == 0.0
    assert overlay_multiplier(1, thesis("Underweight"), "veto")[0] == 0.0
    assert overlay_multiplier(1, thesis("Buy"), "veto")[0] == 1.0
    assert overlay_multiplier(1, thesis("Hold"), "veto")[0] == 1.0
    assert overlay_multiplier(-1, thesis("Buy"), "veto")[0] == 0.0
    # unusable research never acts (fail-open), even if it "says" Sell
    assert overlay_multiplier(1, thesis("Sell", STATUS_PLUMBING), "veto")[0] == 1.0
    assert overlay_multiplier(1, thesis("Sell", STATUS_UNAVAILABLE), "veto")[0] == 1.0
    assert overlay_multiplier(1, None, "veto")[0] == 1.0
    with pytest.raises(ValueError):
        overlay_multiplier(1, None, "boost")


def test_overlay_never_exceeds_one():
    for mode in ("off", "advisory", "veto"):
        for r in ("Buy", "Overweight", "Hold", "Sell", None):
            for side in (1, -1):
                assert 0.0 <= overlay_multiplier(side, thesis(r), mode)[0] <= 1.0


def test_research_without_credentials_is_unavailable(cfg, tmp_path, monkeypatch):
    for _, k in adapter.PROVIDER_ENV:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.delenv("TRADINGAGENTS_LLM_PROVIDER", raising=False)
    c = {**cfg, "agents": {**cfg["agents"], "cache_dir": str(tmp_path), "python": "/bin/true"}}
    rep = adapter.research(c, "2024-01-02", {"side": 1})
    assert rep.status == STATUS_UNAVAILABLE and "credentials" in rep.reason
    c["agents"]["python"] = str(tmp_path / "missing-python")
    assert "missing" in adapter.research(c, "2024-01-02", {"side": 1}).reason
    c["agents"]["mode"] = "off"
    assert adapter.research(c, "2024-01-02", {"side": 1}).reason == "agents.mode=off"


def test_call_budget(tmp_path):
    b = adapter.CallBudget(tmp_path / "b.json", 2)
    assert b.try_consume("x") and b.try_consume("x") and not b.try_consume("x")


def test_lumibot_completed_bars_guard():
    pytest.importorskip("lumibot")
    from swingtrader.lumibot_bridge.strategy import completed_bars
    idx = pd.date_range("2024-01-01", periods=5, freq="D", tz="America/New_York")
    df = pd.DataFrame({"close": range(5)}, index=idx)
    out = completed_bars(df, pd.Timestamp("2024-01-04 00:00", tz="America/New_York"))
    assert list(out.index.day) == [1, 2, 3]  # the bar stamped "today" is excluded


def test_paper_replay_matches_backtest(spec, costs, limits):
    """The paper runner's open-ended replay must produce the same closed trades as a backtest."""
    rng = np.random.default_rng(3)
    bars = make_bars(4000 + np.cumsum(rng.normal(0.5, 20, 500)))
    mk = lambda: TrendPullback(params={"trend_len": 50, "rsi_len": 2, "rsi_entry": 15, "exit_ma": 5,  # noqa: E731
                                       "max_hold": 10, "stop_atr": 2.5}, vol_filter_lookback=60)
    a = run_backtest(bars, mk(), spec, costs, RiskManager(limits, spec, costs), bars.index[0], bars.index[-1], 1e5)
    b = run_backtest(bars, mk(), spec, costs, RiskManager(limits, spec, costs), bars.index[0], bars.index[-1], 1e5,
                     close_at_end=False)
    ta = a.trades[a.trades["exit_reason"] != "end_of_test"].reset_index(drop=True)
    pd.testing.assert_frame_equal(ta, b.trades.reset_index(drop=True))
    assert "position" in b.final_state and "next_session_order" in b.final_state


def test_paper_requires_promotion(cfg, tmp_path, monkeypatch):
    from swingtrader.paper import runner
    monkeypatch.setattr(runner, "resolve", lambda p: tmp_path / p)
    with pytest.raises(runner.PromotionRequired):
        runner.run_paper(cfg, dry_run=True)
    (tmp_path / "results").mkdir()
    (tmp_path / "results" / "promotion.json").write_text(json.dumps({"passed": False, "candidate": "x",
                                                                    "failures": ["f"]}))
    with pytest.raises(runner.PromotionRequired):
        runner.run_paper(cfg, dry_run=True)

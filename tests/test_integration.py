"""Integration tests: need downloaded data, LumiBot and/or the agents env.

Run with:  .venv/bin/python -m pytest -m integration
"""

import json
import subprocess

import pandas as pd
import pytest

from swingtrader.config import resolve

pytestmark = pytest.mark.integration

AGENTS_PY = resolve(".venv-agents/bin/python")
SPX = resolve("data/processed/spx_sessions.parquet")


@pytest.fixture(scope="module")
def have_data():
    if not SPX.exists():
        pytest.skip("run `swingtrader download` and `swingtrader data` first")


def test_pinned_hashes(have_data, cfg):
    from swingtrader.data.sources import CORE_SOURCES, SOURCES, local_path, sha256_of
    for k in CORE_SOURCES:
        p = local_path(resolve(cfg["data"]["raw_dir"]), SOURCES[k])
        assert sha256_of(p) == SOURCES[k].sha256, k


@pytest.mark.skipif(not AGENTS_PY.exists(), reason="agents env not installed")
def test_tradingagents_graph_offline_and_point_in_time(have_data, tmp_path):
    as_of = "2024-03-15"
    req = {"as_of": as_of, "ticker": "^GSPC", "analysts": ["market"], "bars_path": str(SPX),
           "work_dir": str(tmp_path / "home"), "candidate": {"side": 1}}
    (tmp_path / "req.json").write_text(json.dumps(req))
    out = tmp_path / "out.json"
    proc = subprocess.run([str(AGENTS_PY), "-m", "swingtrader.agents.ta_worker", "--request",
                           str(tmp_path / "req.json"), "--out", str(out), "--fake-llm"],
                          capture_output=True, text=True, timeout=600, cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr[-2000:]
    rep = json.loads(out.read_text())
    assert rep["status"] == "fake_llm_plumbing_test" and rep["rating"] == "Hold"
    assert rep["bull_case"] and rep["bear_case"] and rep["risk_debate"] and rep["final_decision"]
    assert {c["tool"] for c in rep["tool_calls"]} == {"get_stock_data", "get_indicators"}
    # the local vendor never serves rows after as_of, whatever the model asks for
    code = ("import json,sys; from swingtrader.agents.ta_worker import register_local_vendor;"
            "from tradingagents.dataflows import router; log=[];"
            f"register_local_vendor({str(SPX)!r}, {as_of!r}, log);"
            "txt=router.VENDOR_METHODS['get_stock_data']['swingtrader_local']('^GSPC','2024-03-01','2024-12-31');"
            "print(txt.strip().splitlines()[-1].split(',')[0])")
    last = subprocess.run([str(AGENTS_PY), "-c", code], capture_output=True, text=True, timeout=300).stdout.strip()
    assert pd.Timestamp(last) <= pd.Timestamp(as_of)


@pytest.mark.skipif(not AGENTS_PY.exists(), reason="agents env not installed")
def test_agents_env_has_incompatible_pandas_for_lumibot():
    v = subprocess.run([str(AGENTS_PY), "-c", "import pandas; print(pandas.__version__)"],
                       capture_output=True, text=True).stdout.strip()
    assert int(v.split(".")[0]) >= 3  # TradingAgents requires pandas>=3.0.6


def test_lumibot_parity_short_window(have_data, cfg):
    pytest.importorskip("lumibot")
    from swingtrader.lumibot_bridge.run_backtest import run_lumibot_backtest
    params = {"trend_len": 100, "rsi_len": 2, "rsi_entry": 10, "exit_ma": 5, "max_hold": 10, "stop_atr": 2.5}
    res = run_lumibot_backtest(cfg, "2021-01-04", "2022-12-30", family="pullback", params_json=json.dumps(params))
    p = res["parity"]
    assert p["internal_entries"] == p["lumibot_entries"] == p["matching_entry_sessions"]
    assert abs(res["parity_equity"]["final_diff_usd"]) < 250
    for f in ("lumibot_backtest_2021-01-04_2022-12-30.json", "lumibot_events_2021-01-04_2022-12-30.csv"):
        resolve("results").joinpath(f).unlink(missing_ok=True)

"""Main-environment side of the TradingAgents integration.

TradingAgents runs in a separate interpreter (.venv-agents) because it requires
pandas>=3.0.6 while lumibot==4.6.30 resolves to pandas<3. The boundary is a JSON
request/response file pair and a subprocess with a timeout.

Cost guards: agents are only called for a deterministic entry SIGNAL (never on
every bar), results are cached on disk per (date, candidate, mode), and a per-day
call budget is enforced before any process is spawned.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
from pathlib import Path

import pandas as pd

from swingtrader.agents.overlay import overlay_multiplier
from swingtrader.agents.schema import STATUS_ERROR, STATUS_UNAVAILABLE, ThesisReport
from swingtrader.config import config_hash, resolve

PROVIDER_ENV = (("anthropic", "ANTHROPIC_API_KEY"), ("openai", "OPENAI_API_KEY"), ("google", "GOOGLE_API_KEY"))


def detect_provider() -> str | None:
    forced = os.environ.get("TRADINGAGENTS_LLM_PROVIDER")
    if forced:
        return forced
    for name, key in PROVIDER_ENV:
        if os.environ.get(key):
            return name
    return None


class CallBudget:
    def __init__(self, path: Path, max_per_day: int):
        self.path, self.max = path, max_per_day

    def _load(self) -> dict:
        return json.loads(self.path.read_text()) if self.path.exists() else {}

    def try_consume(self, day: str) -> bool:
        d = self._load()
        today = dt.date.today().isoformat()  # budget is per wall-clock day (cost), not per as-of date
        if d.get(today, 0) >= self.max:
            return False
        d[today] = d.get(today, 0) + 1
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(d))
        return True


def research(cfg: dict, as_of: str, candidate: dict, fake_llm: bool = False, timeout_s: int = 1800) -> ThesisReport:
    a = cfg["agents"]
    ticker = a["research_ticker"]
    if a["mode"] == "off":
        return ThesisReport(status=STATUS_UNAVAILABLE, as_of=as_of, ticker=ticker, candidate=candidate,
                            reason="agents.mode=off")
    py = resolve(a["python"])
    cache_dir = resolve(a["cache_dir"])
    key = config_hash({"as_of": as_of, "candidate": candidate, "fake": fake_llm, "analysts": a["analysts"],
                       "ticker": ticker})
    out_path = cache_dir / f"{as_of}_{key}.json"
    if out_path.exists():
        return ThesisReport.from_dict(json.loads(out_path.read_text()))
    if not py.exists():
        return ThesisReport(status=STATUS_UNAVAILABLE, as_of=as_of, ticker=ticker, candidate=candidate,
                            reason=f"agents interpreter {py} missing: run scripts/setup_envs.sh")
    provider = None if fake_llm else detect_provider()
    if not fake_llm and provider is None:
        return ThesisReport(status=STATUS_UNAVAILABLE, as_of=as_of, ticker=ticker, candidate=candidate,
                            reason="no LLM credentials (ANTHROPIC_API_KEY / OPENAI_API_KEY / GOOGLE_API_KEY)")
    if not fake_llm and not CallBudget(cache_dir / "budget.json", a["max_calls_per_day"]).try_consume(as_of):
        return ThesisReport(status=STATUS_UNAVAILABLE, as_of=as_of, ticker=ticker, candidate=candidate,
                            reason=f"daily agent call budget ({a['max_calls_per_day']}) exhausted")
    cache_dir.mkdir(parents=True, exist_ok=True)
    req = {"as_of": as_of, "ticker": ticker, "analysts": a["analysts"], "candidate": candidate,
           "bars_path": str(resolve(cfg["data"]["processed_dir"]) / "spx_sessions.parquet"),
           "work_dir": str(cache_dir / "ta_home"), "provider": provider,
           "deep_think_llm": a.get("deep_think_llm"), "quick_think_llm": a.get("quick_think_llm")}
    req_path = cache_dir / f"{as_of}_{key}.request.json"
    req_path.write_text(json.dumps(req, indent=1))
    tmp_out = out_path.with_suffix(".tmp.json")
    cmd = [str(py), "-m", "swingtrader.agents.ta_worker", "--request", str(req_path), "--out", str(tmp_out)]
    if fake_llm:
        cmd.append("--fake-llm")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s, cwd=str(cache_dir))
    except subprocess.TimeoutExpired:
        return ThesisReport(status=STATUS_ERROR, as_of=as_of, ticker=ticker, candidate=candidate,
                            reason=f"agent run exceeded {timeout_s}s")
    if not tmp_out.exists():
        return ThesisReport(status=STATUS_ERROR, as_of=as_of, ticker=ticker, candidate=candidate,
                            reason=f"worker produced no output (exit {proc.returncode}): {proc.stderr[-800:]}")
    rep = ThesisReport.from_dict(json.loads(tmp_out.read_text()))
    if rep.status not in (STATUS_ERROR, STATUS_UNAVAILABLE):
        tmp_out.replace(out_path)  # only successful runs are cached
    else:
        tmp_out.unlink(missing_ok=True)
    return rep


def promoted_candidate(cfg: dict) -> dict | None:
    p = resolve("results") / "promotion.json"
    if not p.exists():
        return None
    d = json.loads(p.read_text())
    return d if d.get("passed") else None


def signal_on(cfg: dict, family: str, params: dict, as_of: str) -> dict:
    """Deterministic decision from the completed session `as_of` (flat-book view)."""
    from swingtrader.data.pipeline import load_sessions
    from swingtrader.strategies import make_strategy
    from swingtrader.strategies.base import PositionView
    bars = load_sessions(cfg)
    bars = bars[bars.index <= pd.Timestamp(as_of)]
    strat = make_strategy(family, params, cfg)
    row = next(strat.features(bars).iloc[[-1]].itertuples(index=False))
    d = strat.decide(row, PositionView())
    return {"session": str(bars.index[-1].date()), "family": family, "params": params, "side": d.entry_side,
            "stop_distance": d.stop_distance, "reason": d.reason}


def research_cli(cfg: dict, date: str, dry_run: bool = False) -> dict:
    cand = promoted_candidate(cfg)
    if cand is None:
        sel = json.loads((resolve("results") / "train_selection.json").read_text())
        c = sel.get("selected") or sel["top_ranked_if_none_passed"]
        cand = {"family": c["family"], "params": c["params"]}
    sig = signal_on(cfg, cand["family"], cand["params"], date)
    out = {"signal": sig, "agents_mode": cfg["agents"]["mode"]}
    if sig["side"] == 0 and not dry_run:
        out["note"] = "no deterministic entry signal on this session -> agents not called (cost guard)"
        return out
    rep = research(cfg, sig["session"], sig, fake_llm=dry_run)
    mult, why = overlay_multiplier(sig["side"] or 1, rep, cfg["agents"]["mode"])
    out.update({"thesis": json.loads(rep.to_json()), "size_multiplier": mult, "overlay_reason": why,
                "usable_for_trading": rep.usable})
    return out

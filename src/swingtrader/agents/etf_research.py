"""Project-owned TradingAgents adapter for ETF candidates (stable interface, typed records).

Nothing outside this module touches TradingAgents' internals; the worker that imports the
upstream package runs in `.venv-agents` (pandas>=3) behind a JSON/subprocess boundary
(agents/ta_worker.py), because lumibot==4.6.30 needs pandas<3.

A ResearchRecord is a HYPOTHESIS. It can only reach an order through an `entry_filter` whose
value the deterministic PortfolioRiskGate clamps to [0, 1]; it can never create, enlarge, keep or
reverse a position, and never bypasses a lockout, cap or kill switch.

Point-in-time rules (enforced by `validate` and `ResearchService`):
  * data_cutoff must be <= decision_ts, and every source timestamp <= decision_ts;
  * a record is usable for a decision only if it was GENERATED no later than
    decision_ts + max_latency (wall clock). A record produced today about a past date is
    hindsight-contaminated (the model has seen the future) and is rejected;
  * historical replay never calls a model: it only reads records that were cached at the time;
  * fresh calls are only allowed for decisions within max_latency of the current wall clock.
Fail closed: a missing, late, malformed, contradictory or non-research (plumbing) record means
"no agent-assisted entry" in `gate` mode; deterministic baseline entries do not depend on agents.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

RATINGS = ("Buy", "Overweight", "Hold", "Underweight", "Sell")
BIAS = {"Buy": 1, "Overweight": 1, "Hold": 0, "Underweight": -1, "Sell": -1}
SCHEMA_VERSION = "etf-research-record/1"
PROMPT_CONFIG_VERSION = "ta-v0.7.0-market-only-local-vendor/1"
STATUS_RESEARCH = "research"          # produced by a real model run
STATUS_PLUMBING = "plumbing_test"     # scripted local model: never usable
DISABLED_INPUTS = {
    "news": "no point-in-time dated news archive available to this project; upstream vendors would return today's news",
    "social": "no point-in-time sentiment archive; disabled",
    "fundamentals": "ETFs have no single-issuer fundamentals; upstream fundamentals are not point-in-time",
    "macro": "no point-in-time macro vintage data (e.g. ALFRED) wired in; disabled",
}


def _utc(ts) -> dt.datetime:
    t = dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


@dataclass
class ResearchRecord:
    instrument: str
    decision_ts: str                     # ISO-8601 UTC: when the trading decision is made
    data_cutoff: str                     # ISO-8601 UTC: last data timestamp the model could see
    generated_at: str                    # ISO-8601 UTC wall clock when the record was produced
    status: str                          # research | plumbing_test
    timeframes_assessed: list[str]
    rating: str | None
    direction_bias: int
    confidence: float | None             # None: upstream v0.7.0 produces no calibrated confidence
    thesis: str
    counter_thesis: str
    risks: str
    invalidation_conditions: list[str]
    source_timestamps: list[str]
    model: str | None
    provider: str | None
    prompt_config_version: str = PROMPT_CONFIG_VERSION
    schema_version: str = SCHEMA_VERSION
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    candidate: dict | None = None
    disabled_inputs: dict = field(default_factory=lambda: dict(DISABLED_INPUTS))
    data_fingerprint: str | None = None
    temperature: float | None = None
    seed: int | None = None
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def validate(d: dict, decision_ts=None, max_latency_s: int = 3600) -> list[str]:
    """Return the list of reasons the record may NOT be used (empty list = usable)."""
    errs = []
    req = ResearchRecord.__dataclass_fields__
    for k in ("instrument", "decision_ts", "data_cutoff", "generated_at", "status", "rating", "direction_bias",
              "thesis", "counter_thesis", "model", "provider", "run_id"):
        if k not in d:
            errs.append(f"missing field {k}")
    if errs:
        return errs
    unknown = set(d) - set(req)
    if unknown:
        errs.append(f"unknown fields {sorted(unknown)}")
    if d["status"] != STATUS_RESEARCH:
        errs.append(f"status {d['status']!r} is not research")
    if d["rating"] not in RATINGS:
        errs.append(f"rating {d['rating']!r} not in {RATINGS}")
    elif BIAS[d["rating"]] != d["direction_bias"]:
        errs.append("direction_bias contradicts rating")
    if d.get("confidence") is not None and not (0.0 <= float(d["confidence"]) <= 1.0):
        errs.append("confidence outside [0, 1]")
    if not str(d.get("thesis", "")).strip() or not str(d.get("counter_thesis", "")).strip():
        errs.append("thesis and counter-thesis are both required")
    try:
        dec, cut, gen = _utc(d["decision_ts"]), _utc(d["data_cutoff"]), _utc(d["generated_at"])
    except Exception as exc:  # noqa: BLE001
        return errs + [f"bad timestamp: {exc}"]
    if cut > dec:
        errs.append("data_cutoff after decision time (look-ahead)")
    for s in d.get("source_timestamps", []) or []:
        try:
            if _utc(s) > dec:
                errs.append(f"source timestamp {s} after decision time")
        except Exception:  # noqa: BLE001
            errs.append(f"bad source timestamp {s}")
    if decision_ts is not None and _utc(decision_ts) != dec:
        errs.append("record is for a different decision time")
    if gen > dec + dt.timedelta(seconds=max_latency_s):
        errs.append("generated after the decision deadline (late or hindsight-contaminated)")
    return errs


def cache_key(instrument: str, decision_ts: str, candidate: dict, config: dict, data_fingerprint: str) -> str:
    blob = json.dumps({"i": instrument, "t": decision_ts, "c": candidate, "cfg": config, "data": data_fingerprint,
                       "v": PROMPT_CONFIG_VERSION}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:24]


class ResearchService:
    """Cache-first access to research records with call budget, timeout and retries."""

    def __init__(self, cache_dir: Path, mode: str = "replay", max_calls_per_day: int = 2, timeout_s: int = 900,
                 retries: int = 1, max_latency_s: int = 3600, worker_python: Path | None = None,
                 config: dict | None = None, now=None):
        if mode not in ("replay", "forward"):
            raise ValueError(mode)
        self.cache_dir, self.mode = Path(cache_dir), mode
        self.max_calls, self.timeout_s, self.retries = max_calls_per_day, timeout_s, retries
        self.max_latency_s, self.worker_python = max_latency_s, worker_python
        self.config = config or {"analysts": ["market"], "max_debate_rounds": 1}
        self._now = now or (lambda: dt.datetime.now(dt.timezone.utc))
        self.calls_made = 0
        self.audit: list[dict] = []

    def _path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def store(self, rec: ResearchRecord, key: str) -> Path:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        p = self._path(key)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(rec.to_dict(), indent=1, default=str))
        tmp.replace(p)
        return p

    def get(self, instrument: str, decision_ts: str, candidate: dict, data_fingerprint: str) -> tuple[dict | None, list[str]]:
        key = cache_key(instrument, decision_ts, candidate, self.config, data_fingerprint)
        p = self._path(key)
        if p.exists():
            try:
                d = json.loads(p.read_text())
            except Exception as exc:  # noqa: BLE001
                return self._log(None, [f"malformed cache file: {exc}"], key)
            return self._log(d, validate(d, decision_ts, self.max_latency_s), key)
        if self.mode == "replay":
            return self._log(None, ["no record cached at decision time (replay never calls a model)"], key)
        now = self._now()
        if abs((now - _utc(decision_ts)).total_seconds()) > self.max_latency_s:
            return self._log(None, ["fresh call refused: decision time is not now (would be hindsight)"], key)
        if self.calls_made >= self.max_calls:
            return self._log(None, [f"call budget ({self.max_calls}) exhausted"], key)
        last_err = "worker not configured"
        for _ in range(1 + self.retries):
            self.calls_made += 1
            try:
                d = self._call_worker(instrument, decision_ts, candidate)
            except Exception as exc:  # noqa: BLE001
                last_err = f"{type(exc).__name__}: {exc}"
                continue
            errs = validate(d, decision_ts, self.max_latency_s)
            if d.get("status") in (STATUS_RESEARCH, STATUS_PLUMBING):
                self.store(ResearchRecord(**{k: v for k, v in d.items() if k in ResearchRecord.__dataclass_fields__}), key)
            return self._log(d, errs, key)
        return self._log(None, [last_err], key)

    def _call_worker(self, instrument, decision_ts, candidate) -> dict:
        if self.worker_python is None or not Path(self.worker_python).exists():
            raise RuntimeError("TradingAgents environment (.venv-agents) not available")
        raise RuntimeError("live research calls require LLM credentials; none configured in this environment")

    def _log(self, d, errs, key):
        self.audit.append({"key": key, "usable": d is not None and not errs, "reasons": errs,
                           "run_id": (d or {}).get("run_id")})
        return d, errs


def entry_filter_from(service: ResearchService, policy: str, fingerprint_fn):
    """Build the callable the engines accept. policy:
      off       -> 1.0, no research consulted (deterministic baseline)
      advisory  -> 1.0 always; research is fetched and logged only
      gate      -> agent-assisted variant: 1.0 only with a valid record that does not oppose the
                   signal; otherwise 0.0 (fail closed). Never > 1."""
    if policy not in ("off", "advisory", "gate"):
        raise ValueError(policy)

    def f(cand: dict) -> tuple[float, str]:
        if policy == "off":
            return 1.0, "agents off"
        sym, day = cand["sym"], cand["date"]
        decision_ts = f"{str(day)[:10]}T13:25:00+00:00"   # decision made before the 09:30 ET open
        c = {"sym": sym, "pid": cand.get("pid"), "dir": int(cand.get("dir", 0))}
        d, errs = service.get(sym, decision_ts, c, fingerprint_fn(sym, day))
        if policy == "advisory":
            return 1.0, "advisory: " + ("usable" if d and not errs else "; ".join(errs))
        if d is None or errs:
            return 0.0, "gate fail-closed: " + "; ".join(errs)
        if d["direction_bias"] == -int(cand.get("dir", 0)):
            return 0.0, f"gate veto: {d['rating']} opposes signal"
        return 1.0, f"gate pass: {d['rating']}"
    return f


def from_ta_output(out: dict, decision_ts: str, data_cutoff: str, generated_at: str) -> ResearchRecord:
    """Map the worker's ThesisReport-shaped JSON to a ResearchRecord (no invented fields)."""
    rating = out.get("rating") if out.get("rating") in RATINGS else None
    status = STATUS_PLUMBING if out.get("status") == "fake_llm_plumbing_test" else (
        STATUS_RESEARCH if out.get("status") == "ok" else str(out.get("status")))
    inval = [ln.strip() for ln in str(out.get("trader_plan", "")).splitlines()
             if any(w in ln.lower() for w in ("stop", "invalidat", "exit if"))][:5]
    mi = out.get("model_info") or {}
    return ResearchRecord(
        instrument=out.get("ticker"), decision_ts=decision_ts, data_cutoff=data_cutoff, generated_at=generated_at,
        status=status, timeframes_assessed=["1d"], rating=rating, direction_bias=BIAS.get(rating, 0),
        confidence=None, thesis=str(out.get("bull_case") or out.get("final_decision") or ""),
        counter_thesis=str(out.get("bear_case") or ""), risks=str(out.get("risk_debate") or ""),
        invalidation_conditions=inval,
        source_timestamps=[c.get("end") or c.get("curr_date") for c in out.get("tool_calls", [])
                           if c.get("end") or c.get("curr_date")],
        model=mi.get("deep"), provider=mi.get("provider"), candidate=out.get("candidate"),
        notes=out.get("reason") or "")


def run_plumbing(bars, ticker: str, as_of: str, work_dir: Path, agents_python: Path,
                 timeout_s: int = 900) -> tuple[ResearchRecord | None, str]:
    """Run the REAL TradingAgents graph with the scripted local model (no API calls) on our
    point-in-time ETF bars. The result is a plumbing_test record: never usable for trading.

    `bars` (executable daily OHLCV) is cut to sessions STRICTLY before `as_of` before it is written,
    because the decision is made before the open of `as_of` (the worker's own vendor clamp is
    `<= as_of`, which would expose that session's close)."""
    import pandas as pd
    work_dir.mkdir(parents=True, exist_ok=True)
    pit = bars[bars.index < pd.Timestamp(as_of)][["open", "high", "low", "close", "volume"]]
    bars_parquet = work_dir / f"{ticker}_pit.parquet"
    pit.to_parquet(bars_parquet)
    cutoff = f"{pit.index[-1].date()}T21:00:00+00:00"            # that session's 16:00 ET close
    req = {"as_of": as_of, "ticker": ticker, "analysts": ["market"], "candidate": {"sym": ticker},
           "bars_path": str(bars_parquet), "work_dir": str(work_dir / "ta_home"), "provider": None}
    rp, op = work_dir / "request.json", work_dir / "out.json"
    rp.write_text(json.dumps(req))
    t0 = dt.datetime.now(dt.timezone.utc)
    proc = subprocess.run([str(agents_python), "-m", "swingtrader.agents.ta_worker", "--request", str(rp),
                           "--out", str(op), "--fake-llm"], capture_output=True, text=True, timeout=timeout_s,
                          cwd=str(work_dir))
    if not op.exists():
        return None, f"worker exit {proc.returncode}: {proc.stderr[-1500:]}"
    out = json.loads(op.read_text())
    rec = from_ta_output(out, f"{as_of}T13:25:00+00:00", cutoff, t0.isoformat())
    rec.source_timestamps = [cutoff]          # what was actually served, not what the agents asked for
    max_seen = max((str(c.get("end") or c.get("curr_date")) for c in out.get("tool_calls", [])), default=None)
    return rec, (out.get("reason") or "ok") + f"; tool calls requested data up to {max_seen}; served <= {pit.index[-1].date()}"

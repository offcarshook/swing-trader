"""Append-only experiment log and the holdout guard.

Every research run appends a JSON line (timestamp, git commit, config hash,
what ran, headline numbers). Failed experiments are logged exactly like
successful ones. The HoldoutGuard records every evaluation on the holdout
period: evaluating a DIFFERENT candidate/config after the holdout has been
touched raises unless an explicit reason is given -- and that reason is logged
and printed in every subsequent report.
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
from pathlib import Path

from swingtrader.config import PROJECT_ROOT, config_hash, resolve


def git_commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=PROJECT_ROOT,
                             capture_output=True, text=True, timeout=5)
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=PROJECT_ROOT,
                               capture_output=True, text=True, timeout=5).stdout.strip()
        return (out.stdout.strip() or "uncommitted") + ("+dirty" if dirty else "")
    except Exception:  # noqa: BLE001
        return "unknown"


class ExperimentLog:
    def __init__(self, path: str | Path = "results/experiment_log.jsonl"):
        self.path = resolve(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, kind: str, payload: dict, cfg: dict | None = None) -> dict:
        rec = {
            "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "kind": kind,
            "git": git_commit(),
            "config_hash": config_hash(cfg) if cfg else None,
            **payload,
        }
        with open(self.path, "a") as fh:
            fh.write(json.dumps(rec, default=str) + "\n")
        return rec

    def read(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]


class HoldoutReuseError(RuntimeError):
    pass


class HoldoutGuard:
    def __init__(self, path: str | Path = "results/holdout_registry.json"):
        self.path = resolve(path)

    def _load(self) -> list[dict]:
        return json.loads(self.path.read_text()) if self.path.exists() else []

    def authorize(self, candidate_id: str, cand_hash: str, override_reason: str | None = None) -> dict:
        entries = self._load()
        seen = {(e["candidate_id"], e["hash"]) for e in entries}
        if entries and (candidate_id, cand_hash) not in seen:
            if not override_reason:
                raise HoldoutReuseError(
                    f"holdout already used for {sorted(seen)}; evaluating a different candidate "
                    "is tuning on the test set. Pass an explicit override reason to proceed (it is logged).")
        rec = {
            "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "candidate_id": candidate_id, "hash": cand_hash,
            "evaluation_number": len(entries) + 1,
            "override_reason": override_reason,
            "git": git_commit(),
        }
        entries.append(rec)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(entries, indent=1))
        return rec

    def history(self) -> list[dict]:
        return self._load()

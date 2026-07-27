"""Append-only eval run registry. misc/docs/08-evals.md §7.

SQLite at data/evals/registry.db + a JSON mirror per run, following the
project's existing store pattern (src/rehearsal/store/db.py, ids.py — read,
not imported: evals may depend on anything per misc/docs/15-workstreams.md
§4, but this stays a self-contained sqlite3 usage rather than pulling in
the store package's migration machinery for one table).

Kept from the full §7 schema: run_id, created_at, eval_id, split, n,
git_commit, git_dirty, metrics_json, intervals_json, gate, gate_detail,
notes. Dropped as decorative for this phase (no live model host exists —
see NOT-BUILT-YET.md): suite_version, prompt_role/version/sha256,
model_role/id/quant/sha256, runtime, dataset_path/sha256, seed,
temperature/top_p/max_tokens, host_class, artifact_path, unseal_reason.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import time
from pathlib import Path

from rehearsal.evals.result import EvalResult
from rehearsal.store.ids import new_ulid

DB_PATH = Path("data/evals/registry.db")
RUNS_DIR = Path("data/evals/runs")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS eval_runs (
    run_id         TEXT PRIMARY KEY,
    created_at     TEXT NOT NULL,
    eval_id        TEXT NOT NULL,
    split          TEXT NOT NULL,
    n              INTEGER NOT NULL,
    git_commit     TEXT NOT NULL,
    git_dirty      INTEGER NOT NULL,
    metrics_json   TEXT NOT NULL,
    intervals_json TEXT NOT NULL,
    gate           TEXT NOT NULL,
    gate_detail    TEXT NOT NULL,
    notes          TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_eval_runs_eval ON eval_runs(eval_id, created_at);
CREATE INDEX IF NOT EXISTS idx_eval_runs_split ON eval_runs(split, created_at);

CREATE TRIGGER IF NOT EXISTS eval_runs_no_update BEFORE UPDATE ON eval_runs
BEGIN SELECT RAISE(ABORT, 'eval_runs is append-only'); END;

CREATE TRIGGER IF NOT EXISTS eval_runs_no_delete BEFORE DELETE ON eval_runs
BEGIN SELECT RAISE(ABORT, 'eval_runs is append-only'); END;
"""


class RegistryError(RuntimeError):
    """A dirty tree tried to record a TEST/live run (§7: not reproducible)."""


def _git_state() -> tuple[str, bool]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"], capture_output=True, text=True, check=True
            ).stdout.strip()
        )
        return commit, dirty
    except Exception:
        # ponytail: fail closed — an unreadable git state acts dirty rather
        # than silently letting an unreproducible TEST/live run through.
        return "unknown", True


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA)
    return conn


def record_run(result: EvalResult, *, db_path: Path = DB_PATH, runs_dir: Path = RUNS_DIR) -> str:
    """Append one immutable run record; returns the run_id.

    Raises RegistryError if the git tree is dirty and result.split is
    "test" or "live" — a number produced from uncommitted code cannot be
    reproduced, so it is refused rather than recorded (§7).
    """
    git_commit, git_dirty = _git_state()
    if git_dirty and result.split in ("test", "live"):
        raise RegistryError(
            f"refusing to record a {result.split!r}-split run on a dirty git tree "
            "(misc/docs/08-evals.md §7)"
        )

    run_id = new_ulid()
    row = {
        "run_id": run_id,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "eval_id": result.eval_id,
        "split": result.split,
        "n": result.n,
        "git_commit": git_commit,
        "git_dirty": int(git_dirty),
        "metrics_json": json.dumps(result.metrics),
        "intervals_json": json.dumps(result.intervals),
        "gate": result.gate.value,
        "gate_detail": result.gate_detail,
        "notes": result.notes,
    }
    conn = _connect(db_path)
    try:
        conn.execute(
            "INSERT INTO eval_runs (run_id, created_at, eval_id, split, n, git_commit, "
            "git_dirty, metrics_json, intervals_json, gate, gate_detail, notes) "
            "VALUES (:run_id, :created_at, :eval_id, :split, :n, :git_commit, :git_dirty, "
            ":metrics_json, :intervals_json, :gate, :gate_detail, :notes)",
            row,
        )
        conn.commit()
    finally:
        conn.close()

    runs_dir.mkdir(parents=True, exist_ok=True)
    (runs_dir / f"{run_id}.json").write_text(json.dumps(row, indent=2), encoding="utf-8")
    return run_id


def read_run(run_id: str, *, runs_dir: Path = RUNS_DIR) -> dict[str, object]:
    """Re-read a recorded run from its JSON mirror without touching SQLite."""
    path = runs_dir / f"{run_id}.json"
    data: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    return data

"""registry.py — the append-only eval run registry. misc/docs/08-evals.md §7."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from rehearsal.evals import registry
from rehearsal.evals.result import EvalResult, GateOutcome


def _result(split: str = "fixture") -> EvalResult:
    return EvalResult(
        eval_id="EV-00",
        split=split,  # type: ignore[arg-type]
        n=58,
        metrics={"extractor_conformance": 1.0},
        intervals={},
        gate=GateOutcome.PASS,
        gate_detail="extractor_conformance 1.00 (58/58) == 1.00 required",
        artifacts=[],
        notes="clean",
    )


def test_record_run_on_clean_tree_succeeds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registry, "_git_state", lambda: ("abc123", False))
    db_path = tmp_path / "registry.db"
    runs_dir = tmp_path / "runs"

    run_id = registry.record_run(_result("dev"), db_path=db_path, runs_dir=runs_dir)

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT eval_id, gate, git_dirty FROM eval_runs WHERE run_id = ?", (run_id,)
    ).fetchone()
    conn.close()
    assert row == ("EV-00", "pass", 0)
    assert (runs_dir / f"{run_id}.json").exists()


def test_record_run_refuses_dirty_test_split(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(registry, "_git_state", lambda: ("abc123", True))
    with pytest.raises(registry.RegistryError):
        registry.record_run(
            _result("test"), db_path=tmp_path / "registry.db", runs_dir=tmp_path / "runs"
        )


def test_record_run_refuses_dirty_live_split(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(registry, "_git_state", lambda: ("abc123", True))
    with pytest.raises(registry.RegistryError):
        registry.record_run(
            _result("live"), db_path=tmp_path / "registry.db", runs_dir=tmp_path / "runs"
        )


def test_record_run_allows_dirty_dev_split(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registry, "_git_state", lambda: ("abc123", True))
    run_id = registry.record_run(
        _result("dev"), db_path=tmp_path / "registry.db", runs_dir=tmp_path / "runs"
    )
    assert run_id


def test_eval_runs_table_is_append_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registry, "_git_state", lambda: ("abc123", False))
    db_path = tmp_path / "registry.db"
    run_id = registry.record_run(_result("dev"), db_path=db_path, runs_dir=tmp_path / "runs")

    conn = sqlite3.connect(db_path)
    with pytest.raises(sqlite3.Error):
        conn.execute("UPDATE eval_runs SET gate = 'fail' WHERE run_id = ?", (run_id,))
    with pytest.raises(sqlite3.Error):
        conn.execute("DELETE FROM eval_runs WHERE run_id = ?", (run_id,))
    conn.close()


def test_read_run_roundtrips_json_mirror(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registry, "_git_state", lambda: ("abc123", False))
    runs_dir = tmp_path / "runs"
    run_id = registry.record_run(
        _result("dev"), db_path=tmp_path / "registry.db", runs_dir=runs_dir
    )
    row = registry.read_run(run_id, runs_dir=runs_dir)
    assert row["run_id"] == run_id
    assert row["eval_id"] == "EV-00"

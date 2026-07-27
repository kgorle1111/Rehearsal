"""Coverage for `src/rehearsal/cli.py`'s `review`/`demo` commands (commit
536fbcb, landed out-of-band — see NOT-BUILT-YET.md P-extra). Added at the
P5 review gate; nobody owns this file yet.

No test here calls Ollama or reaches a real network. `cmd_demo`'s
scenario-approval gate (Golden Rule: the bank has no override) is tested
against WS7's real, currently-pending seed scenarios — the approval gate
must refuse them exactly as it refuses any other unapproved scenario.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

import rehearsal.cli as cli


def _make_scenario(path: Path, scenario_id: str, status: str) -> None:
    path.write_text(
        json.dumps(
            {
                "scenario_id": scenario_id,
                "schema_version": "1.0.0",
                "clinical_state": {
                    "condition": "c",
                    "medications": [],
                    "symptom_timeline": [],
                    "allergies": [],
                    "emotional_state": "worried",
                    "health_literacy": "low",
                    "language_variety": "es-MX",
                    "onset": "today",
                },
                "difficulty": {
                    "numeric_density": 1,
                    "idiom_load": 1,
                    "emotional_load": 1,
                    "register_distance": 1,
                },
                "term_manifest": [],
                "provenance": {"author": "test", "limitations": []},
                "review": {"status": status, "reviewer": None},
            }
        )
    )


# ---- cmd_review -----------------------------------------------------------


def test_review_reports_nothing_pending_when_all_approved(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _make_scenario(tmp_path / "sc_1.json", "sc_1", "approved")
    args = argparse.Namespace(scenarios=tmp_path)
    rc = cli.cmd_review(args)
    assert rc == 0
    assert "No pending scenarios" in capsys.readouterr().out


def test_review_rejects_empty_reviewer_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _make_scenario(tmp_path / "sc_1.json", "sc_1", "pending")
    monkeypatch.setattr("builtins.input", lambda *_: "")
    args = argparse.Namespace(scenarios=tmp_path)
    rc = cli.cmd_review(args)
    assert rc == 1
    assert "reviewer name is required" in capsys.readouterr().out


def test_review_approve_writes_status_and_reviewer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario_path = tmp_path / "sc_1.json"
    _make_scenario(scenario_path, "sc_1", "pending")
    answers = iter(["Kannishk", "y"])
    monkeypatch.setattr("builtins.input", lambda *_: next(answers))
    args = argparse.Namespace(scenarios=tmp_path)
    rc = cli.cmd_review(args)
    assert rc == 0
    data = json.loads(scenario_path.read_text())
    assert data["review"] == {"status": "approved", "reviewer": "Kannishk"}


# ---- cmd_demo ---------------------------------------------------------


def test_demo_returns_error_when_no_scenarios_found(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = argparse.Namespace(
        scenario=None, scenarios=tmp_path, model="m", host="http://localhost:11434"
    )
    rc = cli.cmd_demo(args)
    assert rc == 1
    assert "No scenarios found" in capsys.readouterr().err


def test_demo_refuses_unapproved_scenario_without_touching_ollama(
    seed_scenarios_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # WS7's real seed scenarios are all review.status="pending" (per
    # NOT-BUILT-YET.md) — the demo path must refuse to run one, and it must
    # do so before ever constructing a live-model client.
    args = argparse.Namespace(
        scenario="sc_0001_dm2_metformin_counseling",
        scenarios=seed_scenarios_dir,
        model="m",
        host="http://localhost:11434",
    )
    rc = cli.cmd_demo(args)
    assert rc == 1
    err = capsys.readouterr().err
    assert "rehearsal review" in err

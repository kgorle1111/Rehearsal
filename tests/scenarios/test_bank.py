from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from rehearsal.contracts import ScenarioRecord, ScenarioReview
from rehearsal.scenarios.bank import (
    ScenarioBank,
    ScenarioNotApproved,
    load_scenario_file,
    scenario_from_dict,
    scenario_to_dict,
)
from rehearsal.scenarios.graph import validate_clinical_state

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "scenarios"


def test_seed_scenarios_exist() -> None:
    files = sorted(DATA_DIR.glob("*.json"))
    assert len(files) >= 3, "expect at least 3 hand-authored seed scenarios"


@pytest.mark.parametrize("path", sorted(DATA_DIR.glob("*.json")), ids=lambda p: p.stem)
def test_every_seed_scenario_round_trips_and_validates(path: Path) -> None:
    record, provenance = load_scenario_file(path)
    assert isinstance(record, ScenarioRecord)

    # Round-trip: dict -> ScenarioRecord -> dict -> ScenarioRecord is stable.
    round_tripped = scenario_from_dict(scenario_to_dict(record))
    assert round_tripped == record

    # Every seed scenario's clinical state is internally well-formed.
    assert validate_clinical_state(record.clinical_state) == []

    # Every seed scenario is honestly marked as unreviewed/agent-authored —
    # a model must never mark its own content "approved".
    assert record.review.status != "approved"
    assert "agent" in provenance.author or "unreviewed" in provenance.author


def test_unapproved_scenario_cannot_load() -> None:
    """The key DoD item: ScenarioBank.get() on a pending-review scenario
    raises ScenarioNotApproved, with no override anywhere in the call."""
    bank = ScenarioBank(DATA_DIR)
    # Every seed scenario ships review.status="pending" (no human has
    # reviewed agent-authored content yet).
    scenario_id = bank.list_ids()[0]
    with pytest.raises(ScenarioNotApproved):
        bank.get(scenario_id)


def test_get_has_no_override_parameter() -> None:
    """There is no --force/bypass flag anywhere in ScenarioBank.get()."""
    params = inspect.signature(ScenarioBank.get).parameters
    assert set(params) == {"self", "scenario_id"}


def test_load_all_excludes_unapproved() -> None:
    bank = ScenarioBank(DATA_DIR)
    # No seed scenario is approved yet (a human has not reviewed them).
    assert bank.load_all() == ()


def test_load_all_returns_only_approved(tmp_path: Path) -> None:
    """Synthetic fixture proving load_all() *would* return an approved
    scenario if one existed, without relying on ever marking a real seed
    scenario approved ourselves."""
    approved_dir = tmp_path
    # Build a minimal valid scenario dict from scratch, one pending one approved.
    base = scenario_to_dict(_minimal_record("sc_test_pending", "pending"))
    approved = scenario_to_dict(_minimal_record("sc_test_approved", "approved"))
    (approved_dir / "pending.json").write_text(json.dumps(base))
    (approved_dir / "approved.json").write_text(json.dumps(approved))

    bank = ScenarioBank(approved_dir)
    loaded = bank.load_all()
    assert len(loaded) == 1
    assert loaded[0].scenario_id == "sc_test_approved"
    assert bank.get("sc_test_approved").scenario_id == "sc_test_approved"
    with pytest.raises(ScenarioNotApproved):
        bank.get("sc_test_pending")


def _minimal_record(scenario_id: str, status: str) -> ScenarioRecord:
    from rehearsal.contracts import ClinicalState

    return ScenarioRecord(
        scenario_id=scenario_id,
        schema_version="1.0.0",
        clinical_state=ClinicalState(
            condition="asthma",
            medications=(),
            symptom_timeline=(),
            allergies=(),
            emotional_state="calm",
            health_literacy="low",
            language_variety="es-neutral",
            onset="today",
        ),
        difficulty={"band": "introductory"},
        term_manifest=(),
        review=ScenarioReview(status=status, reviewer="test" if status == "approved" else None),
    )

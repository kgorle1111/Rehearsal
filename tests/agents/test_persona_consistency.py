from __future__ import annotations

import re
from pathlib import Path

from rehearsal.agents.clinician import ClinicianAgent
from rehearsal.agents.model_client import ConversationNode, ScriptedModelClient
from rehearsal.agents.patient import PatientAgent
from rehearsal.agents.persona import check_persona_consistency
from rehearsal.contracts import SpeakerRole
from rehearsal.scenarios.bank import load_scenario_file

REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_PATH = REPO_ROOT / "data" / "scenarios" / "sc_0001_dm2_metformin_counseling.json"


def test_full_session_persona_consistency_rate() -> None:
    """Run a full simulated session (ScriptedModelClient, sc_0001) through
    the checker and assert + print the measured rate."""
    record, _ = load_scenario_file(SCENARIO_PATH)
    state = record.clinical_state

    clinician = ClinicianAgent(client=ScriptedModelClient())
    patient = PatientAgent(client=ScriptedModelClient())

    utterances: list[str] = []
    for med in state.medications:
        node = ConversationNode(speaker=SpeakerRole.CLINICIAN, facts=(med,))
        utterances.append(clinician.take_turn(state, node).reply_text)
    for entry in state.symptom_timeline:
        node = ConversationNode(speaker=SpeakerRole.PATIENT, facts=(entry,))
        utterances.append(patient.take_turn(state, node).reply_text)
    for allergy in state.allergies:
        node = ConversationNode(speaker=SpeakerRole.PATIENT, facts=(allergy,))
        utterances.append(patient.take_turn(state, node).reply_text)

    report = check_persona_consistency(tuple(utterances), state)
    print(
        f"persona_consistency_rate = {report.rate:.2f} "
        f"({report.consistent_utterances}/{report.total_utterances})"
    )
    assert report.total_utterances == len(utterances) > 0
    assert report.rate == 1.0
    assert report.violations == ()


def test_checker_detects_a_real_contradiction() -> None:
    """Prove the checker isn't a rubber stamp: hand-craft an utterance that
    names a real medication with the WRONG dose and confirm it is flagged."""
    # sc_0001's real fact is metformin 500mg twice a day; this utterance
    # names the drug but states a dose (850) that matches neither the
    # recorded dose nor frequency.
    record, _ = load_scenario_file(SCENARIO_PATH)
    state = record.clinical_state
    contradictory = "You should take metformin 850mg once a day."
    report = check_persona_consistency((contradictory,), state)
    assert report.rate == 0.0
    assert len(report.violations) == 1
    assert "metformin" in report.violations[0].detail


def test_empty_session_reports_rate_one() -> None:
    record, _ = load_scenario_file(SCENARIO_PATH)
    report = check_persona_consistency((), record.clinical_state)
    assert report.rate == 1.0
    assert report.total_utterances == 0


def _parse_prompt_front_matter(path: Path) -> dict[str, str]:
    """Minimal stdlib front-matter reader — no pyyaml dependency exists in
    this project (checked; not declared in pyproject.toml), so this reads
    only the flat ``key: value`` lines a prompt header actually needs
    validated. Multi-line block scalars (``notes: >``) are intentionally
    not reconstructed here, only detected as present."""
    lines = path.read_text().splitlines()
    assert lines[0].strip() == "---", f"{path} does not start with a front-matter fence"
    end = lines[1:].index("---") + 1
    key_re = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$")
    result: dict[str, str] = {}
    for line in lines[1:end]:
        m = key_re.match(line)
        if m:
            result[m.group(1)] = m.group(2)
    return result


def test_prompt_files_carry_valid_version_front_matter() -> None:
    prompt_files = {
        "clinician": REPO_ROOT / "prompts" / "clinician" / "v1.md",
        "patient": REPO_ROOT / "prompts" / "patient" / "v1.md",
        "coach": REPO_ROOT / "prompts" / "coach" / "v1.md",
    }
    for role, path in prompt_files.items():
        assert path.exists(), f"missing prompt file: {path}"
        header = _parse_prompt_front_matter(path)
        assert header["role"] == role
        assert header["prompt_id"] == f"{role}/v1"
        assert header["schema"]  # non-empty

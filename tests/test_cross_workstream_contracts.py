"""Cross-workstream contract tests — the seams BUILD.md §7 says the
orchestrator bridges: scorer<->scenario, agent<->scenario, orchestrator<->
scenario-bank. Each test below exercises two workstreams' *public* APIs
against the frozen `rehearsal.contracts` types only — no reaching into
either side's private internals.

This file does not re-test what WS1/WS3/WS4/WS7 already cover in their own
unit suites (extractor correctness, persona-consistency rate, FSM
reachability, scenario approval-gate). It only proves the pieces actually
fit together when wired with real (not fabricated) data from one side.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

import pytest

from rehearsal.agents.clinician import ClinicianAgent
from rehearsal.agents.model_client import ConversationNode, ScriptedModelClient
from rehearsal.agents.patient import PatientAgent
from rehearsal.contracts import ScenarioRecord, ScoreStatus, SpeakerRole, TurnRecord
from rehearsal.orchestrator.eventlog import Event
from rehearsal.orchestrator.loop import RunConfig, SessionOrchestrator
from rehearsal.orchestrator.scheduler import GraphNode
from rehearsal.scenarios.bank import ScenarioProvenance
from rehearsal.scoring.engine import score_turn
from tests.runtime.fakes import FakeAudioIO, FakeModelHosts, LogicalClock

SC_0001 = "sc_0001_dm2_metformin_counseling"


# ---------------------------------------------------------------------------
# Seam 1: scorer <-> scenario (WS1 <-> WS7)
# ---------------------------------------------------------------------------


def test_term_manifest_flows_into_score_turn_without_error(
    load_seed_scenario: Callable[[str], tuple[ScenarioRecord, ScenarioProvenance]],
    make_turn_record: Callable[..., TurnRecord],
) -> None:
    """A `TurnRecord` built from a real WS7 seed scenario's `term_manifest`
    (using each entry's `en`/`es` acceptable renderings, not a fabricated
    string) scores cleanly through WS1's `score_turn()` — the two
    workstreams agree on what a "clean" rendering looks like.

    This is a genuine gap: WS1's own tests build `TurnRecord`s from
    hand-written strings (`tests/scoring/test_engine.py`); WS7's own tests
    never call the scorer at all. Neither side's suite proves the manifest
    a real scenario ships is actually extractor-clean.
    """
    record, _ = load_seed_scenario(SC_0001)
    assert record.term_manifest, "sc_0001 must ship a non-empty term manifest to test this seam"

    source = ". ".join(t.en for t in record.term_manifest) + "."
    rendering = ". ".join(t.es for t in record.term_manifest) + "."
    turn = make_turn_record(source, rendering)

    result = score_turn(turn)

    assert result.turn_id == turn.turn_id
    assert result.status is ScoreStatus.EXTRACTOR_ONLY
    # every term_manifest entry is marked as an accepted (en, es) pairing —
    # scoring the manifest against itself must not manufacture a critical
    # finding, or the manifest and the extractors disagree about ground truth.
    critical = [f for f in result.findings if f.severity.value == "critical"]
    assert critical == [], f"manifest-clean rendering scored critical: {critical}"


# ---------------------------------------------------------------------------
# Seam 2: agent <-> scenario (WS3 <-> WS7)
# ---------------------------------------------------------------------------


def test_real_clinical_state_flows_into_clinician_and_patient_agents(
    load_seed_scenario: Callable[[str], tuple[ScenarioRecord, ScenarioProvenance]],
) -> None:
    """A real WS7 `ClinicalState` (not a hand-built one) drives both agents
    without error, for every fact category the state carries. WS3's own
    persona test already covers sc_0001 end to end for the numeric
    consistency rate; this test's job is narrower and different: prove the
    *type* flowing out of `load_scenario_file` is accepted as-is by both
    agent classes with no adaptation layer in between.
    """
    record, _ = load_seed_scenario(SC_0001)
    state = record.clinical_state
    clinician = ClinicianAgent(client=ScriptedModelClient())
    patient = PatientAgent(client=ScriptedModelClient())

    assert state.medications, "sc_0001 must carry at least one medication to test this seam"
    for med in state.medications:
        node = ConversationNode(speaker=SpeakerRole.CLINICIAN, facts=(med,))
        turn = clinician.take_turn(state, node)
        assert turn.reply_text

    assert state.allergies, "sc_0001 must carry at least one allergy to test this seam"
    for allergy in state.allergies:
        node = ConversationNode(speaker=SpeakerRole.PATIENT, facts=(allergy,))
        turn = patient.take_turn(state, node)
        assert turn.reply_text


# ---------------------------------------------------------------------------
# Seam 3: orchestrator <-> real scenario bank (WS4 <-> WS7) — a real gap
# ---------------------------------------------------------------------------


def test_real_scenario_bank_does_not_satisfy_orchestrators_scenariobank_protocol(
    seed_scenarios_dir: object,
) -> None:
    """Documents a genuine, currently-unresolved integration gap.

    `SessionOrchestrator` (src/rehearsal/orchestrator/loop.py) is built
    against a structural `ScenarioBank` Protocol requiring
    `entry_node(scenario_id, seed) -> GraphNode` and
    `successor(node, seed) -> GraphNode | None` — graph-traversal calls.

    WS7's real `rehearsal.scenarios.bank.ScenarioBank` (src/rehearsal/
    scenarios/bank.py) has no graph at all: it exposes `get`, `get_provenance`,
    `load_all`, `list_ids` — a flat, non-traversable store. WS7 was never
    asked to build node traversal (see model_client.py's own docstring,
    which says the same thing from the agents side: "WS7 shipped
    ClinicalState and its validator, not node traversal").

    So `SessionOrchestrator(..., bank=real_bank, ...)` constructs fine
    (bank is only used inside `run()`), but `real_bank` does not have
    `entry_node`/`successor` at all — calling `run()` with it fails with
    `AttributeError`, not a graceful degradation. This test proves that
    failure exactly, so the gap is visible instead of silently worked
    around by a caller reaching for `FakeScenarioBank` and forgetting why.
    """
    from rehearsal.scenarios.bank import ScenarioBank as RealScenarioBank

    real_bank = RealScenarioBank(seed_scenarios_dir)  # type: ignore[arg-type]
    assert not hasattr(real_bank, "entry_node")
    assert not hasattr(real_bank, "successor")

    orch = SessionOrchestrator(
        store=_StoreStub(),
        hosts=FakeModelHosts(),
        bank=real_bank,  # type: ignore[arg-type]  # real bank lacks entry_node/successor entirely
        audio=FakeAudioIO(),
        clock=LogicalClock(),
    )
    cfg = RunConfig(scenario_id=SC_0001, trainee_id="trainee-1", max_turns=2, root_seed=1)

    with pytest.raises(AttributeError):
        import asyncio

        asyncio.run(orch.run(cfg, "ses_gap_test"))


class _StoreStub:
    """Minimal Store double — only needs to survive up to the
    `entry_node` call the gap test above fails on, so it does not replay
    WS4's own `tests/runtime/fakes.py` store double (there isn't one; WS4's
    tests use an in-memory `EventLog` directly, which is out of this
    workstream's ownership to import here for a one-call smoke test)."""

    def __init__(self) -> None:
        self._events: list[Event] = []

    def append(
        self,
        session_id: str,
        kind: str,
        payload: dict[str, object] | None = None,
        *,
        turn_index: int | None = None,
        ts_ms: int = 0,
        mono_ms: int = 0,
    ) -> Event:
        event = Event(
            seq=len(self._events) + 1,
            session_id=session_id,
            turn_index=turn_index,
            kind=kind,
            ts_ms=ts_ms,
            mono_ms=mono_ms,
            payload=payload or {},
            prev_hash="0" * 64,
            hash="0" * 64,
        )
        self._events.append(event)
        return event

    def events_for(self, session_id: str) -> list[Event]:
        return [e for e in self._events if e.session_id == session_id]


# Referenced only for the type checker's sake — GraphNode is not
# instantiated directly in this file, it's part of the documented gap above.
_ = GraphNode


# ---------------------------------------------------------------------------
# Import boundary: agents/ must never import scoring/ (WS5 isolation claim)
# ---------------------------------------------------------------------------
#
# WS4 already has `tests/runtime/test_no_scoring_import.py`, which checks
# `runtime/`, `orchestrator/` and `voice/`. `agents/` sits on the same side
# of the isolation boundary (misc/docs/15-workstreams.md §4 — the
# clinician/patient agents must not see grading/rubric internals) and
# `coach.py`'s own docstring claims "never import rehearsal.scoring", but
# no test enforced that claim anywhere. This closes that specific gap using
# the same static-grep approach WS4 used, without duplicating WS4's file or
# its checked directories.
_AGENTS_ROOT = Path(__file__).resolve().parent.parent / "src" / "rehearsal" / "agents"
_SCORING_IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+rehearsal\.scoring\b", re.MULTILINE)


def test_no_agents_module_imports_scoring() -> None:
    offenders = [
        str(path)
        for path in _AGENTS_ROOT.rglob("*.py")
        if _SCORING_IMPORT_RE.search(path.read_text())
    ]
    assert not offenders, f"forbidden import of rehearsal.scoring in: {offenders}"

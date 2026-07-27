"""Shared fault-injection surface, not owned by any single workstream.

WS4 already has a solid, dedicated fault-injection test for crash-resume
determinism at `tests/runtime/test_resume.py`
(`test_twenty_mid_turn_kills_resolve_correctly_and_deterministically`) — it
is not duplicated here.

This file covers a genuine gap found while auditing the other workstreams'
failure paths per `misc/docs/14-testing-strategy.md` §11 (the fault
catalogue) and BUILD.md's WS-TEST brief: WS1's `score_turn()` had a
documented failure mode (a grader call fails) with no test proving the
documented behaviour actually happened — it didn't, until the orchestrator
fixed `run_grader()` during the P3 gate (see the test below).
"""

from __future__ import annotations

from typing import Literal

from rehearsal.contracts import Direction, ScoreStatus, TurnRecord
from rehearsal.scoring.engine import score_turn
from rehearsal.scoring.grader import GraderOutput


class _RaisingGraderClient:
    """Simulates fault F-01/F-02 from misc/docs/14-testing-strategy.md §11.1
    (grader returns malformed JSON / a socket dies) — from `engine.py`'s
    point of view, any of those faults surface as the client raising
    instead of returning a `GraderOutput`."""

    def grade(
        self,
        *,
        source: str,
        rendering: str,
        direction: Literal["en_to_es", "es_to_en"],
        speaker: Literal["clinician", "patient"],
    ) -> GraderOutput:
        raise ValueError("malformed grader response")


def _turn() -> TurnRecord:
    return TurnRecord(
        turn_id="t1",
        session_id="s1",
        direction=Direction.EN_TO_ES,
        source_utterance="Take 500 mg once daily.",
        source_lang="en",
        rendering_transcript="Tome 250 miligramos una vez al dia.",
    )


def test_grader_client_exception_degrades_instead_of_crashing_the_turn() -> None:
    """Was xfail (BUG, reported to WS1 — run_grader() had no try/except
    around client.grade()); fixed in src/rehearsal/scoring/grader.py by the
    orchestrator during the P3 gate. A failing grader now degrades the turn
    to extractor-only instead of crashing it, as engine.py's own docstring
    always promised."""
    turn = _turn()
    record = score_turn(turn, _RaisingGraderClient())
    assert record.status == ScoreStatus.EXTRACTOR_ONLY
    assert record.extractor_findings  # dosage substitution still caught deterministically

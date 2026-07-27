"""Shared fault-injection surface, not owned by any single workstream.

WS4 already has a solid, dedicated fault-injection test for crash-resume
determinism at `tests/runtime/test_resume.py`
(`test_twenty_mid_turn_kills_resolve_correctly_and_deterministically`) — it
is not duplicated here.

This file covers a genuine gap found while auditing the other workstreams'
failure paths per `misc/docs/14-testing-strategy.md` §11 (the fault
catalogue) and BUILD.md's WS-TEST brief: WS1's `score_turn()` has a
documented failure mode (a grader call fails) with no test proving the
documented behaviour actually happens.
"""

from __future__ import annotations

from typing import Literal

import pytest

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
        rendering_transcript="Tome 500 miligramos una vez al dia.",
    )


@pytest.mark.xfail(
    reason=(
        "BUG (not fixed here — WS1 owns src/rehearsal/scoring/engine.py, "
        "outside this workstream's ownership per BUILD.md §1 rule 8): "
        "engine.py's own module docstring says a grader client's absence "
        "'degrades the status rather than raising' (engine.py:26-29), and "
        "run_grader()'s docstring says the same for an unavailable grader "
        "(grader.py:69-70). But score_turn() calls "
        "`run_grader(grader_client, ...)` with no try/except around the "
        "client.grade() call inside run_grader() — a grader client that "
        "raises (fault F-01/F-02/F-04/F-06 in "
        "misc/docs/14-testing-strategy.md §11.1: malformed JSON, wrong "
        "shape, truncated response, socket death) propagates the raw "
        "exception out of score_turn() and crashes the whole turn instead "
        "of degrading to ScoreStatus.EXTRACTOR_ONLY with the extractor "
        "findings preserved. Reported to WS1; not fixed here."
    ),
    strict=True,
)
def test_grader_client_exception_degrades_instead_of_crashing_the_turn() -> None:
    turn = _turn()
    # This is what the documented contract promises: a failing grader
    # degrades the turn to extractor-only, it does not raise out of
    # score_turn(). Today it raises — this assertion never runs because
    # the ValueError propagates first, which is exactly the bug.
    record = score_turn(turn, _RaisingGraderClient())
    assert record.status == ScoreStatus.EXTRACTOR_ONLY
    assert record.extractor_findings  # dosage substitution still caught deterministically

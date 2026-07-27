"""Proves GraderProgram delegates to a GraderClient unchanged (docs/04 §10.2)."""

from __future__ import annotations

from rehearsal.optimise.program import GraderContext, GraderProgram
from rehearsal.scoring.grader import StubGraderClient


def test_call_delegates_to_client_and_returns_its_output() -> None:
    program = GraderProgram(instruction="grade it", demos=(), client=StubGraderClient())
    ctx = GraderContext(
        source="Tomo dos pastillas.",
        rendering="I take two pills.",
        direction="es_to_en",
        speaker="patient",
    )
    out = program(ctx)
    assert out.abstain is False
    assert out.findings == ()
    assert out.clean_reason == "stub: no model host wired"

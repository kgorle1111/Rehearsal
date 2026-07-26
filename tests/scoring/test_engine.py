"""Smoke tests for the top-level entry point: TurnRecord in, ScoreRecord out."""

from __future__ import annotations

from rehearsal.contracts import Direction, ScoreStatus, TurnRecord
from rehearsal.scoring.engine import score_turn
from rehearsal.scoring.grader import StubGraderClient


def _turn(source: str, rendering: str, direction: Direction = Direction.EN_TO_ES) -> TurnRecord:
    return TurnRecord(
        turn_id="t1",
        session_id="s1",
        direction=direction,
        source_utterance=source,
        source_lang="en" if direction == Direction.EN_TO_ES else "es",
        rendering_transcript=rendering,
    )


def test_score_turn_with_no_grader_client_is_extractor_only() -> None:
    turn = _turn("Take 500 mg once daily.", "Tome 250 miligramos una vez al dia.")
    record = score_turn(turn)
    assert record.turn_id == "t1"
    assert record.status == ScoreStatus.EXTRACTOR_ONLY
    assert record.model_findings == ()
    # a dose substitution (500mg -> 250mg) should have been caught deterministically
    assert any(f.extractor_name == "dosage" for f in record.extractor_findings)
    assert any(f.severity.value == "critical" for f in record.findings)


def test_score_turn_with_stub_grader_is_complete() -> None:
    turn = _turn("Take 500 mg once daily.", "Tome 500 miligramos una vez al dia.")
    record = score_turn(turn, StubGraderClient())
    assert record.status == ScoreStatus.COMPLETE
    # clean rendering: no dosage mismatch expected
    assert not any(f.extractor_name == "dosage" for f in record.findings)


def test_score_turn_empty_rendering_fails_without_charging_findings() -> None:
    turn = _turn("Take 500 mg once daily.", "   ")
    record = score_turn(turn)
    assert record.status == ScoreStatus.FAILED
    assert record.findings == ()

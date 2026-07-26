"""Top-level entry point. misc/docs/06-scoring-engine.md §2.1. TurnRecord in, ScoreRecord out."""

from __future__ import annotations

from typing import Literal

from rehearsal.contracts import Direction, ScoreRecord, ScoreStatus, SpeakerRole, TurnRecord
from rehearsal.scoring.extractors import run_extractors
from rehearsal.scoring.grader import GraderClient, run_grader
from rehearsal.scoring.merge import merge_findings

_RENDERING_LANG: dict[Direction, tuple[Literal["en", "es"], Literal["en", "es"]]] = {
    Direction.EN_TO_ES: ("en", "es"),
    Direction.ES_TO_EN: ("es", "en"),
}


def score_turn(
    turn: TurnRecord,
    grader_client: GraderClient | None = None,
    *,
    speaker: SpeakerRole = SpeakerRole.CLINICIAN,
    grader_prompt_version: str = "stub-0.0.0",
    seed: int = 0,
) -> ScoreRecord:
    """Score one interpreted turn. Pure with respect to (turn, grader_client) —
    the only I/O is inside `grader_client.grade`, and its absence degrades the
    status rather than raising (§2.1, §5.6).
    """
    source_lang, rendering_lang = _RENDERING_LANG[turn.direction]

    if not turn.rendering_transcript.strip():
        return ScoreRecord(
            turn_id=turn.turn_id,
            findings=(),
            extractor_findings=(),
            model_findings=(),
            grader_prompt_version=grader_prompt_version,
            model_versions={},
            seed=seed,
            status=ScoreStatus.FAILED,
        )

    extractor_findings = run_extractors(
        turn.source_utterance, turn.rendering_transcript, source_lang, rendering_lang
    )

    grader_output = run_grader(
        grader_client,
        source=turn.source_utterance,
        rendering=turn.rendering_transcript,
        direction=turn.direction.value,
        speaker=speaker.value,
    )
    model_findings = grader_output.findings if grader_output is not None else ()

    findings = merge_findings(extractor_findings, grader_output)

    status = ScoreStatus.COMPLETE if grader_output is not None else ScoreStatus.EXTRACTOR_ONLY

    return ScoreRecord(
        turn_id=turn.turn_id,
        findings=findings,
        extractor_findings=extractor_findings,
        model_findings=model_findings,
        grader_prompt_version=grader_prompt_version,
        model_versions={},
        seed=seed,
        status=status,
    )


__all__ = ["score_turn"]

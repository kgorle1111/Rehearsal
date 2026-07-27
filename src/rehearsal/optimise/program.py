"""GraderProgram — the one typed module a prompt optimiser searches over.
misc/docs/04-ai-engineering.md §10.2. Reuses WS1's `GraderClient`/`GraderOutput`
(src/rehearsal/scoring/grader.py) unchanged rather than redefining a parallel
verdict/context shape.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from rehearsal.scoring.grader import GraderClient, GraderOutput

# docs/04 §10.2 search-space bounds — enforced by candidate construction, not here.
INSTRUCTION_TOKEN_LIMIT = 900
DEMOS_TOKEN_LIMIT = 700
DEMOS_MAX_COUNT = 4


@dataclass(frozen=True, slots=True)
class CalibrationDemo:
    """One DEV-drawn few-shot demo. Never sourced from TEST — callers only
    ever construct these from `data/calibration/dev.jsonl`."""

    item_id: str
    source: str
    rendering: str
    direction: Literal["en_to_es", "es_to_en"]
    speaker: Literal["clinician", "patient"]
    label_summary: str


@dataclass(frozen=True, slots=True)
class GraderContext:
    """What one grading call needs — same shape `GraderClient.grade` takes."""

    source: str
    rendering: str
    direction: Literal["en_to_es", "es_to_en"]
    speaker: Literal["clinician", "patient"]


class GraderProgram:
    """One structured call. The optimiser may rewrite `instruction` and choose
    `demos`; the client and the output schema are frozen by construction."""

    def __init__(
        self,
        instruction: str,
        demos: Sequence[CalibrationDemo],
        client: GraderClient,
    ) -> None:
        self.instruction = instruction
        self.demos = tuple(demos)
        self._client = client

    def __call__(self, ctx: GraderContext) -> GraderOutput:
        # ponytail: no real model host exists yet (NOT-BUILT-YET.md P2/P3), so
        # `instruction`/`demos` have nowhere to render into today — StubGraderClient
        # ignores them. A real GraderClient implementation is the seam that reads
        # them (baked into how it's constructed); this call shape doesn't change.
        return self._client.grade(
            source=ctx.source,
            rendering=ctx.rendering,
            direction=ctx.direction,
            speaker=ctx.speaker,
        )


__all__ = ["CalibrationDemo", "GraderContext", "GraderProgram"]

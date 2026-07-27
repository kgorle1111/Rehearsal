"""Stage B — the single structured grader call. misc/docs/06-scoring-engine.md §5.

No LLM host is wired up in this phase (BUILD.md WS1 scope note). This module is
the seam: a `GraderClient` Protocol any future host adapter implements, plus a
`StubGraderClient` for tests. `run_grader` is the only thing `engine.py` calls;
it never imports a concrete client, so swapping in a real model host later is a
DI change, not a scoring-plane change.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from rehearsal.contracts import Finding


@dataclass(frozen=True, slots=True)
class GraderOutput:
    """The engine-facing shape of a grader call. `findings` carry
    `provenance=Provenance.GRADER` and a non-None `confidence` — the grader
    estimates, it does not prove (§3.2)."""

    abstain: bool
    findings: tuple[Finding, ...]
    clean_reason: str | None = None
    abstain_reason: str | None = None


class GraderClient(Protocol):
    """Implemented by whatever model host lands later. §5.4: temperature 0,
    one structured call per turn, sees only source/rendering/direction/speaker —
    never extractor findings, never the manifest, never prior turns (§5.2)."""

    def grade(
        self,
        *,
        source: str,
        rendering: str,
        direction: Literal["en_to_es", "es_to_en"],
        speaker: Literal["clinician", "patient"],
    ) -> GraderOutput: ...


class StubGraderClient:
    """A fake client for tests and for running the pipeline with no model host.
    Always abstains with a clean reason — deterministic, no I/O, proves the
    merge logic (`tests/scoring/test_merge.py`) without a live model call."""

    def grade(
        self,
        *,
        source: str,
        rendering: str,
        direction: Literal["en_to_es", "es_to_en"],
        speaker: Literal["clinician", "patient"],
    ) -> GraderOutput:
        return GraderOutput(abstain=False, findings=(), clean_reason="stub: no model host wired")


def run_grader(
    client: GraderClient | None,
    *,
    source: str,
    rendering: str,
    direction: Literal["en_to_es", "es_to_en"],
    speaker: Literal["clinician", "patient"],
) -> GraderOutput | None:
    """None means 'grader unavailable' — the caller (engine.py) must treat that
    as `status = grader_unavailable` and keep the symbolic findings (§5.6).

    A raising client (malformed response, dead socket, any host-side fault —
    docs/14-testing-strategy.md fault classes F-01/F-02/F-04/F-06) degrades
    the same way as a missing client. A model failing is never allowed to
    crash the turn; the extractor findings must still land."""
    if client is None:
        return None
    try:
        return client.grade(
            source=source, rendering=rendering, direction=direction, speaker=speaker
        )
    except Exception:
        return None


__all__ = ["GraderOutput", "GraderClient", "StubGraderClient", "run_grader"]

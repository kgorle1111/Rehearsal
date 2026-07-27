"""The prompt-optimisation search loop. misc/docs/08-evals.md §6 steps 2-4,
misc/docs/04-ai-engineering.md §10.3.

DEV-only, structurally: this module never imports or names the sealed
calibration split or the evals package's guard around it — there is nothing
here that *could* touch it, which is stronger than a runtime check.
`tests/optimise/test_no_test_leakage.py` proves that by reading this file's
own source text (and deliberately does not name the banned strings in this
docstring either, so the proof stays honest about what it is checking).

Candidates arrive pre-scored on DEV (a `dict[str, float]` of metrics) rather
than being evaluated here: there is no live model host yet
(NOT-BUILT-YET.md P2/P3), so "evaluate a candidate" today means re-scoring
recorded calibration items, which belongs to `rehearsal.evals`/
`rehearsal.scoring`, not to this loop.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from rehearsal.optimise.metric import HasMetrics, optimisation_metric


@dataclass(frozen=True, slots=True)
class Candidate:
    """One instruction/demos variant, already scored on DEV by the caller."""

    label: str
    instruction: str
    metrics: dict[str, float]  # DEV metrics — satisfies HasMetrics structurally


@dataclass(frozen=True, slots=True)
class CandidateRecord:
    """One row of the search trace — every candidate evaluated, not just the
    winner (docs/04 §10.3: "the trace is what tells a reader whether a gain
    came from 8 candidates or 400"). `tokens`/`wall_time_s` are real wall-time
    measurements of this loop's own bookkeeping, not of a model call — there
    is no model call to measure yet."""

    candidate_hash: str
    label: str
    dev_metrics: dict[str, float]
    score: float
    tokens: int
    wall_time_s: float


@dataclass(frozen=True, slots=True)
class SearchResult:
    baseline: HasMetrics
    trace: tuple[CandidateRecord, ...]
    selected: CandidateRecord | None
    rejected_reason: str | None = None


def _hash_candidate(instruction: str) -> str:
    return hashlib.sha256(instruction.encode()).hexdigest()[:16]


def run_search(
    baseline: HasMetrics,
    candidates: Sequence[Candidate],
    *,
    tokens_fn: Callable[[Candidate], int] | None = None,
) -> SearchResult:
    """Score every candidate, record all of them, then select the single best
    by `optimisation_metric` — refusing to promote a candidate whose
    `critical_recall` regresses vs baseline even when its composite score is
    higher (docs/08-evals.md §6; WS-6 DoD in misc/docs/15-workstreams.md)."""
    baseline_recall = baseline.metrics["critical_recall"]
    trace: list[CandidateRecord] = []
    for c in candidates:
        start = time.perf_counter()
        score = optimisation_metric(c)
        elapsed = time.perf_counter() - start
        trace.append(
            CandidateRecord(
                candidate_hash=_hash_candidate(c.instruction),
                label=c.label,
                dev_metrics=dict(c.metrics),
                score=score,
                tokens=tokens_fn(c) if tokens_fn is not None else 0,
                wall_time_s=elapsed,
            )
        )

    if not trace:
        return SearchResult(
            baseline=baseline, trace=(), selected=None, rejected_reason="no candidates evaluated"
        )

    best = max(trace, key=lambda rec: rec.score)

    if best.score <= 0.0:
        return SearchResult(
            baseline=baseline,
            trace=tuple(trace),
            selected=None,
            rejected_reason="no candidate cleared the critical_recall floor",
        )

    if best.dev_metrics["critical_recall"] < baseline_recall:
        return SearchResult(
            baseline=baseline,
            trace=tuple(trace),
            selected=None,
            rejected_reason=(
                f"best composite (score={best.score:.4f}, label={best.label!r}) regresses "
                f"critical_recall {best.dev_metrics['critical_recall']:.4f} < baseline "
                f"{baseline_recall:.4f}; refused"
            ),
        )

    return SearchResult(baseline=baseline, trace=tuple(trace), selected=best, rejected_reason=None)


__all__ = ["Candidate", "CandidateRecord", "SearchResult", "run_search"]

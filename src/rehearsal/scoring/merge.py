"""Merge — the deterministic combination. misc/docs/06-scoring-engine.md §6.

No model call, no randomness, no I/O. Implements the load-bearing subset of the
nine merge steps that the frozen contract can express:

- M1 seed: every extractor finding is kept unmodified — the semantic stage
  never filters the symbolic set.
- M4/M5 territory: a grader finding whose rendering span overlaps an extractor
  finding's rendering span is dropped (the extractor already adjudicated that
  span — "the extractor wins on the critical categories").
- S11/S12 (§3.1): the grader can never assign `critical` severity. Every
  grader-origin finding is forced to `non_critical` here — not because the
  model's opinion is worthless, but because principle 1 requires a deterministic
  check in front of any `critical` finding, and no manifest-anchoring is wired
  into this phase to provide one. This is the strict, safe collapse of S9-S12
  for a grader whose findings are structurally unanchored right now.
- Span honesty: every finding kept by this function has a real span (or is an
  omission, whose `source_span` stands in — schema note on `Finding`).
"""

from __future__ import annotations

from rehearsal.contracts import Finding, Provenance, Severity
from rehearsal.scoring.grader import GraderOutput


def _spans_overlap(a: tuple[int, int] | None, b: tuple[int, int] | None) -> bool:
    if a is None or b is None:
        return False
    return a[0] < b[1] and b[0] < a[1]


def _as_tuple(span: object) -> tuple[int, int] | None:
    if span is None:
        return None
    return (span.start, span.end)  # type: ignore[attr-defined]


def merge_findings(
    extractor_findings: tuple[Finding, ...], grader_output: GraderOutput | None
) -> tuple[Finding, ...]:
    """extractor findings + grader output -> the final Finding tuple. Pure."""
    merged: list[Finding] = list(extractor_findings)  # M1 — never filtered.

    if grader_output is None or grader_output.abstain:
        return tuple(merged)

    extractor_rendering_spans = [_as_tuple(f.rendering_span) for f in extractor_findings]

    for gf in grader_output.findings:
        gf_span = _as_tuple(gf.rendering_span)
        # M4/M5 — territory check: extractor already adjudicated this span.
        if any(_spans_overlap(gf_span, es) for es in extractor_rendering_spans):
            continue
        # S11/S12 — grader can never raise severity. Force non_critical, always.
        merged.append(
            Finding(
                type=gf.type,
                severity=Severity.NON_CRITICAL,
                note=gf.note,
                provenance=Provenance.GRADER,
                source_span=gf.source_span,
                rendering_span=gf.rendering_span,
                extractor_name=None,
                confidence=gf.confidence,
            )
        )

    return tuple(merged)


__all__ = ["merge_findings"]

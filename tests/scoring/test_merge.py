"""Unit tests proving the merge logic against a stub grader client (BUILD.md WS1 item 2)."""

from __future__ import annotations

from rehearsal.contracts import ErrorType, Finding, Provenance, Severity, Span
from rehearsal.scoring.grader import GraderOutput
from rehearsal.scoring.merge import merge_findings


def _extractor_finding(kind: ErrorType, severity: Severity, span: tuple[int, int]) -> Finding:
    return Finding(
        type=kind,
        severity=severity,
        note="test",
        provenance=Provenance.EXTRACTOR,
        rendering_span=Span(*span),
        source_span=Span(*span),
        extractor_name="dosage",
        confidence=None,
    )


def _grader_finding(kind: ErrorType, span: tuple[int, int], confidence: float = 0.7) -> Finding:
    return Finding(
        type=kind,
        severity=Severity.NON_CRITICAL,  # grader output never carries critical (§3.1 S11/S12)
        note="grader test",
        provenance=Provenance.GRADER,
        rendering_span=Span(*span),
        source_span=None,
        extractor_name=None,
        confidence=confidence,
    )


def test_extractor_findings_pass_through_unmodified() -> None:
    ef = _extractor_finding(ErrorType.SUBSTITUTION, Severity.CRITICAL, (0, 5))
    merged = merge_findings((ef,), None)
    assert merged == (ef,)


def test_grader_none_keeps_only_extractor_findings() -> None:
    ef = _extractor_finding(ErrorType.OMISSION, Severity.CRITICAL, (0, 5))
    merged = merge_findings((ef,), None)
    assert merged == (ef,)


def test_grader_abstain_admits_nothing() -> None:
    ef = _extractor_finding(ErrorType.OMISSION, Severity.CRITICAL, (0, 5))
    gf = _grader_finding(ErrorType.EDITORIALIZATION, (10, 20))
    grader_output = GraderOutput(abstain=True, findings=(gf,))
    merged = merge_findings((ef,), grader_output)
    assert merged == (ef,)


def test_grader_finding_admitted_when_no_territory_overlap() -> None:
    ef = _extractor_finding(ErrorType.SUBSTITUTION, Severity.CRITICAL, (0, 5))
    gf = _grader_finding(ErrorType.EDITORIALIZATION, (20, 30))
    grader_output = GraderOutput(abstain=False, findings=(gf,))
    merged = merge_findings((ef,), grader_output)
    assert len(merged) == 2
    assert gf in merged


def test_grader_finding_dropped_on_territory_overlap() -> None:
    """M4/M5: the extractor already adjudicated this span — the grader's opinion is dropped."""
    ef = _extractor_finding(ErrorType.SUBSTITUTION, Severity.CRITICAL, (0, 10))
    gf = _grader_finding(ErrorType.DISTORTION, (2, 6))  # overlaps ef's span
    grader_output = GraderOutput(abstain=False, findings=(gf,))
    merged = merge_findings((ef,), grader_output)
    assert merged == (ef,)


def test_critical_severity_never_downgraded_by_merge() -> None:
    """Property: no extractor-origin critical finding is weakened by merging in grader output."""
    ef = _extractor_finding(ErrorType.SUBSTITUTION, Severity.CRITICAL, (0, 5))
    gf = _grader_finding(ErrorType.EDITORIALIZATION, (20, 30))
    grader_output = GraderOutput(abstain=False, findings=(gf,))
    merged = merge_findings((ef,), grader_output)
    critical = [f for f in merged if f.provenance == Provenance.EXTRACTOR]
    assert all(f.severity == Severity.CRITICAL for f in critical)


def test_grader_finding_is_never_critical() -> None:
    """S11/S12: the grader can never assign critical severity, even if it tried to."""
    ef = _extractor_finding(ErrorType.OMISSION, Severity.CRITICAL, (0, 5))
    smuggled_critical = Finding(
        type=ErrorType.DISTORTION,
        severity=Severity.CRITICAL,  # a misbehaving/future client trying to smuggle severity
        note="a grader should never get to say this",
        provenance=Provenance.GRADER,
        rendering_span=Span(50, 60),
        source_span=None,
        extractor_name=None,
        confidence=0.9,
    )
    grader_output = GraderOutput(abstain=False, findings=(smuggled_critical,))
    merged = merge_findings((ef,), grader_output)
    grader_origin = [f for f in merged if f.provenance == Provenance.GRADER]
    assert len(grader_origin) == 1
    assert grader_origin[0].severity == Severity.NON_CRITICAL


def test_every_finding_has_a_real_span() -> None:
    """No finding exists without a span, except omissions which use source_span."""
    ef_omission = Finding(
        type=ErrorType.OMISSION,
        severity=Severity.CRITICAL,
        note="omitted",
        provenance=Provenance.EXTRACTOR,
        rendering_span=None,
        source_span=Span(0, 5),
        extractor_name="allergy",
        confidence=None,
    )
    gf = _grader_finding(ErrorType.EDITORIALIZATION, (20, 30))
    grader_output = GraderOutput(abstain=False, findings=(gf,))
    merged = merge_findings((ef_omission,), grader_output)
    for f in merged:
        if f.type == ErrorType.OMISSION:
            assert f.source_span is not None
        else:
            assert f.rendering_span is not None or f.source_span is not None

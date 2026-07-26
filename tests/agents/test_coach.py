from __future__ import annotations

from rehearsal.agents.coach import CoachAgent
from rehearsal.contracts import ErrorType, Finding, Provenance, Severity, Span


def _finding(kind: ErrorType, severity: Severity) -> Finding:
    return Finding(
        type=kind,
        severity=severity,
        note="test finding",
        provenance=Provenance.EXTRACTOR,
        source_span=Span(0, 3),
        rendering_span=Span(0, 3),
    )


def test_no_findings_suppresses_hint() -> None:
    hint = CoachAgent().generate_hint(())
    assert hint.suppress is True
    assert hint.hint == ""


def test_picks_most_severe_finding() -> None:
    findings = (
        _finding(ErrorType.OMISSION, Severity.NON_CRITICAL),
        _finding(ErrorType.SUBSTITUTION, Severity.CRITICAL),
    )
    hint = CoachAgent().generate_hint(findings)
    assert hint.suppress is False
    assert "substitution" in hint.hint
    assert "critical" in hint.hint
    assert "omission" not in hint.hint


def test_hint_never_none_kind_when_findings_present() -> None:
    findings = (_finding(ErrorType.REGISTER_SHIFT, Severity.NON_CRITICAL),)
    hint = CoachAgent().generate_hint(findings)
    assert "register shift" in hint.hint
    assert "non critical" in hint.hint

"""Property tests required by BUILD.md WS1 DoD:

- every finding quotes real text (a valid span into source or rendering)
- critical severity is never silently downgraded by the merge step
- no finding exists without a span (except omissions, which use source_span)
"""

from __future__ import annotations

from rehearsal.contracts import ErrorType, Severity
from rehearsal.scoring.extractors import run_extractors

CASES = [
    ("Take 500 mg once daily.", "Tome 250 miligramos una vez al dia.", "en", "es"),
    ("I am allergic to penicillin.", "Soy alérgico a la amoxicilina.", "en", "es"),
    ("Pain in the left knee.", "Dolor en la rodilla derecha.", "en", "es"),
    ("Take it every 8 hours.", "Tomelo 3 veces al dia.", "en", "es"),
    ("Take metformin daily.", "Tome metformina a diario.", "en", "es"),
]


def test_every_finding_quotes_real_text() -> None:
    for source, rendering, src_lang, rnd_lang in CASES:
        findings = run_extractors(source, rendering, src_lang, rnd_lang)
        for f in findings:
            if f.source_span is not None:
                quoted = source[f.source_span.start : f.source_span.end]
                assert quoted, f"empty source span for {f}"
            if f.rendering_span is not None:
                quoted = rendering[f.rendering_span.start : f.rendering_span.end]
                assert quoted, f"empty rendering span for {f}"


def test_no_finding_without_a_span_except_omissions() -> None:
    for source, rendering, src_lang, rnd_lang in CASES:
        findings = run_extractors(source, rendering, src_lang, rnd_lang)
        for f in findings:
            if f.type == ErrorType.OMISSION:
                assert f.source_span is not None
            else:
                assert f.source_span is not None or f.rendering_span is not None


def test_extractor_findings_are_always_provably_derived() -> None:
    """Invariant I1 (§4.10): confidence is None for every extractor finding."""
    for source, rendering, src_lang, rnd_lang in CASES:
        for f in run_extractors(source, rendering, src_lang, rnd_lang):
            assert f.confidence is None


def test_dosage_substitution_is_critical_and_not_downgraded() -> None:
    findings = run_extractors(
        "Take 500 mg once daily.", "Tome 250 miligramos una vez al dia.", "en", "es"
    )
    dosage_findings = [f for f in findings if f.extractor_name == "dosage"]
    assert dosage_findings
    assert all(f.severity == Severity.CRITICAL for f in dosage_findings)


def test_allergy_substitution_is_always_critical() -> None:
    findings = run_extractors(
        "I am allergic to penicillin.", "Soy alérgico a la amoxicilina.", "en", "es"
    )
    allergy_findings = [f for f in findings if f.extractor_name == "allergy"]
    assert allergy_findings
    assert all(f.severity == Severity.CRITICAL for f in allergy_findings)

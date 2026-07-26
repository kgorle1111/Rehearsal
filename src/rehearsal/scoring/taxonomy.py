"""Extractor-specific taxonomy constants. misc/docs/06-scoring-engine.md §3.

`ErrorType` and `Severity` are the frozen contract — imported, never redefined
(BUILD.md golden rule 7). This module only adds the category-legality and
severity-assignment tables that sit on top of them.
"""

from __future__ import annotations

from rehearsal.contracts import ErrorType, Severity

EXTRACTOR_OWNED: frozenset[ErrorType] = frozenset(
    {ErrorType.OMISSION, ErrorType.ADDITION, ErrorType.SUBSTITUTION, ErrorType.DISTORTION}
)
GRADER_ONLY: frozenset[ErrorType] = frozenset(
    {
        ErrorType.EDITORIALIZATION,
        ErrorType.ROLE_EXCHANGE,
        ErrorType.REGISTER_SHIFT,
        ErrorType.FALSE_FLUENCY,
        ErrorType.FIRST_PERSON_VIOLATION,
    }
)
# Grader MAY propose EXTRACTOR_OWNED kinds; it may never set their severity (S11/S12).
assert EXTRACTOR_OWNED | GRADER_ONLY == frozenset(ErrorType)
assert not (EXTRACTOR_OWNED & GRADER_ONLY)

CRITICAL_FACT_KINDS: frozenset[str] = frozenset(
    {
        "quantity",
        "dosage",
        "unit",
        "frequency",
        "duration_onset",
        "negation",
        "laterality",
        "allergy",
    }
)

# S1-S10, in evaluation order, first match wins — the deterministic authority on
# whether an *extractor* finding is critical (§3.1). merge.py applies S11-S13 on
# top of this for grader-origin findings.
SEVERITY_RULES: dict[str, Severity] = {
    "allergy": Severity.CRITICAL,  # S1
    "negation_required": Severity.CRITICAL,  # S2
    "dosage_dose": Severity.CRITICAL,  # S3
    "frequency_per_day": Severity.CRITICAL,  # S4
    "laterality": Severity.CRITICAL,  # S5
    "duration_symptom_onset": Severity.CRITICAL,  # S6 (temporal extractor unimplemented, §4.10)
    "dosage_count": Severity.CRITICAL,  # S7
    "frequency_underspecified": Severity.NON_CRITICAL,  # S8
    "entity_medication": Severity.CRITICAL,  # S9
    "entity_body_site_or_procedure": Severity.CRITICAL,  # S10
}

# §4.10 — temporal is specified but not implemented. Any finding of this kind,
# from any origin, is capped here rather than left to reach a human unguarded.
TEMPORAL_CAP: Severity = Severity.NON_CRITICAL

__all__ = [
    "EXTRACTOR_OWNED",
    "GRADER_ONLY",
    "CRITICAL_FACT_KINDS",
    "SEVERITY_RULES",
    "TEMPORAL_CAP",
]

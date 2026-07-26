"""Stage A — deterministic extractors. misc/docs/06-scoring-engine.md §4.

Seven extractors are implemented, per BUILD.md WS1 scope: entities, numbers,
dosage, frequency, negation, laterality, allergy. `temporal` is specified but
NOT implemented (§4.10) — it is deliberately absent from EXTRACTOR_ORDER, and
any grader-origin `temporal`-labelled finding is capped at non_critical by
merge.py (taxonomy.TEMPORAL_CAP), never claimed as working.

ponytail: comparison here uses the source utterance itself as ground truth
(manifest-first, source-second collapses to source-only because `TurnRecord`
in the frozen contract carries no `TermManifestSlice` yet — that field belongs
to a content-plane workstream not yet wired). Each extractor's own `extract()`
parser is manifest-independent and is what the EV-00 fixture grid grades;
swap the comparison functions below to manifest-vs-rendering the day
`TurnRecord` grows a manifest field, without touching the parsers.
"""

from __future__ import annotations

from rehearsal.contracts import ErrorType, Finding, Provenance, Severity, Span
from rehearsal.scoring.extractors import allergy, dosage, entities, frequency, laterality
from rehearsal.scoring.taxonomy import SEVERITY_RULES

EXTRACTOR_ORDER: tuple[str, ...] = (
    "entities",
    "numbers",
    "dosage",
    "frequency",
    "negation",
    "laterality",
    "allergy",
)


def _finding(
    kind: ErrorType,
    severity: Severity,
    note: str,
    extractor_name: str,
    source_span: tuple[int, int] | None,
    rendering_span: tuple[int, int] | None,
) -> Finding:
    return Finding(
        type=kind,
        severity=severity,
        note=note[:200],
        provenance=Provenance.EXTRACTOR,
        source_span=Span(*source_span) if source_span else None,
        rendering_span=Span(*rendering_span) if rendering_span else None,
        extractor_name=extractor_name,
        confidence=None,
    )


def _compare_dosage(source: str, rendering: str, src_lang: str, rnd_lang: str) -> list[Finding]:
    findings: list[Finding] = []
    src_doses = [d for d in dosage.extract(source, src_lang) if d.family is not None]  # type: ignore[arg-type]
    rnd_doses = [d for d in dosage.extract(rendering, rnd_lang) if d.family is not None]  # type: ignore[arg-type]
    used = [False] * len(rnd_doses)
    for sd in src_doses:
        match_idx = next(
            (
                i
                for i, rd in enumerate(rnd_doses)
                if not used[i] and rd.family == sd.family and rd.base_value == sd.base_value
            ),
            None,
        )
        if match_idx is not None:
            used[match_idx] = True
            continue
        mismatch_idx = next(
            (i for i, rd in enumerate(rnd_doses) if not used[i] and rd.family == sd.family), None
        )
        severity = SEVERITY_RULES["dosage_count" if sd.family == "count" else "dosage_dose"]
        if mismatch_idx is not None:
            used[mismatch_idx] = True
            rd = rnd_doses[mismatch_idx]
            findings.append(
                _finding(
                    ErrorType.SUBSTITUTION,
                    severity,
                    f"dose mismatch: source {sd.value}{sd.unit or ''} "
                    f"vs rendering {rd.value}{rd.unit or ''}",
                    "dosage",
                    sd.span,
                    rd.span,
                )
            )
        else:
            findings.append(
                _finding(
                    ErrorType.OMISSION,
                    severity,
                    f"dose omitted: source had {sd.value}{sd.unit or ''}",
                    "dosage",
                    sd.span,
                    None,
                )
            )
    return findings


def _compare_frequency(source: str, rendering: str, src_lang: str, rnd_lang: str) -> list[Finding]:
    findings: list[Finding] = []
    src_freqs = frequency.extract(source, src_lang)  # type: ignore[arg-type]
    rnd_freqs = frequency.extract(rendering, rnd_lang)  # type: ignore[arg-type]
    if not src_freqs:
        return findings
    sf = src_freqs[0]
    rf = rnd_freqs[0] if rnd_freqs else None
    if rf is None:
        if not sf.prn:
            findings.append(
                _finding(
                    ErrorType.OMISSION,
                    SEVERITY_RULES["frequency_per_day"],
                    "frequency omitted entirely",
                    "frequency",
                    sf.span,
                    None,
                )
            )
        return findings
    if sf.prn != rf.prn:
        findings.append(
            _finding(
                ErrorType.DISTORTION,
                Severity.CRITICAL,
                "as-needed vs scheduled dosing mismatch",
                "frequency",
                sf.span,
                rf.span,
            )
        )
    elif sf.per_day is not None and rf.per_day is not None and sf.per_day != rf.per_day:
        findings.append(
            _finding(
                ErrorType.SUBSTITUTION,
                SEVERITY_RULES["frequency_per_day"],
                f"frequency mismatch: {sf.per_day}/day vs {rf.per_day}/day",
                "frequency",
                sf.span,
                rf.span,
            )
        )
    elif sf.interval_hours is not None and rf.interval_hours is None and sf.per_day == rf.per_day:
        findings.append(
            _finding(
                ErrorType.DISTORTION,
                SEVERITY_RULES["frequency_underspecified"],
                "interval lost, per-day rate preserved (frequency_underspecified)",
                "frequency",
                sf.span,
                rf.span,
            )
        )
    return findings


def _compare_laterality(source: str, rendering: str, src_lang: str, rnd_lang: str) -> list[Finding]:
    findings: list[Finding] = []
    src_lat = [m for m in laterality.extract(source, src_lang) if m.anchor_span]  # type: ignore[arg-type]
    rnd_lat = [m for m in laterality.extract(rendering, rnd_lang) if m.anchor_span]  # type: ignore[arg-type]
    for sm in src_lat:
        match = next((rm for rm in rnd_lat if rm.value == sm.value), None)
        if match is not None:
            continue
        mismatch = rnd_lat[0] if rnd_lat else None
        if mismatch is not None:
            findings.append(
                _finding(
                    ErrorType.DISTORTION,
                    SEVERITY_RULES["laterality"],
                    f"laterality mismatch: {sm.value} vs {mismatch.value}",
                    "laterality",
                    sm.span,
                    mismatch.span,
                )
            )
        else:
            findings.append(
                _finding(
                    ErrorType.OMISSION,
                    SEVERITY_RULES["laterality"],
                    f"laterality omitted: source said {sm.value}",
                    "laterality",
                    sm.span,
                    None,
                )
            )
    return findings


def _compare_allergy(source: str, rendering: str, src_lang: str, rnd_lang: str) -> list[Finding]:
    findings: list[Finding] = []
    src_allergies = allergy.extract(source, src_lang)  # type: ignore[arg-type]
    rnd_allergies = allergy.extract(rendering, rnd_lang)  # type: ignore[arg-type]
    for sa in src_allergies:
        match = next(
            (ra for ra in rnd_allergies if ra.allergen_entity_id == sa.allergen_entity_id), None
        )
        if match is None:
            other = next(
                (ra for ra in rnd_allergies if ra.allergen_entity_id != sa.allergen_entity_id), None
            )
            if other is not None:
                findings.append(
                    _finding(
                        ErrorType.SUBSTITUTION,
                        Severity.CRITICAL,
                        f"allergen substituted: {sa.allergen} vs {other.allergen}",
                        "allergy",
                        sa.span,
                        other.span,
                    )
                )
            else:
                findings.append(
                    _finding(
                        ErrorType.OMISSION,
                        Severity.CRITICAL,
                        f"allergy to {sa.allergen} omitted",
                        "allergy",
                        sa.span,
                        None,
                    )
                )
        elif match.polarity != sa.polarity:
            findings.append(
                _finding(
                    ErrorType.DISTORTION,
                    Severity.CRITICAL,
                    f"allergy polarity flipped for {sa.allergen}",
                    "allergy",
                    sa.span,
                    match.span,
                )
            )
    return findings


def _compare_entities(source: str, rendering: str, src_lang: str, rnd_lang: str) -> list[Finding]:
    findings: list[Finding] = []
    src_ents = entities.extract(source, src_lang)  # type: ignore[arg-type]
    rnd_ents = entities.extract(rendering, rnd_lang)  # type: ignore[arg-type]
    rnd_ids = {e.entity_id for e in rnd_ents}
    for se in src_ents:
        if se.entity_id in rnd_ids:
            continue
        if se.kind not in ("medication", "body_site", "procedure"):
            continue
        severity = SEVERITY_RULES[
            "entity_medication" if se.kind == "medication" else "entity_body_site_or_procedure"
        ]
        same_kind_other = next((re_ for re_ in rnd_ents if re_.kind == se.kind), None)
        if same_kind_other is not None:
            findings.append(
                _finding(
                    ErrorType.SUBSTITUTION,
                    severity,
                    f"{se.kind} substituted: {se.surface} vs {same_kind_other.surface}",
                    "entities",
                    se.span,
                    same_kind_other.span,
                )
            )
        else:
            findings.append(
                _finding(
                    ErrorType.OMISSION,
                    severity,
                    f"{se.kind} omitted: {se.surface}",
                    "entities",
                    se.span,
                    None,
                )
            )
    return findings


def run_extractors(
    source: str, rendering: str, source_lang: str, rendering_lang: str
) -> tuple[Finding, ...]:
    """(source, rendering, source_lang, rendering_lang) -> Findings, always runs,
    never raises for content reasons (§2.3 stage 2 contract)."""
    findings: list[Finding] = []
    findings += _compare_entities(source, rendering, source_lang, rendering_lang)
    findings += _compare_dosage(source, rendering, source_lang, rendering_lang)
    findings += _compare_frequency(source, rendering, source_lang, rendering_lang)
    findings += _compare_laterality(source, rendering, source_lang, rendering_lang)
    findings += _compare_allergy(source, rendering, source_lang, rendering_lang)
    return tuple(findings)


__all__ = ["EXTRACTOR_ORDER", "run_extractors"]

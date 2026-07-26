from __future__ import annotations

from rehearsal.contracts import Allergy, ClinicalState, Medication, SymptomTimelineEntry
from rehearsal.scenarios.graph import (
    clinical_state_from_dict,
    clinical_state_to_dict,
    validate_clinical_state,
)


def _valid_state() -> ClinicalState:
    return ClinicalState(
        condition="type 2 diabetes mellitus",
        medications=(
            Medication(
                name="metformin",
                dose="500",
                unit="mg",
                route="oral",
                frequency_per_day=2,
                duration="4 years",
            ),
        ),
        symptom_timeline=(SymptomTimelineEntry(offset="3 weeks ago", symptom="fatigue"),),
        allergies=(Allergy(substance="penicillin"),),
        emotional_state="worried",
        health_literacy="low",
        language_variety="es-MX-rural-central",
        onset="3 weeks ago, gradual",
    )


def test_round_trip_through_dict() -> None:
    state = _valid_state()
    round_tripped = clinical_state_from_dict(clinical_state_to_dict(state))
    assert round_tripped == state


def test_valid_state_has_no_errors() -> None:
    assert validate_clinical_state(_valid_state()) == []


def test_rejects_unknown_health_literacy() -> None:
    state = ClinicalState(
        condition="asthma",
        medications=(),
        symptom_timeline=(),
        allergies=(),
        emotional_state="worried",
        health_literacy="genius",  # not in the closed vocabulary
        language_variety="es-neutral",
        onset="today",
    )
    errors = validate_clinical_state(state)
    assert any("health_literacy" in e for e in errors)


def test_rejects_non_positive_frequency() -> None:
    state = ClinicalState(
        condition="asthma",
        medications=(
            Medication(
                name="albuterol",
                dose="90",
                unit="mcg",
                route="inhaled",
                frequency_per_day=0,
                duration="ongoing",
            ),
        ),
        symptom_timeline=(),
        allergies=(),
        emotional_state="worried",
        health_literacy="low",
        language_variety="es-neutral",
        onset="today",
    )
    errors = validate_clinical_state(state)
    assert any("frequency_per_day" in e for e in errors)


def test_rejects_empty_condition() -> None:
    state = ClinicalState(
        condition="   ",
        medications=(),
        symptom_timeline=(),
        allergies=(),
        emotional_state="calm",
        health_literacy="low",
        language_variety="es-neutral",
        onset="today",
    )
    errors = validate_clinical_state(state)
    assert any("condition" in e for e in errors)

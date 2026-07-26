"""Clinical-state schema (de)serialization and validation.

Ground-truth-by-construction (BUILD.md golden rule 2): this module never
invents or infers clinical facts. It only (a) converts between the frozen
``contracts.ClinicalState`` dataclass and plain JSON-able dicts, and (b)
checks that a given ``ClinicalState`` is internally well-formed — closed
vocabularies respected, no empty-string facts, no non-positive frequencies.
All checks are deterministic field predicates; nothing here calls a model.
"""

from __future__ import annotations

from typing import Any

from rehearsal.contracts import Allergy, ClinicalState, Medication, SymptomTimelineEntry

# Closed vocabularies, mirrored from misc/docs/07-data-and-scenarios.md §3.3/§3.4.
# A scenario author must pick from these; a free string is a build failure,
# not a silent default, because language_variety and health_literacy select
# lexicon/register files elsewhere in the pipeline.
HEALTH_LITERACY_VALUES = frozenset({"low", "moderate", "high"})

EMOTIONAL_STATE_VALUES = frozenset(
    {
        "calm",
        "worried",
        "fearful",
        "frustrated",
        "embarrassed",
        "resigned",
        "hopeful",
        "distracted",
        "in_pain",
    }
)

LANGUAGE_VARIETY_VALUES = frozenset(
    {
        "es-MX-rural-central",
        "es-MX-urban",
        "es-US-heritage",
        "es-neutral",
    }
)


class ClinicalStateInvalid(ValueError):
    """Raised by ``validate_clinical_state`` (strict) with all errors joined."""


def validate_clinical_state(state: ClinicalState) -> list[str]:
    """Return a list of validation errors; empty list means valid.

    Pure field-level checks — no model, no I/O. Consequential decisions
    (approve/reject) are never made here; this only tells a caller what is
    wrong so a human reviewer or a build step can act on it.
    """
    errors: list[str] = []

    if not state.condition.strip():
        errors.append("condition must be non-empty")
    if not state.onset.strip():
        errors.append("onset must be non-empty")

    if state.health_literacy not in HEALTH_LITERACY_VALUES:
        errors.append(
            f"health_literacy {state.health_literacy!r} not in {sorted(HEALTH_LITERACY_VALUES)}"
        )
    if state.emotional_state not in EMOTIONAL_STATE_VALUES:
        errors.append(
            f"emotional_state {state.emotional_state!r} not in {sorted(EMOTIONAL_STATE_VALUES)}"
        )
    if state.language_variety not in LANGUAGE_VARIETY_VALUES:
        errors.append(
            f"language_variety {state.language_variety!r} not in {sorted(LANGUAGE_VARIETY_VALUES)}"
        )

    for i, med in enumerate(state.medications):
        prefix = f"medications[{i}]"
        if not med.name.strip():
            errors.append(f"{prefix}.name must be non-empty")
        if not med.dose.strip():
            errors.append(f"{prefix}.dose must be non-empty")
        if not med.unit.strip():
            errors.append(f"{prefix}.unit must be non-empty")
        if not med.route.strip():
            errors.append(f"{prefix}.route must be non-empty")
        if not med.duration.strip():
            errors.append(f"{prefix}.duration must be non-empty")
        if med.frequency_per_day <= 0:
            errors.append(f"{prefix}.frequency_per_day must be > 0, got {med.frequency_per_day}")

    for i, entry in enumerate(state.symptom_timeline):
        prefix = f"symptom_timeline[{i}]"
        if not entry.offset.strip():
            errors.append(f"{prefix}.offset must be non-empty")
        if not entry.symptom.strip():
            errors.append(f"{prefix}.symptom must be non-empty")

    for i, allergy in enumerate(state.allergies):
        if not allergy.substance.strip():
            errors.append(f"allergies[{i}].substance must be non-empty")

    return errors


def assert_valid_clinical_state(state: ClinicalState) -> None:
    """Strict variant: raises ``ClinicalStateInvalid`` if any check fails."""
    errors = validate_clinical_state(state)
    if errors:
        raise ClinicalStateInvalid("; ".join(errors))


def clinical_state_to_dict(state: ClinicalState) -> dict[str, Any]:
    """Convert a ``ClinicalState`` to a plain JSON-able dict."""
    return {
        "condition": state.condition,
        "medications": [
            {
                "name": m.name,
                "dose": m.dose,
                "unit": m.unit,
                "route": m.route,
                "frequency_per_day": m.frequency_per_day,
                "duration": m.duration,
            }
            for m in state.medications
        ],
        "symptom_timeline": [
            {"offset": e.offset, "symptom": e.symptom} for e in state.symptom_timeline
        ],
        "allergies": [{"substance": a.substance} for a in state.allergies],
        "emotional_state": state.emotional_state,
        "health_literacy": state.health_literacy,
        "language_variety": state.language_variety,
        "onset": state.onset,
    }


def clinical_state_from_dict(data: dict[str, Any]) -> ClinicalState:
    """Inverse of ``clinical_state_to_dict``. Raises KeyError on missing fields."""
    medications = tuple(
        Medication(
            name=m["name"],
            dose=m["dose"],
            unit=m["unit"],
            route=m["route"],
            frequency_per_day=m["frequency_per_day"],
            duration=m["duration"],
        )
        for m in data["medications"]
    )
    symptom_timeline = tuple(
        SymptomTimelineEntry(offset=e["offset"], symptom=e["symptom"])
        for e in data["symptom_timeline"]
    )
    allergies = tuple(Allergy(substance=a["substance"]) for a in data["allergies"])
    return ClinicalState(
        condition=data["condition"],
        medications=medications,
        symptom_timeline=symptom_timeline,
        allergies=allergies,
        emotional_state=data["emotional_state"],
        health_literacy=data["health_literacy"],
        language_variety=data["language_variety"],
        onset=data["onset"],
    )

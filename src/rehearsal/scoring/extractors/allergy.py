"""`allergy` extractor — allergen identity and assertion polarity.

misc/docs/06-scoring-engine.md §4.9.

Every finding this extractor would emit is critical (S1), unconditionally — that
rule lives in taxonomy.py, not here; this module only parses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from rehearsal.scoring.extractors.entities import extract as extract_entities
from rehearsal.scoring.extractors.negation import check_targets

_ALLERGY_TARGETS_EN = ("allergic", "allergy", "allergies")
_ALLERGY_TARGETS_ES = ("alérgico", "alergica", "alérgica", "alergico", "alergia", "alergias")

_WINDOW_CHARS = 40


@dataclass(frozen=True, slots=True)
class AllergyMatch:
    allergen_entity_id: str
    allergen: str
    polarity: Literal["allergic", "not_allergic"]
    span: tuple[int, int]


def extract(text: str, lang: Literal["en", "es"]) -> tuple[AllergyMatch, ...]:
    entities = extract_entities(text, lang)
    targets = _ALLERGY_TARGETS_EN if lang == "en" else _ALLERGY_TARGETS_ES
    found_targets = [t for t in targets if re.search(re.escape(t), text, re.IGNORECASE)]
    polarities = check_targets(text, lang, tuple(found_targets))

    out: list[AllergyMatch] = []
    for entity in entities:
        if entity.kind != "medication":
            continue
        # An allergen mention needs an allergy-word nearby to count as an allergy fact.
        nearby = [p for p in polarities if abs(p.span[0] - entity.span[0]) <= _WINDOW_CHARS]
        if not nearby:
            continue
        polarity: Literal["allergic", "not_allergic"] = (
            "not_allergic" if nearby[0].polarity == "negated" else "allergic"
        )
        out.append(
            AllergyMatch(
                allergen_entity_id=entity.entity_id,
                allergen=entity.surface,
                polarity=polarity,
                span=entity.span,
            )
        )
    return tuple(out)


def to_dict(a: AllergyMatch) -> dict[str, object]:
    return {
        "allergen_entity_id": a.allergen_entity_id,
        "allergen": a.allergen,
        "polarity": a.polarity,
        "span": list(a.span),
    }


__all__ = ["AllergyMatch", "extract", "to_dict"]

"""`entities` extractor — closed-world named entity presence. misc/docs/06-scoring-engine.md §4.4.

Closed-world against a reference lexicon. The real system's closed world is the
scenario's `TermManifestSlice` (docs/07-data-and-scenarios.md), but `TurnRecord`
in the frozen contract carries no manifest field yet — content-plane wiring is a
different workstream. `_LEXICON` below is a small built-in stand-in so this
extractor is self-contained and testable now.
ponytail: swap `_LEXICON` for `manifest.entities` the day TurnRecord grows that
field; the match/fuzzy/cognate logic below does not change.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Literal

FUZZY_THRESHOLD = 0.88  # ponytail: calibration knob (§4.4); raise if variants start colliding.

# entity_id -> (kind, surface_en, surface_es)
_LEXICON: dict[str, tuple[str, tuple[str, ...], tuple[str, ...]]] = {
    "med.metformin": ("medication", ("metformin",), ("metformina",)),
    "med.amoxicillin": ("medication", ("amoxicillin",), ("amoxicilina",)),
    "med.azithromycin": ("medication", ("azithromycin",), ("azitromicina",)),
    "med.lisinopril": ("medication", ("lisinopril",), ("lisinopril",)),
    "med.ibuprofen": ("medication", ("ibuprofen",), ("ibuprofeno",)),
    "med.insulin": ("medication", ("insulin",), ("insulina",)),
    "med.penicillin": ("medication", ("penicillin",), ("penicilina",)),
    "med.aspirin": ("medication", ("aspirin",), ("aspirina",)),
    "site.knee": ("body_site", ("knee",), ("rodilla",)),
    "site.shoulder": ("body_site", ("shoulder",), ("hombro",)),
    "site.ear": ("body_site", ("ear",), ("oído", "oido")),
    "site.eye": ("body_site", ("eye",), ("ojo",)),
    "site.arm": ("body_site", ("arm",), ("brazo",)),
    "site.leg": ("body_site", ("leg",), ("pierna",)),
    "cond.diabetes": ("condition", ("diabetes",), ("diabetes",)),
    "cond.hypertension": ("condition", ("hypertension",), ("hipertensión", "hipertension")),
}

_WORD_RE = re.compile(r"[A-Za-zÀ-ÿ]+")


@dataclass(frozen=True, slots=True)
class EntityMatch:
    entity_id: str
    kind: str
    surface: str
    span: tuple[int, int]
    matched_fuzzy: bool


def _all_surfaces(entity_id: str) -> tuple[str, ...]:
    _kind, en, es = _LEXICON[entity_id]
    return en + es


def extract(text: str, lang: Literal["en", "es"]) -> tuple[EntityMatch, ...]:
    out: list[EntityMatch] = []
    for m in _WORD_RE.finditer(text):
        word = m.group(0).casefold()
        best: tuple[str, str, str, bool] | None = None  # entity_id, kind, surface, fuzzy
        best_ratio = 0.0
        for entity_id, (kind, _en, _es) in _LEXICON.items():
            for surface in _all_surfaces(entity_id):
                if word == surface.casefold():
                    best = (entity_id, kind, surface, False)
                    best_ratio = 1.0
                    break
                ratio = difflib.SequenceMatcher(None, word, surface.casefold()).ratio()
                if ratio >= FUZZY_THRESHOLD and ratio > best_ratio:
                    best = (entity_id, kind, surface, True)
                    best_ratio = ratio
            if best_ratio == 1.0:
                break
        if best is not None:
            entity_id, kind, surface, fuzzy = best
            out.append(
                EntityMatch(
                    entity_id=entity_id,
                    kind=kind,
                    surface=word,
                    span=(m.start(), m.end()),
                    matched_fuzzy=fuzzy,
                )
            )
    return tuple(out)


def to_dict(e: EntityMatch) -> dict[str, object]:
    return {
        "entity_id": e.entity_id,
        "kind": e.kind,
        "surface": e.surface,
        "span": list(e.span),
        "matched_fuzzy": e.matched_fuzzy,
    }


__all__ = ["EntityMatch", "extract", "to_dict", "LEXICON"]
LEXICON = _LEXICON

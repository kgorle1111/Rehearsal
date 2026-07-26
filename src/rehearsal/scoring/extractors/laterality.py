"""`laterality` extractor — left/right/bilateral, anchored to a body site.
misc/docs/06-scoring-engine.md §4.8.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from rehearsal.scoring.extractors.entities import extract as extract_entities

ANCHOR_WINDOW_TOKENS = 6  # §4.8

_LEXICON: dict[str, tuple[str, ...]] = {
    "left": ("left",),
    "right": ("right",),
    "bilateral": ("both", "bilateral", "either"),
}
_LEXICON_ES: dict[str, tuple[str, ...]] = {
    "left": ("izquierdo", "izquierda", "izquierdos", "izquierdas"),
    "right": ("derecho", "derecha", "derechos", "derechas"),
    "bilateral": ("ambos", "ambas", "los dos", "las dos", "bilateral", "bilaterales"),
}

_WORD_RE = re.compile(r"[A-Za-zÀ-ÿ]+")


@dataclass(frozen=True, slots=True)
class LateralityMatch:
    value: Literal["left", "right", "bilateral"]
    span: tuple[int, int]
    anchor_span: tuple[int, int] | None


def _lexicon(lang: Literal["en", "es"]) -> dict[str, tuple[str, ...]]:
    return _LEXICON if lang == "en" else _LEXICON_ES


def extract(text: str, lang: Literal["en", "es"]) -> tuple[LateralityMatch, ...]:
    lex = _lexicon(lang)
    entities = extract_entities(text, lang)
    body_sites = [e for e in entities if e.kind == "body_site"]
    words = list(_WORD_RE.finditer(text))

    out: list[LateralityMatch] = []
    for i, m in enumerate(words):
        word = m.group(0).casefold()
        value: Literal["left", "right", "bilateral"] | None = None
        for candidate, surfaces in lex.items():
            if word in surfaces:
                value = candidate  # type: ignore[assignment]
                break
        if value is None:
            continue
        anchor_span: tuple[int, int] | None = None
        best_dist = ANCHOR_WINDOW_TOKENS + 1
        for site in body_sites:
            # token distance approximated by word-index distance
            site_word_idx = next(
                (j for j, w in enumerate(words) if w.start() == site.span[0]), None
            )
            if site_word_idx is None:
                continue
            dist = abs(site_word_idx - i)
            if dist <= ANCHOR_WINDOW_TOKENS and dist < best_dist:
                best_dist = dist
                anchor_span = site.span
        if anchor_span is not None:
            out.append(
                LateralityMatch(value=value, span=(m.start(), m.end()), anchor_span=anchor_span)
            )
    return tuple(out)


def to_dict(m: LateralityMatch) -> dict[str, object]:
    return {
        "value": m.value,
        "span": list(m.span),
        "anchor_span": list(m.anchor_span) if m.anchor_span else None,
    }


__all__ = ["LateralityMatch", "extract", "to_dict"]

"""Normalisation pre-pass shared by every extractor. misc/docs/06-scoring-engine.md §4.1.

ponytail: implements N1-N4 (NFC, whitespace fold, casefold, diacritics-retained)
because those are what the fixture grid actually exercises. N5-N8 (punctuation
isolation, numeral-expansion-as-annotation, unit folding, elision expansion) are
folded into numbers.py/dosage.py/frequency.py directly instead of as a shared
offset-mapped pass — upgrade to a real offset_map here if an extractor ever
needs to report a span through more than casefold+whitespace.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class NormalizedText:
    original: str
    folded: str
    lang: Literal["en", "es"]


def normalize(text: str, lang: Literal["en", "es"]) -> NormalizedText:
    nfc = unicodedata.normalize("NFC", text)
    folded = " ".join(nfc.split()).casefold()
    return NormalizedText(original=text, folded=folded, lang=lang)


def find_span(haystack: str, needle: str, start: int = 0) -> tuple[int, int] | None:
    """Locate `needle` in `haystack` case-insensitively (diacritics preserved).

    Returns half-open offsets into `haystack`, or None. This is the extractor-side
    analogue of guard G3 (span verification) — extractor spans are asserted, not
    guarded, because they come from the parser, not a model (§4.10 invariant I1).
    """
    hay_fold = unicodedata.normalize("NFC", haystack).casefold()
    needle_fold = unicodedata.normalize("NFC", needle).casefold()
    idx = hay_fold.find(needle_fold, start)
    if idx == -1:
        return None
    return (idx, idx + len(needle_fold))

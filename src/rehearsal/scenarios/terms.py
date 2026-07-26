"""Term-manifest generator: rule-based surface-form expansion only.

CRITICAL CONSTRAINT (BUILD.md, this workstream's brief): a model must never
author manifest entries. This module is pure, deterministic string
transformation over a term already supplied by a human/scenario author — it
never invents a clinical fact, only additional ways of *saying* one the
caller already gave it.

Exactly four rules are applied, each documented at its function:
  1. identity      — the given en/es forms are always included verbatim.
  2. numeral        — digit forms 0-100 get a spelled-out counterpart and
                       vice versa, in both languages.
  3. unit expansion — a small fixed abbreviation table (mg, ml, mcg, g, kg)
                       expands to its singular/plural word form.
  4. pluralization  — single-word terms get a naive plural form appended
                       (English: +s / +es; Spanish: +s / +es).

No rule looks anything up in a corpus, calls a model, or guesses; each is a
closed table or a fixed string transform. `docs/07-data-and-scenarios.md §7`.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from rehearsal.contracts import TermManifestEntry

# Rule 2: numeral <-> spelled-out word, 0-100.
_EN_ONES = [
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
    "sixteen", "seventeen", "eighteen", "nineteen",
]  # fmt: skip
_EN_TENS = [
    "", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
    "eighty", "ninety",
]  # fmt: skip

_ES_ONES = [
    "cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho",
    "nueve", "diez", "once", "doce", "trece", "catorce", "quince",
    "dieciséis", "diecisiete", "dieciocho", "diecinueve",
]  # fmt: skip
_ES_TENS = [
    "", "", "veinte", "treinta", "cuarenta", "cincuenta", "sesenta",
    "setenta", "ochenta", "noventa",
]  # fmt: skip

_NUMERAL_RE = re.compile(r"\b\d{1,3}\b")


def _number_to_en_word(n: int) -> str | None:
    if n < 20:
        return _EN_ONES[n]
    if n < 100:
        tens, ones = divmod(n, 10)
        return _EN_TENS[tens] if ones == 0 else f"{_EN_TENS[tens]}-{_EN_ONES[ones]}"
    if n == 100:
        return "one hundred"
    return None


def _number_to_es_word(n: int) -> str | None:
    if n < 20:
        return _ES_ONES[n]
    if n < 30:
        ones = n - 20
        return "veinte" if ones == 0 else f"veinti{_ES_ONES[ones]}"
    if n < 100:
        tens, ones = divmod(n, 10)
        return _ES_TENS[tens] if ones == 0 else f"{_ES_TENS[tens]} y {_ES_ONES[ones]}"
    if n == 100:
        return "cien"
    return None


def _expand_numerals(text: str, to_word: Callable[[int], str | None]) -> str | None:
    """Replace the first standalone 0-100 numeral in ``text`` with its word
    form. Returns None if no numeral is present or it is out of range."""
    match = _NUMERAL_RE.search(text)
    if match is None:
        return None
    word = to_word(int(match.group()))
    if word is None:
        return None
    return text[: match.start()] + word + text[match.end() :]


# Rule 3: unit abbreviation <-> word form, singular and plural, en/es.
# (data/lexicons/frequency_equivalences.json-style table, kept local and
# small since this generator owns only surface-form expansion.)
_UNIT_EXPANSIONS: dict[str, dict[str, tuple[str, str]]] = {
    "mg": {"en": ("milligram", "milligrams"), "es": ("miligramo", "miligramos")},
    "ml": {"en": ("milliliter", "milliliters"), "es": ("mililitro", "mililitros")},
    "mcg": {"en": ("microgram", "micrograms"), "es": ("microgramo", "microgramos")},
    "g": {"en": ("gram", "grams"), "es": ("gramo", "gramos")},
    "kg": {"en": ("kilogram", "kilograms"), "es": ("kilogramo", "kilogramos")},
}

_UNIT_TOKEN_RE = {
    unit: re.compile(rf"\b{re.escape(unit)}\b", re.IGNORECASE) for unit in _UNIT_EXPANSIONS
}


def _expand_units(text: str, lang: str) -> list[str]:
    """Expand a recognised unit abbreviation token in ``text`` to its word
    form(s). Returns [] if no known abbreviation token is present."""
    out: list[str] = []
    for unit, pattern in _UNIT_TOKEN_RE.items():
        match = pattern.search(text)
        if match is None:
            continue
        singular, plural = _UNIT_EXPANSIONS[unit][lang]
        # Pick plural unless the immediately preceding token is "1"/"uno"/"un".
        preceding = text[: match.start()].strip().split(" ")[-1] if match.start() else ""
        word = singular if preceding in {"1", "uno", "un"} else plural
        out.append(text[: match.start()] + word + text[match.end() :])
    return out


# Rule 4: naive single-word pluralization.
def _pluralize_en(word: str) -> str | None:
    if " " in word:
        return None
    if word.endswith(("s", "x", "z", "ch", "sh")):
        return word + "es"
    return word + "s"


def _pluralize_es(word: str) -> str | None:
    if " " in word:
        return None
    if word.endswith(("a", "e", "i", "o", "u")):
        return word + "s"
    return word + "es"


def expand_renderings(en: str, es: str) -> tuple[str, ...]:
    """Apply the four surface-form rules to an (en, es) term pair.

    Deterministic and total: never raises, never calls a model. Always
    includes the original en/es forms; additional forms are appended only
    when a rule actually fires (e.g. no numeral present -> rule 2 no-op).
    """
    renderings: list[str] = [en, es]

    for text, to_word in ((en, _number_to_en_word), (es, _number_to_es_word)):
        expanded = _expand_numerals(text, to_word)
        if expanded is not None:
            renderings.append(expanded)

    renderings.extend(_expand_units(en, "en"))
    renderings.extend(_expand_units(es, "es"))

    plural_en = _pluralize_en(en)
    if plural_en is not None and plural_en != en:
        renderings.append(plural_en)
    plural_es = _pluralize_es(es)
    if plural_es is not None and plural_es != es:
        renderings.append(plural_es)

    # Dedup, preserve first-seen order.
    seen: set[str] = set()
    deduped: list[str] = []
    for r in renderings:
        if r not in seen:
            seen.add(r)
            deduped.append(r)
    return tuple(deduped)


def build_term_manifest_entry(
    term_id: str, kind: str, en: str, es: str, critical: bool
) -> TermManifestEntry:
    """Build one ``contracts.TermManifestEntry`` from an author-supplied
    term_id + en/es pair, with ``acceptable_renderings`` filled in by the
    rule-based expansion above. The scoring engine's extractors consume
    this shape directly (`contracts.TermManifestEntry`)."""
    return TermManifestEntry(
        term_id=term_id,
        kind=kind,
        en=en,
        es=es,
        critical=critical,
        acceptable_renderings=expand_renderings(en, es),
    )

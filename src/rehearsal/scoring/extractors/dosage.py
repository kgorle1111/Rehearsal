"""`dosage` extractor — quantity + unit + form. misc/docs/06-scoring-engine.md §4.3.

ponytail: temperature and mass_ratio ("mg/mL") compound families are not
implemented — not in the fixture grid's documented trap list (mass, volume,
count, activity are). Add a family row + fixture when a scenario needs one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from rehearsal.scoring.extractors.numbers import extract as extract_numbers

# unit surface form (casefolded) -> (family, multiplier to family base, canonical symbol)
_UNIT_ALIASES: dict[str, tuple[str, Decimal, str | None]] = {
    # mass, base = mg
    "g": ("mass", Decimal(1000), "mg"),
    "gram": ("mass", Decimal(1000), "mg"),
    "grams": ("mass", Decimal(1000), "mg"),
    "gramo": ("mass", Decimal(1000), "mg"),
    "gramos": ("mass", Decimal(1000), "mg"),
    "gr": ("mass", Decimal(1000), "mg"),
    "mg": ("mass", Decimal(1), "mg"),
    "milligram": ("mass", Decimal(1), "mg"),
    "milligrams": ("mass", Decimal(1), "mg"),
    "miligramo": ("mass", Decimal(1), "mg"),
    "miligramos": ("mass", Decimal(1), "mg"),
    "mcg": ("mass", Decimal("0.001"), "mg"),
    "µg": ("mass", Decimal("0.001"), "mg"),
    "μg": ("mass", Decimal("0.001"), "mg"),
    "ug": ("mass", Decimal("0.001"), "mg"),
    "microgram": ("mass", Decimal("0.001"), "mg"),
    "micrograms": ("mass", Decimal("0.001"), "mg"),
    "microgramo": ("mass", Decimal("0.001"), "mg"),
    "microgramos": ("mass", Decimal("0.001"), "mg"),
    # volume, base = mL
    "l": ("volume", Decimal(1000), "mL"),
    "litro": ("volume", Decimal(1000), "mL"),
    "litros": ("volume", Decimal(1000), "mL"),
    "liter": ("volume", Decimal(1000), "mL"),
    "liters": ("volume", Decimal(1000), "mL"),
    "ml": ("volume", Decimal(1), "mL"),
    "mililitro": ("volume", Decimal(1), "mL"),
    "mililitros": ("volume", Decimal(1), "mL"),
    "milliliter": ("volume", Decimal(1), "mL"),
    "milliliters": ("volume", Decimal(1), "mL"),
    "cc": ("volume", Decimal(1), "mL"),
    "teaspoon": ("volume", Decimal(5), "mL"),
    "tsp": ("volume", Decimal(5), "mL"),
    "cucharadita": ("volume", Decimal(5), "mL"),
    "cucharaditas": ("volume", Decimal(5), "mL"),
    "tablespoon": ("volume", Decimal(15), "mL"),
    "cucharada": ("volume", Decimal(15), "mL"),
    "cucharadas": ("volume", Decimal(15), "mL"),
    # activity, base = unit
    "unit": ("activity", Decimal(1), "unit"),
    "units": ("activity", Decimal(1), "unit"),
    "unidad": ("activity", Decimal(1), "unit"),
    "unidades": ("activity", Decimal(1), "unit"),
    "u": ("activity", Decimal(1), "unit"),
    "ui": ("activity", Decimal(1), "unit"),
    "iu": ("activity", Decimal(1), "unit"),
    # count (form nouns, no unit conversion — value stands alone)
    "tablet": ("count", Decimal(1), None),
    "tablets": ("count", Decimal(1), None),
    "tab": ("count", Decimal(1), None),
    "pill": ("count", Decimal(1), None),
    "pills": ("count", Decimal(1), None),
    "pastilla": ("count", Decimal(1), None),
    "pastillas": ("count", Decimal(1), None),
    "tableta": ("count", Decimal(1), None),
    "tabletas": ("count", Decimal(1), None),
    "comprimido": ("count", Decimal(1), None),
    "comprimidos": ("count", Decimal(1), None),
    "capsule": ("count", Decimal(1), None),
    "capsules": ("count", Decimal(1), None),
    "capsula": ("count", Decimal(1), None),
    "capsulas": ("count", Decimal(1), None),
    "cápsula": ("count", Decimal(1), None),
    "cápsulas": ("count", Decimal(1), None),
    "drop": ("count", Decimal(1), None),
    "drops": ("count", Decimal(1), None),
    "gota": ("count", Decimal(1), None),
    "gotas": ("count", Decimal(1), None),
    "puff": ("count", Decimal(1), None),
    "puffs": ("count", Decimal(1), None),
}

_UNIT_TOKEN_RE = re.compile(r"[A-Za-zÀ-ÿµμ]+")


@dataclass(frozen=True, slots=True)
class Dose:
    value: Decimal
    unit: str | None  # canonical symbol, or None for countable forms
    family: str | None  # "mass" | "volume" | "activity" | "count" | None (bare number)
    base_value: Decimal | None
    span: tuple[int, int]


def extract(text: str, lang: Literal["en", "es"]) -> tuple[Dose, ...]:
    """Pair every number in `text` with a trailing unit/form token, if present."""
    numbers = extract_numbers(text, lang)
    out: list[Dose] = []
    for n in numbers:
        tail = text[n.span[1] :]
        m = _UNIT_TOKEN_RE.match(tail.lstrip())
        if m is None:
            out.append(Dose(value=n.value, unit=None, family=None, base_value=None, span=n.span))
            continue
        leading_ws = len(tail) - len(tail.lstrip())
        word = m.group(0).casefold()
        alias = _UNIT_ALIASES.get(word)
        if alias is None:
            out.append(Dose(value=n.value, unit=None, family=None, base_value=None, span=n.span))
            continue
        family, multiplier, canonical = alias
        end = n.span[1] + leading_ws + len(m.group(0))
        base_value = n.value * multiplier if family != "count" else n.value
        out.append(
            Dose(
                value=n.value,
                unit=canonical,
                family=family,
                base_value=base_value,
                span=(n.span[0], end),
            )
        )
    return tuple(out)


def to_dict(d: Dose) -> dict[str, object]:
    return {
        "value": str(d.value),
        "unit": d.unit,
        "family": d.family,
        "base_value": str(d.base_value) if d.base_value is not None else None,
        "span": list(d.span),
    }


__all__ = ["Dose", "extract", "to_dict"]

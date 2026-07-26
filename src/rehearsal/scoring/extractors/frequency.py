"""`frequency` extractor — rate and interval. misc/docs/06-scoring-engine.md §4.6.

ponytail: the pattern table below covers the fixture grid's documented trap
(`cada 8 horas` vs `3 veces al día` — same per_day, textually unrelated) plus the
common canonical phrasings. Full free-text frequency parsing is open-ended;
widen the table when a fixture demonstrates a miss.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

_INT_WORD = r"(?P<n>\d+|un|una|uno|dos|tres|cuatro|cinco|six|two|three|four|five|one)"
_WORD_TO_INT = {
    "un": 1,
    "una": 1,
    "uno": 1,
    "dos": 2,
    "tres": 3,
    "cuatro": 4,
    "cinco": 5,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
}


def _n(match: re.Match[str]) -> Decimal:
    raw = match.group("n")
    return Decimal(_WORD_TO_INT.get(raw, raw) if not raw.isdigit() else raw)


@dataclass(frozen=True, slots=True)
class Frequency:
    per_day: Decimal | None
    interval_hours: Decimal | None
    prn: bool
    at_night: bool
    span: tuple[int, int]


_TWICE_PER_DAY = Decimal(2)

# Priority order matters: earlier patterns claim their span first, so a phrase
# like "dos veces al dia" is consumed whole by "per_day" before the bare "once"
# catch-all ("al dia") gets a chance to also match inside it.
_PATTERNS: list[
    tuple[re.Pattern[str], Literal["interval", "per_day", "twice", "once", "night", "prn"]]
] = [
    (re.compile(rf"cada\s+{_INT_WORD}\s+horas?"), "interval"),
    (re.compile(rf"every\s+{_INT_WORD}\s+hours?"), "interval"),
    (re.compile(rf"{_INT_WORD}\s+veces\s+al\s+d[ií]a"), "per_day"),
    (re.compile(rf"{_INT_WORD}\s+times\s+(a|per)\s+day"), "per_day"),
    (re.compile(r"dos\s+veces\s+al\s+d[ií]a"), "twice"),
    (re.compile(r"twice\s+(a\s+day|daily)"), "twice"),
    (re.compile(r"una\s+vez\s+al\s+d[ií]a|al\s+d[ií]a|diario"), "once"),
    (re.compile(r"once\s+a\s+day|daily"), "once"),
    (re.compile(r"por\s+la\s+noche|antes\s+de\s+dormir"), "night"),
    (re.compile(r"at\s+bedtime|at\s+night"), "night"),
    (re.compile(r"si\s+es\s+necesario|cuando\s+lo\s+necesite"), "prn"),
    (re.compile(r"as\s+needed|\bprn\b", re.IGNORECASE), "prn"),
]


def extract(text: str, lang: Literal["en", "es"]) -> tuple[Frequency, ...]:
    folded = text.casefold()
    out: list[Frequency] = []
    claimed: list[tuple[int, int]] = []
    for pattern, kind in _PATTERNS:
        for m in pattern.finditer(folded):
            span = (m.start(), m.end())
            if any(span[0] < c[1] and c[0] < span[1] for c in claimed):
                continue  # already consumed by a higher-priority pattern
            claimed.append(span)
            if kind == "interval":
                hours = _n(m)
                out.append(
                    Frequency(
                        per_day=(Decimal(24) / hours) if hours else None,
                        interval_hours=hours,
                        prn=False,
                        at_night=False,
                        span=span,
                    )
                )
            elif kind == "per_day":
                out.append(
                    Frequency(
                        per_day=_n(m), interval_hours=None, prn=False, at_night=False, span=span
                    )
                )
            elif kind == "once":
                out.append(
                    Frequency(
                        per_day=Decimal(1),
                        interval_hours=None,
                        prn=False,
                        at_night=False,
                        span=span,
                    )
                )
            elif kind == "twice":
                out.append(
                    Frequency(
                        per_day=Decimal(2),
                        interval_hours=None,
                        prn=False,
                        at_night=False,
                        span=span,
                    )
                )
            elif kind == "night":
                out.append(
                    Frequency(
                        per_day=Decimal(1), interval_hours=None, prn=False, at_night=True, span=span
                    )
                )
            elif kind == "prn":
                out.append(
                    Frequency(
                        per_day=None, interval_hours=None, prn=True, at_night=False, span=span
                    )
                )
    out.sort(key=lambda f: f.span[0])
    return tuple(out)


def to_dict(f: Frequency) -> dict[str, object]:
    return {
        "per_day": str(f.per_day) if f.per_day is not None else None,
        "interval_hours": str(f.interval_hours) if f.interval_hours is not None else None,
        "prn": f.prn,
        "at_night": f.at_night,
        "span": list(f.span),
    }


__all__ = ["Frequency", "extract", "to_dict"]

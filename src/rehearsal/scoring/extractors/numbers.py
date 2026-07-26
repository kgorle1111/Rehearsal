"""`numbers` extractor — cardinals, decimals, cross-lingual. misc/docs/06-scoring-engine.md §4.2.

Decimal throughout, never float (golden rule 6). Digit-form parsing implements the
decimal-separator disambiguation table (D1-D4); D5 (manifest-aware honesty rule) is
not implemented here because no manifest is wired into the frozen contract yet
(`TurnRecord` carries no `TermManifestSlice`) — that is the upgrade path once the
content-plane workstream lands a manifest type in `contracts`.

ponytail: ranges ("entre 5 y 10") and approximation-of-a-range are not implemented —
not exercised by the fixture grid's documented trap list. Add when a fixture needs it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from rehearsal.scoring.normalize import find_span

_APPROX_EN = ("about", "around", "roughly")
_APPROX_ES = ("unos", "unas", "como", "aproximadamente", "más o menos")

_WORDS_EN: dict[str, int] = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
    "a": 1,
    "an": 1,
}
_WORDS_ES: dict[str, int] = {
    "cero": 0,
    "uno": 1,
    "una": 1,
    "un": 1,
    "dos": 2,
    "tres": 3,
    "cuatro": 4,
    "cinco": 5,
    "seis": 6,
    "siete": 7,
    "ocho": 8,
    "nueve": 9,
    "diez": 10,
    "once": 11,
    "doce": 12,
    "trece": 13,
    "catorce": 14,
    "quince": 15,
    "dieciseis": 16,
    "dieciséis": 16,
    "diecisiete": 17,
    "dieciocho": 18,
    "diecinueve": 19,
    "veinte": 20,
    "veintiuno": 21,
    "veintiun": 21,
    "veintiún": 21,
    "veintidos": 22,
    "veintidós": 22,
    "treinta": 30,
    "cuarenta": 40,
    "cincuenta": 50,
    "sesenta": 60,
    "setenta": 70,
    "ochenta": 80,
    "noventa": 90,
    "cien": 100,
    "ciento": 100,
    "quinientos": 500,
    "quinientas": 500,
}

_NUMBER_RE = re.compile(r"\d[\d.,  ]*\d|\d")


@dataclass(frozen=True, slots=True)
class Number:
    value: Decimal
    span: tuple[int, int]
    written: bool
    approximate: bool


def _digit_value(raw: str, lang: Literal["en", "es"]) -> Decimal:
    """Apply decimal-separator disambiguation D1-D4 to a raw digit-group string."""
    seps = [c for c in raw if c in ".,  "]
    cleaned_variants: list[str] = []
    if len(seps) == 0:
        return Decimal(raw)
    if set(seps) - {","} == set() or set(seps) - {"."} == set():
        # Only one kind of separator present, possibly repeated.
        sep = seps[0]
        parts = raw.split(sep)
        last_len = len(parts[-1])
        if len(parts) > 1 and last_len == 3 and len(parts) == 2 and int(parts[0]) >= 1:
            # ambiguous 3-digit group: could be thousands or decimal. D1: thousands
            # if the whole thing read as thousands is >= 1000 either way (single group).
            if len(parts) == 2:
                thousands_reading = Decimal(parts[0] + parts[1])
                if thousands_reading >= 1000:
                    # D3: language default disambiguates between decimal/thousands.
                    if (lang == "en" and sep == ",") or (lang == "es" and sep == "."):
                        return thousands_reading
                    return Decimal(f"{parts[0]}.{parts[1]}")
        if len(parts) > 1 and last_len in (1, 2) or last_len >= 4:
            # D2: decimal
            return Decimal(f"{parts[0]}.{parts[1]}" if len(parts) == 2 else raw.replace(sep, ""))
        # multiple thousands groups, e.g. 1.234.567 or 1,234,567
        return Decimal("".join(parts))
    # D4: both separators present, last one is decimal.
    last_sep_idx = max(raw.rfind(","), raw.rfind("."))
    int_part = re.sub(r"[.,  ]", "", raw[:last_sep_idx])
    frac_part = raw[last_sep_idx + 1 :]
    cleaned_variants.append(f"{int_part}.{frac_part}")
    return Decimal(cleaned_variants[0])


def _extract_digits(text: str, lang: Literal["en", "es"]) -> list[Number]:
    out: list[Number] = []
    for m in _NUMBER_RE.finditer(text):
        raw = m.group(0)
        try:
            value = _digit_value(raw, lang)
        except Exception:  # noqa: BLE001 - malformed numeral, skip rather than crash a whole turn
            continue
        approximate = _has_approx_marker(text, m.start(), lang)
        out.append(
            Number(value=value, span=(m.start(), m.end()), written=False, approximate=approximate)
        )
    return out


def _has_approx_marker(text: str, pos: int, lang: Literal["en", "es"]) -> bool:
    window = text[max(0, pos - 20) : pos].casefold()
    markers = _APPROX_EN if lang == "en" else _APPROX_ES
    return any(marker in window for marker in markers)


def _extract_written(text: str, lang: Literal["en", "es"]) -> list[Number]:
    lexicon = _WORDS_EN if lang == "en" else _WORDS_ES
    out: list[Number] = []
    for m in re.finditer(r"[A-Za-zÀ-ÿ]+", text):
        word = m.group(0).casefold()
        if word in lexicon:
            approximate = _has_approx_marker(text, m.start(), lang)
            out.append(
                Number(
                    value=Decimal(lexicon[word]),
                    span=(m.start(), m.end()),
                    written=True,
                    approximate=approximate,
                )
            )
    return out


def extract(text: str, lang: Literal["en", "es"]) -> tuple[Number, ...]:
    """Parse every cardinal in `text` (digit-form and written) into canonical Numbers."""
    numbers = _extract_digits(text, lang) + _extract_written(text, lang)
    numbers.sort(key=lambda n: n.span[0])
    return tuple(numbers)


def to_dict(n: Number) -> dict[str, object]:
    return {
        "value": str(n.value),
        "span": list(n.span),
        "written": n.written,
        "approximate": n.approximate,
    }


__all__ = ["Number", "extract", "to_dict", "find_span"]

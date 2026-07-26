"""`negation` extractor — cues, scope, polarity. misc/docs/06-scoring-engine.md §4.7.

NegEx-style cue + scope-window algorithm, no dependency, deterministic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

SCOPE_WINDOW = 8  # ponytail: calibration knob (§4.7); widen only with a fixture showing a miss.

_PRE_CUES_EN = (
    "never",
    "cannot",
    "can't",
    "don't",
    "doesn't",
    "didn't",
    "hasn't",
    "haven't",
    "won't",
    "shouldn't",
    "without",
    "denies",
    "deny",
    "neither",
    "nor",
    "none",
    "not",
    "n't",
    "no",
)
_PRE_CUES_ES = (
    "nunca",
    "jamás",
    "sin",
    "ni",
    "ninguno",
    "ninguna",
    "nada",
    "tampoco",
    "niega",
    "no",
)

_PSEUDO_EN = ("not only", "not just", "no increase", "no change", "no wonder", "not necessarily")
_PSEUDO_ES = (
    "no sólo",
    "no solo",
    "no obstante",
    "no es que",
    "sin embargo",
    "sin duda",
    "no sé si",
)

_TERMINATORS_EN = {"but", "however", "although", "except", "unless", "and"}
_TERMINATORS_ES = {
    "pero",
    "sino",
    "aunque",
    "excepto",
    "salvo",
}  # "y" deliberately excluded (§4.7 step 4)
_CONCORD_ES = {"nada", "nunca", "ni"}  # continues the same negation rather than a new one

_TOKEN_RE = re.compile(r"[A-Za-zÀ-ÿ']+|[.,;?!¿¡]")


@dataclass(frozen=True, slots=True)
class NegationSpan:
    cue: str
    span: tuple[int, int]  # cue span in original text
    scope_span: tuple[int, int]  # covered token range in original text


@dataclass(frozen=True, slots=True)
class TargetPolarity:
    target: str
    span: tuple[int, int]
    polarity: Literal["negated", "affirmed"]
    ambiguous: bool


def _tokens_with_spans(text: str) -> list[tuple[str, int, int]]:
    return [(m.group(0), m.start(), m.end()) for m in _TOKEN_RE.finditer(text)]


def extract_cues(text: str, lang: Literal["en", "es"]) -> tuple[NegationSpan, ...]:
    """Find negation cues and their scope window, applying the pseudo-negation
    exclusion (checked first, greedily) and the terminator/concord rules."""
    folded = text.casefold()
    pseudo = _PSEUDO_EN if lang == "en" else _PSEUDO_ES
    pre_cues = _PRE_CUES_EN if lang == "en" else _PRE_CUES_ES
    terminators = _TERMINATORS_EN if lang == "en" else _TERMINATORS_ES
    concord = set() if lang == "en" else _CONCORD_ES

    pseudo_spans: list[tuple[int, int]] = []
    for phrase in pseudo:
        start = 0
        while True:
            idx = folded.find(phrase, start)
            if idx == -1:
                break
            pseudo_spans.append((idx, idx + len(phrase)))
            start = idx + len(phrase)

    def inside_pseudo(pos: int) -> bool:
        return any(a <= pos < b for a, b in pseudo_spans)

    tokens = _tokens_with_spans(folded)
    cues: list[NegationSpan] = []
    for i, (tok, s, e) in enumerate(tokens):
        cue_word = tok if tok != "n't" else "n't"
        if cue_word not in pre_cues:
            continue
        if inside_pseudo(s):
            continue
        # Walk forward, capped at SCOPE_WINDOW tokens or a terminator.
        # Concord cues (Spanish nada/nunca/ni) extend rather than start a new scope.
        scope_end = e
        count = 0
        for _tok2, _s2, e2 in tokens[i + 1 :]:
            if count >= SCOPE_WINDOW:
                break
            if _tok2 in terminators and _tok2 not in concord:
                break
            if _tok2 in (".", "?", "!", ";"):
                break
            scope_end = e2
            count += 1
        cues.append(NegationSpan(cue=tok, span=(s, e), scope_span=(s, scope_end)))
    return tuple(cues)


def check_targets(
    text: str, lang: Literal["en", "es"], targets: tuple[str, ...]
) -> tuple[TargetPolarity, ...]:
    """For each literal target phrase, report whether it falls in an odd number
    of (non-concord) negation scopes -> negated, else affirmed. §4.7 steps 6-7."""
    cues = extract_cues(text, lang)
    folded = text.casefold()
    out: list[TargetPolarity] = []
    for target in targets:
        target_fold = target.casefold()
        idx = folded.find(target_fold)
        if idx == -1:
            continue
        t_span = (idx, idx + len(target_fold))
        covering = [c for c in cues if c.scope_span[0] <= t_span[0] < c.scope_span[1]]
        negated = len(covering) % 2 == 1
        out.append(
            TargetPolarity(
                target=target,
                span=t_span,
                polarity="negated" if negated else "affirmed",
                ambiguous=False,
            )
        )
    return tuple(out)


def to_dict(t: TargetPolarity) -> dict[str, object]:
    return {
        "target": t.target,
        "span": list(t.span),
        "polarity": t.polarity,
        "ambiguous": t.ambiguous,
    }


__all__ = ["NegationSpan", "TargetPolarity", "extract_cues", "check_targets", "to_dict"]

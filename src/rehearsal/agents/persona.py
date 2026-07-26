"""Deterministic persona-consistency checker. misc/docs/04, BUILD.md WS3.

Detects contradictions between what agent utterances say and what a
session's ``ClinicalState`` actually holds — e.g. the clinician naming a
dose that doesn't match ``ClinicalState.medications``.

# ponytail: term/number matching against the state's medications, not
# exhaustive NLP. It only catches the case a scripted (or future model)
# agent is most likely to get wrong: naming a medication by name but
# stating a number that isn't its recorded dose or frequency. It will
# miss paraphrased contradictions ("a bit more than usual") and it does
# not check symptom/allergy facts, since those rarely carry a
# corrigible number. Upgrade to a real term extractor (WS1's) if/when
# false negatives on those categories start mattering.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from rehearsal.contracts import ClinicalState

_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


@dataclass(frozen=True, slots=True)
class ConsistencyViolation:
    utterance_index: int
    detail: str


@dataclass(frozen=True, slots=True)
class PersonaConsistencyReport:
    total_utterances: int
    consistent_utterances: int
    violations: tuple[ConsistencyViolation, ...]

    @property
    def rate(self) -> float:
        if self.total_utterances == 0:
            return 1.0
        return self.consistent_utterances / self.total_utterances


def check_persona_consistency(
    utterances: tuple[str, ...], state: ClinicalState
) -> PersonaConsistencyReport:
    """Scan each utterance for a named medication whose stated dose/
    frequency numbers contradict the state. An utterance naming a
    medication but citing a number absent from that medication's own
    dose and frequency is flagged."""
    violations: list[ConsistencyViolation] = []
    for index, utterance in enumerate(utterances):
        lowered = utterance.lower()
        for med in state.medications:
            if med.name.lower() not in lowered:
                continue
            numbers_in_utterance = set(_NUMBER_RE.findall(utterance))
            if not numbers_in_utterance:
                continue  # names the drug, states no number — nothing to check
            expected = {med.dose, str(med.frequency_per_day)}
            if numbers_in_utterance.isdisjoint(expected):
                violations.append(
                    ConsistencyViolation(
                        utterance_index=index,
                        detail=(
                            f"mentions {med.name!r} with numbers {sorted(numbers_in_utterance)} "
                            f"but state records dose={med.dose!r} "
                            f"frequency_per_day={med.frequency_per_day}"
                        ),
                    )
                )
    total = len(utterances)
    consistent = total - len({v.utterance_index for v in violations})
    return PersonaConsistencyReport(
        total_utterances=total,
        consistent_utterances=consistent,
        violations=tuple(violations),
    )

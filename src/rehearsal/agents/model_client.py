"""The model seam for the clinician and patient agents.

No real model host exists in this build yet (MLX/llama.cpp wiring is WS4's
job, later). Everything downstream of `LiveModelClient` — clinician.py,
patient.py — is written against the Protocol below, not against any
concrete client, so that dropping in a real implementation later requires
no change to the agent classes.

``ConversationNode`` is a deliberate simplification. The full scenario
graph (``docs/07-data-and-scenarios.md``) is not built yet — WS7 shipped
``ClinicalState`` and its validator, not node traversal — so this is the
smallest structure WS3's agents need: which facts (drawn verbatim from a
``ClinicalState``) a given turn must convey, and who speaks it. A future
graph module can produce these without either agent class changing.

``CounterpartTurn`` is a trimmed version of ``CounterpartTurn`` in
misc/docs/04-ai-engineering.md §4.1: just the reply text and a
verbatim-heard field. ``heard_confidence``, ``node_satisfied`` and
``repair_request`` are dropped because nothing in this phase consumes them
(no orchestrator, no trainee audio) — added back when WS4 needs them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from rehearsal.contracts import (
    Allergy,
    ClinicalState,
    Medication,
    SpeakerRole,
    SymptomTimelineEntry,
)

Fact = Medication | SymptomTimelineEntry | Allergy


@dataclass(frozen=True, slots=True)
class ConversationNode:
    """What one turn must convey. Stand-in for a future scenario-graph node.

    ``facts`` must be objects drawn from the ``ClinicalState`` passed
    alongside this node — that invariant is what makes clinical-fact
    invention structurally impossible for a client that only reads
    ``facts`` (see ``ScriptedModelClient``).
    """

    speaker: SpeakerRole
    facts: tuple[Fact, ...]


@dataclass(frozen=True, slots=True)
class CounterpartTurn:
    """Simplified ``CounterpartTurn`` (misc/docs/04-ai-engineering.md §4.1)."""

    reply_text: str
    heard_verbatim: str = ""


class LiveModelClient(Protocol):
    """The seam a real model host implements (WS4, future).

    ``generate_turn`` receives exactly what a real model call would need:
    who is speaking, the full clinical state (for persona/register
    grounding), and the node naming which facts this turn must convey. A
    real implementation would render these into an assembled prompt
    context per docs/04 §6 and run inference; that assembly step does not
    exist here because there is nothing yet to assemble a prompt for.
    """

    def generate_turn(
        self, role: SpeakerRole, state: ClinicalState, node: ConversationNode
    ) -> CounterpartTurn: ...


def _render_fact(fact: Fact) -> str:
    """Deterministic, verbatim-from-state phrasing of one clinical fact.

    ponytail: naive template per fact type, no register/literacy variation.
    Upgrade when a real model (or richer scripted persona) replaces this.
    """
    if isinstance(fact, Medication):
        return (
            f"You should take {fact.name} {fact.dose}{fact.unit}, "
            f"{fact.frequency_per_day} times a day, for {fact.duration}."
        )
    if isinstance(fact, SymptomTimelineEntry):
        return f"{fact.offset}, I started having {fact.symptom}."
    return f"I have an allergy to {fact.substance}."  # Allergy


class ScriptedModelClient:
    """Deterministic stand-in for a real model.

    Composes an utterance purely from ``node.facts`` — fields that are
    themselves drawn from the caller's ``ClinicalState`` — so the output
    can only ever contain facts traceable to the input. It never reads
    ``state`` directly, which is what makes clinical-fact-invention
    structurally impossible to demonstrate here, not just empirically
    absent.
    """

    def generate_turn(
        self, role: SpeakerRole, state: ClinicalState, node: ConversationNode
    ) -> CounterpartTurn:
        del state  # unused: the scripted client only ever reads node.facts
        sentences = [_render_fact(fact) for fact in node.facts]
        reply_text = " ".join(sentences) if sentences else "Go on."
        return CounterpartTurn(reply_text=reply_text)

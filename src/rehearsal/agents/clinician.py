"""ClinicianAgent — the English-speaking counterpart. misc/docs/04 §4.1."""

from __future__ import annotations

from dataclasses import dataclass

from rehearsal.agents.model_client import ConversationNode, CounterpartTurn, LiveModelClient
from rehearsal.contracts import ClinicalState, SpeakerRole


class WrongSpeakerError(ValueError):
    """Raised when a node meant for the other speaker is handed to this agent."""


@dataclass(frozen=True, slots=True)
class ClinicianAgent:
    """Plays the clinician. Verbalises ``ClinicalState`` facts named by a
    node's ``facts``; never invents a fact not present in that tuple."""

    client: LiveModelClient

    def take_turn(self, state: ClinicalState, node: ConversationNode) -> CounterpartTurn:
        if node.speaker is not SpeakerRole.CLINICIAN:
            raise WrongSpeakerError(f"node.speaker={node.speaker} is not CLINICIAN")
        return self.client.generate_turn(SpeakerRole.CLINICIAN, state, node)

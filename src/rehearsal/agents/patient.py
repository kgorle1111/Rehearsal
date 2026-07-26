"""PatientAgent — the Spanish-speaking counterpart. misc/docs/04 §4.2."""

from __future__ import annotations

from dataclasses import dataclass

from rehearsal.agents.clinician import WrongSpeakerError as WrongSpeakerError
from rehearsal.agents.model_client import ConversationNode, CounterpartTurn, LiveModelClient
from rehearsal.contracts import ClinicalState, SpeakerRole


@dataclass(frozen=True, slots=True)
class PatientAgent:
    """Plays the patient. Same shape as ``ClinicianAgent``, patient-side
    facts only — enforced by the ``node.speaker`` check, not by a separate
    context allowlist (that enforcement is WS5's ``isolation.py``)."""

    client: LiveModelClient

    def take_turn(self, state: ClinicalState, node: ConversationNode) -> CounterpartTurn:
        if node.speaker is not SpeakerRole.PATIENT:
            raise WrongSpeakerError(f"node.speaker={node.speaker} is not PATIENT")
        return self.client.generate_turn(SpeakerRole.PATIENT, state, node)

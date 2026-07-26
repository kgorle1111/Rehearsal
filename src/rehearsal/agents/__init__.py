"""Counterpart and coach agents. misc/docs/04-ai-engineering.md."""

from __future__ import annotations

from rehearsal.agents.clinician import ClinicianAgent, WrongSpeakerError
from rehearsal.agents.coach import CoachAgent, CoachHint
from rehearsal.agents.model_client import (
    ConversationNode,
    CounterpartTurn,
    LiveModelClient,
    ScriptedModelClient,
)
from rehearsal.agents.patient import PatientAgent
from rehearsal.agents.persona import (
    ConsistencyViolation,
    PersonaConsistencyReport,
    check_persona_consistency,
)

__all__ = [
    "ClinicianAgent",
    "CoachAgent",
    "CoachHint",
    "ConsistencyViolation",
    "ConversationNode",
    "CounterpartTurn",
    "LiveModelClient",
    "PatientAgent",
    "PersonaConsistencyReport",
    "ScriptedModelClient",
    "WrongSpeakerError",
    "check_persona_consistency",
]

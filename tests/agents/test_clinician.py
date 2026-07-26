from __future__ import annotations

import random

import pytest

from rehearsal.agents.clinician import ClinicianAgent, WrongSpeakerError
from rehearsal.agents.model_client import ConversationNode, ScriptedModelClient
from rehearsal.contracts import ClinicalState, Medication, SpeakerRole


def _state(**overrides: object) -> ClinicalState:
    defaults: dict[str, object] = {
        "condition": "type 2 diabetes mellitus",
        "medications": (
            Medication(
                name="metformin",
                dose="500",
                unit="mg",
                route="oral",
                frequency_per_day=2,
                duration="4 years",
            ),
        ),
        "symptom_timeline": (),
        "allergies": (),
        "emotional_state": "worried",
        "health_literacy": "low",
        "language_variety": "es-MX-rural-central",
        "onset": "3 weeks ago, gradual",
    }
    defaults.update(overrides)
    return ClinicalState(**defaults)  # type: ignore[arg-type]


def test_take_turn_wrong_speaker_raises() -> None:
    agent = ClinicianAgent(client=ScriptedModelClient())
    state = _state()
    node = ConversationNode(speaker=SpeakerRole.PATIENT, facts=state.medications)
    with pytest.raises(WrongSpeakerError):
        agent.take_turn(state, node)


def test_take_turn_conveys_only_node_facts() -> None:
    agent = ClinicianAgent(client=ScriptedModelClient())
    state = _state()
    node = ConversationNode(speaker=SpeakerRole.CLINICIAN, facts=state.medications)
    turn = agent.take_turn(state, node)
    assert "metformin" in turn.reply_text
    assert "500" in turn.reply_text
    assert "twice" not in turn.reply_text  # never editorialises the number


def test_take_turn_empty_node_produces_placeholder() -> None:
    agent = ClinicianAgent(client=ScriptedModelClient())
    state = _state()
    node = ConversationNode(speaker=SpeakerRole.CLINICIAN, facts=())
    turn = agent.take_turn(state, node)
    assert turn.reply_text  # never empty string


def test_clinical_fact_invention_rate_zero() -> None:
    """Property test: give the clinician a state with several medications
    but a node naming only ONE of them. The others' names/doses — real
    clinical facts the agent *had access to* via ``state`` — must never
    appear in the output. This is the trap: a buggy implementation that
    reads ``state`` instead of only ``node.facts`` would fail it."""
    rng = random.Random(1234)
    agent = ClinicianAgent(client=ScriptedModelClient())
    total = 0
    invented = 0
    names = ["metformin", "lisinopril", "atorvastatin", "amlodipine", "omeprazole"]
    for _trial in range(50):
        n_meds = rng.randint(2, 5)
        chosen_names = rng.sample(names, n_meds)
        # distinct doses, so a match is never a coincidental collision
        chosen_doses = rng.sample(range(5, 999), n_meds)
        medications = tuple(
            Medication(
                name=name,
                dose=str(dose),
                unit="mg",
                route="oral",
                frequency_per_day=rng.randint(1, 4),
                duration=f"{rng.randint(1, 10)} years",
            )
            for name, dose in zip(chosen_names, chosen_doses, strict=True)
        )
        state = _state(medications=medications)
        conveyed = rng.choice(medications)
        node = ConversationNode(speaker=SpeakerRole.CLINICIAN, facts=(conveyed,))
        turn = agent.take_turn(state, node)
        total += 1
        withheld = [m for m in medications if m is not conveyed]
        if any(m.name in turn.reply_text or m.dose in turn.reply_text for m in withheld):
            invented += 1
        assert conveyed.name in turn.reply_text
        assert conveyed.dose in turn.reply_text

    rate = invented / total
    print(f"clinical_fact_invention_rate = {rate:.2f} ({invented}/{total})")
    assert rate == 0.0

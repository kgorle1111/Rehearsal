from __future__ import annotations

import random

import pytest

from rehearsal.agents.model_client import ConversationNode, ScriptedModelClient
from rehearsal.agents.patient import PatientAgent, WrongSpeakerError
from rehearsal.contracts import Allergy, ClinicalState, SpeakerRole, SymptomTimelineEntry


def _state(**overrides: object) -> ClinicalState:
    defaults: dict[str, object] = {
        "condition": "type 2 diabetes mellitus",
        "medications": (),
        "symptom_timeline": (
            SymptomTimelineEntry(offset="3 weeks ago", symptom="increased thirst and fatigue"),
        ),
        "allergies": (Allergy(substance="penicillin"),),
        "emotional_state": "worried",
        "health_literacy": "low",
        "language_variety": "es-MX-rural-central",
        "onset": "3 weeks ago, gradual",
    }
    defaults.update(overrides)
    return ClinicalState(**defaults)  # type: ignore[arg-type]


def test_take_turn_wrong_speaker_raises() -> None:
    agent = PatientAgent(client=ScriptedModelClient())
    state = _state()
    node = ConversationNode(speaker=SpeakerRole.CLINICIAN, facts=state.symptom_timeline)
    with pytest.raises(WrongSpeakerError):
        agent.take_turn(state, node)


def test_take_turn_conveys_symptom_fact() -> None:
    agent = PatientAgent(client=ScriptedModelClient())
    state = _state()
    node = ConversationNode(speaker=SpeakerRole.PATIENT, facts=state.symptom_timeline)
    turn = agent.take_turn(state, node)
    assert "increased thirst and fatigue" in turn.reply_text
    assert "3 weeks ago" in turn.reply_text


def test_take_turn_conveys_allergy_fact_only() -> None:
    agent = PatientAgent(client=ScriptedModelClient())
    state = _state()
    node = ConversationNode(speaker=SpeakerRole.PATIENT, facts=state.allergies)
    turn = agent.take_turn(state, node)
    assert "penicillin" in turn.reply_text
    assert "thirst" not in turn.reply_text  # symptom not in this node's facts


def test_clinical_fact_invention_rate_zero() -> None:
    """Property test, patient-side: several symptom entries in the state,
    the node names only one. The withheld symptoms' text must never
    appear in the output even though the agent's ``state`` argument
    contains them."""
    rng = random.Random(4321)
    agent = PatientAgent(client=ScriptedModelClient())
    symptom_pool = [
        ("3 weeks ago", "increased thirst and fatigue"),
        ("4 days ago", "shortness of breath at night"),
        ("2 months ago", "blurred vision"),
        ("1 week ago", "numbness in the feet"),
        ("yesterday", "dizziness on standing"),
    ]
    total = 0
    invented = 0
    for _ in range(50):
        n = rng.randint(2, len(symptom_pool))
        chosen = rng.sample(symptom_pool, n)
        entries = tuple(SymptomTimelineEntry(offset=o, symptom=s) for o, s in chosen)
        state = _state(symptom_timeline=entries)
        conveyed = rng.choice(entries)
        node = ConversationNode(speaker=SpeakerRole.PATIENT, facts=(conveyed,))
        turn = agent.take_turn(state, node)
        total += 1
        withheld = [e for e in entries if e is not conveyed]
        if any(e.symptom in turn.reply_text for e in withheld):
            invented += 1
        assert conveyed.symptom in turn.reply_text

    rate = invented / total
    print(f"clinical_fact_invention_rate (patient) = {rate:.2f} ({invented}/{total})")
    assert rate == 0.0

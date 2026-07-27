"""Coverage for `src/rehearsal/hosts/ollama.py` (commit 536fbcb, landed
out-of-band — see NOT-BUILT-YET.md P-extra). Added at the P5 review gate;
nobody owns this file yet.

Scope: the pure/mockable seams only — `_extract_json`'s parsing tolerance,
`_chat`'s network-failure -> `OllamaUnavailable` translation, and the
grader's malformed-output-degrades-to-abstain contract (Golden Rule 1: no
model output reaches a `Finding` without going through this guard). No test
here talks to a real Ollama server.

Also covers the P5 security-review fixes: loopback-only host enforcement
(finding 1, HIGH), quote-to-span computed in code rather than trusted from
the model (finding 2, part of the isolation/span-honesty fixes), and the
fact-presence sanity check (`check_facts_present`).
"""

from __future__ import annotations

import json
import urllib.request
from urllib.error import URLError

import pytest

import rehearsal.hosts.ollama as ollama
from rehearsal.agents.model_client import ConversationNode
from rehearsal.contracts import ClinicalState, Medication, SpeakerRole
from rehearsal.scoring.grader import GraderOutput

# ---- _extract_json -------------------------------------------------------


def test_extract_json_parses_object_wrapped_in_prose_and_fences() -> None:
    raw = 'Sure, here you go:\n```json\n{"clean": true, "findings": []}\n```\nlet me know!'
    assert ollama._extract_json(raw) == {"clean": True, "findings": []}


def test_extract_json_raises_on_no_object() -> None:
    with pytest.raises(json.JSONDecodeError):
        ollama._extract_json("no json here at all")


def test_extract_json_skips_leading_unbalanced_brace() -> None:
    # A stray "{" before the real object (e.g. from a broken fence) must not
    # abort the scan — it should keep looking for a balanced object.
    raw = 'garbage { still garbage {"clean": true, "findings": []}'
    assert ollama._extract_json(raw) == {"clean": True, "findings": []}


# ---- _ensure_loopback / UnsafeHost ----------------------------------------


@pytest.mark.parametrize(
    "host",
    ["http://localhost:11434", "http://127.0.0.1:11434", "http://[::1]:11434"],
)
def test_loopback_hosts_are_accepted(host: str) -> None:
    ollama._ensure_loopback(host)  # must not raise


@pytest.mark.parametrize(
    "host",
    [
        "http://example.com:11434",
        "http://10.0.0.5:11434",
        "http://my-gpu-box.local:11434",
        "http://0.0.0.0:11434",
    ],
)
def test_non_loopback_hosts_are_rejected(host: str) -> None:
    with pytest.raises(ollama.UnsafeHost, match="not loopback"):
        ollama._ensure_loopback(host)


def test_chat_refuses_non_loopback_host_before_any_network_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def _spy(*args: object, **kwargs: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(urllib.request, "urlopen", _spy)
    with pytest.raises(ollama.UnsafeHost):
        ollama._chat("http://example.com:11434", "gemma4:e4b-mlx", [])
    assert called is False, "must reject before touching the network, not after"


# ---- _chat -----------------------------------------------------------


def test_chat_raises_ollama_unavailable_on_connection_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise(*args: object, **kwargs: object) -> None:
        raise URLError("connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", _raise)
    with pytest.raises(ollama.OllamaUnavailable, match="not reachable"):
        ollama._chat(
            "http://localhost:11434", "gemma4:e4b-mlx", [{"role": "user", "content": "hi"}]
        )


# ---- OllamaGraderClient.grade --------------------------------------------


def test_grader_abstains_on_malformed_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ollama, "_chat", lambda *a, **k: "not json")
    out = ollama.OllamaGraderClient().grade(
        source="x", rendering="y", direction="en_to_es", speaker="clinician"
    )
    assert isinstance(out, GraderOutput)
    assert out.abstain is True
    assert out.findings == ()


def test_grader_filters_unknown_finding_types(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.dumps(
        {
            "clean": False,
            "findings": [
                {"type": "not_a_real_type", "severity": "critical", "note": "bogus"},
                {"type": "omission", "severity": "critical", "note": "real one", "confidence": 0.9},
            ],
        }
    )
    monkeypatch.setattr(ollama, "_chat", lambda *a, **k: payload)
    out = ollama.OllamaGraderClient().grade(
        source="x", rendering="y", direction="es_to_en", speaker="patient"
    )
    assert out.abstain is False
    assert len(out.findings) == 1
    assert out.findings[0].type.value == "omission"


def test_grader_clamps_out_of_range_confidence(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.dumps(
        {
            "clean": False,
            "findings": [
                {"type": "distortion", "severity": "non_critical", "note": "n", "confidence": 5.0},
            ],
        }
    )
    monkeypatch.setattr(ollama, "_chat", lambda *a, **k: payload)
    out = ollama.OllamaGraderClient().grade(
        source="x", rendering="y", direction="en_to_es", speaker="clinician"
    )
    assert out.findings[0].confidence == 1.0


def test_grader_reports_clean_when_no_findings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ollama, "_chat", lambda *a, **k: '{"clean": true, "findings": []}')
    out = ollama.OllamaGraderClient().grade(
        source="x", rendering="y", direction="en_to_es", speaker="clinician"
    )
    assert out.abstain is False
    assert out.findings == ()
    assert out.clean_reason


def test_grader_computes_span_from_verbatim_quote(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.dumps(
        {
            "clean": False,
            "findings": [
                {
                    "type": "distortion",
                    "severity": "non_critical",
                    "note": "n",
                    "rendering_quote": "wrong",
                    "confidence": 0.8,
                }
            ],
        }
    )
    monkeypatch.setattr(ollama, "_chat", lambda *a, **k: payload)
    out = ollama.OllamaGraderClient().grade(
        source="x", rendering="this is wrong here", direction="en_to_es", speaker="clinician"
    )
    f = out.findings[0]
    assert f.rendering_span is not None
    assert f.rendering_span.start == "this is wrong here".index("wrong")
    assert f.rendering_span.end == f.rendering_span.start + len("wrong")


def test_grader_finding_with_unfindable_quote_has_no_span(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.dumps(
        {
            "clean": False,
            "findings": [
                {
                    "type": "distortion",
                    "severity": "non_critical",
                    "note": "n",
                    "rendering_quote": "not actually in the rendering",
                    "confidence": 0.8,
                }
            ],
        }
    )
    monkeypatch.setattr(ollama, "_chat", lambda *a, **k: payload)
    out = ollama.OllamaGraderClient().grade(
        source="x", rendering="something else entirely", direction="en_to_es", speaker="clinician"
    )
    assert out.findings[0].rendering_span is None


def test_spanless_grader_finding_dropped_by_merge(monkeypatch: pytest.MonkeyPatch) -> None:
    """The model claiming a quote that isn't verbatim in the rendering must
    not silently produce a located-looking Finding that survives merge —
    merge.py drops any grader finding with no span at all."""
    from rehearsal.scoring.merge import merge_findings

    payload = json.dumps(
        {
            "clean": False,
            "findings": [
                {"type": "distortion", "severity": "critical", "note": "n", "confidence": 0.9}
            ],
        }
    )
    monkeypatch.setattr(ollama, "_chat", lambda *a, **k: payload)
    out = ollama.OllamaGraderClient().grade(
        source="x", rendering="y", direction="en_to_es", speaker="clinician"
    )
    assert out.findings[0].rendering_span is None
    assert out.findings[0].source_span is None
    merged = merge_findings((), out)
    assert merged == ()


# ---- check_facts_present ---------------------------------------------


def test_check_facts_present_flags_a_dropped_medication() -> None:
    med = Medication(
        name="metformin", dose="500", unit="mg", route="oral", frequency_per_day=2, duration="4y"
    )
    node = ConversationNode(speaker=SpeakerRole.PATIENT, facts=(med,))
    missing = ollama.check_facts_present(node, "I have a headache today.")
    assert len(missing) == 1
    assert "metformin" in missing[0]


def test_check_facts_present_empty_when_keywords_present() -> None:
    med = Medication(
        name="metformin", dose="500", unit="mg", route="oral", frequency_per_day=2, duration="4y"
    )
    node = ConversationNode(speaker=SpeakerRole.PATIENT, facts=(med,))
    missing = ollama.check_facts_present(
        node, "You should take metformin 500mg twice a day for 4 years."
    )
    assert missing == ()


# ---- OllamaLiveClient.generate_turn ---------------------------------


def test_live_client_speaks_only_spanish_for_patient_persona(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}

    def _fake_chat(host: str, model: str, messages: list[dict[str, str]], **kwargs: object) -> str:
        captured["prompt"] = messages[0]["content"]
        return "Me duele la cabeza."

    monkeypatch.setattr(ollama, "_chat", _fake_chat)
    state = ClinicalState(
        condition="c",
        medications=(
            Medication(
                name="metformin",
                dose="500",
                unit="mg",
                route="oral",
                frequency_per_day=2,
                duration="4 years",
            ),
        ),
        symptom_timeline=(),
        allergies=(),
        emotional_state="worried",
        health_literacy="low",
        language_variety="es-MX",
        onset="today",
    )
    node = ConversationNode(speaker=SpeakerRole.PATIENT, facts=(state.medications[0],))
    turn = ollama.OllamaLiveClient().generate_turn(SpeakerRole.PATIENT, state, node)
    assert turn.reply_text == "Me duele la cabeza."
    assert "Speak ONLY Spanish" in captured["prompt"]
    assert "metformin" in captured["prompt"]

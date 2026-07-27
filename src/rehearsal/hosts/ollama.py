"""Ollama-backed implementations of the two model seams.

`OllamaLiveClient` fills `agents.model_client.LiveModelClient` (counterpart
turns); `OllamaGraderClient` fills `scoring.grader.GraderClient` (the single
structured grade call). Both talk to a local Ollama server over HTTP with
stdlib urllib only — no new dependency.

Demo-scoped: one model serves both seams. The doc set's two-model layout
(separate live/grader processes, GPU admission control) is deferred — see
ROADMAP.md.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Literal

from rehearsal.agents.model_client import ConversationNode, CounterpartTurn, _render_fact
from rehearsal.contracts import ClinicalState, ErrorType, Finding, Provenance, Severity, SpeakerRole
from rehearsal.scoring.grader import GraderOutput

DEFAULT_MODEL = "gemma4:e4b-mlx"
DEFAULT_HOST = "http://localhost:11434"


class OllamaUnavailable(RuntimeError):
    """Ollama isn't reachable. Message says how to fix it."""


def _chat(
    host: str,
    model: str,
    messages: list[dict[str, str]],
    *,
    json_format: bool = False,
    temperature: float = 0.7,
    timeout: float = 120.0,
) -> str:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature},
    }
    if json_format:
        payload["format"] = "json"
    req = urllib.request.Request(
        f"{host}/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.load(resp)
    except (urllib.error.URLError, OSError) as e:
        raise OllamaUnavailable(
            f"Ollama not reachable at {host} ({e}); start it with `ollama serve` "
            f"and ensure the model exists (`ollama pull {model}`)"
        ) from e
    return str(body["message"]["content"]).strip()


@dataclass(frozen=True, slots=True)
class OllamaLiveClient:
    """Counterpart turns via a local Gemma. Information isolation holds by
    construction: the prompt contains only persona surface + the node's
    facts — no rubric, no manifest, no learner model (misc/docs/04 §6)."""

    model: str = DEFAULT_MODEL
    host: str = DEFAULT_HOST

    def generate_turn(
        self, role: SpeakerRole, state: ClinicalState, node: ConversationNode
    ) -> CounterpartTurn:
        facts = "\n".join(f"- {_render_fact(f)}" for f in node.facts)
        if role is SpeakerRole.PATIENT:
            persona = (
                "You are a Spanish-speaking patient (Mexican Spanish) at a clinic visit. "
                f"You feel {state.emotional_state}. Health literacy: {state.health_literacy}. "
                "Speak ONLY Spanish, in the first person, naturally and briefly (1-3 sentences)."
            )
        else:
            persona = (
                "You are an English-speaking clinician at a clinic visit. "
                "Speak ONLY English, addressing the patient directly, briefly (1-3 sentences), "
                "in plain professional language."
            )
        prompt = (
            f"{persona}\n\n"
            "Say one conversational utterance that conveys EXACTLY these facts — "
            "all of them, and nothing clinical beyond them:\n"
            f"{facts}\n\n"
            "Reply with the utterance only, no quotes, no preamble."
        )
        text = _chat(self.host, self.model, [{"role": "user", "content": prompt}])
        return CounterpartTurn(reply_text=text, heard_verbatim="")


_VALID_TYPES = {e.value for e in ErrorType}


def _extract_json(raw: str) -> Any:
    """Parse the first complete JSON object in `raw`. The gemma4 mlx build
    ignores Ollama's format=json and wraps output in ```json fences, sometimes
    with stray text before the object — so scan for a balanced {...} instead
    of trusting the whole string."""
    start = raw.find("{")
    if start == -1:
        raise json.JSONDecodeError("no object", raw, 0)
    decoder = json.JSONDecoder()
    while start != -1:
        try:
            obj, _ = decoder.raw_decode(raw, start)
            return obj
        except json.JSONDecodeError:
            start = raw.find("{", start + 1)
    raise json.JSONDecodeError("no parseable object", raw, 0)


@dataclass(frozen=True, slots=True)
class OllamaGraderClient:
    """The single structured grade call (misc/docs/06 §5): temperature 0,
    sees only source/rendering/direction/speaker. Malformed model output
    degrades to abstain — never raises into the scoring plane."""

    model: str = DEFAULT_MODEL
    host: str = DEFAULT_HOST
    prompt_version: str = field(default="grader/ollama-v1")

    def grade(
        self,
        *,
        source: str,
        rendering: str,
        direction: Literal["en_to_es", "es_to_en"],
        speaker: Literal["clinician", "patient"],
    ) -> GraderOutput:
        en_to_es = direction == "en_to_es"
        src_lang, ren_lang = ("English", "Spanish") if en_to_es else ("Spanish", "English")
        prompt = (
            "You are grading a medical interpreter trainee's rendering for semantic "
            "fidelity only. Deterministic checks already handle numbers, dosage, "
            "frequency, negation, laterality and allergies — do NOT re-flag those. "
            "Flag only genuinely semantic problems: omission, addition, substitution, "
            "distortion, editorialization, role_exchange, register_shift, "
            "false_fluency, first_person_violation.\n\n"
            f"The {speaker} said ({src_lang} source):\n{source}\n\n"
            f"Trainee rendering ({ren_lang}):\n{rendering}\n\n"
            "Respond with JSON only:\n"
            '{"clean": true|false, "findings": [{"type": "<one of the nine types>", '
            '"severity": "critical"|"non_critical", "note": "<one line>", '
            '"confidence": 0.0-1.0}]}\n'
            'If the rendering is faithful, return {"clean": true, "findings": []}.'
        )
        raw = _chat(
            self.host,
            self.model,
            [{"role": "user", "content": prompt}],
            json_format=True,
            temperature=0.0,
        )
        try:
            data = _extract_json(raw)
            findings = tuple(
                Finding(
                    type=ErrorType(f["type"]),
                    severity=Severity(f.get("severity", "non_critical")),
                    note=str(f.get("note", ""))[:200],
                    provenance=Provenance.GRADER,
                    confidence=max(0.0, min(1.0, float(f.get("confidence", 0.5)))),
                )
                for f in data.get("findings", [])
                if f.get("type") in _VALID_TYPES
            )
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            return GraderOutput(abstain=True, findings=(), abstain_reason="malformed grader output")
        if not findings:
            return GraderOutput(
                abstain=False, findings=(), clean_reason="grader found no semantic issues"
            )
        return GraderOutput(abstain=False, findings=findings)


__all__ = ["OllamaLiveClient", "OllamaGraderClient", "OllamaUnavailable", "DEFAULT_MODEL"]

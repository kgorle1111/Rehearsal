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
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Literal

from rehearsal.agents.isolation import assemble
from rehearsal.agents.model_client import ConversationNode, CounterpartTurn, Fact, _render_fact
from rehearsal.contracts import (
    ClinicalState,
    ErrorType,
    Finding,
    Provenance,
    Severity,
    Span,
    SpeakerRole,
)
from rehearsal.scoring.grader import GraderOutput

DEFAULT_MODEL = "gemma4:e4b-mlx"
DEFAULT_HOST = "http://localhost:11434"

_LOOPBACK_HOSTNAMES = {"localhost", "127.0.0.1", "::1"}


class OllamaUnavailable(RuntimeError):
    """Ollama isn't reachable. Message says how to fix it."""


class UnsafeHost(ValueError):
    """`host` doesn't resolve to loopback.

    Trainee speech (and, per misc/docs/12-security-privacy.md §6.2, sometimes
    unprompted real clinical content the trainee narrates) goes into this
    request in cleartext HTTP with no TLS and no allowlist. A remote host —
    a shared team default, a copy-pasted config, "let's use my GPU box" —
    would exfiltrate it. This is the T2/B4 threat misc/docs/03's "no cloud
    inference in the core loop" rule exists to prevent; this check is what
    actually enforces it for the one real model-call path in this build.
    """


def _ensure_loopback(host: str) -> None:
    hostname = urllib.parse.urlparse(host).hostname
    if hostname not in _LOOPBACK_HOSTNAMES:
        raise UnsafeHost(
            f"host={host!r} is not loopback (hostname={hostname!r}). Trainee "
            f"speech would leave this machine in cleartext. Use "
            f"http://localhost:<port> or http://127.0.0.1:<port>."
        )


def _chat(
    host: str,
    model: str,
    messages: list[dict[str, str]],
    *,
    json_format: bool = False,
    temperature: float = 0.7,
    timeout: float = 120.0,
) -> str:
    _ensure_loopback(host)
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


_INSTRUCTION = (
    "Say one conversational utterance that conveys EXACTLY these facts — "
    "all of them, and nothing clinical beyond them. Reply with the "
    "utterance only, no quotes, no preamble."
)


def _fact_keywords(fact: Fact) -> tuple[str, ...]:
    """A few distinctive words from a rendered fact, for the presence check
    below. Cheap and approximate on purpose — this is a sanity flag, not a
    replacement for real ground-truth-by-construction (see
    `check_facts_present`'s docstring)."""
    rendered = _render_fact(fact)
    words = [w.strip(".,").lower() for w in rendered.split()]
    return tuple(w for w in words if len(w) >= 5)


def check_facts_present(node: ConversationNode, reply_text: str) -> tuple[str, ...]:
    """Flags facts whose distinctive keywords don't appear anywhere in the
    model's reply. Returns the missing facts' rendered text.

    This does NOT make `reply_text` ground-truth-by-construction the way
    `ScriptedModelClient`'s output is — a live model can still paraphrase a
    dose or drop a qualifier in a way that keeps every keyword present while
    changing the clinical meaning. It only catches the coarse failure (a
    fact dropped or substituted for an unrelated one entirely). See
    NOT-BUILT-YET.md P-extra for the honest limitation.
    """
    lowered = reply_text.lower()
    missing: list[str] = []
    for fact in node.facts:
        keywords = _fact_keywords(fact)
        if keywords and not any(kw in lowered for kw in keywords):
            missing.append(_render_fact(fact))
    return tuple(missing)


@dataclass(frozen=True, slots=True)
class OllamaLiveClient:
    """Counterpart turns via a local Gemma.

    The prompt is built through `agents.isolation.assemble()` — the same
    single chokepoint every other context construction in this codebase
    goes through — so the allowlist and rubric-vocabulary canary apply here
    too, rather than this being the one hand-formatted-string exception to
    misc/docs/04 §5's enforcement point.

    Ground truth is NOT verified by construction here the way it is for
    `ScriptedModelClient` (see `check_facts_present` and NOT-BUILT-YET.md
    P-extra) — the model is asked to convey exactly these facts, but nothing
    stops it from paraphrasing one away. `cli.py`'s demo loop calls
    `check_facts_present` and surfaces a visible warning when it fires,
    rather than silently trusting the output as scoring ground truth.
    """

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
        isolation_role: Literal["clinician", "patient"] = (
            "patient" if role is SpeakerRole.PATIENT else "clinician"
        )
        ctx = assemble(isolation_role, {"role_card": persona, "node": facts})
        prompt = f"{ctx.text}\n\n{_INSTRUCTION}"
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


def _quote_to_span(text: str, quote: object) -> Span | None:
    """Deterministic: the model supplies a quote, code computes the offset
    by exact substring search. Offsets are never taken from the model
    directly — the model isn't asked for indices, and if it were, trusting
    them would be a Golden Rule 1 violation (a model deciding something
    code can check). A quote that isn't found verbatim (paraphrased,
    empty, missing) yields None, and merge.py drops spanless grader
    findings outright rather than keeping an unlocated one."""
    if not isinstance(quote, str) or not quote:
        return None
    idx = text.find(quote)
    if idx == -1:
        return None
    return Span(start=idx, end=idx + len(quote))


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
            "For each finding, quote the EXACT substring of the rendering that is "
            "the problem (copy it verbatim, do not paraphrase) — this locates the "
            "finding; offsets are computed from your quote, not asked of you.\n\n"
            "Respond with JSON only:\n"
            '{"clean": true|false, "findings": [{"type": "<one of the nine types>", '
            '"severity": "critical"|"non_critical", "note": "<one line>", '
            '"rendering_quote": "<exact verbatim substring of the rendering>", '
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
                    rendering_span=_quote_to_span(rendering, f.get("rendering_quote")),
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

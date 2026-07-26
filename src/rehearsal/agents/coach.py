"""CoachAgent — feedback phrasing. misc/docs/04 §4.4.

Phrases; does not assess. Everything it says is determined by the findings
it is handed. Deterministic-templated, like the other agents in this phase
(no real model call — see model_client.py docstring). Runtime code must
never import rehearsal.scoring (misc/docs/15-workstreams.md §4); this
module takes plain ``contracts.Finding`` values, which already carry
``type``/``severity`` without importing anything scoring-owned.
"""

from __future__ import annotations

from dataclasses import dataclass

from rehearsal.contracts import Finding, Severity

_SEVERITY_ORDER = {Severity.CRITICAL: 0, Severity.NON_CRITICAL: 1}


@dataclass(frozen=True, slots=True)
class CoachHint:
    """Simplified ``CoachHint`` (misc/docs/04 §4.4)."""

    hint: str
    suppress: bool


class CoachAgent:
    """Turns a list of findings into one short, deterministic hint. No
    state (unlike Clinician/PatientAgent it holds no model client — this
    phase needs no model call at all), so this is a plain class, not a
    dataclass."""

    def generate_hint(self, findings: tuple[Finding, ...]) -> CoachHint:
        if not findings:
            return CoachHint(hint="", suppress=True)
        # ponytail: pick the single most-severe finding and phrase only that
        # one. A real model call could weave several findings into a
        # sentence; a template cannot without reading like a list.
        worst = min(findings, key=lambda f: _SEVERITY_ORDER[f.severity])
        kind_text = worst.type.value.replace("_", " ")
        severity_text = worst.severity.value.replace("_", " ")
        return CoachHint(
            hint=f"Watch your {kind_text} — flagged as {severity_text} on that turn.",
            suppress=False,
        )

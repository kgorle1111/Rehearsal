"""Information isolation: the one legal way to build a model context.

misc/docs/04-ai-engineering.md §5. `assemble()` is the sole constructor of a
model context — allowlist, not denylist, and it raises rather than sanitises.
This is the chokepoint that runs BEFORE any model call, so it works
regardless of what generates the context (scripted stand-in today, a real
model host later).

Scope note: only clinician/patient/coach roles are wired up this phase
(WS3's agents). `grader`/`composer` are out of scope — FIELD_ALLOWLIST is a
plain dict keyed by Role so adding a role later is one entry, not a
restructure.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Literal

from rehearsal.contracts import ErrorType, Severity

Role = Literal["clinician", "patient", "coach"]

# clinician/patient share a shape: they are the two sides of the encounter
# and must never see rubric, verdict, or learner-model internals (T1-T3).
_ENCOUNTER_FIELDS: Final[frozenset[str]] = frozenset({
    "role_card", "node", "encounter_summary", "recent_turns",
    "difficulty", "style_directives", "audio_ref",
})

FIELD_ALLOWLIST: Final[dict[Role, frozenset[str]]] = {
    "clinician": _ENCOUNTER_FIELDS,
    "patient": _ENCOUNTER_FIELDS,
    "coach": frozenset({
        "verdict_summary", "weak_categories", "turns_remaining", "tone",
    }),
}

# Taxonomy vocabulary that must never appear in a clinician/patient context.
# Derived from contracts.ErrorType/Severity values plus the explicit list in
# misc/docs/04-ai-engineering.md §5.3.
BANNED_SUBSTRINGS: Final[frozenset[str]] = frozenset(
    {t.value.replace("_", " ") for t in ErrorType}
    | {s.value.replace("_", " ") for s in Severity}
    | {
        "omission", "addition", "substitution", "distortion", "editorialization",
        "role exchange", "register shift", "false fluency",
        "first person violation", "rubric", "severity", "critical error",
        "fidelity score", "kappa",
    }
)


class IsolationViolation(RuntimeError):
    """Raised when a context assembly attempts a field its role does not allow,
    or when a clinician/patient context contains rubric vocabulary.

    Hard runtime error, never a warning — it aborts the turn.
    """


@dataclass(frozen=True, slots=True)
class AssembledContext:
    """The exact bytes a model call would see, plus their hash (misc/docs/04 §6.5)."""

    role: Role
    text: str
    context_sha: str


def _render(role: Role, fields: Mapping[str, object]) -> str:
    """Deterministic, order-stable rendering of allowed field values to text.

    Field values only, not Python key names — a rendered prompt is a template
    over the data, not a dict dump, and field names like `rubric_text` are an
    eval-harness label, not text a live model would ever see.
    """
    return "\n".join(str(fields[key]) for key in sorted(fields))


def _context_sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _assemble(
    role: Role, fields: Mapping[str, object], allowed: frozenset[str]
) -> AssembledContext:
    if extra := set(fields) - allowed:
        raise IsolationViolation(f"role={role} disallowed fields: {sorted(extra)}")
    text = _render(role, fields)
    if role in ("clinician", "patient"):
        lowered = text.lower()
        if hits := sorted(t for t in BANNED_SUBSTRINGS if t in lowered):
            raise IsolationViolation(f"role={role} rubric vocabulary in context: {hits}")
    return AssembledContext(role=role, text=text, context_sha=_context_sha(text))


def assemble(role: Role, fields: Mapping[str, object]) -> AssembledContext:
    """The ONLY constructor of a model context. Allowlist, not denylist."""
    return _assemble(role, fields, FIELD_ALLOWLIST[role])


def assemble_leaked(role: Role, fields: Mapping[str, object]) -> AssembledContext:
    """Eval-only: widens the counterpart allowlist by exactly one field,
    `rubric_text`, for the leakage A/B (misc/docs/04 §5.4). Never used outside
    the harness — production code has no path to this function.
    """
    if role not in ("clinician", "patient"):
        raise IsolationViolation(
            f"assemble_leaked is only defined for counterpart roles, got {role!r}"
        )
    leaked_allowlist = FIELD_ALLOWLIST[role] | {"rubric_text"}
    return _assemble(role, fields, leaked_allowlist)


@dataclass(frozen=True, slots=True)
class LeakageABResult:
    """What the mechanism-level A/B can honestly report without a live model host."""

    role: Role
    clean: AssembledContext
    leaked: AssembledContext | None
    canary_blocked_leaked_arm: bool
    context_sha_differs: bool | None  # None when the leaked arm never got built
    behavioral_delta: None  # kn: no live model host wired up yet; see report()

    def report(self) -> str:
        lines = [
            f"leakage A/B — role={self.role}",
            f"  clean arm  context_sha={self.clean.context_sha[:12]}",
        ]
        if self.canary_blocked_leaked_arm:
            lines.append(
                "  leaked arm: BLOCKED before construction — the vocabulary "
                "canary fired on the injected rubric_text (belt-and-braces "
                "layer caught this one; would not catch a paraphrase)."
            )
        else:
            assert self.leaked is not None
            lines.append(f"  leaked arm context_sha={self.leaked.context_sha[:12]}")
            lines.append(f"  context_sha differs: {self.context_sha_differs}")
        lines.append(
            "  behavioral/session-level delta: — (requires a live model host, "
            "not yet available; isolation not yet shown to matter)"
        )
        return "\n".join(lines)


def run_leakage_ab(role: Role, fields: Mapping[str, object], rubric_text: str) -> LeakageABResult:
    """Construct both arms from identical input fields plus one extra
    `rubric_text` value on the leaked arm, and report whatever comparison is
    honestly available. Does not claim a behavioral delta it cannot measure.

    If `rubric_text` itself trips the vocabulary canary, the leaked arm is
    reported as blocked rather than silently swallowed or fabricated.
    """
    clean = assemble(role, fields)
    try:
        leaked = assemble_leaked(role, {**fields, "rubric_text": rubric_text})
    except IsolationViolation:
        return LeakageABResult(
            role=role,
            clean=clean,
            leaked=None,
            canary_blocked_leaked_arm=True,
            context_sha_differs=None,
            behavioral_delta=None,
        )
    return LeakageABResult(
        role=role,
        clean=clean,
        leaked=leaked,
        canary_blocked_leaked_arm=False,
        context_sha_differs=clean.context_sha != leaked.context_sha,
        behavioral_delta=None,
    )

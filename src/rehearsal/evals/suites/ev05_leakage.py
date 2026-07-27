"""EV-05 — information-isolation leakage A/B. misc/docs/08-evals.md §4.6.

Wraps WS5's src/rehearsal/agents/isolation.py::run_leakage_ab — does not
rebuild the mechanism. Reports it honestly: the allowlist and rubric-vocab
canary are provably enforced (mechanism-level), but the behavioral
`leakage_delta` (utterance-difficulty A/B over a live session) needs a live
model host that does not exist yet — NOT-BUILT-YET.md P2: "Leakage A/B has
no behavioral number."
"""

from __future__ import annotations

from rehearsal.agents.isolation import run_leakage_ab
from rehearsal.evals.result import EvalConfig, EvalResult, GateOutcome

_SAMPLE_FIELDS: dict[str, object] = {
    "role_card": "You are the patient in this encounter.",
    "node": "intake",
    "encounter_summary": "Follow-up visit for a chronic condition.",
    "recent_turns": (),
    "difficulty": "moderate",
    "style_directives": "plain, conversational language",
    "audio_ref": None,
}
_SAMPLE_RUBRIC_TEXT = "critical severity omission substitution error taxonomy rubric"


def run(cfg: EvalConfig) -> EvalResult:
    result = run_leakage_ab("patient", _SAMPLE_FIELDS, _SAMPLE_RUBRIC_TEXT)
    metrics: dict[str, float] = {
        "canary_blocked_leaked_arm": float(result.canary_blocked_leaked_arm),
    }
    if result.context_sha_differs is not None:
        metrics["context_sha_differs"] = float(result.context_sha_differs)

    return EvalResult(
        eval_id="EV-05",
        split=cfg.split,
        n=1,
        metrics=metrics,
        intervals={},
        gate=GateOutcome.REPORT_ONLY,
        gate_detail="no pass/fail threshold per §4.6 — pre-registered measurement, not a gate",
        artifacts=[],
        notes=(
            "Isolation mechanism (allowlist + rubric-vocabulary canary) is verified "
            "in code. leakage_delta — the paired permutation-test effect size over "
            "24 scenarios x ~12 turns — is BLOCKED-ON-HARDWARE: it requires a live "
            "model host to generate real counterpart utterances in both arms, which "
            "does not exist yet (see NOT-BUILT-YET.md P2). Mechanism report follows.\n"
            + result.report()
        ),
    )

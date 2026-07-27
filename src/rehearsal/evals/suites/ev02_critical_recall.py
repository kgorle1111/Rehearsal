"""EV-02 — critical-error recall, the safety gate. misc/docs/08-evals.md §4.3.

BLOCKED-ON-HUMAN: same as EV-01. critical_recall needs gold critical-severity
labels from the human calibration set, which does not exist yet. The
matching/metrics machinery this suite would call (matching.match_errors,
metrics.critical_recall_from_matches) is built and unit-tested against
synthetic label sets in tests/evals/ — it is only the real labels that are
missing.
"""

from __future__ import annotations

from pathlib import Path

from rehearsal.evals.result import EvalConfig, EvalResult, GateOutcome

DEV_PATH = Path("data/calibration/dev.jsonl")


def run(cfg: EvalConfig) -> EvalResult:
    return EvalResult(
        eval_id="EV-02",
        split=cfg.split,
        n=0,
        metrics={},
        intervals={},
        gate=GateOutcome.SKIPPED,
        gate_detail="no DEV calibration labels exist",
        artifacts=[],
        notes=(
            "BLOCKED-ON-HUMAN: data/calibration/dev.jsonl does not exist yet. "
            "critical_recall requires human-labelled critical errors "
            "(dosage, frequency, allergy, negation, laterality, onset) from "
            "misc/SETUP.md §6, which no agent may generate (BUILD.md §5). "
            f"dev.jsonl present: {DEV_PATH.exists()}."
        ),
    )

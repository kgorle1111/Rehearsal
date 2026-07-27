"""EV-01 — grader calibration vs human labels. misc/docs/08-evals.md §4.2.

BLOCKED-ON-HUMAN: `data/calibration/dev.jsonl` does not exist. Only the 40
UNLABELLED source/rendering pairs in `data/calibration/items.jsonl` exist.
Per BUILD.md §5 / misc/docs/15-workstreams.md §6, no agent may generate the
calibration labels — kappa_macro cannot be computed until a human completes
the labelling protocol in misc/SETUP.md §6.
"""

from __future__ import annotations

from pathlib import Path

from rehearsal.evals.result import EvalConfig, EvalResult, GateOutcome

DEV_PATH = Path("data/calibration/dev.jsonl")


def run(cfg: EvalConfig) -> EvalResult:
    return EvalResult(
        eval_id="EV-01",
        split=cfg.split,
        n=0,
        metrics={},
        intervals={},
        gate=GateOutcome.SKIPPED,
        gate_detail="no DEV calibration labels exist",
        artifacts=[],
        notes=(
            "BLOCKED-ON-HUMAN: data/calibration/dev.jsonl does not exist yet. "
            "kappa_macro requires the 25-item hand-labelled DEV split from "
            "misc/SETUP.md §6, which no agent may generate (BUILD.md §5). "
            f"dev.jsonl present: {DEV_PATH.exists()}."
        ),
    )

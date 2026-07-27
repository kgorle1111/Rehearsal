"""EV-03 — the human ceiling. misc/docs/08-evals.md §4.4.

BLOCKED-ON-HUMAN: kappa_intra needs the delayed re-label sample
(data/calibration/relabel.jsonl) and kappa_inter needs a second labeller's
subset (data/calibration/rater2.jsonl, optional per spec). Neither exists.
Per §4.4's own rule, kappa_macro may never be published without kappa_intra
printed beside it — that rule is enforced by report.py (not owned here) and
this suite's SKIPPED result is the honest input to it.
"""

from __future__ import annotations

from pathlib import Path

from rehearsal.evals.result import EvalConfig, EvalResult, GateOutcome

RELABEL_PATH = Path("data/calibration/relabel.jsonl")
RATER2_PATH = Path("data/calibration/rater2.jsonl")


def run(cfg: EvalConfig) -> EvalResult:
    return EvalResult(
        eval_id="EV-03",
        split=cfg.split,
        n=0,
        metrics={},
        intervals={},
        gate=GateOutcome.SKIPPED,
        gate_detail="no relabel or rater2 calibration data exist",
        artifacts=[],
        notes=(
            "BLOCKED-ON-HUMAN: data/calibration/relabel.jsonl "
            f"(present: {RELABEL_PATH.exists()}) and data/calibration/rater2.jsonl "
            f"(present: {RATER2_PATH.exists()}) do not exist. kappa_intra and "
            "kappa_inter require the delayed re-label pass and second labeller "
            "from misc/SETUP.md §6.5, which no agent may generate (BUILD.md §5)."
        ),
    )

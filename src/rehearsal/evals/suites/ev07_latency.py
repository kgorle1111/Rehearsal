"""EV-07 — latency and real-time budget conformance. misc/docs/08-evals.md §4.8.

Wraps WS4's src/rehearsal/runtime/budget.py::BudgetGuard — a synthetic-clock
proof that the grader-shed (L2) degrade rule fires correctly, not a measured
latency number. NOT-BUILT-YET.md P2: "No real latency numbers... There is no
p95 T_gap, no barge_in_stop_ms, no measurement on any reference hardware."
This suite reports that honestly rather than fabricating p95/p99 figures.
"""

from __future__ import annotations

from rehearsal.evals.result import EvalConfig, EvalResult, GateOutcome
from rehearsal.runtime.budget import BudgetGuard, DegradeLevel, TurnBudget


def run(cfg: EvalConfig) -> EvalResult:
    budget = TurnBudget()
    guard = BudgetGuard(budget=budget)

    within_ok, sig_ok = guard.check("grader_wall_ms", budget.grader_wall_ms - 1)
    within_1, sig_1 = guard.check("grader_wall_ms", budget.grader_wall_ms + 1)
    within_2, sig_2 = guard.check("grader_wall_ms", budget.grader_wall_ms + 1)
    mechanism_ok = (
        within_ok
        and sig_ok is None
        and not within_1
        and sig_1 is None
        and not within_2
        and sig_2 == DegradeLevel.L2
    )

    return EvalResult(
        eval_id="EV-07",
        split=cfg.split,
        n=0,
        metrics={},
        intervals={},
        gate=GateOutcome.SKIPPED,
        gate_detail="no reference-hardware latency run exists",
        artifacts=[],
        notes=(
            f"BudgetGuard L2 (sustained grader-overshoot -> degrade) mechanism "
            f"verified on a synthetic clock: {mechanism_ok}. "
            "p95_first_audio_ms, p99_barge_in_stop_ms, grader_backlog_rate, "
            "resident_memory_peak_gb, audio_underrun_count are BLOCKED-ON-HARDWARE: "
            "no live model host, TTS backend, or reference machine exists yet "
            "(see NOT-BUILT-YET.md P2)."
        ),
    )

"""The four-cell honest report. misc/docs/08-evals.md §6 steps 6-7.

Baseline-DEV, candidate-DEV, baseline-TEST, candidate-TEST — each an
optional point estimate with an optional interval. Unmeasured is `—`, never
fabricated. Today TEST is always unmeasured: there is no optimisation run
to seal against (no `data/calibration/test.jsonl` split exists as a real
optimisation result yet), so those two cells render as `—` /
"BLOCKED-ON-HUMAN, no TEST split exists".
"""

from __future__ import annotations

from dataclasses import dataclass

BLOCKED_ON_HUMAN = "BLOCKED-ON-HUMAN, no TEST split exists"
NO_MEASURABLE_IMPROVEMENT = "no measurable improvement on the sealed split"


@dataclass(frozen=True, slots=True)
class PointEstimate:
    """A metric value with its 95% interval. `value=None` means unmeasured —
    never a fabricated placeholder like 0.0."""

    value: float | None
    interval: tuple[float, float] | None = None


@dataclass(frozen=True, slots=True)
class FourCellReport:
    baseline_dev: PointEstimate
    candidate_dev: PointEstimate
    baseline_test: PointEstimate
    candidate_test: PointEstimate
    metric_name: str = "optimisation_metric"


def _fmt(pe: PointEstimate) -> str:
    if pe.value is None:
        return "—"
    if pe.interval is None:
        return f"{pe.value:.4f}"
    lo, hi = pe.interval
    return f"{pe.value:.4f} [{lo:.4f}, {hi:.4f}]"


def sealed_split_verdict(baseline_test: PointEstimate, candidate_test: PointEstimate) -> str:
    """docs/08-evals.md §6 step 7's honesty rule. If either TEST cell is
    unmeasured, say so plainly rather than compute a delta from nothing. If
    the TEST improvement is smaller than the width of its interval, report
    'no measurable improvement' — even if DEV looked great."""
    if baseline_test.value is None or candidate_test.value is None:
        return BLOCKED_ON_HUMAN
    delta = candidate_test.value - baseline_test.value
    if candidate_test.interval is not None:
        width = candidate_test.interval[1] - candidate_test.interval[0]
        if abs(delta) < width:
            return NO_MEASURABLE_IMPROVEMENT
    return f"measured delta {delta:+.4f} on TEST"


def render(report: FourCellReport) -> str:
    overfit_gap: str
    if report.baseline_dev.value is not None and report.candidate_dev.value is not None:
        dev_delta = report.candidate_dev.value - report.baseline_dev.value
        overfit_gap = f"DEV delta {dev_delta:+.4f}"
    else:
        overfit_gap = "—"

    lines = [
        f"# Prompt-optimisation report — {report.metric_name}",
        "",
        "| split | baseline | candidate |",
        "|---|---|---|",
        f"| DEV  | {_fmt(report.baseline_dev)} | {_fmt(report.candidate_dev)} |",
        f"| TEST | {_fmt(report.baseline_test)} | {_fmt(report.candidate_test)} |",
        "",
        f"DEV change: {overfit_gap}",
        f"TEST verdict: {sealed_split_verdict(report.baseline_test, report.candidate_test)}",
    ]
    return "\n".join(lines)


__all__ = [
    "BLOCKED_ON_HUMAN",
    "NO_MEASURABLE_IMPROVEMENT",
    "FourCellReport",
    "PointEstimate",
    "render",
    "sealed_split_verdict",
]

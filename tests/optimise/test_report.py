"""Proves the four-cell report's honesty rules (docs/08-evals.md §6 steps 6-7)."""

from __future__ import annotations

from rehearsal.optimise.report import (
    BLOCKED_ON_HUMAN,
    NO_MEASURABLE_IMPROVEMENT,
    FourCellReport,
    PointEstimate,
    render,
    sealed_split_verdict,
)

_UNMEASURED = PointEstimate(value=None)


def test_blocked_on_human_when_test_split_does_not_exist() -> None:
    """Today there is no real optimisation run, so TEST cells are always None —
    the report must say BLOCKED-ON-HUMAN, never fabricate a delta."""
    report = FourCellReport(
        baseline_dev=PointEstimate(0.70, (0.65, 0.75)),
        candidate_dev=PointEstimate(0.78, (0.73, 0.83)),
        baseline_test=_UNMEASURED,
        candidate_test=_UNMEASURED,
    )
    out = render(report)
    assert BLOCKED_ON_HUMAN in out
    assert sealed_split_verdict(report.baseline_test, report.candidate_test) == BLOCKED_ON_HUMAN


def test_small_test_delta_reports_no_measurable_improvement() -> None:
    baseline = PointEstimate(0.70, (0.60, 0.80))  # width 0.20
    candidate = PointEstimate(0.72, (0.62, 0.82))  # delta 0.02 < width 0.20
    assert sealed_split_verdict(baseline, candidate) == NO_MEASURABLE_IMPROVEMENT


def test_large_test_delta_reports_measured_gain() -> None:
    baseline = PointEstimate(0.50, (0.45, 0.55))  # width 0.10
    candidate = PointEstimate(0.80, (0.75, 0.85))  # delta 0.30 > width 0.10
    verdict = sealed_split_verdict(baseline, candidate)
    assert verdict.startswith("measured delta")
    assert "+0.3000" in verdict


def test_render_never_fabricates_missing_values() -> None:
    report = FourCellReport(
        baseline_dev=_UNMEASURED,
        candidate_dev=_UNMEASURED,
        baseline_test=_UNMEASURED,
        candidate_test=_UNMEASURED,
    )
    out = render(report)
    assert out.count("—") >= 4

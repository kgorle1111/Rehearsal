"""Proves the search loop's trace recording, floor enforcement, and regression
rejection against synthetic scored candidates (BUILD.md WS6 DoD)."""

from __future__ import annotations

from dataclasses import dataclass

from rehearsal.optimise.loop import Candidate, run_search


@dataclass(frozen=True, slots=True)
class _FakeBaseline:
    metrics: dict[str, float]


_BASELINE = _FakeBaseline(
    metrics={"critical_recall": 0.92, "kappa_macro": 0.60, "fp_rate_clean": 0.10}
)


def test_trace_has_one_row_per_candidate_evaluated() -> None:
    candidates = [
        Candidate(
            "a", "instr a", {"critical_recall": 0.95, "kappa_macro": 0.65, "fp_rate_clean": 0.08}
        ),
        Candidate(
            "b", "instr b", {"critical_recall": 0.93, "kappa_macro": 0.55, "fp_rate_clean": 0.12}
        ),
        Candidate(
            "c", "instr c", {"critical_recall": 0.40, "kappa_macro": 0.90, "fp_rate_clean": 0.00}
        ),
    ]
    result = run_search(_BASELINE, candidates)
    assert len(result.trace) == 3
    assert {rec.label for rec in result.trace} == {"a", "b", "c"}
    assert all(rec.candidate_hash for rec in result.trace)


def test_no_candidates_yields_no_selection() -> None:
    result = run_search(_BASELINE, [])
    assert result.trace == ()
    assert result.selected is None
    assert result.rejected_reason == "no candidates evaluated"


def test_hard_floor_candidate_never_selected_even_if_alone() -> None:
    """A synthetic candidate with critical_recall < 0.90 and otherwise-perfect
    other terms: optimisation_metric is 0.0, so it cannot be selected."""
    candidates = [
        Candidate(
            "below_floor",
            "instr",
            {"critical_recall": 0.10, "kappa_macro": 1.0, "fp_rate_clean": 0.0},
        ),
    ]
    result = run_search(_BASELINE, candidates)
    assert result.trace[0].score == 0.0
    assert result.selected is None
    assert result.rejected_reason == "no candidate cleared the critical_recall floor"


def test_refuses_to_promote_better_composite_worse_critical_recall() -> None:
    """The loop's core safety property: a candidate that beats baseline on the
    composite score but regresses critical_recall must be refused."""
    candidates = [
        Candidate(
            "higher_composite_lower_recall",
            "instr",
            {"critical_recall": 0.90, "kappa_macro": 0.95, "fp_rate_clean": 0.00},
        ),
    ]
    # composite = 0.60*0.90 + 0.25*0.95 + 0.15*1.00 = 0.9875, well above baseline's
    baseline_score = 0.60 * 0.92 + 0.25 * 0.60 + 0.15 * (1 - 0.10)
    assert candidates[0].metrics["critical_recall"] < _BASELINE.metrics["critical_recall"]

    result = run_search(_BASELINE, candidates)
    assert result.trace[0].score > baseline_score
    assert result.selected is None
    assert result.rejected_reason is not None
    assert "regresses critical_recall" in result.rejected_reason


def test_selects_best_when_no_regression() -> None:
    candidates = [
        Candidate(
            "a", "instr a", {"critical_recall": 0.95, "kappa_macro": 0.65, "fp_rate_clean": 0.08}
        ),
        Candidate(
            "b", "instr b", {"critical_recall": 0.99, "kappa_macro": 0.70, "fp_rate_clean": 0.05}
        ),
    ]
    result = run_search(_BASELINE, candidates)
    assert result.selected is not None
    assert result.selected.label == "b"
    assert result.rejected_reason is None

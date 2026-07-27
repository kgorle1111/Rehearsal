"""Proves optimisation_metric's hard floor and weighted formula. BUILD.md WS6 DoD."""

from __future__ import annotations

from dataclasses import dataclass

from rehearsal.optimise.metric import optimisation_metric


@dataclass(frozen=True, slots=True)
class _FakeResult:
    """Synthetic EvalResult-shaped object — proves the floor logic without WS9."""

    metrics: dict[str, float]


def test_hard_floor_returns_zero_even_with_high_other_terms() -> None:
    r = _FakeResult(metrics={"critical_recall": 0.50, "kappa_macro": 0.99, "fp_rate_clean": 0.0})
    assert optimisation_metric(r) == 0.0


def test_floor_boundary_is_inclusive() -> None:
    r = _FakeResult(metrics={"critical_recall": 0.90, "kappa_macro": 0.0, "fp_rate_clean": 1.0})
    # 0.90 clears the >= 0.90 floor; composite should be computed, not zeroed.
    assert optimisation_metric(r) == 0.60 * 0.90


def test_formula_matches_docs_08_evals_section_6() -> None:
    r = _FakeResult(metrics={"critical_recall": 1.0, "kappa_macro": 0.8, "fp_rate_clean": 0.1})
    expected = 0.60 * 1.0 + 0.25 * 0.8 + 0.15 * (1.0 - 0.1)
    assert optimisation_metric(r) == expected

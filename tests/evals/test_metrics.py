"""metrics.py — kappa, precision/recall, critical_recall, Wilson interval.

Pure functions tested against constructed synthetic gold/pred label sets —
not calibration data, just the math (misc/docs/08-evals.md §1.1, §3, §8).
"""

from __future__ import annotations

from rehearsal.evals.matching import LabelledError, match_errors
from rehearsal.evals.metrics import (
    cohens_kappa_binary,
    critical_recall,
    critical_recall_from_matches,
    fp_rate_clean,
    kappa_macro,
    precision_recall,
    wilson_interval,
)


def test_wilson_interval_perfect_agreement_bounds() -> None:
    lo, hi = wilson_interval(10, 10)
    assert 0.0 < lo < hi <= 1.0


def test_wilson_interval_zero_n() -> None:
    assert wilson_interval(0, 0) == (0.0, 0.0)


def test_wilson_interval_wider_than_normal_at_small_n() -> None:
    # At n=10, p=0.9, Wilson lower bound should sit noticeably below the
    # naive point estimate — that's the whole point of using it (§8).
    lo, _hi = wilson_interval(9, 10)
    assert lo < 0.9


def test_precision_recall_basic() -> None:
    precision, recall = precision_recall(tp=8, fp=2, fn=2)
    assert precision == 0.8
    assert recall == 0.8


def test_precision_recall_zero_denominators() -> None:
    assert precision_recall(0, 0, 0) == (0.0, 0.0)


def test_critical_recall_basic() -> None:
    assert critical_recall(9, 1) == 0.9
    assert critical_recall(0, 0) == 0.0


def test_fp_rate_clean_basic() -> None:
    assert fp_rate_clean(2, 12) == 2 / 12
    assert fp_rate_clean(0, 0) == 0.0


def test_cohens_kappa_binary_perfect_agreement() -> None:
    gold = [True, False, True, False, True]
    pred = [True, False, True, False, True]
    assert cohens_kappa_binary(gold, pred) == 1.0


def test_cohens_kappa_binary_undefined_when_category_absent_from_gold() -> None:
    # Category never occurs in gold -> None, never silently 1.0 (§1.1).
    gold = [False, False, False]
    pred = [False, False, False]
    assert cohens_kappa_binary(gold, pred) is None


def test_kappa_macro_excludes_undefined_categories() -> None:
    per_category = {
        "dosage": ([True, False, True], [True, False, True]),  # kappa = 1.0
        "laterality": ([False, False, False], [False, False, False]),  # undefined
    }
    macro, per_cat = kappa_macro(per_category)
    assert per_cat["laterality"] is None
    assert macro == 1.0  # only dosage contributes; laterality never counted as 1.0


def test_critical_recall_from_matches_severity_miss_is_a_false_negative() -> None:
    # Matched span+category, but gold=critical / pred=non_critical: per §3
    # decision 3, this is a severity miss -> FN for critical_recall.
    gold = [LabelledError(category="dosage", severity="critical", span=(0, 10))]
    pred = [LabelledError(category="dosage", severity="non_critical", span=(0, 10))]
    match = match_errors(gold, pred)
    tp, fn = critical_recall_from_matches(match, gold, pred)
    assert (tp, fn) == (0, 1)


def test_critical_recall_from_matches_unmatched_critical_gold_is_fn() -> None:
    gold = [LabelledError(category="allergy", severity="critical", span=(0, 5))]
    pred: list[LabelledError] = []
    match = match_errors(gold, pred)
    tp, fn = critical_recall_from_matches(match, gold, pred)
    assert (tp, fn) == (0, 1)


def test_critical_recall_from_matches_true_positive() -> None:
    gold = [LabelledError(category="allergy", severity="critical", span=(0, 5))]
    pred = [LabelledError(category="allergy", severity="critical", span=(0, 5))]
    match = match_errors(gold, pred)
    tp, fn = critical_recall_from_matches(match, gold, pred)
    assert (tp, fn) == (1, 0)

"""Agreement and rate statistics. misc/docs/08-evals.md §1.1, §3, §8.

Pure functions over synthetic labelled data — no calibration labels needed
to test the math itself. Wilson interval for small-n proportions (§8: the
normal approximation is wrong at n ~= 10-15, which is most of this project).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from rehearsal.evals.matching import LabelledError, MatchResult


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a proportion. Correct at small n,
    unlike the normal approximation (misc/docs/08-evals.md §8)."""
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z**2 / n
    center = p + z**2 / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))
    lo = (center - margin) / denom
    hi = (center + margin) / denom
    return (max(0.0, lo), min(1.0, hi))


def precision_recall(tp: int, fp: int, fn: int) -> tuple[float, float]:
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    return precision, recall


def critical_recall(tp_crit: int, fn_crit: int) -> float:
    """TP_critical / (TP_critical + FN_critical). misc/docs/08-evals.md §4.3."""
    denom = tp_crit + fn_crit
    return tp_crit / denom if denom else 0.0


def fp_rate_clean(clean_items_flagged: int, total_clean: int) -> float:
    """Fraction of clean calibration items with >= 1 predicted error."""
    return clean_items_flagged / total_clean if total_clean else 0.0


def critical_recall_from_matches(
    match: MatchResult, gold: Sequence[LabelledError], pred: Sequence[LabelledError]
) -> tuple[int, int]:
    """(TP_crit, FN_crit) per §3 decision 3: a matched pair where gold is
    critical and pred is non_critical is a severity miss — a false negative
    for critical_recall even though it is a true positive for category
    recall. Unmatched critical gold is also a false negative.
    """
    tp_crit = 0
    fn_crit = 0
    matched_gold_idx = {gi for gi, _ in match.matches}
    for gi, pi in match.matches:
        g = gold[gi]
        if g.severity != "critical":
            continue
        if pred[pi].severity == "critical":
            tp_crit += 1
        else:
            fn_crit += 1
    for gi in range(len(gold)):
        if gi in matched_gold_idx:
            continue
        if gold[gi].severity == "critical":
            fn_crit += 1
    return tp_crit, fn_crit


def cohens_kappa_binary(gold: Sequence[bool], pred: Sequence[bool]) -> float | None:
    """Cohen's kappa for one category's turn-level presence/absence.

    Returns None when the category never occurs in gold — misc/docs/08-evals.md
    §1.1/§5: undefined categories are excluded from the macro-average, never
    silently counted as 1.0.
    """
    n = len(gold)
    if n == 0 or not any(gold):
        return None
    po = sum(1 for g, p in zip(gold, pred, strict=True) if g == p) / n
    p_gold_yes = sum(gold) / n
    p_pred_yes = sum(pred) / n
    pe = p_gold_yes * p_pred_yes + (1 - p_gold_yes) * (1 - p_pred_yes)
    if pe == 1.0:
        return 1.0 if po == 1.0 else 0.0
    return (po - pe) / (1 - pe)


def kappa_macro(
    per_category: Mapping[str, tuple[Sequence[bool], Sequence[bool]]],
) -> tuple[float | None, dict[str, float | None]]:
    """Macro-average Cohen's kappa over turn x category presence, for
    categories that occur in the split (misc/docs/08-evals.md §1.1, §3a).

    `per_category` maps category -> (gold_bools, pred_bools), one bool per
    turn (did this category occur in this turn at all?).
    """
    per_cat_kappa: dict[str, float | None] = {
        cat: cohens_kappa_binary(gold, pred) for cat, (gold, pred) in per_category.items()
    }
    occurring = [k for k in per_cat_kappa.values() if k is not None]
    macro = sum(occurring) / len(occurring) if occurring else None
    return macro, per_cat_kappa

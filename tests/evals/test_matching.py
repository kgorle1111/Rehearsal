"""matching.match_errors — greedy max-IoU span alignment. misc/docs/08-evals.md §3."""

from __future__ import annotations

from rehearsal.evals.matching import LabelledError, match_errors


def _e(
    category: str, severity: str, span: tuple[int, int], kind: str = "rendering"
) -> LabelledError:
    return LabelledError(category=category, severity=severity, span=span, span_kind=kind)  # type: ignore[arg-type]


def test_exact_span_and_category_matches() -> None:
    gold = [_e("dosage", "critical", (0, 10))]
    pred = [_e("dosage", "critical", (0, 10))]
    result = match_errors(gold, pred)
    assert result.matches == ((0, 0),)
    assert result.unmatched_gold == ()
    assert result.unmatched_pred == ()


def test_below_iou_threshold_does_not_match() -> None:
    gold = [_e("dosage", "critical", (0, 10))]
    pred = [_e("dosage", "critical", (9, 19))]  # IoU = 1/19, well below 0.5
    result = match_errors(gold, pred)
    assert result.matches == ()
    assert result.unmatched_gold == (0,)
    assert result.unmatched_pred == (0,)


def test_category_strict_blocks_mismatched_category() -> None:
    gold = [_e("dosage", "critical", (0, 10))]
    pred = [_e("frequency", "critical", (0, 10))]
    result = match_errors(gold, pred, require_category=True)
    assert result.matches == ()

    result_blind = match_errors(gold, pred, require_category=False)
    assert result_blind.matches == ((0, 0),)


def test_span_kind_mismatch_never_matches() -> None:
    gold = [_e("dosage", "critical", (0, 10), kind="source")]
    pred = [_e("dosage", "critical", (0, 10), kind="rendering")]
    result = match_errors(gold, pred)
    assert result.matches == ()


def test_greedy_picks_highest_iou_first() -> None:
    # pred[0] overlaps gold[0] perfectly; pred[1] overlaps gold[0] partially.
    # Greedy must take the perfect match, leaving pred[1] unmatched.
    gold = [_e("dosage", "critical", (0, 10))]
    pred = [
        _e("dosage", "critical", (5, 15)),  # IoU = 5/15
        _e("dosage", "critical", (0, 10)),  # IoU = 1.0
    ]
    result = match_errors(gold, pred)
    assert result.matches == ((0, 1),)
    assert result.unmatched_pred == (0,)


def test_severity_mismatch_still_matches_span_and_category() -> None:
    # §3 decision 3: severity is scored separately — a critical/non-critical
    # mismatch on an otherwise-matched pair is still a category-level match.
    gold = [_e("dosage", "critical", (0, 10))]
    pred = [_e("dosage", "non_critical", (0, 10))]
    result = match_errors(gold, pred)
    assert result.matches == ((0, 0),)

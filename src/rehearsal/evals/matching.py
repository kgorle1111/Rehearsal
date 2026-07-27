"""Span/category alignment between gold and predicted errors. misc/docs/08-evals.md §3.

Greedy maximum-IoU alignment over character spans, highest-IoU-first.
Severity is deliberately NOT part of the match test — §3.3: a matched pair
with a severity mismatch is still a match (true positive for category
recall) but a separate severity miss, which the caller (metrics.py) turns
into a false negative for critical_recall.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

SpanKind = Literal["source", "rendering"]


@dataclass(frozen=True, slots=True)
class LabelledError:
    category: str
    severity: str  # "critical" | "non_critical"
    span: tuple[int, int]
    # Omissions carry a span in the SOURCE, not the rendering (§3b).
    span_kind: SpanKind = "rendering"


@dataclass(frozen=True, slots=True)
class MatchResult:
    matches: tuple[tuple[int, int], ...]  # (gold_index, pred_index)
    unmatched_gold: tuple[int, ...]  # -> FN
    unmatched_pred: tuple[int, ...]  # -> FP


def _iou(a: tuple[int, int], b: tuple[int, int]) -> float:
    inter = max(0, min(a[1], b[1]) - max(a[0], b[0]))
    union = (a[1] - a[0]) + (b[1] - b[0]) - inter
    return inter / union if union > 0 else 0.0


def match_errors(
    gold: Sequence[LabelledError],
    pred: Sequence[LabelledError],
    *,
    iou_threshold: float = 0.5,
    require_category: bool = True,
) -> MatchResult:
    """Greedy maximum-IoU alignment over character spans of the rendering.

    A gold error and a predicted error match when their character spans have
    IoU >= iou_threshold, their span_kind agrees (source-coordinate omissions
    only match other source-coordinate spans), and (if require_category)
    their categories are equal. Unmatched gold -> FN. Unmatched pred -> FP.
    """
    candidates: list[tuple[float, int, int]] = []
    for gi, g in enumerate(gold):
        for pi, p in enumerate(pred):
            if g.span_kind != p.span_kind:
                continue
            if require_category and g.category != p.category:
                continue
            iou = _iou(g.span, p.span)
            if iou >= iou_threshold:
                candidates.append((iou, gi, pi))
    # Greedy, highest-IoU-first (§3, decision 1): inspectable line by line at
    # the handful-of-errors-per-turn scale this project operates at.
    candidates.sort(key=lambda c: c[0], reverse=True)

    used_gold: set[int] = set()
    used_pred: set[int] = set()
    matches: list[tuple[int, int]] = []
    for _iou_val, gi, pi in candidates:
        if gi in used_gold or pi in used_pred:
            continue
        used_gold.add(gi)
        used_pred.add(pi)
        matches.append((gi, pi))

    unmatched_gold = tuple(i for i in range(len(gold)) if i not in used_gold)
    unmatched_pred = tuple(i for i in range(len(pred)) if i not in used_pred)
    return MatchResult(
        matches=tuple(matches), unmatched_gold=unmatched_gold, unmatched_pred=unmatched_pred
    )

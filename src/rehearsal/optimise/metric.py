"""The prompt-optimisation objective. misc/docs/08-evals.md §6 — formula owned
there, imported/reused here verbatim, never restated with different numbers.

Accepts a minimal duck-typed shape rather than importing WS9's concrete
`EvalResult` (its `metrics: dict[str, float]` field is the only thing this
function reads, and `rehearsal.evals.result` was still an empty stub — just
`__init__.py` — when this was written). `EvalResult` is a frozen dataclass
with that exact field, so it satisfies `HasMetrics` structurally with no
import needed; swapping the real type in later is a no-op for callers.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

CRITICAL_RECALL_FLOOR = 0.90


@runtime_checkable
class HasMetrics(Protocol):
    """Structural stand-in for `rehearsal.evals.result.EvalResult`."""

    @property
    def metrics(self) -> dict[str, float]: ...


def optimisation_metric(r: HasMetrics) -> float:
    """Safety-dominant composite. Hard floor returns 0.0 — a floor is a wall,
    a soft penalty is a price an optimiser will pay (docs/08-evals.md §6)."""
    if r.metrics["critical_recall"] < CRITICAL_RECALL_FLOOR:
        return 0.0
    return (
        0.60 * r.metrics["critical_recall"]
        + 0.25 * r.metrics["kappa_macro"]
        + 0.15 * (1.0 - r.metrics["fp_rate_clean"])
    )


__all__ = ["CRITICAL_RECALL_FLOOR", "HasMetrics", "optimisation_metric"]

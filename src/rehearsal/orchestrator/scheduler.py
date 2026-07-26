"""Turn planning and the overlap scheduling rule. misc/docs/03-system-architecture.md §6.1/§6.2.

The scheduler's single rule: scoring for turn N must be *launched* (not
necessarily complete) before `capture.ended` of turn N+1 is processed. If it
is not, the verdict lands late and the coach hint is dropped — nothing
blocks. Sustained lateness (queue depth >= 2) escalates the degradation
ladder via `should_shed`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from rehearsal.orchestrator.resume import SessionView
from rehearsal.orchestrator.seeds import derive_seed
from rehearsal.runtime.budget import DegradeLevel, TurnBudget


class GraphNode(Protocol):
    """Structural stand-in for `ClinicalStateGraph`'s node (misc/docs/03
    §9), which is not built yet. Only the field the scheduler actually
    needs."""

    @property
    def node_id(self) -> str: ...


@dataclass(frozen=True, slots=True)
class TurnPlan:
    turn_index: int
    speaker: Literal["clinician", "patient"]
    direction: Literal["en->es", "es->en"]
    node_id: str
    seed: int
    budget: TurnBudget


class TurnScheduler:
    def __init__(self, budget: TurnBudget | None = None) -> None:
        self.budget = budget or TurnBudget()

    def next_plan(self, view: SessionView, node: GraphNode) -> TurnPlan:
        if view.root_seed is None:
            raise ValueError("root_seed must be drawn before a turn can be planned")
        turn_index = max(view.turn_seeds) + 1 if view.turn_seeds else 0
        seed = derive_seed(view.root_seed, "graph_walk", turn_index)
        speaker: Literal["clinician", "patient"] = (
            "clinician" if turn_index % 2 == 0 else "patient"
        )
        direction: Literal["en->es", "es->en"] = "en->es" if speaker == "clinician" else "es->en"
        return TurnPlan(
            turn_index=turn_index,
            speaker=speaker,
            direction=direction,
            node_id=node.node_id,
            seed=seed,
            budget=self.budget,
        )

    def should_shed(self, queue_depth: int, ewma_grader_ms: float) -> DegradeLevel:
        """misc/docs/03-system-architecture.md §14: L2 (grader shed) takes
        priority over L1 (hint shed) when both triggers are active."""
        if ewma_grader_ms > self.budget.grader_wall_ms:
            return DegradeLevel.L2
        if queue_depth >= 2:
            return DegradeLevel.L1
        return DegradeLevel.L0

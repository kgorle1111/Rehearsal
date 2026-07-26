"""Turn latency budget and the guard that measures it.

misc/docs/03-system-architecture.md §6.4 (`TurnBudget`, exact field set and
defaults) and §14 (degradation ladder). `TurnBudget` is configuration, not a
constant — `rehearsal doctor` is meant to write a machine-local override; that
CLI is out of WS4 scope, this module only owns the shape and the guard logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


@dataclass(frozen=True, slots=True)
class TurnBudget:
    """misc/docs/03-system-architecture.md §6.4. Field set and defaults are frozen."""

    source_generation_ms: int = 900
    tts_first_audio_ms: int = 400
    barge_in_stop_ms: int = 120
    capture_max_ms: int = 45_000
    grader_wall_ms: int = 3_500
    persist_turn_ms: int = 50


class DegradeLevel(IntEnum):
    """misc/docs/03-system-architecture.md §14. Not a session state — an
    orthogonal attribute of a live session."""

    L0 = 0  # nominal
    L1 = 1  # hint shed
    L2 = 2  # grader shed
    L3 = 3  # TTS fallback
    L4 = 4  # text mode
    L5 = 5  # stop


class UnknownBudgetStage(ValueError):
    pass


@dataclass
class BudgetGuard:
    """Measures a stage's elapsed time against `TurnBudget` and maps sustained
    grader overshoot to a `DegradeLevel` per §14's L2 rule ("grader p95 >
    grader_wall_ms sustained").

    ponytail: only the grader-shed (L2) rule is implemented as sustained/
    consecutive tracking here, because it is the one §14 trigger this
    workstream can measure honestly without hardware. L1 (score queue depth)
    is `TurnScheduler.should_shed`; L3-L5 need real TTS/audio/store signals
    this build has none of — BLOCKED-ON-HARDWARE, not faked.
    """

    budget: TurnBudget = field(default_factory=TurnBudget)
    _consecutive_grader_overshoot: int = field(default=0, init=False, repr=False)

    def check(self, stage: str, elapsed_ms: int) -> tuple[bool, DegradeLevel | None]:
        """Return (within_budget, degrade_signal_if_sustained)."""
        if not hasattr(self.budget, stage):
            raise UnknownBudgetStage(stage)
        limit = getattr(self.budget, stage)
        within = elapsed_ms <= limit

        if stage != "grader_wall_ms":
            return within, None

        if within:
            self._consecutive_grader_overshoot = 0
            return within, None

        self._consecutive_grader_overshoot += 1
        if self._consecutive_grader_overshoot >= 2:
            return within, DegradeLevel.L2
        return within, None

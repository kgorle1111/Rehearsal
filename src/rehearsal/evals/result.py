"""The contract every eval returns. misc/docs/08-evals.md §2.2.

`EvalConfig` is the input every suite's `run()` takes: split, seed, model
roles, prompt versions, dry_run — nothing else. An eval that needs a network
call, a live human, or a wall-clock schedule does not belong in this suite.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Literal

Split = Literal["dev", "test", "fixture", "live", "replay"]


class GateOutcome(str, Enum):  # noqa: UP042 — exact contract shape per misc/docs/08-evals.md §2.2
    PASS = "pass"
    FAIL = "fail"
    REPORT_ONLY = "report_only"  # measured, deliberately not gated
    SKIPPED = "skipped"  # prerequisite missing; must state why


@dataclass(frozen=True, slots=True)
class EvalResult:
    eval_id: str  # "EV-02"
    split: Split
    n: int  # denominator — always reported
    metrics: dict[str, float]
    intervals: dict[str, tuple[float, float]]  # 95%; empty only if n too small to bootstrap
    gate: GateOutcome
    gate_detail: str  # "critical_recall <r> < gate 0.90 (dev)"
    artifacts: list[Path]
    notes: str


@dataclass(frozen=True, slots=True)
class EvalConfig:
    split: Split = "fixture"
    seed: int = 0
    model_roles: tuple[str, ...] = ()
    prompt_versions: dict[str, str] = field(default_factory=dict)
    dry_run: bool = False

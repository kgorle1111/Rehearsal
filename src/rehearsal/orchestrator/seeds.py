"""Deterministic per-draw seed derivation. misc/docs/03-system-architecture.md §6.3.

Every stochastic draw in a session derives from one recorded 64-bit root seed;
no component calls a global RNG. `derive_seed` is pure and exact per spec.
"""

from __future__ import annotations

import hashlib
from typing import Final

NAMESPACES: Final = (
    "scenario_selection",  # which scenario, which entry node
    "graph_walk",  # which legal successor node
    "clinician_sampling",
    "patient_sampling",
    "coach_sampling",
    "distractor_injection",  # difficulty knobs: speed, overlap, numeric density
)


def derive_seed(root_seed: int, namespace: str, turn_index: int) -> int:
    h = hashlib.blake2b(f"{root_seed}:{namespace}:{turn_index}".encode(), digest_size=8)
    return int.from_bytes(h.digest(), "big")

"""Crash-resume: pure folding logic over the event log. misc/docs/03-system-architecture.md §8.3.

"A turn boundary is the only resumable checkpoint." `fold` is a pure function
(no I/O beyond having already read the events) that reconstructs a
`SessionView`; `resumable_state` applies the §8.3 rule: resume at the last
durable state directly, unless a turn was left open (`turn.opened` with no
matching close), in which case that turn is abandoned and must be re-planned
with the *same* derived seed, never a new one.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from rehearsal.orchestrator.eventlog import Event
from rehearsal.orchestrator.fsm import EVENT_KIND_TO_DURABLE_STATE, SessionState

# Event kinds that close whatever turn is currently open.
_TURN_CLOSING_KINDS = frozenset({"rendering.emitted", "turn.abandoned"})


def _as_int(value: object) -> int:
    """`Event.payload` is `dict[str, object]` (§10.3: JSON-shaped); this is
    the one narrowing point that turns it back into the `int` every seed and
    turn_index actually is at runtime."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"expected an int, got {value!r}")
    return value


@dataclass(frozen=True, slots=True)
class SessionView:
    session_id: str
    root_seed: int | None
    state: SessionState
    last_durable_state: SessionState
    open_turn_index: int | None
    open_turn_seed: int | None
    turn_seeds: dict[int, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ResumeOutcome:
    state: SessionState
    reopen_turn_index: int | None = None
    reopen_seed: int | None = None
    turn_abandoned: bool = False


def fold(events: Iterable[Event]) -> SessionView:
    events = list(events)
    session_id = events[0].session_id if events else ""

    root_seed: int | None = None
    last_durable = SessionState.INIT
    state = SessionState.INIT
    open_turn_index: int | None = None
    open_turn_seed: int | None = None
    turn_seeds: dict[int, int] = {}

    for e in events:
        if e.kind == "session.created":
            raw = e.payload.get("root_seed")
            root_seed = _as_int(raw) if raw is not None else None

        if e.kind == "turn.opened":
            idx_raw = e.turn_index if e.turn_index is not None else e.payload.get("turn_index")
            seed_raw = e.payload.get("seed")
            if idx_raw is not None and seed_raw is not None:
                idx = _as_int(idx_raw)
                seed = _as_int(seed_raw)
                turn_seeds[idx] = seed
                open_turn_index = idx
                open_turn_seed = seed

        if e.kind in _TURN_CLOSING_KINDS:
            idx_raw = e.turn_index if e.turn_index is not None else e.payload.get("turn_index")
            if (
                idx_raw is not None
                and open_turn_index is not None
                and _as_int(idx_raw) == open_turn_index
            ):
                open_turn_index = None
                open_turn_seed = None

        durable = EVENT_KIND_TO_DURABLE_STATE.get(e.kind)
        if durable is not None:
            last_durable = durable
            state = durable

    return SessionView(
        session_id=session_id,
        root_seed=root_seed,
        state=state,
        last_durable_state=last_durable,
        open_turn_index=open_turn_index,
        open_turn_seed=open_turn_seed,
        turn_seeds=turn_seeds,
    )


def resumable_state(view: SessionView) -> ResumeOutcome:
    if view.open_turn_index is not None:
        # Rule 3: turn was in flight. Re-open the same turn_index with the
        # same derived seed — never a new one — per §8.3 point 3.
        return ResumeOutcome(
            state=view.last_durable_state,
            reopen_turn_index=view.open_turn_index,
            reopen_seed=view.open_turn_seed,
            turn_abandoned=True,
        )
    # Rule 2: last event was a durable-state event, resume there directly.
    return ResumeOutcome(state=view.last_durable_state)

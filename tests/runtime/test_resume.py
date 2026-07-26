"""Crash-resume determinism. misc/docs/03-system-architecture.md §8.3.

Builds a synthetic multi-turn session event stream and truncates it at 20
distinct mid-turn points (simulating a crash between `turn.opened` and its
matching `rendering.emitted`/`turn.abandoned`), then proves `fold` +
`resumable_state` resolve each one to the correct, *identical* resumable
state — including the same re-derived seed for the same turn_index, run
twice per truncation point to prove the fold is a pure function, not just
"probably right this once".
"""

from rehearsal.orchestrator.eventlog import Event
from rehearsal.orchestrator.fsm import SessionState
from rehearsal.orchestrator.resume import fold, resumable_state
from rehearsal.orchestrator.seeds import derive_seed

SESSION_ID = "ses_test"
ROOT_SEED = 987654321
N_TURNS = 20


def _e(seq: int, kind: str, payload: dict[str, object], turn_index: int | None = None) -> Event:
    return Event(
        seq=seq, session_id=SESSION_ID, turn_index=turn_index, kind=kind,
        ts_ms=seq, mono_ms=seq, payload=payload, prev_hash="x" * 64, hash="y" * 64,
    )


def _closed_turn_events(seq: int, turn_index: int) -> tuple[list[Event], int]:
    """A fully closed turn: opened -> source.emitted -> capture.ended -> rendering.emitted."""
    seed = derive_seed(ROOT_SEED, "graph_walk", turn_index)
    opened_payload = {"turn_index": turn_index, "seed": seed, "node_id": f"n{turn_index}"}
    events = [
        _e(seq, "turn.opened", opened_payload, turn_index),
        _e(seq + 1, "source.emitted", {"text": "..."}, turn_index),
        _e(seq + 2, "capture.ended", {}, turn_index),
        _e(seq + 3, "rendering.emitted", {"text": "..."}, turn_index),
    ]
    return events, seq + 4


def _prefix_killed_mid_turn(kill_turn_index: int, *, kill_depth: int) -> list[Event]:
    """A session log for turns [0, kill_turn_index) fully closed, then
    `kill_turn_index` opened and killed `kill_depth` events into it (before
    its rendering.emitted lands)."""
    events = [
        _e(1, "session.created", {"trainee_id": "t1", "root_seed": ROOT_SEED}),
        _e(2, "scenario.bound", {"node_id": "n0"}),
    ]
    seq = 3
    for i in range(kill_turn_index):
        closed, seq = _closed_turn_events(seq, i)
        events.extend(closed)

    seed = derive_seed(ROOT_SEED, "graph_walk", kill_turn_index)
    opened_payload = {"turn_index": kill_turn_index, "seed": seed, "node_id": f"n{kill_turn_index}"}
    in_flight = [
        _e(seq, "turn.opened", opened_payload, kill_turn_index),
        _e(seq + 1, "source.emitted", {"text": "..."}, kill_turn_index),
        _e(seq + 2, "capture.ended", {}, kill_turn_index),
    ]
    events.extend(in_flight[:kill_depth])
    return events


def test_twenty_mid_turn_kills_resolve_correctly_and_deterministically() -> None:
    resolved = 0
    for kill_turn_index in range(N_TURNS):
        # vary the exact kill depth too (right after open vs. mid-capture)
        kill_depth = 1 + (kill_turn_index % 3)
        prefix = _prefix_killed_mid_turn(kill_turn_index, kill_depth=kill_depth)

        view_a = fold(prefix)
        outcome_a = resumable_state(view_a)
        view_b = fold(prefix)
        outcome_b = resumable_state(view_b)

        assert outcome_a == outcome_b, f"non-deterministic fold at turn {kill_turn_index}"

        expected_seed = derive_seed(ROOT_SEED, "graph_walk", kill_turn_index)
        assert outcome_a.turn_abandoned is True
        assert outcome_a.reopen_turn_index == kill_turn_index
        assert outcome_a.reopen_seed == expected_seed
        expected_durable = (
            SessionState.ARMED if kill_turn_index == 0 else SessionState.TURN_CLOSING
        )
        assert outcome_a.state == expected_durable
        resolved += 1

    assert resolved == N_TURNS
    print(f"resume: {resolved} synthetic mid-turn kills resolved correctly, deterministically")


def test_clean_completion_has_no_open_turn() -> None:
    events = [
        _e(1, "session.created", {"trainee_id": "t1", "root_seed": ROOT_SEED}),
        _e(2, "scenario.bound", {"node_id": "n0"}),
    ]
    seq = 3
    for i in range(3):
        closed, seq = _closed_turn_events(seq, i)
        events.extend(closed)
    events.append(_e(seq, "encounter.ended", {}))

    view = fold(events)
    outcome = resumable_state(view)
    assert outcome.turn_abandoned is False
    assert view.open_turn_index is None
    assert view.state is SessionState.DEBRIEF


if __name__ == "__main__":
    test_twenty_mid_turn_kills_resolve_correctly_and_deterministically()
    test_clean_completion_has_no_open_turn()
    print("resume: all checks passed")

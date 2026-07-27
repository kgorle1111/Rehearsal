"""Projection writers. misc/docs/11-backend-api.md §6.2: `events` and `blobs`
are the truth; every other table is a projection that can be dropped and
rebuilt. Per that rule, `sessions` is never hand-`UPDATE`d anywhere else —
every write to it goes through `upsert_session`, driven by a freshly-folded
`SessionView`, so the row can never diverge from what `fold()` would produce.

This module does not implement `rebuild()`/`verify()` from §6.8's full
projection-rebuild contract (that needs `turns`/`findings` producers this
workstream doesn't build) — just the one projection the API surface
actually drives: `sessions`, kept in sync on every lifecycle transition.
"""

from __future__ import annotations

import sqlite3

from rehearsal.orchestrator.resume import SessionView


def upsert_session(
    conn: sqlite3.Connection,
    view: SessionView,
    *,
    trainee_id: str,
    scenario_id: str,
    difficulty: int,
    max_turns: int,
    text_mode: bool,
    started_ms: int | None,
    ended_ms: int | None,
    abort_reason: str | None,
    last_seq: int,
) -> None:
    conn.execute(
        """
        INSERT INTO sessions (session_id, trainee_id, scenario_id, root_seed, state,
                               difficulty, max_turns, text_mode, started_ms, ended_ms,
                               abort_reason, last_seq)
        VALUES (:session_id, :trainee_id, :scenario_id, :root_seed, :state,
                :difficulty, :max_turns, :text_mode, :started_ms, :ended_ms,
                :abort_reason, :last_seq)
        ON CONFLICT (session_id) DO UPDATE SET
            state = excluded.state,
            started_ms = COALESCE(sessions.started_ms, excluded.started_ms),
            ended_ms = excluded.ended_ms,
            abort_reason = excluded.abort_reason,
            last_seq = excluded.last_seq
        """,
        {
            "session_id": view.session_id,
            "trainee_id": trainee_id,
            "scenario_id": scenario_id,
            "root_seed": view.root_seed,
            "state": view.state.value,
            "difficulty": difficulty,
            "max_turns": max_turns,
            "text_mode": int(text_mode),
            "started_ms": started_ms,
            "ended_ms": ended_ms,
            "abort_reason": abort_reason,
            "last_seq": last_seq,
        },
    )
    conn.commit()


def upsert_learner(conn: sqlite3.Connection, trainee_id: str, *, created_ms: int) -> None:
    conn.execute(
        "INSERT INTO learners (trainee_id, created_ms) VALUES (?, ?) "
        "ON CONFLICT (trainee_id) DO NOTHING",
        (trainee_id, created_ms),
    )
    conn.commit()

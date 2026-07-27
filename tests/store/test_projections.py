"""`store.projections.upsert_session`/`upsert_learner` write what they claim."""

from __future__ import annotations

from pathlib import Path

from rehearsal.orchestrator.fsm import SessionState
from rehearsal.orchestrator.resume import SessionView
from rehearsal.store.db import connect
from rehearsal.store.projections import upsert_learner, upsert_session


def test_upsert_learner_inserts_and_is_idempotent(tmp_path: Path) -> None:
    conn = connect(tmp_path / "rehearsal.db")
    upsert_learner(conn, "trainee-1", created_ms=1000)
    upsert_learner(conn, "trainee-1", created_ms=9999)  # second call must not error or overwrite

    rows = conn.execute("SELECT * FROM learners WHERE trainee_id = 'trainee-1'").fetchall()
    assert len(rows) == 1
    assert rows[0]["created_ms"] == 1000  # ON CONFLICT DO NOTHING keeps the first write


def test_upsert_session_inserts_a_matching_row(tmp_path: Path) -> None:
    conn = connect(tmp_path / "rehearsal.db")
    upsert_learner(conn, "trainee-1", created_ms=1000)
    view = SessionView(
        session_id="sess-1",
        root_seed=42,
        state=SessionState.ARMED,
        last_durable_state=SessionState.ARMED,
        open_turn_index=None,
        open_turn_seed=None,
    )
    upsert_session(
        conn,
        view,
        trainee_id="trainee-1",
        scenario_id="sc_0001",
        difficulty=3,
        max_turns=24,
        text_mode=False,
        started_ms=None,
        ended_ms=None,
        abort_reason=None,
        last_seq=2,
    )
    row = conn.execute("SELECT * FROM sessions WHERE session_id = 'sess-1'").fetchone()
    assert row is not None
    assert row["state"] == "armed"
    assert row["root_seed"] == 42
    assert row["scenario_id"] == "sc_0001"
    assert row["text_mode"] == 0
    assert row["last_seq"] == 2


def test_upsert_session_preserves_started_ms_once_set(tmp_path: Path) -> None:
    """`ON CONFLICT ... started_ms = COALESCE(sessions.started_ms, excluded.started_ms)`
    — a later upsert must never clobber the first-recorded start time."""
    conn = connect(tmp_path / "rehearsal.db")
    upsert_learner(conn, "trainee-1", created_ms=1000)
    view = SessionView(
        session_id="sess-1",
        root_seed=42,
        state=SessionState.SOURCE_SPEAKING,
        last_durable_state=SessionState.ARMED,
        open_turn_index=0,
        open_turn_seed=42,
    )
    upsert_session(
        conn, view, trainee_id="trainee-1", scenario_id="sc_0001", difficulty=3,
        max_turns=24, text_mode=False, started_ms=5000, ended_ms=None,
        abort_reason=None, last_seq=3,
    )
    # A later sync passes a different started_ms (e.g. recomputed) — must be ignored.
    upsert_session(
        conn, view, trainee_id="trainee-1", scenario_id="sc_0001", difficulty=3,
        max_turns=24, text_mode=False, started_ms=99999, ended_ms=None,
        abort_reason=None, last_seq=4,
    )
    row = conn.execute(
        "SELECT started_ms, last_seq FROM sessions WHERE session_id = 'sess-1'"
    ).fetchone()
    assert row["started_ms"] == 5000
    assert row["last_seq"] == 4

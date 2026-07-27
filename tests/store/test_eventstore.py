"""`store.eventstore.SqliteEventLog` — the durable, SQLite-backed twin of
`orchestrator.eventlog.EventLog` (already covered by
`tests/runtime/test_eventlog.py`, which is the in-memory class). This file
is deliberately not a duplicate: it exercises the SQL persistence,
autoincrement `seq`, and `verify()` against real rows on disk, none of
which the in-memory test touches.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from rehearsal.orchestrator.eventlog import GENESIS_HASH
from rehearsal.store.db import connect
from rehearsal.store.eventstore import SqliteEventLog


def _log(tmp_path: Path) -> SqliteEventLog:
    conn = connect(tmp_path / "rehearsal.db")
    return SqliteEventLog(conn)


def test_first_event_chains_from_genesis_and_persists(tmp_path: Path) -> None:
    log = _log(tmp_path)
    e = log.append("s1", "session.created", {"trainee_id": "t1"})
    assert e.prev_hash == GENESIS_HASH
    assert e.seq == 1
    # round-trips through SQLite, not just returned in-memory
    assert log.events_for("s1") == [e]


def test_chain_links_within_a_session(tmp_path: Path) -> None:
    log = _log(tmp_path)
    e1 = log.append("s1", "session.created", {})
    e2 = log.append("s1", "scenario.bound", {"node_id": "n0"})
    assert e2.prev_hash == e1.hash


def test_sessions_have_independent_chains(tmp_path: Path) -> None:
    log = _log(tmp_path)
    # Realistic usage: every real `session.created` payload carries
    # trainee_id/scenario_id/root_seed, so two sessions' first events are
    # never byte-identical in practice (see the bug-reproduction test below
    # for what happens when they are).
    log.append("s1", "session.created", {"trainee_id": "t1", "root_seed": 111})
    e = log.append("s2", "session.created", {"trainee_id": "t2", "root_seed": 222})
    assert e.prev_hash == GENESIS_HASH


def test_BUG_identical_payloads_across_sessions_collide_on_global_hash_index(
    tmp_path: Path,
) -> None:
    """BUG REPRODUCTION — expected to FAIL (raise), not pass.

    `hash = sha256(prev_hash || kind || canonical_payload)` (eventstore.py,
    matching the in-memory `orchestrator.eventlog.EventLog` formula) does
    not include `session_id`. `0001_init.sql` puts a *global* UNIQUE index
    on `events.hash` (`idx_events_hash`), not one scoped to
    `(session_id, hash)`. Two different sessions whose event histories are
    byte-for-byte identical up to a given point (same prior chain position,
    same event kind, same payload) produce the identical hash and the
    second session's `append()` raises `sqlite3.IntegrityError` instead of
    succeeding — even though `SqliteEventLog.verify()` is explicitly scoped
    per-session (`events_for(session_id)`), implying independent sessions
    were meant to never interfere with each other.

    Practical risk: LOW today — every real `session.created` payload
    embeds a random 64-bit `root_seed` (see `SessionRuntime.create_session`
    in `src/rehearsal/api/runtime.py`), so accidental collision is
    astronomically unlikely in production traffic. But `session.paused`,
    `session.resumed`, and `session.aborted` (reason="user") events carry
    NO distinguishing payload at all — two different sessions pausing at
    the same relative chain position with the same prior history segment
    (e.g. two fresh sessions on the same scenario, paused immediately after
    `armed`) are one coincidence away from this. Reported as a finding, not
    fixed here (out of tests/ ownership; the fix is a schema migration —
    `idx_events_hash` should be `UNIQUE(session_id, hash)` — which is a
    one-way door requiring a human call, not a test-writer's unilateral
    edit).
    """
    log = _log(tmp_path)
    log.append("s1", "session.created", {})
    with pytest.raises(sqlite3.IntegrityError):
        log.append("s2", "session.created", {})


def test_verify_passes_on_untouched_log(tmp_path: Path) -> None:
    log = _log(tmp_path)
    log.append("s1", "session.created", {})
    log.append("s1", "scenario.bound", {"node_id": "n0"})
    assert log.verify("s1") is True


def test_verify_detects_a_broken_chain(tmp_path: Path) -> None:
    """`events` is append-only (UPDATE/DELETE trigger-blocked, see below), so
    the only way a row can be wrong is a bad INSERT — e.g. a bug that writes
    a stale `prev_hash`. verify() must catch that, not trust the row blindly."""
    conn = connect(tmp_path / "rehearsal.db")
    log = SqliteEventLog(conn)
    log.append("s1", "session.created", {})

    # Insert a row that doesn't chain from the real last hash — simulates a
    # corrupted/forged append that bypassed SqliteEventLog.append().
    conn.execute(
        "INSERT INTO events (session_id, turn_index, ts_ms, mono_ms, kind, payload, "
        "prev_hash, hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("s1", None, 0, 0, "scenario.bound", "{}", "f" * 64, "e" * 64),
    )
    conn.commit()

    assert log.verify("s1") is False


def test_events_no_update_trigger_blocks_tampering(tmp_path: Path) -> None:
    """The `events_no_update` trigger (0001_init.sql) is the actual tamper
    defense — UPDATE is rejected outright rather than merely detected after
    the fact by verify()."""
    conn = connect(tmp_path / "rehearsal.db")
    log = SqliteEventLog(conn)
    log.append("s1", "session.created", {})

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE events SET kind = 'tampered' WHERE session_id = 's1'")


def test_max_seq_reflects_last_appended_seq(tmp_path: Path) -> None:
    log = _log(tmp_path)
    assert log.max_seq("s1") == 0
    log.append("s1", "session.created", {})
    e2 = log.append("s1", "scenario.bound", {})
    assert log.max_seq("s1") == e2.seq


def test_events_for_after_filters_and_orders_by_seq(tmp_path: Path) -> None:
    log = _log(tmp_path)
    e1 = log.append("s1", "session.created", {})
    e2 = log.append("s1", "scenario.bound", {})
    log.append("s1", "session.paused", {})
    result = log.events_for("s1", after=e1.seq)
    assert [e.seq for e in result] == [e2.seq, e2.seq + 1]

"""SQLite-backed event log — the durable twin of `orchestrator.eventlog.EventLog`.

WS4's `EventLog` (src/rehearsal/orchestrator/eventlog.py) is explicitly
in-memory ("SQLite persistence... is WS-API's job", its own docstring). This
module is that job: it appends to the `events` table using the *identical*
hash-chain formula (`sha256(prev_hash || kind || canonical_payload)`,
chained per `session_id`) so a row written here and a row written by the
in-memory `EventLog` are bit-for-bit interchangeable, and reads come back as
the same `orchestrator.eventlog.Event` dataclass — which is what lets
`rehearsal.orchestrator.resume.fold()` operate on either without caring
which one produced the rows.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time

from rehearsal.orchestrator.eventlog import GENESIS_HASH, Event


def _canonical(payload: dict[str, object]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


class ChainError(RuntimeError):
    """`verify()` found a broken or tampered hash chain."""


class SqliteEventLog:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def _last_hash(self, session_id: str) -> str:
        row = self._conn.execute(
            "SELECT hash FROM events WHERE session_id = ? ORDER BY seq DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        return str(row["hash"]) if row is not None else GENESIS_HASH

    def append(
        self,
        session_id: str,
        kind: str,
        payload: dict[str, object] | None = None,
        *,
        turn_index: int | None = None,
        ts_ms: int | None = None,
        mono_ms: int = 0,
    ) -> Event:
        payload = payload or {}
        ts_ms = ts_ms if ts_ms is not None else int(time.time() * 1000)
        prev_hash = self._last_hash(session_id)
        digest = hashlib.sha256((prev_hash + kind + _canonical(payload)).encode()).hexdigest()
        cur = self._conn.execute(
            "INSERT INTO events (session_id, turn_index, ts_ms, mono_ms, kind, payload, "
            "prev_hash, hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (session_id, turn_index, ts_ms, mono_ms, kind, _canonical(payload), prev_hash, digest),
        )
        self._conn.commit()
        seq = cur.lastrowid
        assert seq is not None
        return Event(
            seq=seq,
            session_id=session_id,
            turn_index=turn_index,
            kind=kind,
            ts_ms=ts_ms,
            mono_ms=mono_ms,
            payload=payload,
            prev_hash=prev_hash,
            hash=digest,
        )

    def events_for(self, session_id: str, *, after: int = 0, limit: int | None = None) -> list[Event]:
        sql = "SELECT * FROM events WHERE session_id = ? AND seq > ? ORDER BY seq"
        params: list[object] = [session_id, after]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        rows = self._conn.execute(sql, params).fetchall()
        return [_row_to_event(r) for r in rows]

    def max_seq(self, session_id: str) -> int:
        row = self._conn.execute(
            "SELECT MAX(seq) AS m FROM events WHERE session_id = ?", (session_id,)
        ).fetchone()
        return int(row["m"]) if row["m"] is not None else 0

    def verify(self, session_id: str) -> bool:
        prev = GENESIS_HASH
        for e in self.events_for(session_id):
            if e.prev_hash != prev:
                return False
            expected = hashlib.sha256(
                (e.prev_hash + e.kind + _canonical(e.payload)).encode()
            ).hexdigest()
            if expected != e.hash:
                return False
            prev = e.hash
        return True


def _row_to_event(row: sqlite3.Row) -> Event:
    return Event(
        seq=int(row["seq"]),
        session_id=str(row["session_id"]),
        turn_index=row["turn_index"],
        kind=str(row["kind"]),
        ts_ms=int(row["ts_ms"]),
        mono_ms=int(row["mono_ms"]),
        payload=json.loads(row["payload"]),
        prev_hash=str(row["prev_hash"]),
        hash=str(row["hash"]),
    )

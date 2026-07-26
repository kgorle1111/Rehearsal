"""Append-only, hash-chained event log. misc/docs/03-system-architecture.md §10.1/§10.3.

"The event log is the truth." This is the source-of-truth append primitive
the orchestrator writes to and `resume.fold` reads back. It is in-process and
list-backed — SQLite persistence and the projection tables (`sessions`,
`turns`, `verdicts`, ...) are WS-API's job, not this workstream's; building a
general-purpose database layer here would be scope creep this build doesn't
need to prove any of its DoD items.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

GENESIS_HASH = "0" * 64


@dataclass(frozen=True, slots=True)
class Event:
    seq: int
    session_id: str
    turn_index: int | None
    kind: str
    ts_ms: int
    mono_ms: int
    payload: dict[str, object]
    prev_hash: str
    hash: str


def _canonical(payload: dict[str, object]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


class EventLog:
    """§10.3: `hash = sha256(prev_hash || kind || canonical_payload)`, chained
    per session (`prev_hash` = the previous event's hash *in this session*)."""

    def __init__(self) -> None:
        self._events: list[Event] = []
        self._last_hash: dict[str, str] = {}
        self._seq = 0

    def append(
        self,
        session_id: str,
        kind: str,
        payload: dict[str, object] | None = None,
        *,
        turn_index: int | None = None,
        ts_ms: int = 0,
        mono_ms: int = 0,
    ) -> Event:
        payload = payload or {}
        prev_hash = self._last_hash.get(session_id, GENESIS_HASH)
        digest = hashlib.sha256((prev_hash + kind + _canonical(payload)).encode()).hexdigest()
        self._seq += 1
        event = Event(
            seq=self._seq,
            session_id=session_id,
            turn_index=turn_index,
            kind=kind,
            ts_ms=ts_ms,
            mono_ms=mono_ms,
            payload=payload,
            prev_hash=prev_hash,
            hash=digest,
        )
        self._events.append(event)
        self._last_hash[session_id] = digest
        return event

    def events_for(self, session_id: str) -> list[Event]:
        return [e for e in self._events if e.session_id == session_id]

    def verify(self, session_id: str) -> bool:
        """Recompute the hash chain for a session. False means a record in the
        prefix was edited after the fact — the tamper-evidence §10.3 exists for."""
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

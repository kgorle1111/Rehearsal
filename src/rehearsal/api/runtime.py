"""SessionRuntime — the thin, honest orchestrator adapter.

Per the brief: "you may use WS4's SessionFSM/EventLog directly, or a thin
fake if wiring the full orchestrator is too much — be honest about which."
This is the former, not a fake: every transition here is a real
`SessionFSM.apply()` call against the real transition table, and every
event it produces is a real hash-chained row in the `events` table via
`SqliteEventLog`. What it does *not* do is drive the voice pipeline —
`start` opens exactly one turn (`turn_index=0`) and stops there, because
there is no capture/TTS/scoring loop wired to this API. A session created
here can legally reach `source_speaking` and be paused/resumed/aborted from
it, and `GET /api/sessions/{id}` reports real, fold()-derived state — it
just never progresses turn-by-turn on its own, because nothing in this
workstream's scope produces the events (`rendering.emitted`, etc.) that
would move it further.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import replace
from typing import cast

from fastapi import status

from rehearsal.api.errors import ApiError, not_found
from rehearsal.api.models import (
    AbortRequest,
    EventItem,
    EventPage,
    ScenarioDetail,
    ScenarioSummary,
    SessionAck,
    SessionCreated,
    SessionCreateRequest,
    SessionPage,
    SessionSummary,
    SessionViewOut,
)
from rehearsal.contracts import ScenarioRecord
from rehearsal.orchestrator.eventlog import Event
from rehearsal.orchestrator.fsm import (
    ANY_LIVE,
    TERMINAL,
    TRANSITIONS,
    InvalidTransition,
    SessionFSM,
    SessionState,
)
from rehearsal.orchestrator.resume import fold
from rehearsal.scenarios.bank import ScenarioBank, ScenarioNotApproved
from rehearsal.store.eventstore import SqliteEventLog
from rehearsal.store.ids import new_ulid
from rehearsal.store.projections import upsert_learner, upsert_session

LIVE_STATES = (
    "configuring", "armed", "source_speaking", "awaiting_rendering",
    "rendering_capturing", "turn_closing", "paused", "recovering",
)

_TRIGGER_BY_ACTION = {
    "start": "trainee_starts",
    "pause": "pause",
    "resume": "resume",
    "abort": "abort",
}

_DIFFICULTY_BAND_INDEX = {
    "novice": 1,
    "beginner": 2,
    "intermediate": 3,
    "advanced": 4,
    "expert": 5,
}


def _difficulty_index(raw: dict[str, object]) -> int:
    """`ScenarioRecord.difficulty` is a tag dict (misc/docs/07 §5), not a
    scalar. The runtime/orchestrator plane wants an int 1..5
    (misc/docs/03 §6.1's `difficulty:int`), so this derives one from the
    scenario's `band` tag. Unrecognized/missing band defaults to 3
    (mid-scale) rather than raising — a scenario missing this tag should
    still be runnable."""
    band = raw.get("band")
    if isinstance(band, str) and band in _DIFFICULTY_BAND_INDEX:
        return _DIFFICULTY_BAND_INDEX[band]
    return 3


def _allowed_triggers(state: SessionState) -> list[str]:
    triggers = {t.trigger for t in TRANSITIONS if t.from_state == state}
    if state not in TERMINAL:
        triggers |= {t.trigger for t in TRANSITIONS if t.from_state == ANY_LIVE}
    return sorted(triggers)


class SessionRuntime:
    def __init__(self, conn: sqlite3.Connection, scenario_bank: ScenarioBank) -> None:
        self._conn = conn
        self._events = SqliteEventLog(conn)
        self._bank = scenario_bank
        self._fsms: dict[str, SessionFSM] = {}

    # ── scenario lookup ────────────────────────────────────────────────

    def _get_approved_scenario(self, scenario_id: str) -> ScenarioRecord:
        try:
            return self._bank.get(scenario_id)
        except (KeyError, ScenarioNotApproved) as e:
            raise ApiError(
                code="scenario_unknown",
                message=f"Scenario {scenario_id!r} is not available to bind.",
                http_status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"scenario_id": scenario_id},
            ) from e

    # ── session row helpers ────────────────────────────────────────────

    def _row(self, session_id: str) -> sqlite3.Row:
        row = self._conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row is None:
            raise not_found(f"session {session_id!r}", session_id=session_id)
        return cast(sqlite3.Row, row)

    def _fsm_for(self, session_id: str) -> SessionFSM:
        """Lazily rebuilt from the event log — works whether this session
        was created in this process or the FSM cache was cold (e.g. after a
        restart), because `fold()` is the single source of truth for state."""
        if session_id not in self._fsms:
            events = self._events.events_for(session_id)
            if not events:
                raise not_found(f"session {session_id!r}", session_id=session_id)
            view = fold(events)
            fsm = SessionFSM(SessionState.INIT)
            fsm.reset_to(view.state)
            self._fsms[session_id] = fsm
        return self._fsms[session_id]

    def _sync_projection(self, session_id: str, *, abort_reason: str | None = None) -> SessionFSM:
        fsm = self._fsm_for(session_id)
        row = self._row(session_id)
        # Same reasoning as get_session: fold()'s view.state only tracks
        # durable checkpoints, so it silently disagrees with the live FSM on
        # every non-durable state (source_speaking, rendering_capturing,
        # recovering). Without this, sessions.state (and therefore
        # GET /api/sessions?state=... filtering) could never reflect that a
        # session is actually mid-turn.
        view = replace(fold(self._events.events_for(session_id)), state=fsm.state)
        started_ms = row["started_ms"]
        if started_ms is None and fsm.state not in (SessionState.INIT, SessionState.CONFIGURING):
            started_ms = int(time.time() * 1000)
        ended_ms = row["ended_ms"]
        if fsm.state in TERMINAL and ended_ms is None:
            ended_ms = int(time.time() * 1000)
        upsert_session(
            self._conn,
            view,
            trainee_id=row["trainee_id"],
            scenario_id=row["scenario_id"],
            difficulty=row["difficulty"],
            max_turns=row["max_turns"],
            text_mode=bool(row["text_mode"]),
            started_ms=started_ms,
            ended_ms=ended_ms,
            abort_reason=abort_reason if abort_reason is not None else row["abort_reason"],
            last_seq=self._events.max_seq(session_id),
        )
        return fsm

    # ── endpoints ───────────────────────────────────────────────────────

    def create_session(self, req: SessionCreateRequest) -> SessionCreated:
        scenario = self._get_approved_scenario(req.scenario_id)

        live = self._conn.execute(
            f"SELECT session_id FROM sessions WHERE state IN "
            f"({','.join('?' for _ in LIVE_STATES)})",
            LIVE_STATES,
        ).fetchone()
        if live is not None:
            raise ApiError(
                code="session_already_live",
                message="A session is already running; abort or complete it first.",
                http_status=status.HTTP_409_CONFLICT,
                detail={"live_session_id": live["session_id"]},
            )

        session_id = new_ulid()
        root_seed = (
            req.root_seed
            if req.root_seed is not None
            # `sessions.root_seed` is a SQLite STRICT INTEGER column (signed
            # 64-bit, max 2**63-1); an 8-byte unsigned draw overflows it on
            # ~50% of draws (OverflowError on every upsert_session call for
            # any seed >= 2**63). Mask off the sign bit to stay in range.
            else int.from_bytes(os.urandom(8), "big") & 0x7FFF_FFFF_FFFF_FFFF
        )
        difficulty = (
            req.difficulty
            if req.difficulty is not None
            else _difficulty_index(scenario.difficulty)
        )

        fsm = SessionFSM(SessionState.INIT)
        fsm.apply("configure", guard_ok=True)
        self._events.append(
            session_id,
            "session.created",
            {"trainee_id": req.trainee_id, "scenario_id": req.scenario_id, "root_seed": root_seed},
        )
        self._events.append(session_id, "seed.drawn", {"seed": root_seed})
        fsm.apply("bind_complete", guard_ok=True)
        self._events.append(session_id, "scenario.bound", {"scenario_id": req.scenario_id})
        self._fsms[session_id] = fsm

        upsert_learner(self._conn, req.trainee_id, created_ms=int(time.time() * 1000))
        view = fold(self._events.events_for(session_id))
        upsert_session(
            self._conn,
            view,
            trainee_id=req.trainee_id,
            scenario_id=req.scenario_id,
            difficulty=difficulty,
            max_turns=req.max_turns,
            text_mode=req.text_mode,
            started_ms=None,
            ended_ms=None,
            abort_reason=None,
            last_seq=self._events.max_seq(session_id),
        )

        return SessionCreated(
            session_id=session_id,
            state=fsm.state.value,
            scenario_id=req.scenario_id,
            root_seed=root_seed,
            difficulty=difficulty,
            planned_turns=req.max_turns,
            ws_url=f"/ws/session/{session_id}",
            hosts={},
        )

    def transition(
        self, session_id: str, action: str, body: AbortRequest | None = None
    ) -> SessionAck:
        self._row(session_id)  # 404 if unknown
        fsm = self._fsm_for(session_id)
        trigger = _TRIGGER_BY_ACTION[action]
        try:
            t = fsm.apply(trigger, guard_ok=True)
        except InvalidTransition as e:
            raise ApiError(
                code="illegal_transition",
                message=f"Cannot {action} a session in state {fsm.state.value!r}.",
                http_status=status.HTTP_409_CONFLICT,
                session_id=session_id,
                detail={"state": fsm.state.value, "allowed": _allowed_triggers(fsm.state)},
            ) from e

        for kind in t.events:
            payload: dict[str, object] = {}
            turn_index = None
            if kind == "turn.opened":
                turn_index = 0
                payload = {"seed": self._row(session_id)["root_seed"]}
            elif kind == "session.aborted" and body is not None:
                payload = {"reason": body.reason}
            self._events.append(session_id, kind, payload, turn_index=turn_index)

        abort_reason = body.reason if (action == "abort" and body is not None) else None
        self._sync_projection(session_id, abort_reason=abort_reason)

        return SessionAck(
            session_id=session_id,
            accepted=True,
            state=fsm.state.value,
            event_seq=self._events.max_seq(session_id),
        )

    def get_session(self, session_id: str) -> SessionViewOut:
        events = self._events.events_for(session_id)
        if not events:
            raise not_found(f"session {session_id!r}", session_id=session_id)
        view = fold(events)
        # `fold()` reconstructs the last DURABLE checkpoint — the crash-resume
        # question ("where would resume land"), not "what is happening right
        # now". Non-durable states (source_speaking, rendering_capturing,
        # recovering) never appear in its output by design (§8.1), so using
        # it here would report a session as "armed" moments after it was
        # correctly started into "source_speaking". `_fsm_for` holds the
        # live, in-process FSM when one exists, and falls back to the same
        # fold()-derived state honestly when it doesn't (e.g. after a
        # process restart, before anything repopulates the cache) — so it is
        # never less accurate than `view.state`, only sometimes more so.
        state = self._fsm_for(session_id).state
        row = self._conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        return SessionViewOut(
            session_id=session_id,
            state=state.value,
            trainee_id=row["trainee_id"] if row else None,
            scenario_id=row["scenario_id"] if row else None,
            root_seed=view.root_seed,
            turn_index=view.open_turn_index,
            planned_turns=row["max_turns"] if row else None,
            started_ms=row["started_ms"] if row else None,
            event_seq=self._events.max_seq(session_id),
        )

    def list_sessions(
        self,
        *,
        trainee_id: str | None = None,
        state: str | None = None,
        before: str | None = None,
        limit: int = 50,
    ) -> SessionPage:
        clauses: list[str] = []
        params: list[object] = []
        if trainee_id is not None:
            clauses.append("trainee_id = ?")
            params.append(trainee_id)
        if state is not None:
            clauses.append("state = ?")
            params.append(state)
        if before is not None:
            clauses.append("session_id < ?")
            params.append(before)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._conn.execute(
            f"SELECT * FROM sessions {where} ORDER BY session_id DESC LIMIT ?",
            (*params, limit + 1),
        ).fetchall()
        next_before = rows[limit]["session_id"] if len(rows) > limit else None
        items = [
            SessionSummary(
                session_id=r["session_id"],
                trainee_id=r["trainee_id"],
                scenario_id=r["scenario_id"],
                state=r["state"],
                started_ms=r["started_ms"],
                root_seed=r["root_seed"],
            )
            for r in rows[:limit]
        ]
        return SessionPage(items=items, next_before=next_before)

    def get_events(
        self,
        session_id: str,
        *,
        after: int = 0,
        limit: int = 500,
        kinds: list[str] | None = None,
    ) -> EventPage:
        self._row(session_id)  # 404 if unknown
        sql = "SELECT * FROM events WHERE session_id = ? AND seq > ?"
        params: list[object] = [session_id, after]
        if kinds:
            sql += f" AND kind IN ({','.join('?' for _ in kinds)})"
            params.extend(kinds)
        sql += " ORDER BY seq LIMIT ?"
        params.append(limit)
        rows = self._conn.execute(sql, params).fetchall()

        chain_ok = self._events.verify(session_id)
        items = [
            EventItem(
                seq=r["seq"],
                turn_index=r["turn_index"],
                ts_ms=r["ts_ms"],
                mono_ms=r["mono_ms"],
                kind=r["kind"],
                payload=json.loads(r["payload"]),
                prev_hash=r["prev_hash"],
                hash=r["hash"],
            )
            for r in rows
        ]
        next_after = items[-1].seq if items else None
        return EventPage(items=items, next_after=next_after, chain_ok=chain_ok)

    # ── scenarios (read-only projection of WS7's ScenarioBank) ─────────

    def get_scenario(self, scenario_id: str) -> ScenarioDetail:
        try:
            record = self._bank.get(scenario_id)
        except (KeyError, ScenarioNotApproved) as e:
            raise not_found(f"scenario {scenario_id!r}") from e
        return ScenarioDetail(
            scenario_id=record.scenario_id,
            schema_version=record.schema_version,
            difficulty=_difficulty_index(record.difficulty),
            condition=record.clinical_state.condition,
            review_status=record.review.status,
            clinical_state={
                "condition": record.clinical_state.condition,
                "emotional_state": record.clinical_state.emotional_state,
                "health_literacy": record.clinical_state.health_literacy,
                "language_variety": record.clinical_state.language_variety,
                "onset": record.clinical_state.onset,
            },
            term_manifest=[
                {"term_id": t.term_id, "kind": t.kind, "critical": t.critical}
                for t in record.term_manifest
            ],
        )

    def list_scenarios(self, *, difficulty: int | None = None) -> list[ScenarioSummary]:
        records = self._bank.load_all()
        summaries = [
            ScenarioSummary(
                scenario_id=r.scenario_id,
                schema_version=r.schema_version,
                difficulty=_difficulty_index(r.difficulty),
                condition=r.clinical_state.condition,
                review_status=r.review.status,
            )
            for r in records
        ]
        if difficulty is not None:
            summaries = [s for s in summaries if s.difficulty == difficulty]
        return summaries

    def events_since(self, session_id: str, *, after: int = 0) -> list[Event]:
        """Raw events for the WS layer — no 404 check, callers already know
        the session exists (they got it from `events_for` at connect time)."""
        return self._events.events_for(session_id, after=after)

    def live_session_id(self) -> str | None:
        row = self._conn.execute(
            f"SELECT session_id FROM sessions WHERE state IN "
            f"({','.join('?' for _ in LIVE_STATES)}) LIMIT 1",
            LIVE_STATES,
        ).fetchone()
        return row["session_id"] if row else None

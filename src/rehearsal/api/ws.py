"""`/ws/session/{id}` — a projection of the event log, not a second channel.
misc/docs/11-backend-api.md §5.

Implements the *mechanism* generically (subscribe, replay-from-seq on
connect, gap-replay on reconnect, then live-stream anything appended after)
rather than hardcoding all twenty-plus message types from §5.3 — any event
`kind` written to the log flows through unchanged, `t` is exactly the event
kind (§5.2). Not built, per the brief's explicit scope cut: the
backpressure/dropped-message-class machinery of §5.6 (there is one
unbounded-ish send per tick, no queue depth cap) and most of the close-code
table in §5.7 (only 4004 "unknown session" and the plain 1000 close are
implemented).

# ponytail: live delivery is a 50ms poll of the `events` table for new rows
past the last-sent seq, not a pub/sub fan-out. For a single-socket-per-
session server (§8.2 — enforced at the process level anyway) this is
indistinguishable from push at the timescales the UI cares about, and it
is a five-line loop instead of an event-bus dependency. Upgrade when a
second concurrent reader of the same session's live stream is a real
requirement (`asyncio.Condition` per session, notified from `append()`).
"""

from __future__ import annotations

import asyncio
import json
import time

from fastapi import WebSocket, WebSocketDisconnect

from rehearsal.api.errors import ApiError
from rehearsal.api.models import AbortRequest
from rehearsal.api.runtime import SessionRuntime

POLL_INTERVAL_S = 0.05
_COMMAND_ACTIONS = {"start", "pause", "resume", "abort"}


def _envelope(kind: str, seq: int, turn: int | None, ms: int, d: dict[str, object]) -> str:
    return json.dumps({"t": kind, "seq": seq, "turn": turn, "ms": ms, "d": d})


async def session_ws(websocket: WebSocket, session_id: str, runtime: SessionRuntime) -> None:
    await websocket.accept()

    events = runtime.events_since(session_id)
    if not events:
        await websocket.send_text(
            _envelope(
                "error", 0, None, int(time.time() * 1000),
                ApiError(
                    code="not_found", message=f"session {session_id!r} does not exist.",
                    http_status=404, session_id=session_id,
                ).body()["error"],
            )
        )
        await websocket.close(code=4004)
        return

    last_seq: int | None = None
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
        hello = json.loads(raw)
        if hello.get("t") == "hello":
            last_seq = hello.get("d", {}).get("last_seq")
    except (TimeoutError, json.JSONDecodeError, KeyError):
        pass  # a client that skips `hello` gets a full replay, per §5.5's spirit

    await websocket.send_text(
        _envelope(
            "hello", 0, None, int(time.time() * 1000),
            {
                "session_id": session_id,
                "event_seq": events[-1].seq,
                "resumed_from": last_seq,
                "server_build": "dev",
            },
        )
    )

    replay_from = last_seq if last_seq is not None else 0
    to_replay = [e for e in events if e.seq > replay_from]
    is_gap = last_seq is not None
    if is_gap and to_replay:
        await websocket.send_text(
            _envelope("gap.begin", 0, None, int(time.time() * 1000),
                       {"from": to_replay[0].seq, "to": to_replay[-1].seq})
        )
    for e in to_replay:
        await websocket.send_text(_envelope(e.kind, e.seq, e.turn_index, e.ts_ms, e.payload))
    if is_gap and to_replay:
        await websocket.send_text(_envelope("gap.end", 0, None, int(time.time() * 1000), {}))

    last_sent = to_replay[-1].seq if to_replay else events[-1].seq

    try:
        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=POLL_INTERVAL_S)
                msg = json.loads(raw)
                t = msg.get("t")
                if t == "ping":
                    await websocket.send_text(
                        _envelope("pong", 0, None, int(time.time() * 1000), {})
                    )
                elif t in _COMMAND_ACTIONS:
                    body = AbortRequest(**msg.get("d", {})) if t == "abort" else None
                    try:
                        runtime.transition(session_id, t, body)
                    except ApiError as exc:
                        await websocket.send_text(
                            _envelope("error", 0, None, int(time.time() * 1000), exc.body()["error"])
                        )
                # "ack" and "coach.dismiss" are transport-only; nothing to do
            except TimeoutError:
                pass
            except json.JSONDecodeError:
                await websocket.close(code=4022)
                return

            new_events = runtime.events_since(session_id, after=last_sent)
            for e in new_events:
                await websocket.send_text(_envelope(e.kind, e.seq, e.turn_index, e.ts_ms, e.payload))
                last_sent = e.seq
    except WebSocketDisconnect:
        return

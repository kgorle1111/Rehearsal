"""`/ws/session/{id}` replays a session from the event log (WS-API DoD).
Covers both cases the DoD names: full replay-from-start on connect, and
live-tail (a new event appended after the socket is already connected).
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from tests.api.conftest import APPROVED_SCENARIO_ID


def test_ws_unknown_session_closes_with_4004(client: TestClient) -> None:
    with client.websocket_connect("/ws/session/does-not-exist") as ws:
        msg = json.loads(ws.receive_text())
        assert msg["t"] == "error"
        assert msg["d"]["code"] == "not_found"


def test_ws_replays_full_event_log_from_connect(client: TestClient) -> None:
    session_id = client.post(
        "/api/sessions", json={"scenario_id": APPROVED_SCENARIO_ID, "trainee_id": "trainee-1"}
    ).json()["session_id"]
    client.post(f"/api/sessions/{session_id}/start")

    with client.websocket_connect(f"/ws/session/{session_id}") as ws:
        hello = json.loads(ws.receive_text())
        assert hello["t"] == "hello"
        assert hello["d"]["session_id"] == session_id

        # No prior `hello` sent by the client -> full replay from seq 0,
        # not a gap-replay (no gap.begin/gap.end framing).
        replayed = []
        for _ in range(5):
            replayed.append(json.loads(ws.receive_text()))

        kinds = [m["t"] for m in replayed]
        assert kinds == [
            "session.created",
            "seed.drawn",
            "scenario.bound",
            "session.started",
            "turn.opened",
        ]
        # seq numbers are monotonic and match the real event log.
        assert [m["seq"] for m in replayed] == sorted(m["seq"] for m in replayed)


def test_ws_live_tails_a_new_event_appended_after_connect(client: TestClient) -> None:
    session_id = client.post(
        "/api/sessions", json={"scenario_id": APPROVED_SCENARIO_ID, "trainee_id": "trainee-1"}
    ).json()["session_id"]

    with client.websocket_connect(f"/ws/session/{session_id}") as ws:
        json.loads(ws.receive_text())  # hello
        replayed = [json.loads(ws.receive_text()) for _ in range(3)]  # created/seed/bound
        assert [m["t"] for m in replayed] == ["session.created", "seed.drawn", "scenario.bound"]

        # Trigger a brand-new transition over REST while the socket is open.
        start_resp = client.post(f"/api/sessions/{session_id}/start")
        assert start_resp.status_code == 202

        # The poll loop (ws.py: 50ms tick) must pick up the new rows and
        # push them down the same open connection — this is the live-tail
        # half of "replays a session from the event log", not just replay.
        live = [json.loads(ws.receive_text()) for _ in range(2)]
        assert [m["t"] for m in live] == ["session.started", "turn.opened"]


def test_ws_resume_from_last_seq_only_gap_replays_missed_events(client: TestClient) -> None:
    session_id = client.post(
        "/api/sessions", json={"scenario_id": APPROVED_SCENARIO_ID, "trainee_id": "trainee-1"}
    ).json()["session_id"]
    events = client.get(f"/api/sessions/{session_id}/events").json()["items"]
    last_seq = events[1]["seq"]  # pretend the client already saw the first 2 events

    with client.websocket_connect(f"/ws/session/{session_id}") as ws:
        ws.send_text(json.dumps({"t": "hello", "d": {"last_seq": last_seq}}))
        hello = json.loads(ws.receive_text())
        assert hello["t"] == "hello"
        assert hello["d"]["resumed_from"] == last_seq

        gap_begin = json.loads(ws.receive_text())
        assert gap_begin["t"] == "gap.begin"

        replayed = [json.loads(ws.receive_text()) for _ in range(1)]
        assert replayed[0]["t"] == "scenario.bound"  # only the missed tail, not the whole log

        gap_end = json.loads(ws.receive_text())
        assert gap_end["t"] == "gap.end"

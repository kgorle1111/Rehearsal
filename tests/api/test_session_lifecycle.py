"""Session lifecycle: create -> start -> abort, proving the FSM wiring is
real (not a fake) — each transition below is a genuine `SessionFSM.apply()`
call producing genuine hash-chained events, per `runtime.py`'s own docstring.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.api.conftest import APPROVED_SCENARIO_ID


def test_create_start_abort_moves_through_real_fsm_states(client: TestClient) -> None:
    create_resp = client.post(
        "/api/sessions", json={"scenario_id": APPROVED_SCENARIO_ID, "trainee_id": "trainee-1"}
    )
    assert create_resp.status_code == 201
    session_id = create_resp.json()["session_id"]
    assert create_resp.json()["state"] == "armed"

    start_resp = client.post(f"/api/sessions/{session_id}/start")
    assert start_resp.status_code == 202
    assert start_resp.json()["state"] == "source_speaking"

    abort_resp = client.post(f"/api/sessions/{session_id}/abort", json={"reason": "user"})
    assert abort_resp.status_code == 202
    assert abort_resp.json()["state"] == "aborted"

    # A terminal session can never transition again — proves this isn't a
    # fake that just echoes whatever action it's told.
    resume_after_abort = client.post(f"/api/sessions/{session_id}/resume")
    assert resume_after_abort.status_code == 409


def test_events_accumulate_across_the_lifecycle_with_an_intact_chain(client: TestClient) -> None:
    session_id = client.post(
        "/api/sessions", json={"scenario_id": APPROVED_SCENARIO_ID, "trainee_id": "trainee-1"}
    ).json()["session_id"]
    client.post(f"/api/sessions/{session_id}/start")
    client.post(f"/api/sessions/{session_id}/abort")

    events = client.get(f"/api/sessions/{session_id}/events").json()
    assert events["chain_ok"] is True
    kinds = [e["kind"] for e in events["items"]]
    assert kinds == [
        "session.created",
        "seed.drawn",
        "scenario.bound",
        "session.started",
        "turn.opened",
        "session.aborted",
    ]


def test_get_session_state_matches_the_live_fsm_for_non_durable_states(
    client: TestClient,
) -> None:
    """Was a documented bug reproduction (P5 follow-up): `POST .../start`
    returns the real, live FSM state (`"source_speaking"`), but `GET
    /api/sessions/{id}` used to recompute state independently via
    `fold(events)`, which only advances on event kinds present in
    `EVENT_KIND_TO_DURABLE_STATE` — a map with no entry for `session.started`
    /`turn.opened`, because `source_speaking` is a non-durable state by
    design (§8.1). `fold()` answers "where would resume land", not "what is
    happening right now"; those are different questions for a non-durable
    state. Fixed in `SessionRuntime.get_session`/`_sync_projection` by
    reading state from the live, cached `SessionFSM` (which does track
    transient states) rather than re-deriving purely from the event log,
    falling back to the same fold()-derived state when no live FSM is
    cached (e.g. after a process restart) — so it's never less accurate,
    only sometimes more so.
    """
    session_id = client.post(
        "/api/sessions", json={"scenario_id": APPROVED_SCENARIO_ID, "trainee_id": "trainee-1"}
    ).json()["session_id"]

    start_ack_state = client.post(f"/api/sessions/{session_id}/start").json()["state"]
    assert start_ack_state == "source_speaking"

    get_state = client.get(f"/api/sessions/{session_id}").json()["state"]
    assert get_state == start_ack_state

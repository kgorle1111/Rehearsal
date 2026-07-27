"""Contract tests for every REST endpoint in `rehearsal.api.app`. Each
endpoint gets a happy path (status code + response validates against its
own `response_model`) and at least one realistic error path
(404/409/422), per the WS-API DoD.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from rehearsal.api.models import (
    EventPage,
    Health,
    ScenarioDetail,
    ScenarioPage,
    SessionAck,
    SessionCreated,
    SessionPage,
    SessionViewOut,
)
from tests.api.conftest import APPROVED_SCENARIO_ID


def _create(client: TestClient, **overrides: object) -> dict[str, object]:
    body = {"scenario_id": APPROVED_SCENARIO_ID, "trainee_id": "trainee-1", **overrides}
    resp = client.post("/api/sessions", json=body)
    assert resp.status_code == 201, resp.text
    return dict(resp.json())


# ── POST /api/sessions ──────────────────────────────────────────────────


def test_create_session_happy_path(client: TestClient) -> None:
    resp = client.post(
        "/api/sessions", json={"scenario_id": APPROVED_SCENARIO_ID, "trainee_id": "t1"}
    )
    assert resp.status_code == 201
    created = SessionCreated.model_validate(resp.json())
    assert created.state == "armed"
    assert created.scenario_id == APPROVED_SCENARIO_ID
    assert created.ws_url == f"/ws/session/{created.session_id}"


def test_create_session_unknown_scenario_is_422(client: TestClient) -> None:
    resp = client.post("/api/sessions", json={"scenario_id": "does-not-exist", "trainee_id": "t1"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "scenario_unknown"


def test_create_session_unapproved_scenario_is_422(client: TestClient) -> None:
    """A real seed scenario (all `pending`, see NOT-BUILT-YET.md) must never
    be bindable — the approval gate has no override."""
    resp = client.post(
        "/api/sessions",
        json={"scenario_id": "sc_0001_dm2_metformin_counseling", "trainee_id": "t1"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "scenario_unknown"


def test_create_session_malformed_body_is_422(client: TestClient) -> None:
    resp = client.post("/api/sessions", json={"scenario_id": APPROVED_SCENARIO_ID})  # no trainee_id
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "schema_invalid"


def test_create_session_unknown_field_is_422(client: TestClient) -> None:
    """Request models use `extra="forbid"` — an unknown field is a client
    bug the server must not silently swallow (misc/docs/11 §2.1)."""
    resp = client.post(
        "/api/sessions",
        json={"scenario_id": APPROVED_SCENARIO_ID, "trainee_id": "t1", "bogus_field": True},
    )
    assert resp.status_code == 422


def test_create_session_conflicts_with_an_already_live_session(client: TestClient) -> None:
    _create(client)
    resp = client.post(
        "/api/sessions", json={"scenario_id": APPROVED_SCENARIO_ID, "trainee_id": "t2"}
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "session_already_live"


# ── POST /api/sessions/{id}/start|pause|resume|abort ───────────────────


def test_start_session_happy_path(client: TestClient) -> None:
    session_id = _create(client)["session_id"]
    resp = client.post(f"/api/sessions/{session_id}/start")
    assert resp.status_code == 202
    ack = SessionAck.model_validate(resp.json())
    assert ack.accepted is True
    assert ack.state == "source_speaking"


def test_start_unknown_session_is_404(client: TestClient) -> None:
    resp = client.post("/api/sessions/does-not-exist/start")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_pause_then_resume_happy_path(client: TestClient) -> None:
    session_id = _create(client)["session_id"]
    client.post(f"/api/sessions/{session_id}/start")
    pause_resp = client.post(f"/api/sessions/{session_id}/pause")
    assert pause_resp.status_code == 202
    assert SessionAck.model_validate(pause_resp.json()).state == "paused"

    resume_resp = client.post(f"/api/sessions/{session_id}/resume")
    assert resume_resp.status_code == 202
    # Resume lands on the *previous durable checkpoint* (orchestrator/fsm.py
    # PREV_DURABLE / DURABLE set), not necessarily the exact state paused
    # from: `source_speaking` is explicitly non-durable (§8.1), so pausing
    # mid-turn and resuming re-plans from `armed` rather than continuing
    # the in-flight turn. Intentional crash-resume semantics, not a bug.
    assert SessionAck.model_validate(resume_resp.json()).state == "armed"


def test_resume_a_session_that_is_not_paused_is_409(client: TestClient) -> None:
    session_id = _create(client)["session_id"]
    client.post(f"/api/sessions/{session_id}/start")  # now source_speaking, not paused
    resp = client.post(f"/api/sessions/{session_id}/resume")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "illegal_transition"


def test_abort_session_happy_path(client: TestClient) -> None:
    session_id = _create(client)["session_id"]
    resp = client.post(f"/api/sessions/{session_id}/abort", json={"reason": "user"})
    assert resp.status_code == 202
    ack = SessionAck.model_validate(resp.json())
    assert ack.state == "aborted"


def test_abort_an_already_aborted_session_is_409(client: TestClient) -> None:
    session_id = _create(client)["session_id"]
    client.post(f"/api/sessions/{session_id}/abort")
    resp = client.post(f"/api/sessions/{session_id}/abort")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "illegal_transition"


# ── GET /api/sessions/{id} ───────────────────────────────────────────────


def test_get_session_happy_path(client: TestClient) -> None:
    session_id = _create(client)["session_id"]
    resp = client.get(f"/api/sessions/{session_id}")
    assert resp.status_code == 200
    view = SessionViewOut.model_validate(resp.json())
    assert view.session_id == session_id
    assert view.trainee_id == "trainee-1"


def test_get_session_unknown_is_404(client: TestClient) -> None:
    resp = client.get("/api/sessions/does-not-exist")
    assert resp.status_code == 404


# ── GET /api/sessions ─────────────────────────────────────────────────────


def test_list_sessions_happy_path(client: TestClient) -> None:
    session_id = _create(client)["session_id"]
    resp = client.get("/api/sessions")
    assert resp.status_code == 200
    page = SessionPage.model_validate(resp.json())
    assert [s.session_id for s in page.items] == [session_id]


def test_list_sessions_filters_by_trainee_id(client: TestClient) -> None:
    _create(client)
    resp = client.get("/api/sessions", params={"trainee_id": "someone-else"})
    assert resp.status_code == 200
    assert SessionPage.model_validate(resp.json()).items == []


def test_list_sessions_rejects_limit_out_of_bounds(client: TestClient) -> None:
    resp = client.get("/api/sessions", params={"limit": 0})
    assert resp.status_code == 422


# ── GET /api/sessions/{id}/events ────────────────────────────────────────


def test_get_events_happy_path(client: TestClient) -> None:
    session_id = _create(client)["session_id"]
    resp = client.get(f"/api/sessions/{session_id}/events")
    assert resp.status_code == 200
    page = EventPage.model_validate(resp.json())
    assert page.chain_ok is True
    assert [e.kind for e in page.items] == ["session.created", "seed.drawn", "scenario.bound"]


def test_get_events_unknown_session_is_404(client: TestClient) -> None:
    resp = client.get("/api/sessions/does-not-exist/events")
    assert resp.status_code == 404


def test_get_events_filters_by_kind(client: TestClient) -> None:
    session_id = _create(client)["session_id"]
    resp = client.get(f"/api/sessions/{session_id}/events", params={"kinds": "seed.drawn"})
    assert resp.status_code == 200
    page = EventPage.model_validate(resp.json())
    assert [e.kind for e in page.items] == ["seed.drawn"]


# ── GET /api/scenarios ────────────────────────────────────────────────────


def test_list_scenarios_happy_path(client: TestClient) -> None:
    resp = client.get("/api/scenarios")
    assert resp.status_code == 200
    page = ScenarioPage.model_validate(resp.json())
    assert [s.scenario_id for s in page.items] == [APPROVED_SCENARIO_ID]
    assert page.items[0].review_status == "approved"


def test_list_scenarios_filters_by_difficulty(client: TestClient) -> None:
    resp = client.get("/api/scenarios", params={"difficulty": 99})
    assert resp.status_code == 200
    assert ScenarioPage.model_validate(resp.json()).items == []


# ── GET /api/scenarios/{id} ───────────────────────────────────────────────


def test_get_scenario_happy_path(client: TestClient) -> None:
    resp = client.get(f"/api/scenarios/{APPROVED_SCENARIO_ID}")
    assert resp.status_code == 200
    detail = ScenarioDetail.model_validate(resp.json())
    assert detail.condition == "type 2 diabetes mellitus"
    assert len(detail.term_manifest) == 1


def test_get_scenario_unapproved_is_404_not_leaked(client: TestClient) -> None:
    """A pending scenario isn't in this test's bank at all — but the same
    endpoint must 404 rather than 200 for any scenario this bank hasn't
    approved, matching `ScenarioBank.get()`'s no-override gate."""
    resp = client.get("/api/scenarios/sc_0001_dm2_metformin_counseling")
    assert resp.status_code == 404


# ── GET /api/health ────────────────────────────────────────────────────────


def test_health_happy_path(client: TestClient) -> None:
    resp = client.get("/api/health")
    assert resp.status_code == 200
    health = Health.model_validate(resp.json())
    assert health.status == "ok"
    assert health.store["db_ok"] is True
    assert health.live_session_id is None


def test_health_reports_live_session_id_once_a_session_is_active(client: TestClient) -> None:
    session_id = _create(client)["session_id"]
    client.post(f"/api/sessions/{session_id}/start")
    resp = client.get("/api/health")
    assert Health.model_validate(resp.json()).live_session_id == session_id

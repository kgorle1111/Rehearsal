"""The FastAPI surface. misc/docs/11-backend-api.md §3-§5.

`create_app()` is the factory every test and the real entrypoint share —
paths for the DB, blob root, and scenario directory are parameters, not
module-level globals, so tests get an isolated store per run instead of
sharing `~/.rehearsal/`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

from fastapi import FastAPI, Query, WebSocket
from starlette.requests import Request
from starlette.responses import Response

from rehearsal.api.errors import register_exception_handlers
from rehearsal.api.models import (
    AbortRequest,
    EventPage,
    Health,
    ScenarioDetail,
    ScenarioPage,
    SessionAck,
    SessionCreated,
    SessionCreateRequest,
    SessionPage,
    SessionViewOut,
)
from rehearsal.api.runtime import SessionRuntime
from rehearsal.api.ws import session_ws
from rehearsal.scenarios.bank import ScenarioBank
from rehearsal.store.blobs import BlobStore
from rehearsal.store.db import connect


def create_app(
    *,
    db_path: Path | str,
    blob_root: Path | str,
    scenario_dir: Path | str,
) -> FastAPI:
    app = FastAPI(title="rehearsal-api")
    register_exception_handlers(app)

    conn = connect(db_path)
    blobs = BlobStore(blob_root)
    bank = ScenarioBank(Path(scenario_dir))
    runtime = SessionRuntime(conn, bank)

    app.state.conn = conn
    app.state.blobs = blobs
    app.state.runtime = runtime

    @app.middleware("http")
    async def _headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Rehearsal-Api"] = "1"
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.post("/api/sessions", response_model=SessionCreated, status_code=201)
    def create_session(req: SessionCreateRequest) -> SessionCreated:
        return runtime.create_session(req)

    @app.post("/api/sessions/{session_id}/start", response_model=SessionAck, status_code=202)
    def start_session(session_id: str) -> SessionAck:
        return runtime.transition(session_id, "start")

    @app.post("/api/sessions/{session_id}/pause", response_model=SessionAck, status_code=202)
    def pause_session(session_id: str) -> SessionAck:
        return runtime.transition(session_id, "pause")

    @app.post("/api/sessions/{session_id}/resume", response_model=SessionAck, status_code=202)
    def resume_session(session_id: str) -> SessionAck:
        return runtime.transition(session_id, "resume")

    @app.post("/api/sessions/{session_id}/abort", response_model=SessionAck, status_code=202)
    def abort_session(session_id: str, req: AbortRequest | None = None) -> SessionAck:
        return runtime.transition(session_id, "abort", req or AbortRequest())

    @app.get("/api/sessions/{session_id}", response_model=SessionViewOut)
    def get_session(session_id: str) -> SessionViewOut:
        return runtime.get_session(session_id)

    @app.get("/api/sessions", response_model=SessionPage)
    def list_sessions(
        trainee_id: str | None = None,
        state: str | None = None,
        before: str | None = None,
        limit: int = Query(50, ge=1, le=200),
    ) -> SessionPage:
        return runtime.list_sessions(trainee_id=trainee_id, state=state, before=before, limit=limit)

    @app.get("/api/sessions/{session_id}/events", response_model=EventPage)
    def get_events(
        session_id: str,
        after: int = 0,
        limit: int = Query(500, ge=1, le=5000),
        kinds: str | None = None,
    ) -> EventPage:
        kind_list = kinds.split(",") if kinds else None
        return runtime.get_events(session_id, after=after, limit=limit, kinds=kind_list)

    @app.get("/api/scenarios", response_model=ScenarioPage)
    def list_scenarios(difficulty: int | None = None) -> ScenarioPage:
        return ScenarioPage(items=runtime.list_scenarios(difficulty=difficulty))

    @app.get("/api/scenarios/{scenario_id}", response_model=ScenarioDetail)
    def get_scenario(scenario_id: str) -> ScenarioDetail:
        return runtime.get_scenario(scenario_id)

    @app.get("/api/health", response_model=Health)
    def health() -> Health:
        try:
            conn.execute("SELECT 1")
            db_ok = True
        except Exception:
            db_ok = False
        return Health(
            status="ok" if db_ok else "down",
            store={"db_ok": db_ok, "blob_root_writable": Path(blob_root).exists()},
            live_session_id=runtime.live_session_id(),
        )

    @app.websocket("/ws/session/{session_id}")
    async def ws_endpoint(websocket: WebSocket, session_id: str) -> None:
        await session_ws(websocket, session_id, runtime)

    return app

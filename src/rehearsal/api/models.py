"""Request/response models. misc/docs/11-backend-api.md §2.1: `extra="forbid"`
on every request model — an unknown field is a client bug the server must
not silently swallow."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SessionCreateRequest(BaseModel, extra="forbid"):
    scenario_id: str
    trainee_id: str
    direction_policy: Literal["alternating", "graph"] = "graph"
    max_turns: int = Field(24, ge=1, le=60)
    root_seed: int | None = None
    difficulty: int | None = None
    degrade_floor: Literal["L0", "L1", "L2", "L3", "L4"] = "L4"
    text_mode: bool = False


class SessionCreated(BaseModel):
    session_id: str
    state: str
    scenario_id: str
    root_seed: int
    difficulty: int
    planned_turns: int
    ws_url: str
    hosts: dict[str, str]


class SessionAck(BaseModel):
    session_id: str
    accepted: bool
    state: str
    event_seq: int


class AbortRequest(BaseModel, extra="forbid"):
    reason: Literal["user"] = "user"


class SessionViewOut(BaseModel):
    """The folded view. misc/docs/11-backend-api.md §4.3: this must be the
    same shape `resume.fold()` produces — the fields below are exactly
    `SessionView`'s fields (renamed to the wire's `state` string) plus the
    static session metadata `fold()` doesn't carry (trainee_id, scenario_id,
    started_ms), read from the `sessions` projection row."""

    session_id: str
    state: str
    trainee_id: str | None
    scenario_id: str | None
    root_seed: int | None
    turn_index: int | None
    planned_turns: int | None
    started_ms: int | None
    event_seq: int


class SessionSummary(BaseModel):
    session_id: str
    trainee_id: str
    scenario_id: str
    state: str
    started_ms: int | None
    root_seed: int


class SessionPage(BaseModel):
    items: list[SessionSummary]
    next_before: str | None


class EventItem(BaseModel):
    seq: int
    turn_index: int | None
    ts_ms: int
    mono_ms: int
    kind: str
    payload: dict[str, Any]
    prev_hash: str
    hash: str


class EventPage(BaseModel):
    items: list[EventItem]
    next_after: int | None
    chain_ok: bool


class ScenarioSummary(BaseModel):
    scenario_id: str
    schema_version: str
    difficulty: int
    condition: str
    review_status: str


class ScenarioDetail(ScenarioSummary):
    clinical_state: dict[str, Any]
    term_manifest: list[dict[str, Any]]


class ScenarioPage(BaseModel):
    items: list[ScenarioSummary]


class Health(BaseModel):
    status: Literal["ok", "degraded", "down"]
    store: dict[str, Any]
    live_session_id: str | None

# 11 — Backend & API

The server contract and the persistence design. This document is the authority on: every HTTP endpoint, the real-time channel protocol, the complete SQLite schema, the append-only event log and replay, concurrency and isolation, model process management, configuration and feature flags, idempotency and crash recovery, and API versioning policy.

It is the implementation contract for `src/rehearsal/api/` and `src/rehearsal/store/`. `docs/03-system-architecture.md` gives the architectural rationale and the session state machine; this document gives the wire format and the DDL. `docs/10-frontend-spec.md` consumes this document — every type the frontend holds originates here.

**What this document does not restate:** the scoring internals (`docs/06-scoring-engine.md`), the voice/latency budget (`docs/05-voice-pipeline.md`), the eval definitions (`docs/08-evals.md`), the calibration protocol (`SETUP.md` §6), the threat model (`docs/12-security-privacy.md`), or the packaging and runbooks (`docs/13-deployment-ops.md`).

---

## 1. Posture: what kind of server this is

Rehearsal's backend is **a single-user local process that happens to speak HTTP**. That is not a limitation to be apologised for; it is a design decision that removes an entire class of surface area, and it changes what the API contract has to guarantee.

| Property | Decision | Consequence for the contract |
|---|---|---|
| Binding | `127.0.0.1:8420` only, never `0.0.0.0` | No TLS, no CORS allowlist beyond the same origin, no host header validation beyond a loopback assertion |
| Tenancy | **None.** One machine, one installation, one store | No `tenant_id` on any table. No row-level authorisation. No account system |
| Authentication | None in the core loop; the OS user *is* the principal | Filesystem permissions on `~/.rehearsal/` are the access control (`0700`) |
| Concurrency of sessions | **One live session per process** (enforced, §9) | Endpoints that mutate live state can return `409 session_already_live` |
| Client | The bundled SPA served from the same origin at `/` | The API and its only client ship in one artifact and version together (§14) |
| Network egress | Zero from `runtime/`, `scoring/`, `orchestrator/` (boundary B4, `docs/03-system-architecture.md` §12) | No webhooks, no callbacks, no push. The server never initiates a connection |

**Why there is no multi-tenant surface [decided].** Multi-tenancy would require, at minimum: an identity system, per-row authorisation on every read path, encrypted transport, an audit log distinct from the event log, session-scoped resource quotas, and a threat model that includes other users of the same server. Each of those is real work with real failure modes, and every one of them would be built to serve a deployment shape the product does not have. The product's privacy claim is architectural — *the audio has nowhere to go* — and a multi-tenant server is precisely the change that would dismantle it. Horizontal fleet scaling is explicitly out of scope for the same reason.

The cost is stated plainly: a training program wanting a shared cohort dashboard cannot have one without a new, separately designed service. The migration path, if it is ever taken, is **export-based** (`~/.rehearsal/exports/`, redacted, human-initiated) and not a change to this server. Do not add a `tenant_id` column "for later"; later can add it with a migration, and a speculative column that is never non-null is a lie in the schema.

---

## 2. API conventions

### 2.1 Shape

```
Base URL      http://127.0.0.1:8420
HTTP surface  /api/*                     JSON in, JSON out
Realtime      /ws/session/{session_id}   JSON envelopes (§5)
Static        /                          frontend/dist, SPA fallback to index.html
```

| Convention | Rule |
|---|---|
| Content type | `application/json; charset=utf-8` on every request and response with a body, except `GET /api/blobs/{sha256}` (binary) and the SSE endpoints (`text/event-stream`) |
| Casing | `snake_case` everywhere, in JSON as in SQL. One casing rule for the whole system removes a class of mapping bug and a class of argument |
| Times | Integer milliseconds. `*_ms` = wall clock ms since Unix epoch (UTC). `*_mono_ms` = monotonic ms, valid only for arithmetic within one process lifetime. No ISO strings on the hot path; ISO-8601 UTC appears only in the eval registry (`docs/08-evals.md`), which is a different database with different readers |
| Identifiers | `session_id`, `run_id` are **ULIDs** (26 chars, Crockford base32, lexicographically sortable by creation). `trainee_id`, `scenario_id`, `node_id` are opaque slugs matching `^[a-z0-9][a-z0-9_.-]{0,63}$` |
| Nulls | A field that is absent and a field that is `null` mean the same thing: not known yet. Fields are never omitted to mean "false" |
| Unknown request fields | Rejected with `422 schema_invalid`. Pydantic models use `extra="forbid"`. A silently-ignored field is a bug the client cannot see |
| Unknown response fields | Clients must tolerate them (forward compatibility, §14) |
| Pagination | Only on `/api/sessions` and `/api/sessions/{id}/events`. Cursor-based on the monotonic key (`session_id` ULID or event `seq`), never offset-based, because the event log grows during the read |
| Mutation verbs | `POST` for state transitions on a resource (`/start`, `/pause`). No `PUT`, no `PATCH`, no `DELETE` on session data — **nothing in the session record is editable or deletable through the API** |

### 2.2 Error envelope

Every non-2xx response has exactly this body. No endpoint returns a bare string or a FastAPI default `{"detail": ...}`; a global exception handler normalises them.

```json
{
  "error": {
    "code": "session_already_live",
    "message": "A session is already running; abort or complete it first.",
    "http_status": 409,
    "session_id": "01J9F3K8Q2ZC4P0R7T5N2WJ8AB",
    "retriable": false,
    "detail": {"live_session_id": "01J9F3K8Q2ZC4P0R7T5N2WJ8AB"}
  }
}
```

```python
# src/rehearsal/api/errors.py

@dataclass(frozen=True, slots=True)
class ApiError(Exception):
    code: str                      # stable machine string; part of the contract (§14)
    message: str                   # human sentence; NOT part of the contract, may be reworded
    http_status: int
    retriable: bool = False
    session_id: SessionId | None = None
    detail: dict[str, JsonValue] = field(default_factory=dict)
```

`code` is the contract; `message` is prose and may change without notice. Clients switch on `code`, never on `message` or on `http_status` alone (several codes share a status).

**Error messages are prescriptive.** Every message names what failed, why, and the next action — the same rule the project applies to tool errors for agents. `"grader host unavailable"` is a bad message; `"Grader host is not responding; the session continues with critical checks only. Run `rehearsal doctor` to diagnose."` is the standard.

**Error bodies never contain utterance text.** A validation failure on a transcript reports the field and the length, not the content. This follows boundary B7: an error body can be pasted into a bug report, and a bug report is off the machine.

### 2.3 Error code register

| Code | HTTP | Retriable | Raised when |
|---|---|---|---|
| `schema_invalid` | 422 | no | Request body failed validation; `detail.fields` lists paths |
| `not_found` | 404 | no | Session, blob, scenario or finding id does not exist |
| `scenario_unknown` | 422 | no | `scenario_id` not present in the scenario bank |
| `scenario_invalid` | 500 | no | Scenario exists but its state graph failed validation at load |
| `session_already_live` | 409 | no | A create/start was attempted while another session is live (§9.1) |
| `illegal_transition` | 409 | no | The requested transition is not legal from the current state; `detail.state` and `detail.allowed` are included |
| `session_terminal` | 409 | no | The session is `complete`, `aborted` or `failed`; it is immutable |
| `session_not_reviewable` | 409 | no | Review write attempted on a session not in `review` |
| `already_signed` | 409 | no | `review.signed` already exists for this session |
| `host_unavailable` | 503 | yes | A required model host failed its health probe |
| `audio_device_unavailable` | 503 | yes | No usable capture device (see `docs/05-voice-pipeline.md`) |
| `store_unwritable` | 507 | no | Event append failed (disk full, permissions). Sessions pause before this becomes an abort |
| `blob_missing` | 404 | no | Referenced blob is absent from the blob root |
| `blob_corrupt` | 410 | no | Blob bytes present but the sha256 does not match; blob is quarantined |
| `degrade_floor` | 409 | no | Requested operation would require running below `cfg.degrade_floor` |
| `seal_violation` | 403 | no | An operation would read the sealed TEST split without an `unseal_reason` (`docs/08-evals.md` §5) |
| `idempotency_conflict` | 409 | no | Same `Idempotency-Key` replayed with a different body (§13.1) |
| `rate_capped` | 429 | yes | Local self-protection cap hit (§9.4) — the only thing resembling rate limiting |
| `not_loopback` | 403 | no | Request did not arrive on the loopback interface |
| `internal` | 500 | no | Unhandled; the traceback **digest** is in `detail.trace_digest`, never the traceback text |

### 2.4 Standard headers

| Header | Direction | Meaning |
|---|---|---|
| `X-Rehearsal-Api: 1` | response | Major API generation (§14) |
| `X-Rehearsal-Build: <git_commit>` | response | Exact build; the SPA compares it to its own and prompts a reload on mismatch |
| `X-Rehearsal-Event-Seq: <int>` | response, on session endpoints | Highest event `seq` reflected in this response. Lets a client tell whether an HTTP read is behind its WS stream |
| `Idempotency-Key: <ULID>` | request, on session-creating and review POSTs | §13.1 |
| `Cache-Control: no-store` | response | Default on all `/api/*`. Overridden to `public, max-age=31536000, immutable` on `/api/blobs/{sha256}` — content-addressed bytes can never change |

---

## 3. Endpoint index

Streaming column: `WS` = WebSocket, `SSE` = server-sent events, `chunked` = byte stream, `—` = single JSON response.

### 3.1 Session lifecycle

| Method | Path | Request | Response | Errors | Streaming |
|---|---|---|---|---|---|
| `POST` | `/api/sessions` | `SessionCreateRequest` | `201 SessionCreated` | 422, 409, 503, 507 | — |
| `POST` | `/api/sessions/{id}/start` | `{}` | `202 SessionAck` | 404, 409, 503 | — |
| `POST` | `/api/sessions/{id}/pause` | `{}` | `202 SessionAck` | 404, 409 | — |
| `POST` | `/api/sessions/{id}/resume` | `{}` | `202 SessionAck` | 404, 409, 503 | — |
| `POST` | `/api/sessions/{id}/abort` | `AbortRequest` | `202 SessionAck` | 404, 409 | — |
| `GET` | `/api/sessions/{id}` | — | `200 SessionView` | 404 | — |
| `GET` | `/api/sessions` | query | `200 SessionPage` | 422 | — |
| `GET` | `/api/sessions/{id}/report` | query | `200 SessionReport` | 404, 409 | — |
| `GET` | `/api/sessions/{id}/turns/{n}` | — | `200 TurnDetail` | 404 | — |
| `GET` | `/api/sessions/{id}/events` | query | `200 EventPage` | 404, 422 | — |
| `GET` | `/api/sessions/{id}/export` | query | `200` archive | 404, 409, 507 | chunked |

### 3.2 Real-time and review

| Method | Path | Request | Response | Errors | Streaming |
|---|---|---|---|---|---|
| `WS` | `/ws/session/{id}` | `ClientMessage` | `ServerMessage` | close codes §5.7 | **WS** |
| `POST` | `/api/reviews` | `ReviewRequest` | `201 ReviewCreated` | 404, 409, 422 | — |
| `GET` | `/api/sessions/{id}/reviews` | — | `200 ReviewList` | 404 | — |
| `POST` | `/api/sessions/{id}/sign` | `SignRequest` | `200 SessionView` | 404, 409 | — |

### 3.3 Content

| Method | Path | Request | Response | Errors | Streaming |
|---|---|---|---|---|---|
| `GET` | `/api/scenarios` | query | `200 ScenarioPage` | 422 | — |
| `GET` | `/api/scenarios/{scenario_id}` | — | `200 ScenarioDetail` | 404 | — |
| `GET` | `/api/scenarios/{scenario_id}/graph` | — | `200 ClinicalGraph` | 404, 500 | — |
| `GET` | `/api/blobs/{sha256}` | `Range` optional | `200`/`206` bytes | 404, 410 | chunked |
| `HEAD` | `/api/blobs/{sha256}` | — | `200` headers only | 404 | — |

### 3.4 Learner

| Method | Path | Request | Response | Errors | Streaming |
|---|---|---|---|---|---|
| `GET` | `/api/learners/{trainee_id}` | — | `200 LearnerProfile` | 404 | — |
| `GET` | `/api/learners/{trainee_id}/skills` | — | `200 SkillEstimates` | 404 | — |
| `GET` | `/api/learners/{trainee_id}/history` | query | `200 SessionPage` | 404, 422 | — |

### 3.5 System

| Method | Path | Request | Response | Errors | Streaming |
|---|---|---|---|---|---|
| `GET` | `/api/health` | — | `200 Health` | — | — |
| `GET` | `/api/health/stream` | — | `200` | — | **SSE** |
| `GET` | `/api/meta` | — | `200 Meta` | — | — |
| `GET` | `/api/config` | — | `200 EffectiveConfig` | — | — |
| `POST` | `/api/hosts/{role}/warmup` | `{}` | `202 HostStatus` | 404, 503 | — |
| `POST` | `/api/hosts/{role}/restart` | `{}` | `202 HostStatus` | 404, 409 | — |

### 3.6 Deliberately absent endpoints

| Absent | Why |
|---|---|
| `DELETE /api/sessions/{id}` | The record is append-only. Reclamation is `rehearsal gc`, a CLI operation with a dry run and a second explicit confirmation — not one HTTP call away from a UI |
| `PATCH /api/findings/{id}` | A trainer override is an *additional fact* (`reviews` row), never a mutation. This is what makes trainer-override rate measurable (L7 eval) |
| Any auth/session/token endpoint | No account system (§1) |
| Any endpoint that runs an eval | Evals are CLI-driven (`make calibrate`, `rehearsal eval`) and write to a different database. An HTTP-triggered eval invites running one against the sealed TEST split by accident |
| Any endpoint accepting a prompt | Prompts are versioned files in the repo, never runtime input (`docs/04-ai-engineering.md`) |

---

## 4. Endpoint detail

### 4.1 `POST /api/sessions`

Creates a session in `configuring`, binds a scenario, draws and records the root seed. Does **not** start audio.

```python
class SessionCreateRequest(BaseModel, extra="forbid"):
    scenario_id: str
    trainee_id: str
    direction_policy: Literal["alternating", "graph"] = "graph"
    max_turns: int = Field(24, ge=1, le=60)
    root_seed: int | None = None          # None -> drawn from os.urandom(8) and recorded
    difficulty: int | None = None         # None -> LearnerModel.difficulty(trainee_id)
    degrade_floor: Literal["L0","L1","L2","L3","L4"] = "L4"
    text_mode: bool = False               # explicit opt-in; see degrade ladder L4
```

```json
{
  "session_id": "01J9F3K8Q2ZC4P0R7T5N2WJ8AB",
  "state": "armed",
  "scenario_id": "watsonville_diabetes_followup_v3",
  "root_seed": 8123471002938471,
  "difficulty": 3,
  "planned_turns": 18,
  "ws_url": "/ws/session/01J9F3K8Q2ZC4P0R7T5N2WJ8AB",
  "hosts": {"live": "ready", "grader": "ready", "tts": "ready"}
}
```

Preconditions, checked in this order so the client gets the most actionable failure first: scenario exists and its graph validates → no other live session → store writable → live host healthy. A failing grader host does **not** block creation; it degrades to L2 and the response carries `hosts.grader: "unavailable"`, because a session with critical checks only is still worth running and the trainee is told.

`root_seed` is accepted from the client because reproducing a reported session is a first-class operation (`rehearsal replay`). It is recorded in `seed.drawn` either way, so a supplied seed and a drawn seed are indistinguishable downstream.

### 4.2 `POST /api/sessions/{id}/start|pause|resume|abort`

All four return `202` with the same body and are **acknowledgements, not completions** — the real transition arrives on the WebSocket. This is deliberate: the orchestrator is the only writer of session state, and blocking an HTTP request until it has finished a transition would put two clocks on one state machine.

```json
{"session_id": "01J9F…", "accepted": true, "state": "armed", "event_seq": 412}
```

`event_seq` is the seq of the *command acceptance*; the client can wait for `seq > 412` on the WS to see the effect. `AbortRequest` is `{"reason": "user"}` — the enum is `user | audio_device | host_unavailable | store_full | degrade_floor`, and only `user` is accepted from a client.

Legal transitions are exactly the table in `docs/03-system-architecture.md` §8.2. An illegal one returns `409 illegal_transition` with `detail.state` and `detail.allowed`, so the UI can grey the right buttons rather than guess.

### 4.3 `GET /api/sessions/{id}`

Returns the folded `SessionView` — the same structure `fold(events)` produces in `src/rehearsal/orchestrator/resume.py`, so what a reconnecting client sees and what a recovering process sees are the same object. There is no second definition of "session state".

```json
{
  "session_id": "01J9F…",
  "state": "rendering_capturing",
  "trainee_id": "kn",
  "scenario_id": "watsonville_diabetes_followup_v3",
  "root_seed": 8123471002938471,
  "started_ms": 1770000000000,
  "ended_ms": null,
  "abort_reason": null,
  "turn_index": 7,
  "planned_turns": 18,
  "degrade_level": "L1",
  "degrade_max": "L1",
  "degrade_reason": "score_queue_depth",
  "text_mode": false,
  "models": {"live": "gemma-4-e4b-q4_k_m", "grader": "gemma-12b-q4_k_m"},
  "prompt_ver": "grader/v7",
  "scored_turns": 5,
  "pending_verdicts": 2,
  "event_seq": 1183
}
```

`degrade_level` (now) and `degrade_max` (worst reached) are both present because they answer different questions, and every number the session produces is qualified by `degrade_max`. A UI that shows only the current level will show a clean badge at the end of a session that spent ten turns at L2.

### 4.4 `GET /api/sessions` and `GET /api/learners/{id}/history`

```
?trainee_id=kn&state=complete&scenario_id=…&before=01J9F…&limit=50
```

Cursor is a `session_id` ULID; `before` is exclusive; results descend. `SessionPage` is `{"items": [SessionSummary], "next_before": "01J9E…" | null}`. `SessionSummary` is `SessionView` minus the live fields, plus `n_turns`, `n_critical`, `n_non_critical`, `review_state`.

### 4.5 `GET /api/sessions/{id}/report`

The debrief and trainer-review payload. `?include=findings,spans,audio_refs,coach` (default all); `?turn=n` narrows to one turn.

```json
{
  "session_id": "01J9F…",
  "state": "review",
  "degrade_max": "L2",
  "review_state": "open",
  "grader": {"model": "gemma-12b-q4_k_m", "prompt_ver": "grader/v7", "runtime": "mlx 0.x"},
  "coverage": {
    "turns_total": 18,
    "turns_scored_full": 14,
    "turns_scored_extractor_only": 3,
    "turns_unscored": 1,
    "unscored_turn_indices": [17],
    "not_assessed_categories": ["register_shift", "false_fluency", "editorialization",
                               "role_exchange", "first_person_violation"]
  },
  "totals": {"critical": 2, "non_critical": 9, "clean_turns": 7},
  "turns": [
    {
      "turn_index": 6,
      "speaker": "clinician",
      "direction": "en->es",
      "node_id": "meds.dose_change",
      "source_sha": "3fa9c1…e07",
      "rendering_sha": "b21d77…4c1",
      "audio_sha": "9e0aa3…812",
      "rendering_src": "live_verbatim",
      "partial": false,
      "verdict": {
        "verdict_key": "5c1e…",
        "status": "complete",
        "extractor_ms": 38,
        "grader_ms": 2417,
        "findings": [
          {
            "finding_id": 1841,
            "kind": "omission",
            "severity": "critical",
            "origin": "extractor",
            "extractor_name": "frequency",
            "src_start": 44, "src_end": 61,
            "span_start": null, "span_end": null,
            "confidence": 1.0,
            "overruled": false,
            "note": "source frequency 'every eight hours' absent from rendering",
            "reviews": [{"review_id": 77, "action": "agree", "reviewer": "trainer:mrivera"}]
          }
        ]
      },
      "coach": {"emitted": true, "text_sha": "aa71…", "suppressed_reason": null}
    }
  ]
}
```

Three properties of this payload are load-bearing and must not be optimised away:

1. **`coverage` is mandatory and explicit.** An unscored turn is listed by index. A category the grader never ran on is reported as *not assessed*, never as *no error found*. This is principle 7 expressed in a response schema; a report that silently omits an unscored turn is a report that overstates a trainee's performance.
2. **`reviews` are nested under findings but never merge into them.** The finding keeps its original `kind` and `severity` forever. `overruled` is a flag *derived* from the presence of a `reject`/`reclassify` review, and the derivation is in the projection, not in a mutation.
3. **`status: "partial"` propagates upward.** Any partial verdict forces `degrade_max ≥ L2` in the response, so no consumer can compute a session-level rate from partial data without seeing that it did.

Returns `409 illegal_transition` if the session has not reached `debrief` — a mid-session report would be a number computed on a prefix, and someone would quote it.

### 4.6 `GET /api/sessions/{id}/events`

`?after=1183&limit=500&kinds=turn.opened,verdict.merged`. Returns raw event rows in `seq` order, including `hash` and `prev_hash`, so a client (or a reviewer, or a test) can verify the chain independently of the server that produced it.

```json
{"items": [{"seq": 1184, "turn_index": 7, "ts_ms": 1770000121340, "mono_ms": 121340,
            "kind": "rendering.emitted", "payload": {...},
            "prev_hash": "0f2c…", "hash": "77ab…"}],
 "next_after": 1184, "chain_ok": true}
```

`chain_ok` is computed over the returned window and its predecessor hash. This endpoint is what makes "the event log is the truth" checkable by the frontend's debug panel and by `docs/14-testing-strategy.md`'s end-to-end tests, rather than a claim only the backend can make about itself.

### 4.7 `POST /api/reviews`

Appends a `review.override` event and one `reviews` row. Never modifies `findings`.

```python
class ReviewRequest(BaseModel, extra="forbid"):
    session_id: str
    finding_id: int | None = None                   # None -> session-level note
    action: Literal["agree", "reject", "reclassify", "add"]
    new_kind: ErrorKind | None = None               # required iff action in {reclassify, add}
    new_severity: Literal["critical", "non_critical"] | None = None
    turn_index: int | None = None                   # required iff action == "add"
    src_start: int | None = None
    src_end: int | None = None
    span_start: int | None = None
    span_end: int | None = None
    reviewer: str                                   # "trainee" | "trainer:<id>"
    rationale: str = ""
```

Cross-field validation is a model validator, not a chain of `if`s in the route: `reclassify`/`add` require `new_kind`; `add` requires `turn_index` and at least one span pair; `agree` forbids all of them. Violations are `422 schema_invalid` with `detail.fields`.

`POST /api/sessions/{id}/sign` appends `review.signed` and moves the session to `complete`, after which every write endpoint returns `409 session_terminal`. `SignRequest` is `{"reviewer": "trainer:mrivera", "note": ""}`. Signing twice is `409 already_signed` — not idempotent-success, because a second signature usually means the operator is looking at a stale UI.

### 4.8 `GET /api/blobs/{sha256}`

The only binary endpoint. Path parameter must match `^[0-9a-f]{64}$`; anything else is `422` before any filesystem access, which is also the path-traversal guard — the shard path is *derived* from the validated hash (`blobs/sha256/3f/a9/<hash>.<ext>`), never taken from input.

Read path: locate → stream → hash while streaming → compare. A mismatch aborts the response, appends `blob_quarantined`, moves the file to `blobs/quarantine/`, marks the referencing turn, and returns `410 blob_corrupt` on subsequent reads. Returning bytes that failed their own checksum to a trainer reviewing a clinical error would be the worst possible failure of this endpoint.

Supports `Range` (single range only) so the debrief player can seek without downloading a whole utterance. `Content-Type` comes from `blobs.media_type`, and the response is `immutable`-cacheable because a content address cannot describe two byte strings.

### 4.9 `GET /api/scenarios`, `/{id}`, `/{id}/graph`

Read-only projections of the scenario bank. `?difficulty=1..5&specialty=…&skills=numeric_density,idiom&q=…` filters; `q` matches title and setting only, never the utterance corpus, because search over the corpus is a way to read the answer key.

`ClinicalGraph` returns nodes and edges with `speaker`, `intent`, `difficulty_features` — and **not** the scripted fallback line or the term manifest. The manifest is the extractors' ground truth (`docs/07-data-and-scenarios.md`); serving it to a browser that a trainee can open is handing over the answers mid-session. `?include=term_manifest` exists but is gated on `session.state == "complete"` and returns `403 seal_violation` otherwise.

### 4.10 `GET /api/learners/{id}` and `/skills`

```json
{
  "trainee_id": "kn",
  "created_ms": 1760000000000,
  "sessions_total": 41,
  "sessions_complete": 38,
  "difficulty": 3,
  "skills": [
    {"kind": "omission", "ewma_rate": 0.18, "n_observed": 204, "trend": "down",
     "interval_low": 0.13, "interval_high": 0.24, "updated_ms": 1770000000000},
    {"kind": "register_shift", "ewma_rate": null, "n_observed": 4, "trend": null,
     "interval_low": null, "interval_high": null, "updated_ms": 1769000000000}
  ]
}
```

`ewma_rate` is `null` below `min_observations` (default 10) rather than a number computed from four observations. A rate printed from four data points will be read as a fact about the trainee, and `docs/09-ui-ux.md` renders `null` as "not enough practice yet". `interval_*` is a Wilson interval on the underlying counts — the honest-reporting rule applies inside the API, not just in the eval reports.

### 4.11 `GET /api/health`, `/api/health/stream`, `/api/meta`

```json
{
  "status": "degraded",
  "hosts": {
    "live":   {"state": "ready",       "pid": 41022, "loaded_ms": 8412, "last_probe_ms": 1770000000000, "p95_ms": 780, "restarts": 0},
    "grader": {"state": "restarting",  "pid": null,  "loaded_ms": null, "last_probe_ms": 1769999998000, "p95_ms": 2610, "restarts": 1},
    "tts":    {"state": "ready",       "backend": "neural", "voices": ["en-US", "es-MX"]}
  },
  "store": {"db_ok": true, "wal_bytes": 2113536, "blob_root_writable": true, "free_bytes": 88123412480},
  "audio": {"capture_device": "MacBook Pro Microphone", "sample_rate": 16000},
  "live_session_id": "01J9F…",
  "degrade_level": "L2"
}
```

`status` is `ok | degraded | down`. `/api/health/stream` is the same object as SSE (`event: health`, ~1 Hz, `retry: 2000`) — SSE rather than WebSocket because health is a one-directional broadcast that must keep working when no session exists and therefore when no session socket does. `GET /api/meta` returns `{"api": 1, "build": "<git_commit>", "version": "<semver>", "schema_version": 7, "prompt_versions": {...}, "models": {...}}` and is the one endpoint guaranteed to answer while everything else is failing.

### 4.12 `GET /api/sessions/{id}/export`

Streams a `.tar.zst` of the redacted session record to the client (which is the only reason it is HTTP at all — the canonical export path writes to `~/.rehearsal/exports/` from the CLI). `?include_audio=false` is the default and flipping it to `true` requires the query parameter *and* `X-Rehearsal-Confirm-Audio: yes`, because exporting a trainee's voice is a different decision from exporting their scores. Redaction (trainee id → stable pseudonym) runs inside the stream, not as a post-step. Boundary B7 in `docs/03-system-architecture.md` §12 governs.

---

## 5. Real-time channel protocol

### 5.1 What the channel is

`/ws/session/{session_id}` is **a projection of the event log, not a second channel**. Every server message carries the `seq` of the event that produced it. Nothing exists in the browser that does not exist in the log. Consequences: a dropped socket degrades the UI and never the session; a reconnecting client asks for a gap by `seq` and is made whole; and a UI bug can be diagnosed by replaying the log, because the log is what the UI saw.

### 5.2 Envelope

```json
{"t": "turn.committed", "seq": 1184, "turn": 7, "ms": 1770000121340, "d": {...}}
```

| Field | Type | Meaning |
|---|---|---|
| `t` | string | Message type. For log-derived messages this is exactly the event `kind` (`docs/03-system-architecture.md` §10.2) |
| `seq` | int | Event `seq`. Strictly increasing per connection. `0` for transport-only frames (`hello`, `pong`, `gap.begin`) |
| `turn` | int \| null | Turn index; `null` for session-scoped messages |
| `ms` | int | Wall clock ms |
| `d` | object | Type-specific payload, schemas below |

The type set is the event-kind set plus five transport frames (`hello`, `gap.begin`, `gap.end`, `pong`, `error`). Adding a UI-only message type that is not an event kind is forbidden: it would create state the log cannot explain.

### 5.3 Server → client messages

| `t` | Emitted when | Key payload fields |
|---|---|---|
| `hello` | Immediately on accept | `session_id`, `state`, `event_seq`, `resumed_from`, `server_build` |
| `session.started` | Session enters a live state | `state`, `planned_turns` |
| `turn.opened` | A turn begins | `turn_index`, `speaker`, `direction`, `node_id`, `expects` |
| `source.emitted` | Counterpart utterance text is final | `text`, `lang`, `source_sha`, `char_len` |
| `tts.started` / `tts.finished` | Playback boundaries | `voice`, `est_duration_ms` / `actual_duration_ms` |
| `tts.interrupted` | Barge-in | `offset_ms`, `stopped_within_ms` |
| `capture.started` | Mic open, trainee's floor | `deadline_ms` |
| `partial.transcript` | Interim rendering hypothesis | `text`, `stability`, `is_final: false` |
| `capture.ended` | Endpoint detected | `duration_ms`, `audio_sha` |
| `turn.committed` | Rendering is final and durable | `turn_index`, `rendering_sha`, `text`, `rendering_src`, `partial` |
| `score.pending` | Scoring enqueued | `verdict_key`, `queue_depth` |
| `score.ready` | Verdict merged | full `Verdict` + `findings` |
| `score.partial` | Extractor-only verdict | `Verdict` with `status: "partial"`, `not_assessed` |
| `coach.emitted` | A hint is available | `text`, `kind`, `turn_index`, `priority` |
| `coach.suppressed` | A hint was dropped | `reason` (`load` \| `duplicate` \| `capture_active`) |
| `degraded.entered` / `degraded.exited` | Ladder movement | `level`, `trigger`, `human_reason` |
| `budget.exceeded` | A stage overran | `stage`, `budget_ms`, `actual_ms` |
| `host.restarted` | A model host bounced | `role`, `attempt`, `cold_ms` |
| `session.paused` / `session.resumed` | — | `reason` |
| `session.ended` | Terminal | `outcome`, `state`, `abort_reason`, `report_url`, `degrade_max`, `unscored_turn_indices` |
| `error` | Transport or command error | the §2.2 `ApiError` body |

Exact schemas for the six the frontend contract depends on most:

```jsonc
// t: "turn.opened"
{"turn_index": 7, "speaker": "clinician", "direction": "en->es",
 "node_id": "meds.dose_change", "expects": "rendering_es",
 "budget": {"capture_max_ms": 45000}}

// t: "partial.transcript"   — advisory only; never persisted, never scored
{"turn_index": 7, "text": "toma quinientos miligramos", "lang": "es",
 "stability": 0.62, "is_final": false, "since_capture_ms": 1840}

// t: "turn.committed"
{"turn_index": 7, "rendering_sha": "b21d77…4c1", "text": "Tome 500 mg cada ocho horas.",
 "lang": "es", "rendering_src": "live_verbatim", "audio_sha": "9e0aa3…812",
 "duration_ms": 4210, "partial": false, "empty": false}

// t: "score.ready"
{"turn_index": 6, "verdict_key": "5c1e…", "status": "complete",
 "n_critical": 1, "n_non_critical": 2, "extractor_ms": 38, "grader_ms": 2417,
 "not_assessed": [],
 "findings": [{"finding_id": 1841, "kind": "omission", "severity": "critical",
               "origin": "extractor", "extractor_name": "frequency",
               "src_start": 44, "src_end": 61, "span_start": null, "span_end": null,
               "confidence": 1.0, "note": "…"}]}

// t: "coach.emitted"
{"turn_index": 6, "kind": "omission", "priority": "high",
 "text": "The frequency — every eight hours — did not make it across.",
 "text_sha": "aa71…", "display_ms": 6000}

// t: "session.ended"
{"outcome": "completed", "state": "debrief", "abort_reason": null,
 "degrade_max": "L2", "turns_total": 18, "unscored_turn_indices": [17],
 "report_url": "/api/sessions/01J9F…/report"}
```

**`partial.transcript` is explicitly non-authoritative and is never written to the log** — it is the only message type whose `seq` may repeat, and it carries `is_final: false` on every instance. It exists so the trainee sees that the system is hearing them. Scoring uses the committed rendering only. A partial hypothesis scored as a rendering would manufacture omissions, which is the exact failure this product exists to detect.

### 5.4 Client → server messages

| `t` | Payload | Effect |
|---|---|---|
| `hello` | `{"last_seq": int \| null, "client_build": str}` | First frame; drives gap replay (§5.5) |
| `start` / `pause` / `resume` | `{}` | Same transitions as the HTTP endpoints |
| `abort` | `{"reason": "user"}` | Same as `POST /abort` |
| `ack` | `{"seq": int}` | Advances the client's delivery watermark (§5.6) |
| `ping` | `{}` | Answered with `pong`; app-level, independent of the WS control frame |
| `coach.dismiss` | `{"turn_index": int}` | UI acknowledgement; appends nothing to the log |

Commands are accepted on the socket **and** over HTTP, resolving to the same orchestrator calls, because the socket may be down exactly when the user most wants to abort. Both paths go through the same validator and the same transition table; there is no second code path.

### 5.5 Connect, resume and gap replay

```
client  ──► WS upgrade /ws/session/{id}
client  ──► {"t":"hello","d":{"last_seq":1183,"client_build":"a1b2c3d"}}
server  ──► {"t":"hello","seq":0,"d":{"state":"rendering_capturing","event_seq":1201,
                                      "resumed_from":1183,"server_build":"a1b2c3d"}}
server  ──► {"t":"gap.begin","seq":0,"d":{"from":1184,"to":1201}}
server  ──► … replayed events 1184…1201, in order …
server  ──► {"t":"gap.end","seq":1201,"d":{}}
server  ──► … live stream …
```

Rules: `last_seq: null` replays from the session's first event (a fresh tab gets the whole session). A gap larger than `ws_gap_max_events` (default 5000) is answered with `gap.begin` carrying `truncated: true` and the client is instructed to re-fetch `GET /api/sessions/{id}` and `/report` instead of streaming — a UI catch-up must not become a log scan that competes with the live session for the store. A `client_build` mismatch is delivered but flagged, and the SPA prompts a reload rather than the server refusing the connection: refusing to talk to a stale tab in the middle of a session is a worse outcome than a slightly wrong label.

### 5.6 Backpressure and delivery

One socket, one bounded outbound queue (`ws_send_queue_max`, default 256). If the queue fills, messages are dropped by class in a fixed order, and the client is told:

| Class | Behaviour under pressure |
|---|---|
| `partial.transcript` | Dropped first, silently, coalesced to latest |
| `coach.emitted` | Dropped second; a `coach.suppressed` with `reason: "load"` is enqueued in its place |
| `budget.exceeded`, health chatter | Dropped third |
| Everything else (turn, score, state, session) | **Never dropped.** If these cannot be enqueued, the connection is closed with `4290 backpressure` and the client reconnects and replays the gap |

Delivery is at-least-once with client-side dedupe on `seq`. `ack` advances a watermark used only for diagnostics and for trimming the per-connection replay buffer; it never gates the session, because the orchestrator must never wait on a browser.

### 5.7 Close codes

| Code | Meaning | Client action |
|---|---|---|
| `1000` | Session terminal, stream complete | Show the report |
| `4004` | Unknown `session_id` | Navigate away |
| `4009` | Another socket is already attached to this session (§9.2) | Show "open in another tab"; do not auto-retry |
| `4022` | Malformed frame | Log and reconnect once |
| `4290` | Backpressure close | Reconnect with `last_seq` |
| `4503` | Server shutting down | Reconnect with backoff, then fall back to HTTP polling |

Heartbeat: server sends a WS ping every 15 s and closes after two missed pongs. The app-level `ping`/`pong` exists in addition because intermediaries are not the concern here — a wedged event loop is, and a control-frame pong can be answered by a transport layer whose application above it is stuck.

---

## 6. Data model

### 6.1 Two databases, on purpose

| File | Owns | Written by | Lifetime |
|---|---|---|---|
| `~/.rehearsal/rehearsal.db` | The session record: events, projections, content, learner state | `rehearsal-api` only | The installation's life |
| `data/evals/registry.db` | `eval_runs`, `calibration_items` — the measurement record | CLI eval harness only (`docs/08-evals.md` §7) | Repo-relative, git-ignored |

They are separate because they have different writers, different lifetimes, different backup posture and different readers. Putting an append-only measurement registry in the same file as a live-session WAL means a session crash and a metric history share a blast radius, and it invites an HTTP endpoint that runs an eval (§3.6). The eval registry's DDL lives in `docs/08-evals.md` §7 and is **not** duplicated here; §6.9 states only the boundary.

### 6.2 The rule that shapes everything

**`events` and `blobs` are the truth. Every other table in `rehearsal.db` is a projection that can be dropped and rebuilt by `rehearsal replay --rebuild`.** Two practical consequences that a new engineer needs on day one:

1. A bug in a projection is fixed by fixing the fold and rebuilding — never by an `UPDATE`. There is no legitimate `UPDATE` against a projection table outside `src/rehearsal/store/projections.py`.
2. A new derived column is a schema migration plus a rebuild, not a backfill script. The data to compute it is already in the log.

### 6.3 Full DDL

```sql
-- ~/.rehearsal/rehearsal.db
-- Applied by src/rehearsal/store/db.py at startup; see §6.10 for migration mechanics.

PRAGMA journal_mode  = WAL;         -- one writer + many readers without blocking
PRAGMA foreign_keys  = ON;
PRAGMA synchronous   = NORMAL;      -- WAL + NORMAL: durable to process crash, see §13.3
PRAGMA busy_timeout  = 5000;
PRAGMA temp_store    = MEMORY;
PRAGMA mmap_size     = 268435456;

-- ─────────────────────────────────────────────────────────────────────────
-- TRUTH
-- ─────────────────────────────────────────────────────────────────────────

CREATE TABLE events (
  seq         INTEGER PRIMARY KEY AUTOINCREMENT,  -- global monotonic order
  session_id  TEXT    NOT NULL,
  turn_index  INTEGER,                            -- NULL for session-scoped events
  ts_ms       INTEGER NOT NULL,                   -- wall clock, ms since epoch
  mono_ms     INTEGER NOT NULL,                   -- monotonic; latency maths uses this one
  kind        TEXT    NOT NULL,
  payload     TEXT    NOT NULL,                   -- canonical JSON: sorted keys, no whitespace
  prev_hash   TEXT    NOT NULL,                   -- hash of the previous event in this session
  hash        TEXT    NOT NULL                    -- sha256(prev_hash || kind || canonical payload)
) STRICT;

CREATE INDEX        idx_events_session_seq ON events(session_id, seq);
CREATE INDEX        idx_events_kind        ON events(kind, seq);
CREATE INDEX        idx_events_turn        ON events(session_id, turn_index, seq)
                                           WHERE turn_index IS NOT NULL;
CREATE UNIQUE INDEX idx_events_hash        ON events(hash);

CREATE TRIGGER events_no_update BEFORE UPDATE ON events
BEGIN SELECT RAISE(ABORT, 'events is append-only'); END;

CREATE TRIGGER events_no_delete BEFORE DELETE ON events
BEGIN SELECT RAISE(ABORT, 'events is append-only'); END;

CREATE TABLE blobs (
  sha256      TEXT PRIMARY KEY,                   -- lowercase hex, 64 chars
  bytes       INTEGER NOT NULL CHECK (bytes >= 0),
  media_type  TEXT    NOT NULL,                   -- audio/opus | text/plain;charset=utf-8 | application/json
  role        TEXT    NOT NULL,                   -- rendering_audio | source_text | rendering_text
                                                  -- | grader_input | coach_text | export_manifest
  created_ms  INTEGER NOT NULL,
  quarantined INTEGER NOT NULL DEFAULT 0,         -- 1 = hash mismatch observed on read
  CHECK (length(sha256) = 64)
) STRICT;

CREATE INDEX idx_blobs_role_created ON blobs(role, created_ms);
CREATE INDEX idx_blobs_quarantined  ON blobs(quarantined) WHERE quarantined = 1;

-- ─────────────────────────────────────────────────────────────────────────
-- CONTENT (loaded from the scenario bank; rebuilt by `rehearsal content sync`)
-- ─────────────────────────────────────────────────────────────────────────

CREATE TABLE scenarios (
  scenario_id     TEXT PRIMARY KEY,
  version         TEXT    NOT NULL,               -- bank content version, e.g. 'v3'
  title           TEXT    NOT NULL,
  setting         TEXT    NOT NULL,               -- e.g. 'primary care follow-up'
  specialty       TEXT    NOT NULL,
  difficulty      INTEGER NOT NULL CHECK (difficulty BETWEEN 1 AND 5),
  est_turns       INTEGER NOT NULL CHECK (est_turns > 0),
  lang_a          TEXT    NOT NULL DEFAULT 'en-US',
  lang_b          TEXT    NOT NULL DEFAULT 'es-MX',
  skills_json     TEXT    NOT NULL,               -- ["numeric_density","idiom","emotional_register"]
  entry_node_id   TEXT    NOT NULL,
  manifest_sha    TEXT    NOT NULL REFERENCES blobs(sha256),  -- TermManifest, content-addressed
  source_ref      TEXT    NOT NULL DEFAULT '',    -- provenance; docs/07-data-and-scenarios.md
  licence         TEXT    NOT NULL DEFAULT '',
  content_sha     TEXT    NOT NULL,               -- hash of the whole scenario definition
  loaded_ms       INTEGER NOT NULL,
  retired         INTEGER NOT NULL DEFAULT 0
) STRICT;

CREATE INDEX idx_scenarios_difficulty ON scenarios(difficulty, retired);
CREATE INDEX idx_scenarios_specialty  ON scenarios(specialty, retired);

CREATE TABLE clinical_states (
  scenario_id     TEXT    NOT NULL REFERENCES scenarios(scenario_id) ON DELETE CASCADE,
  node_id         TEXT    NOT NULL,
  speaker         TEXT    NOT NULL CHECK (speaker IN ('clinician','patient')),
  intent          TEXT    NOT NULL,               -- 'meds.dose_change', 'hx.onset', …
  persona_json    TEXT    NOT NULL,               -- invariants the agent must not violate
  facts_json      TEXT    NOT NULL,               -- required clinical facts for this node
  fallback_sha    TEXT        REFERENCES blobs(sha256),   -- scripted line, used only on agent failure
  features_json   TEXT    NOT NULL,               -- difficulty features this node exercises
  terminal        INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (scenario_id, node_id)
) STRICT;

CREATE TABLE clinical_edges (
  scenario_id     TEXT    NOT NULL,
  from_node_id    TEXT    NOT NULL,
  to_node_id      TEXT    NOT NULL,
  weight          REAL    NOT NULL DEFAULT 1.0 CHECK (weight > 0),
  guard_json      TEXT    NOT NULL DEFAULT '{}',  -- conditions on accumulated facts
  PRIMARY KEY (scenario_id, from_node_id, to_node_id),
  FOREIGN KEY (scenario_id, from_node_id) REFERENCES clinical_states(scenario_id, node_id) ON DELETE CASCADE,
  FOREIGN KEY (scenario_id, to_node_id)   REFERENCES clinical_states(scenario_id, node_id) ON DELETE CASCADE
) STRICT;

CREATE INDEX idx_clinical_edges_from ON clinical_edges(scenario_id, from_node_id);

-- ─────────────────────────────────────────────────────────────────────────
-- LEARNERS
-- ─────────────────────────────────────────────────────────────────────────

CREATE TABLE learners (
  trainee_id      TEXT PRIMARY KEY,               -- local slug; never an email, never a name
  display_name    TEXT    NOT NULL DEFAULT '',    -- local-only, excluded from every export
  created_ms      INTEGER NOT NULL,
  difficulty      INTEGER NOT NULL DEFAULT 2 CHECK (difficulty BETWEEN 1 AND 5),
  langs_json      TEXT    NOT NULL DEFAULT '["en-US","es-MX"]',
  training_hours  INTEGER,                        -- self-reported; context only, never scored on
  notes           TEXT    NOT NULL DEFAULT ''
) STRICT;

CREATE TABLE skill_estimates (
  trainee_id      TEXT    NOT NULL REFERENCES learners(trainee_id) ON DELETE CASCADE,
  kind            TEXT    NOT NULL,               -- ErrorKind, or '__overall__'
  ewma_rate       REAL,                           -- NULL until n_observed >= min_observations
  n_observed      INTEGER NOT NULL DEFAULT 0,
  n_errors        INTEGER NOT NULL DEFAULT 0,
  n_critical      INTEGER NOT NULL DEFAULT 0,
  interval_low    REAL,
  interval_high   REAL,
  last_session_id TEXT    REFERENCES sessions(session_id),
  updated_ms      INTEGER NOT NULL,
  PRIMARY KEY (trainee_id, kind)
) STRICT;

-- ─────────────────────────────────────────────────────────────────────────
-- SESSION PROJECTIONS
-- ─────────────────────────────────────────────────────────────────────────

CREATE TABLE sessions (
  session_id     TEXT PRIMARY KEY,                -- ULID
  trainee_id     TEXT    NOT NULL REFERENCES learners(trainee_id),
  scenario_id    TEXT    NOT NULL REFERENCES scenarios(scenario_id),
  root_seed      INTEGER NOT NULL,
  state          TEXT    NOT NULL,                -- SessionState, docs/03-system-architecture.md §8
  difficulty     INTEGER NOT NULL,
  max_turns      INTEGER NOT NULL,
  text_mode      INTEGER NOT NULL DEFAULT 0,
  degrade_max    INTEGER NOT NULL DEFAULT 0,      -- 0..5, the WORST level reached
  degrade_reason TEXT,
  started_ms     INTEGER,
  ended_ms       INTEGER,
  abort_reason   TEXT,                            -- user|audio_device|host_unavailable|store_full|degrade_floor
  live_model     TEXT,                            -- resolved model id + quantisation
  grader_model   TEXT,
  runtime        TEXT,                            -- 'mlx 0.x' | 'llama.cpp <build>'
  prompt_ver     TEXT    NOT NULL,                -- grader prompt version, docs/06-scoring-engine.md
  schema_version INTEGER NOT NULL,
  build_commit   TEXT    NOT NULL,
  last_seq       INTEGER NOT NULL DEFAULT 0,      -- highest event seq folded into this row
  review_state   TEXT    NOT NULL DEFAULT 'none'  -- none | open | signed
) STRICT;

CREATE INDEX idx_sessions_trainee ON sessions(trainee_id, started_ms DESC);
CREATE INDEX idx_sessions_state   ON sessions(state);
CREATE UNIQUE INDEX idx_sessions_one_live ON sessions(state)
  WHERE state IN ('configuring','armed','source_speaking','awaiting_rendering',
                  'rendering_capturing','turn_closing','paused','recovering');

CREATE TABLE turns (
  session_id     TEXT    NOT NULL REFERENCES sessions(session_id),
  turn_index     INTEGER NOT NULL CHECK (turn_index >= 0),
  speaker        TEXT    NOT NULL CHECK (speaker IN ('clinician','patient')),
  direction      TEXT    NOT NULL CHECK (direction IN ('en->es','es->en')),
  node_id        TEXT    NOT NULL,
  seed           INTEGER NOT NULL,
  source_sha     TEXT    NOT NULL REFERENCES blobs(sha256),
  rendering_sha  TEXT        REFERENCES blobs(sha256),   -- NULL if empty or abandoned
  audio_sha      TEXT        REFERENCES blobs(sha256),
  rendering_src  TEXT    NOT NULL DEFAULT 'live_verbatim',  -- | offpath_retranscribe | typed
  partial        INTEGER NOT NULL DEFAULT 0,
  abandoned      INTEGER NOT NULL DEFAULT 0,
  opened_ms      INTEGER NOT NULL,
  committed_ms   INTEGER,
  capture_ms     INTEGER,                         -- trainee speaking duration
  degrade_level  INTEGER NOT NULL DEFAULT 0,      -- level in force for THIS turn
  PRIMARY KEY (session_id, turn_index)
) STRICT;
-- node_id deliberately has NO foreign key to clinical_states: a scenario may be
-- retired or re-versioned while historical sessions still reference its nodes, and
-- a historical session must never become unreadable because content moved on.
-- It is validated against the bound scenario's content_sha at fold time instead.

CREATE INDEX idx_turns_node ON turns(node_id);

CREATE TABLE utterances (
  utterance_id   INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id     TEXT    NOT NULL,
  turn_index     INTEGER NOT NULL,
  role           TEXT    NOT NULL CHECK (role IN ('source','rendering','coach')),
  lang           TEXT    NOT NULL,                -- 'en-US' | 'es-MX'
  text_sha       TEXT    NOT NULL REFERENCES blobs(sha256),
  audio_sha      TEXT        REFERENCES blobs(sha256),
  char_len       INTEGER NOT NULL,
  token_len      INTEGER,
  tts_voice      TEXT,                            -- NULL for trainee renderings
  tts_started_ms INTEGER, tts_ended_ms INTEGER,
  capture_started_ms INTEGER, capture_ended_ms INTEGER,
  interrupted_at_ms  INTEGER,                     -- barge-in offset, NULL if not interrupted
  is_final       INTEGER NOT NULL DEFAULT 1,      -- always 1; partial hypotheses are never stored
  UNIQUE (session_id, turn_index, role),
  FOREIGN KEY (session_id, turn_index) REFERENCES turns(session_id, turn_index) ON DELETE CASCADE
) STRICT;

CREATE INDEX idx_utterances_text ON utterances(text_sha);

CREATE TABLE verdicts (
  verdict_key    TEXT PRIMARY KEY,                -- sha256(prompt_ver|grader_model|source_sha|rendering_sha)
  session_id     TEXT    NOT NULL,
  turn_index     INTEGER NOT NULL,
  status         TEXT    NOT NULL CHECK (status IN ('complete','partial','grader_unavailable')),
  not_assessed   TEXT    NOT NULL DEFAULT '[]',   -- JSON array of ErrorKind not evaluated
  n_critical     INTEGER NOT NULL DEFAULT 0,
  n_non_critical INTEGER NOT NULL DEFAULT 0,
  extractor_ms   INTEGER NOT NULL,
  grader_ms      INTEGER,
  grader_model   TEXT    NOT NULL,
  prompt_ver     TEXT    NOT NULL,
  grader_input_sha TEXT      REFERENCES blobs(sha256),  -- the exact assembled context
  superseded_by  TEXT        REFERENCES verdicts(verdict_key),  -- set by --rescore, never overwritten
  created_ms     INTEGER NOT NULL,
  FOREIGN KEY (session_id, turn_index) REFERENCES turns(session_id, turn_index)
) STRICT;

CREATE INDEX idx_verdicts_turn    ON verdicts(session_id, turn_index, created_ms);
CREATE INDEX idx_verdicts_prompt  ON verdicts(prompt_ver, grader_model);

CREATE TABLE findings (
  finding_id     INTEGER PRIMARY KEY AUTOINCREMENT,
  verdict_key    TEXT    NOT NULL REFERENCES verdicts(verdict_key) ON DELETE CASCADE,
  kind           TEXT    NOT NULL CHECK (kind IN (
                    'omission','addition','substitution','distortion','editorialization',
                    'role_exchange','register_shift','false_fluency','first_person_violation')),
  severity       TEXT    NOT NULL CHECK (severity IN ('critical','non_critical')),
  origin         TEXT    NOT NULL CHECK (origin IN ('extractor','grader')),
  extractor_name TEXT,                            -- numbers|dosage|frequency|negation|laterality|allergy|temporal
  src_start      INTEGER, src_end   INTEGER,      -- offsets into the SOURCE text
  span_start     INTEGER, span_end  INTEGER,      -- offsets into the RENDERING text
  confidence     REAL CHECK (confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)),
  overruled      INTEGER NOT NULL DEFAULT 0,      -- derived from reviews; never hand-set
  note           TEXT    NOT NULL DEFAULT '',
  CHECK (origin <> 'extractor' OR extractor_name IS NOT NULL),
  CHECK (src_start IS NOT NULL OR span_start IS NOT NULL)
) STRICT;

CREATE INDEX idx_findings_verdict  ON findings(verdict_key);
CREATE INDEX idx_findings_kind_sev ON findings(kind, severity);

CREATE TABLE reviews (
  review_id      INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id     TEXT    NOT NULL REFERENCES sessions(session_id),
  finding_id     INTEGER     REFERENCES findings(finding_id),  -- NULL = session-level note
  turn_index     INTEGER,                          -- required when action = 'add'
  action         TEXT    NOT NULL CHECK (action IN ('agree','reject','reclassify','add')),
  new_kind       TEXT, new_severity TEXT,
  src_start      INTEGER, src_end   INTEGER,
  span_start     INTEGER, span_end  INTEGER,
  reviewer       TEXT    NOT NULL,                 -- 'trainee' | 'trainer:<id>'
  rationale      TEXT    NOT NULL DEFAULT '',
  event_seq      INTEGER NOT NULL,                 -- the review.override event that produced this row
  created_ms     INTEGER NOT NULL,
  CHECK (action <> 'agree' OR (new_kind IS NULL AND new_severity IS NULL)),
  CHECK (action NOT IN ('reclassify','add') OR new_kind IS NOT NULL),
  CHECK (action <> 'add' OR turn_index IS NOT NULL)
) STRICT;

CREATE INDEX idx_reviews_session ON reviews(session_id, created_ms);
CREATE INDEX idx_reviews_finding ON reviews(finding_id);

-- ─────────────────────────────────────────────────────────────────────────
-- STORE METADATA
-- ─────────────────────────────────────────────────────────────────────────

CREATE TABLE schema_migrations (
  version     INTEGER PRIMARY KEY,
  name        TEXT    NOT NULL,
  applied_ms  INTEGER NOT NULL,
  sql_sha256  TEXT    NOT NULL                     -- detects an edited migration file
) STRICT;

CREATE TABLE idempotency_keys (
  key          TEXT PRIMARY KEY,                   -- client-supplied ULID
  route        TEXT    NOT NULL,
  request_sha  TEXT    NOT NULL,                   -- sha256 of the canonical request body
  status       INTEGER NOT NULL,
  response_json TEXT   NOT NULL,
  created_ms   INTEGER NOT NULL
) STRICT;

CREATE INDEX idx_idem_created ON idempotency_keys(created_ms);
```

### 6.4 Index rationale

Indexes are justified by a named query, not added on suspicion. Every index below exists because a specific read path would otherwise scan.

| Index | Query it serves |
|---|---|
| `idx_events_session_seq` | `fold(events)` on resume and replay — the hottest read in the system |
| `idx_events_kind` | `rehearsal replay --rescore` selecting `rendering.emitted`; eval extraction |
| `idx_events_turn` | Debrief drill-down: every event for one turn |
| `idx_events_hash` | Chain verification; also makes a duplicated append a constraint error rather than a silent second row |
| `idx_sessions_one_live` | **A partial unique index that makes "one live session" a database invariant** (§9.1), not an application convention |
| `idx_sessions_trainee` | Learner history, descending by start |
| `idx_verdicts_turn` | Report assembly; also orders re-scored verdicts for the same turn |
| `idx_verdicts_prompt` | Before/after comparison across prompt versions without a rerun |
| `idx_findings_kind_sev` | Skill-estimate rebuild and per-category aggregation |
| `idx_blobs_quarantined` | `rehearsal doctor` corruption sweep; partial index, near-zero cost |
| `idx_utterances_text` | "Which turns used this exact source string?" — the query behind cross-session grader comparison |

### 6.5 Foreign-key map

```
learners ──< sessions >── scenarios ──< clinical_states ──< clinical_edges
                │                          │
                ├──< turns ────────────────┘ (node_id, validated at fold time)
                │      ├──< utterances
                │      └──< verdicts ──< findings ──< reviews
                ├──< reviews (session-level notes)
                └──< skill_estimates.last_session_id

blobs ◄── turns.source_sha / rendering_sha / audio_sha
      ◄── utterances.text_sha / audio_sha
      ◄── verdicts.grader_input_sha
      ◄── scenarios.manifest_sha
      ◄── clinical_states.fallback_sha
```

`ON DELETE CASCADE` appears only where the parent is itself rebuildable content (`scenarios → clinical_states`) or strictly derived (`verdicts → findings`, `turns → utterances`). It never appears on a path from `sessions`, because no code path deletes a session. `blobs` is referenced but never cascaded from: reclamation is mark-and-sweep in `rehearsal gc`, and a foreign key that could delete a trainee's audio as a side effect of a projection rebuild would be a data-loss bug wearing a constraint's clothing.

### 6.6 Where the `turns`/`utterances` split comes from

`turns` carries the *plan and the pointers* — what was supposed to happen on this turn and which blobs it resolved to. `utterances` carries the *per-utterance record* — timings, voice, language, lengths, barge-in offset — for each of the up-to-three utterances a turn contains (source, rendering, coach).

The sha columns on `turns` are therefore denormalised copies of `utterances.text_sha` / `audio_sha`. That redundancy is accepted deliberately, and it is safe for a specific structural reason: **both tables are projections of the same events, rebuilt by the same fold.** They cannot drift, because neither is ever written independently. The payoff is that the report query and the resume fold — the two reads that matter — need no join to answer "what were the two strings for turn 7", which is the question the entire scoring plane is built around.

### 6.7 Rationale for content-addressed storage

Audio and canonical text live at `~/.rehearsal/blobs/sha256/ab/cd/<sha256>.<ext>` with a sibling `.meta.json`. `blobs` is the index; the filesystem is the store. The reasons, in the order they actually mattered:

| Reason | What it buys |
|---|---|
| **A published number is provably about specific bytes** | `verdicts.verdict_key` is derived from `source_sha` and `rendering_sha`. A re-score is provably a comparison of the same two strings under a different prompt. No later transcript edit can silently change what a reported κ was computed over |
| **Deduplication is free and exact** | The same source utterance recurs across sessions and across the calibration set. One blob, many references — and `idx_utterances_text` turns that duplication into a useful query rather than waste |
| **Writes are idempotent by construction** | A crash mid-write is recovered by re-writing; a write to an existing path is a *verified no-op*, not an overwrite. This is what makes turn persistence safe to retry (§13.2) |
| **Corruption is detectable, not silent** | The read path hashes while streaming. A mismatch quarantines rather than serves. A trainer reviewing a critical dosage error must never be shown bytes that failed their own checksum |
| **Immutability is enforced by the address** | There is no "update this blob" operation to misuse. Changing the content changes the name |
| **Cheap cache semantics** | `Cache-Control: immutable` on `/api/blobs/{sha}` is correct by definition, so the debrief player re-seeks without re-fetching |

**What is deliberately not stored [decided]:** synthesised TTS audio. It is the bulk of the bytes and it is regenerable from the source text plus the recorded voice id, both of which are in the log. **What is deliberately not content-addressed:** nothing that is stored. Text is content-addressed too, and that is the unusual choice — it costs a hash per utterance (microseconds) and buys the first row of that table, which is the project's credibility.

**Cost, stated:** an extra indirection on every read, a `gc` command that must exist and must be conservative, and the fact that "delete this trainee's audio" is a sweep rather than a `DELETE`. Accepted. The retention and deletion story is `docs/12-security-privacy.md`.

### 6.8 Projection rebuild contract

```python
# src/rehearsal/store/projections.py

PROJECTION_TABLES: Final = (
    "sessions", "turns", "utterances", "verdicts", "findings",
    "reviews", "skill_estimates",
)

def rebuild(conn: sqlite3.Connection, session_id: SessionId | None = None) -> RebuildReport:
    """Drop and regenerate projections from `events`. Idempotent.

    session_id=None rebuilds everything. Runs in ONE transaction; a failure
    leaves the previous projections intact. Never touches `events` or `blobs`.
    """

def verify(conn: sqlite3.Connection, session_id: SessionId) -> list[Divergence]:
    """Rebuild into a temp schema and diff against live projections.

    Backs `rehearsal replay --verify`. A non-empty result is a fold bug, and
    it is reported as a divergence list, not a boolean.
    """
```

`scenarios`, `clinical_states` and `clinical_edges` are *content*, not projections of the event log — they are rebuilt from the scenario bank by `rehearsal content sync`, and their `content_sha` is what a session records so that a retired or edited scenario cannot silently change the meaning of a historical session.

### 6.9 The eval boundary: `eval_runs` and `calibration_items`

`eval_runs` is defined in `docs/08-evals.md` §7 and lives in `data/evals/registry.db`. It is append-only, enforced by triggers, and the API server neither reads nor writes it. `calibration_items` lives in the same database as a **read-only index** over the authoritative files:

```sql
-- data/evals/registry.db — index only; data/calibration/{dev,test}.jsonl is authoritative
CREATE TABLE calibration_items (
  item_id       TEXT PRIMARY KEY,                  -- 'CAL-017'
  split         TEXT NOT NULL CHECK (split IN ('dev','test')),
  bucket        TEXT NOT NULL,                     -- clean|critical|non_critical|multi|ambiguous
  direction     TEXT NOT NULL,
  source_sha    TEXT NOT NULL,
  rendering_sha TEXT NOT NULL,
  n_labels      INTEGER NOT NULL,
  n_critical    INTEGER NOT NULL,
  confidence    TEXT NOT NULL CHECK (confidence IN ('sure','unsure')),
  file_sha256   TEXT NOT NULL,                     -- hash of the JSONL the row was indexed from
  indexed_at    TEXT NOT NULL
) STRICT;

CREATE INDEX idx_calibration_split ON calibration_items(split, bucket);
```

The labels themselves are **not** in the table — only the item's shape. Two reasons, both from `SETUP.md` §6: the JSONL files are the frozen artefact with their own `CHANGELOG.md`, and a queryable table of gold labels beside the grader is one convenience function away from a leak into the thing being measured. `file_sha256` is the tamper check: an index whose hash no longer matches the file is refused, not silently refreshed. Reading rows where `split = 'test'` requires an `unseal_reason`, enforced in `src/rehearsal/evals/seal.py`, not by convention.

### 6.10 Migrations

Numbered SQL files in `src/rehearsal/store/migrations/NNNN_name.sql`, applied in order inside one transaction at startup, recorded in `schema_migrations` with the file's sha256. An already-applied migration whose file hash changed is a hard startup failure — an edited migration means two installations have different schemas under the same version number.

| Rule | Reason |
|---|---|
| Migrations never rewrite `events` | It is the truth and it is hash-chained; rewriting it invalidates every chain |
| Projection changes are `DROP` + rebuild, not `ALTER` + backfill | The data to recompute is in the log; a backfill script is a second, weaker fold |
| A migration that would lose data refuses to run without `REHEARSAL_ALLOW_LOSSY_MIGRATION=1` | One-way door; `docs/13-deployment-ops.md` owns the rollback plan |
| The DB is backed up (`rehearsal.db` + `-wal` copy via `VACUUM INTO`) before any migration | Rollback is restore, not reverse-migrate. No down-migrations exist |

---

## 7. The event log and replay

### 7.1 Append

```python
# src/rehearsal/store/events.py

class EventLog:
    def append(self, session_id: SessionId, kind: EventKind,
               payload: Mapping[str, JsonValue], *, turn_index: int | None = None) -> Event:
        """Append one event. Serialised by the store write lock (§9.3).

        Payload is canonicalised (sorted keys, no whitespace, UTF-8) BEFORE hashing,
        so the hash is a function of the meaning, not of dict ordering.
        Raises StoreUnwritable; the caller pauses the session rather than continuing
        unlogged — an unlogged session is a failure, not a session.
        """

    def iter(self, session_id: SessionId, *, after: int = 0) -> Iterator[Event]: ...
    def verify_chain(self, session_id: SessionId) -> ChainReport: ...
```

The chain is `hash = sha256(prev_hash || kind || canonical_payload)`, one hash per append, microseconds each. It buys tamper-evidence: any reported number traces to a specific chain, and a silently edited record is detectable by `rehearsal replay --verify`. Given that the product's entire credibility is the honesty of its measurements, that is not over-engineering — it is the cheapest available proof that the record was not adjusted after the fact.

### 7.2 Replay

```bash
rehearsal replay <session_id>              # reconstruct the session record from events
rehearsal replay <session_id> --rebuild    # drop and regenerate all projections
rehearsal replay <session_id> --rescore    # re-run scoring under the current grader version
rehearsal replay <session_id> --verify     # fresh fold vs recorded; report divergence
```

Replay is a **pure fold**: `fold(events) -> SessionView` performs no I/O beyond the log read, calls no model, and touches no clock. That purity is what makes it testable and what makes crash recovery (§13.2) the same code path as replay rather than a parallel implementation nobody exercises.

`--rescore` writes **new** verdict rows (a different `prompt_ver` yields a different `verdict_key`) and sets `superseded_by` on the old one. Nothing is overwritten, so a before/after comparison across prompt versions is a `SELECT`, not a rerun — which is precisely the mechanism L10 prompt optimisation depends on. Live sessions with humans in them are never re-run to evaluate a prompt change.

`--verify` reports the **divergence rate**, not a pass/fail, because identical seeds guarantee identical *inputs*, not bit-identical model outputs on Metal. The project claims input-level reproducibility and measures output stability separately (`docs/03-system-architecture.md` §6.3).

### 7.3 What a replay reconstructs, and what it cannot

| Reconstructed exactly | Not reconstructed |
|---|---|
| Every prompt, every seed, every parameter, every turn plan | Wall-clock interleaving of audio at the sample level |
| Both canonical strings per turn, byte-identical (blob-addressed) | Synthesised TTS audio (regenerable, not stored) |
| Every verdict and finding, with the grader input that produced it | The trainee's live experience of latency |
| Every human review and its rationale | Model output bit-identity across runs (measured, not claimed) |

---

## 8. Concurrency and session isolation

### 8.1 One live session, enforced in three places

| Layer | Mechanism |
|---|---|
| Database | `idx_sessions_one_live`, a partial unique index over live states. A second live session is a constraint violation, not a race |
| Process | An `asyncio.Lock` around session creation and start, held for the whole precondition check |
| Filesystem | `~/.rehearsal/run/api.pid` with an exclusive `flock`, so a second `rehearsal up` fails loudly instead of two processes sharing a WAL |

The database invariant is the one that matters. The other two produce better error messages; only the index makes the property true under a crash-restart race.

**Why one, not N [decided]:** two live sessions would contend for the same ~20–24 GB of resident model memory on a 48 GB machine, and the latency budget in `docs/05-voice-pipeline.md` is written for a machine with one conversational loop on it. Two sessions would not be twice as useful; they would be two sessions that both stutter, and stutter in a voice loop is indistinguishable from the trainee's own hesitation, which corrupts the measurement.

### 8.2 One socket per session

A second WebSocket for a session that already has one is closed with `4009`. Rationale: two attached tabs both showing "your turn to interpret" is a UI that lies about whose floor it is, and the mic belongs to the machine, not to the tab. The second tab is told explicitly and offered a read-only report view.

`GET` endpoints are unrestricted and concurrent — a trainer reading a past report while a session runs is a normal, supported thing.

### 8.3 Store concurrency

WAL gives one writer and many concurrent readers. The concrete rules:

| Rule | Detail |
|---|---|
| Single writer connection | One `sqlite3.Connection` in write mode, owned by the store, guarded by an `asyncio.Lock`. All appends and projection updates go through it |
| Reader pool | Read-only connections (`mode=ro`), one per worker thread, for report and history queries |
| Writes are off the event loop | `asyncio.to_thread` — an `fsync` on the loop thread is a voice-loop stutter |
| Transaction granularity | One transaction per event append **plus** its projection update. A projection that lags its event by a crash boundary is exactly the case rebuild exists for, but keeping them atomic means the common case never needs it |
| `busy_timeout` 5000 ms | A reader blocking a write for 5 s is a bug worth surfacing, not worth waiting out |
| Long reads | Report assembly and `gc` mark phases run in `BEGIN DEFERRED` read transactions and are chunked so they never hold a snapshot across a turn boundary |

### 8.4 Task isolation inside the process

Three `asyncio` task groups with different failure semantics — the separation exists so a scoring failure cannot end a session:

| Group | Contains | On unhandled exception |
|---|---|---|
| `session` | Orchestrator, audio I/O, TTS, live agent calls | Session → `failed`, log appended with a traceback **digest** |
| `scoring` | Extractors, grader calls, merge, learner update | Verdict → `grader_unavailable`, degrade to L2, **session continues** |
| `serving` | HTTP handlers, WS hub, health SSE | Connection closed; session untouched |

Scoring runs off the critical path by construction (principle 5), so its failure is a degradation, never an abort. The grader call itself runs in a bounded worker with a hard `grader_wall_ms` deadline; exceeding it sheds the verdict rather than blocking the next turn.

### 8.5 Self-protection caps

Not rate limiting in the security sense — there is no adversary on loopback — but bounds that stop a runaway client from starving the session:

| Cap | Default | On breach |
|---|---|---|
| Concurrent report assemblies | 2 | `429 rate_capped`, retriable |
| `GET /api/sessions/{id}/events` page size | 500 | `422 schema_invalid` |
| WS outbound queue | 256 | Class-based shedding, then `4290` (§5.6) |
| Blob read concurrency | 4 | Queued, not rejected |
| Idempotency key retention | 24 h | Swept at startup |

---

## 9. Model process management and warm-up

### 9.1 Supervision

`rehearsal-api` supervises `rehearsal-live` and `rehearsal-grader` as child processes over UNIX sockets (`~/.rehearsal/run/live.sock`, `grader.sock`). Topology and the justification for separate processes are in `docs/03-system-architecture.md` §13.1; the contract is here.

```python
# src/rehearsal/runtime/hosts.py

class ModelHostClient:
    role: Literal["live", "grader"]

    async def spawn(self) -> None: ...
    async def probe(self, *, timeout_ms: int = 2000) -> HostHealth: ...
    async def warmup(self) -> WarmupReport: ...
    async def call(self, req: HostRequest, *, deadline_ms: int) -> HostResponse: ...
    async def terminate(self, *, grace_ms: int = 3000) -> None: ...

class HostState(StrEnum):
    SPAWNING = "spawning"; LOADING = "loading"; WARMING = "warming"
    READY = "ready"; DEGRADED = "degraded"; RESTARTING = "restarting"; DEAD = "dead"
```

### 9.2 Warm-up, and why it is not optional

A cold model's first inference is dominated by weight paging and kernel compilation. Measured on the target class of machine that is seconds, against a `source_generation_ms` budget of 900 ms. If the first turn of a session pays that cost, the trainee's first impression of the product is a stall, and the first turn's latency data is unusable.

Warm-up therefore runs before a session can reach `armed`:

| Step | Live host | Grader host |
|---|---|---|
| 1 | Load weights, report `loading` | Load weights |
| 2 | One tiny generation (≤ 8 tokens) per language, fixed prompt, temperature 0 | One structured grading call over a **fixture** pair from `tests/fixtures/`, never a calibration item |
| 3 | One native-audio call over a 0.5 s silent PCM buffer, exercising the audio path | — |
| 4 | Record `cold_ms`, transition to `ready` | Record `cold_ms`, transition to `ready` |

The grader warms on a fixture and never on a calibration item, because a warm-up that touched `data/calibration/test.jsonl` would be an unlogged read of the sealed split. `POST /api/hosts/{role}/warmup` re-runs this on demand; `rehearsal doctor` runs it and additionally writes the measured budget override to `~/.rehearsal/budget.local.json`.

### 9.3 Restart policy

| Host | Policy | Session impact |
|---|---|---|
| `live` | Auto-restart **once per session**; a second failure aborts with `host_unavailable` | The turn in flight is marked `abandoned`, its partial audio kept and never scored |
| `grader` | Auto-restart with backoff (1 s, 4 s, 15 s), unlimited; may be killed deliberately under memory pressure | Degrade to L2, verdicts `partial`, semantic categories reported *not assessed*. **The session continues** |

Every restart appends `host.restarted` with `role`, `attempt` and `cold_ms`, and surfaces on the WS. Nothing degrades silently: a trainee who does not know the grader was shed will read a clean score as a clean performance.

**Memory-pressure policy.** Under macOS memory pressure the grader is the designated victim — it is off the critical path and its work is re-runnable from the log. The live host is never killed while a session is live; if it cannot be kept resident, the session aborts, because a conversational agent that pauses for a reload has already broken the encounter it was simulating.

### 9.4 Call discipline

Every host call carries an explicit deadline derived from `TurnBudget`, returns a **validated schema instance** or raises, and is retried at most once and only for transport-class failures (socket closed, host restarting). A schema-invalid model response is never retried into a different answer without recording both attempts — the raw response is written as a blob and referenced from `grader.failed`, because a grader that silently succeeded on the second try is a grader whose error rate is unmeasurable. Boundary B5 applies: model output never becomes a state transition or a write without passing validation.

---

## 10. Configuration and feature flags

### 10.1 Precedence

```
defaults in src/rehearsal/config.py
  ← ~/.rehearsal/config.toml          (user, persistent)
  ← ~/.rehearsal/budget.local.json    (machine-measured, written by `rehearsal doctor`)
  ← REHEARSAL_* environment variables (SETUP.md §3)
  ← SessionCreateRequest fields       (per-session, recorded in the log)
```

Later wins. Every layer that contributed is reported by `GET /api/config`, with provenance per key, so "why is this machine behaving differently" is a read rather than an investigation.

```json
{
  "schema_version": 7,
  "values": {
    "grader_wall_ms":   {"value": 3500, "source": "budget.local.json"},
    "capture_max_ms":   {"value": 45000, "source": "default"},
    "tts_backend":      {"value": "neural", "source": "env:REHEARSAL_TTS_BACKEND"},
    "degrade_floor":    {"value": "L4", "source": "config.toml"}
  },
  "flags": {"coach_enabled": true, "offpath_retranscribe": false, "isolation_probe": false}
}
```

**The core product needs no secrets.** There is no credential in this configuration, no API key path, no token. `HF_TOKEN` exists only for first model download and `*_API_KEY` variables only for offline eval tooling (`SETUP.md` §3); neither is read by any module the session touches. `GET /api/config` is safe to render in a browser because there is nothing in it to leak — a property worth preserving deliberately, not by accident.

### 10.2 Feature flags

Flags are booleans in `config.toml` that gate behaviour whose effect on measured numbers must be attributable. Every flag's state is recorded in `session.created`, so a session's numbers can always be attributed to the configuration that produced them.

| Flag | Default | Effect | Removal condition |
|---|---|---|---|
| `coach_enabled` | `true` | Coach interjections during the session | Permanent — this is a product option, not a rollout gate |
| `offpath_retranscribe` | `false` | Second-pass transcription of trainee audio off the critical path, used when live-verbatim text is suspect. Sets `turns.rendering_src = 'offpath_retranscribe'` | When the A/B in `docs/08-evals.md` shows it changes agreement measurably, or shows it does not |
| `isolation_probe` | `false` | Runs the leakage A/B arm: the counterpart agent's context is deliberately given the rubric. **Test-only.** Sessions with it on are marked and excluded from every reported metric | Never — it is the L8 eval's mechanism |
| `strict_budget` | `false` | Treats any budget overshoot as a degrade trigger instead of a warning | When measured budgets stabilise on the target machine class |
| `hash_chain_verify_on_read` | `false` | Verifies the chain on every fold, not only under `--verify` | Stays off in normal use; ~O(n) hashing per session load |

**What is not a feature flag:** anything that changes what a number means without being visible in the record. There is no flag that turns off extractors, no flag that lowers the severity threshold, no flag that suppresses `not_assessed` reporting. A flag that could make a report look better while looking the same is not a flag, it is a hazard.

Flags are read once at session creation and frozen into `SessionConfig`. A flag flipped mid-session would produce a session whose first half and second half are not comparable, and nothing in the schema would record which turn the change landed on.

---

## 11. Deployment posture

`rehearsal up` starts three processes on one machine (`docs/03-system-architecture.md` §13). The API-specific facts:

| Aspect | Decision |
|---|---|
| Server | `uvicorn` with **one worker**. Multiple workers would mean multiple orchestrators, multiple write connections and a shared-nothing assumption that is false here |
| Bind | `127.0.0.1:8420`, asserted at startup. A middleware rejects any request whose client is not loopback with `403 not_loopback` — belt and braces against a future config edit |
| TLS | None. Loopback traffic does not leave the kernel; terminating TLS against a self-signed local certificate would add a trust-store problem and no security |
| Static assets | `frontend/dist` mounted at `/`, SPA fallback to `index.html`. No CDN, no external font or script — the CSP is `default-src 'self'` and a page that needs the network is a page that violates B4 |
| Reverse proxy | Unsupported. Putting this behind a proxy is putting it on a network, which is a different product |
| Shutdown | `SIGTERM` → refuse new sessions, append `session.paused` for a live one, flush the WAL, terminate hosts with grace, exit. A live session survives as a resumable log prefix |
| Logs | Structured JSONL at `~/.rehearsal/logs/`, droppable, rotated by size. **Never conflated with the event log.** Utterance text never appears in an app log |
| Backups | `rehearsal backup` → `VACUUM INTO` a timestamped copy plus a blob-root manifest. The user's own machine is the backup boundary |

---

## 12. Idempotency and crash recovery

### 12.1 Request idempotency

`POST /api/sessions`, `POST /api/reviews` and `POST /api/sessions/{id}/sign` accept `Idempotency-Key: <ULID>`. The server stores `(key, route, sha256(canonical body), status, response)` in `idempotency_keys`:

| Situation | Behaviour |
|---|---|
| Key unseen | Execute, store, return |
| Key seen, same body hash | Return the stored response verbatim, `200`/`201` as originally recorded |
| Key seen, different body hash | `409 idempotency_conflict` — the client reused a key for a different request, which is a client bug worth surfacing loudly |
| Key absent | Execute normally. The key is optional; the SPA always sends one |

Retention is 24 h, swept at startup. The lifecycle transitions (`/start`, `/pause`, `/abort`) need no key because they are idempotent by nature: the transition table rejects a repeat as `illegal_transition` or accepts it as a no-op, and neither outcome duplicates a fact.

### 12.2 Internal idempotency

Three keys carry the property where it actually matters, all of them derived from content rather than from a request:

| Key | Derivation | What it makes safe |
|---|---|---|
| `verdict_key` | `sha256(prompt_ver \| grader_model \| source_sha \| rendering_sha)` | A re-enqueued score after a crash is a cache hit, not a double write. Re-scoring is free and honest |
| Blob address | `sha256(bytes)` | A retried blob write is a verified no-op |
| Event `hash` | Chain hash, `UNIQUE` | A duplicated append is a constraint error, not a second row |

Together these mean the recovery path can simply *redo* work rather than reason about what it already did — which is why §12.3 is short.

### 12.3 Crash recovery

On startup, `rehearsal-api` finds sessions whose last event is not terminal and enters `recovering`. The rule that keeps this simple: **a turn boundary is the only resumable checkpoint.**

1. `fold(events) -> SessionView`. Pure, no I/O beyond the log read — the same function replay uses, so recovery is exercised by every replay test.
2. Last event is a durable-state event → resume there.
3. A turn was in flight (`turn.opened` with no close) → append `turn.abandoned`, re-open the same `turn_index` **with the same derived seed**, so the replayed turn is the turn that was planned, not a new one.
4. Partially captured audio is retained as a blob, referenced by the abandoned turn, marked `partial: true`, and **never scored**. A half-utterance scored as a whole one manufactures a fake omission — the exact failure this system exists to detect.
5. TTS for a completed turn is never re-played. Re-speaking a line the trainee already interpreted corrupts the encounter.
6. In-flight verdicts are re-enqueued; `verdict_key` makes the duplicate a cache hit.
7. If a projection row is missing for an event that exists, the session's projections are rebuilt before it is served. The log is ahead of the projection by at most one crash boundary, by design.

Durability: WAL + `synchronous = NORMAL` guarantees durability against **process** crash, which is the failure this system actually has. It does not guarantee durability against sudden power loss for the last transaction — accepted, stated here rather than discovered later. `synchronous = FULL` would put an `fsync` in every turn's persist budget (`persist_turn_ms = 50`) on a path the trainee can hear. The mitigation is that the lost tail is at most one turn and it is recoverable as an abandoned turn, not as a corrupt session.

Torn blob writes are handled by write-to-temp + `fsync` + atomic `rename`, so a blob is either absent or complete. An event referencing an absent blob is caught at fold time and marks the turn, rather than surfacing as a 500 on the report three days later.

---

## 13. API versioning policy

### 13.1 Paths are unversioned; the generation is a header

`/api/*` carries no version segment. `X-Rehearsal-Api: 1` and `GET /api/meta` report the generation.

**Why [decided].** The server and its only client ship in the same artifact and are installed together; `X-Rehearsal-Build` mismatch is detectable and the SPA prompts a reload. Path versioning exists to let a server support clients it cannot upgrade, and this server has no such client. Adding `/v1/` now would be scaffolding for a deployment shape that does not exist and, per §1, deliberately will not.

**The trigger that changes this [named, so it is a decision and not an oversight]:** the first time an independently-versioned consumer exists — a training-program tool reading exports over HTTP, or a second frontend — the generation moves into the path and both are served in parallel for one release. Until then, one generation.

### 13.2 What is and is not part of the contract

| Part of the contract | Not part of the contract |
|---|---|
| Endpoint paths and methods | Prose in `error.message` |
| Request field names, types, requiredness | Field ordering in JSON |
| Response field **presence** and types | Presence of *additional* response fields |
| `error.code` strings | HTTP status for a given code (may be corrected) |
| WS message `t` values and payload field names | WS message interleaving order across types |
| `seq` monotonicity per session | Absolute `seq` values across sessions |

### 13.3 Change classes

| Class | Examples | Handling |
|---|---|---|
| **Additive** | New optional request field, new response field, new WS message type, new `error.code` | Ship. Clients must tolerate unknown response fields and unknown `t` values (ignore-and-log) |
| **Behavioural** | A field's meaning changes; a status changes; a default moves | Requires a `CHANGELOG.md` entry and a `docs/17-decisions.md` record. Never silent |
| **Breaking** | Field removed or renamed, endpoint removed, `error.code` retired, WS payload field removed | Generation bump. Both generations served for one release; the retired one returns `410` with a pointer thereafter |

### 13.4 Schema versioning is separate from API versioning

`schema_version` (in `GET /api/meta` and on every `sessions` row) tracks the SQLite schema and moves with migrations. It is independent of the API generation: an internal projection change is invisible on the wire, and an API addition frequently needs no migration. Conflating them would force one to bump for the other's reasons, and then neither number would mean anything.

**Content and prompt versions are a third axis**, and they are the one that changes what a *number* means: `scenarios.version`, `scenarios.content_sha`, `verdicts.prompt_ver` and `verdicts.grader_model` are all recorded per row precisely so that a metric can never be compared across a change it did not know about. Three axes, three reasons, recorded separately.

---

## 14. Status register

| Item | Status | Note |
|---|---|---|
| Endpoint surface (§3, §4) | **Decided** | Extends `docs/03-system-architecture.md` §13.3 with report/turn/event/scenario/learner/system reads |
| Error envelope and code register (§2.2, §2.3) | **Decided** | `code` is contract, `message` is prose |
| WS protocol (§5) | **Decided** | Projection of the log; `partial.transcript` never persisted |
| `turns`/`utterances` split (§6.6) | **Decided** | Redundant sha columns accepted; both are folds of the same events |
| Content-addressed blobs (§6.7) | **Decided** | Text as well as audio |
| One live session as a DB invariant (§8.1) | **Decided** | Partial unique index, not an application convention |
| Unversioned paths + header generation (§13.1) | **Decided** | Trigger for change is named |
| `synchronous = NORMAL` (§12.3) | **Decided**, with stated limit | Power-loss tail of at most one turn |
| `offpath_retranscribe` | **Proposed** | Flag exists, default off, gated on an A/B that has not run |
| Wilson intervals on `skill_estimates` | **Proposed** | Interval method is right for counts; `min_observations = 10` is a judgement, not a measurement |
| Export archive format (`.tar.zst` + manifest) | **Proposed** | No consumer exists yet to constrain it |
| WS gap cap (`ws_gap_max_events = 5000`) | **Open** | Chosen to bound a catch-up read, not measured |
| Idempotency retention (24 h) | **Open** | No data on real retry windows |
| Blob GC retention floor | **Open** | Owned by `docs/12-security-privacy.md`; this document only guarantees GC never runs implicitly |

---

## 15. Cross-references

| Document | Relationship |
|---|---|
| `docs/03-system-architecture.md` | Session state machine, trust boundaries, process topology, event kinds. This document is its wire-format and DDL expansion |
| `docs/05-voice-pipeline.md` | Latency budget behind `TurnBudget`; audio capture and barge-in behind `capture.*` and `tts.interrupted` |
| `docs/06-scoring-engine.md` | What produces a `Verdict` and its `findings`; `verdict_key` semantics |
| `docs/07-data-and-scenarios.md` | What fills `scenarios`, `clinical_states`, `clinical_edges` and the term manifest |
| `docs/08-evals.md` | `eval_runs` DDL, the seal discipline, the A/Bs behind two feature flags |
| `docs/09-ui-ux.md` | What the report and skill payloads have to render, including `null` skill rates |
| `docs/10-frontend-spec.md` | The consumer of every schema here |
| `docs/12-security-privacy.md` | Retention, deletion, export redaction, threat model |
| `docs/13-deployment-ops.md` | Packaging, migration rollback, runbooks, observability without telemetry |
| `docs/14-testing-strategy.md` | Contract tests over this surface; fold/rebuild property tests |
| `SETUP.md` §3, §6 | Environment variables; the calibration protocol this document indexes but never duplicates |

# 03 — System Architecture

The end-to-end production architecture of Rehearsal: what the parts are, what each one is responsible for, what crosses between them, what never does, and how the whole thing behaves when something breaks.

This document is the contract between subsystems. It defines names, boundaries, schemas and state. It deliberately does **not** re-specify what other documents own:

| For | Read |
|---|---|
| Error taxonomy definitions and the professional standards behind them | `docs/01-research.md` |
| Audio capture, VAD, barge-in, TTS streaming, latency measurement method | `docs/05-voice-pipeline.md` |
| Extractor internals, rubric text, grader prompt, merge policy details | `docs/06-scoring-engine.md` |
| Scenario sources, licences, ingestion, the clinical state graph authoring format | `docs/07-data-and-scenarios.md` |
| Every eval number this architecture is obliged to produce | `docs/08-evals.md` |
| Calibration set protocol, dev/test split, human ceiling | `SETUP.md` §6 |

Status labels used throughout: **[decided]** (implement as written), **[proposed]** (default choice, cheap to change, no measurement yet), **[open]** (genuinely undecided, listed in §16).

---

## 1. What the architecture has to make true

Rehearsal is a real-time voice loop wrapped around an assessment instrument. Those two things have opposite requirements — the loop needs speed and improvisation, the instrument needs determinism and auditability — and almost every structural decision here exists to keep them apart without letting them drift out of sync.

The seven project principles bind to concrete mechanisms:

| # | Principle | Where it lives in this architecture |
|---|---|---|
| 1 | Model generates, deterministic code decides, human decides ultimately | Every model output is a typed schema instance; §7 `VerdictMerger` is the only thing that produces a score; §11 review gate is the only thing that closes a session record |
| 2 | Ground truth by construction | §9 content plane emits the source utterance *before* it is spoken; `source_sha` is recorded in the event log before the trainee hears it |
| 3 | Neuro-symbolic scoring | §7 splits the scoring plane into deterministic extractors (critical class) and one semantic model call (residue) |
| 4 | Information isolation | §12 `ContextAssembler` allowlists; `IsolationViolation` is a hard runtime error, not a warning |
| 5 | Grader off the critical path | §6 turn scheduler runs scoring for turn *N* concurrently with capture of turn *N+1*; the human's speaking time is the budget |
| 6 | Everything measured | Every component in §5 names the eval that covers it |
| 7 | Honest reporting | §10 event log makes every reported number reconstructable from raw events; degradation is always surfaced, never silent (§14) |

---

## 2. The four planes

The system is four planes with deliberately narrow couplings. A plane is a unit of *latency class and trust*, not a deployment unit — three of the four run inside one process.

| Plane | Latency class | Owns | Talks to |
|---|---|---|---|
| **Session runtime** | Hard real-time (sub-second, human-perceptible) | Audio in/out, the two counterpart agents, turn sequencing, the session state machine | Content plane (reads scenario), event log (appends), scoring plane (fire-and-forget enqueue) |
| **Scoring plane** | Soft real-time (one turn of slack, ~3.5 s) | Deterministic extractors, the single grader call, verdict merge | Event log (reads turn records, appends verdicts), learner plane (emits deltas) |
| **Learner-model plane** | Between-turn / between-session | Per-category performance state, coach message selection, difficulty pressure | Content plane (requests difficulty), scoring plane (consumes verdicts) |
| **Content / scenario plane** | Pre-session and per-turn, cheap | Scenario bank, clinical state graph, source utterance generation, terminology manifest | Runtime (serves next node), scoring plane (serves the term manifest for that scenario) |

### 2.1 The three couplings that matter

1. **Runtime → Scoring is asynchronous and lossy-tolerant.** The runtime enqueues a `ScoreRequest` and never awaits it. If the scoring plane is dead, the session continues and turns are marked `unscored`. A dead grader must never be able to stall a human mid-sentence.
2. **Learner → Runtime is one integer wide.** The learner plane influences the runtime only through `difficulty: int` on the next turn request (and nothing else — see §12, boundary B1). This is the price of information isolation: the counterpart agents cannot be told "he is weak on dosages," because agents that know that speak unnaturally about dosages.
3. **Content → Runtime is a pull, not a push.** The runtime asks the state graph for the next node when it is ready. The content plane has no timer and no ability to advance the conversation on its own.

---

## 3. Full architecture diagram

```
                                  ┌──────────────────────────────────────────┐
                                  │  BROWSER  (127.0.0.1 only, no CDN)       │
                                  │  Session view · waveform · turn strip    │
                                  │  Debrief · review gate · report export   │
                                  └───────────────┬──────────────────────────┘
                                        WebSocket │ /ws/session/{id}   (JSON envelopes, §13.3)
                                        HTTP      │ /api/*
════════════════════════════════════════════════╪═══════════════════════════════════════════════
  PROCESS: rehearsal-api  (uvicorn, asyncio)    │
                                  ┌─────────────▼──────────────┐
                                  │  API GATEWAY + WS HUB      │  deterministic
                                  │  fan-out of runtime events │
                                  └─────────────┬──────────────┘
                                                │
 ┌──────────────────────── SESSION RUNTIME PLANE ────────────────────────────────────────────┐
 │                                              │                                            │
 │   ┌──────────────────────────────────────────▼───────────────────────────────────────┐    │
 │   │            SESSION ORCHESTRATOR   (deterministic — NOT a model, §6)              │    │
 │   │  state machine · turn scheduler · seed ledger · budget guard · degradation ladder │    │
 │   └───┬──────────────┬───────────────┬────────────────┬──────────────┬───────────────┘    │
 │       │              │               │                │              │                    │
 │  ┌────▼─────┐  ┌─────▼──────┐  ┌─────▼──────┐   ┌─────▼──────┐  ┌────▼──────────┐         │
 │  │ AUDIO    │  │ CONTEXT    │  │ CLINICIAN  │   │  PATIENT   │  │ TTS ROUTER    │         │
 │  │ CAPTURE  │  │ ASSEMBLER  │  │  AGENT     │   │   AGENT    │  │ en-US / es-MX │         │
 │  │ VAD/barge│  │ (allowlist │  │ (en, model)│   │(es, model) │  │ streamed,     │         │
 │  │ -in      │  │  chokepoint│  └─────┬──────┘   └─────┬──────┘  │ interruptible │         │
 │  └────┬─────┘  │  — §12)    │        │                │         └────┬──────────┘         │
 │       │        └────────────┘        └────────┬───────┘              │                    │
 │       │  trainee audio frames                 │ native audio in      │ PCM out            │
 └───────┼───────────────────────────────────────┼──────────────────────┼────────────────────┘
         │                                       │                      │
         │                       UNIX socket ~/.rehearsal/run/live.sock │
         │                              ┌────────▼──────────┐           │
         │                              │ PROCESS:          │           │
         │                              │ rehearsal-live    │           │
         │                              │ Gemma 4 E4B q,    │           │
         │                              │ NATIVE AUDIO IN   │           │
         │                              │ (MLX | llama.cpp) │           │
         │                              └───────────────────┘           │
         │                                                              │
         │  ┌───────────────────────────────────────────────────────────▼──────────┐
         └─►│                    EVENT LOG  (append-only, hash-chained, §10)       │
            │        the single source of truth — every table below is a           │
            │        rebuildable projection of this log                            │
            └───┬──────────────────────────────┬───────────────────────────────────┘
                │ enqueue ScoreRequest         │ fold()
                │ (fire-and-forget)            │
 ┌──────────────▼──────── SCORING PLANE ───────┴───────────────────┐   ┌── LEARNER PLANE ────┐
 │  ┌───────────────────────┐   ┌─────────────────────────────┐    │   │ ┌────────────────┐  │
 │  │ DETERMINISTIC         │   │  GRADER  (one structured    │    │   │ │ LEARNER MODEL  │  │
 │  │ EXTRACTORS            │   │  call, temp 0)              │◄───┼───┼─┤ EWMA per error │  │
 │  │ numbers · dosage ·    │   │  semantic residue only:     │    │   │ │ category       │  │
 │  │ frequency · negation ·│   │  register · idiom ·         │    │   │ └───────┬────────┘  │
 │  │ laterality · allergy ·│   │  pragmatics · 1st person    │    │   │         │           │
 │  │ temporal              │   └──────────────┬──────────────┘    │   │ ┌───────▼────────┐  │
 │  └───────────┬───────────┘                  │  UNIX socket      │   │ │ COACH AGENT    │  │
 │              │        ┌─────────────────────▼────────┐          │   │ │ (model, between│  │
 │              └───────►│  VERDICT MERGER              │          │   │ │  turns only)   │  │
 │                       │  deterministic precedence,   │──────────┼──►│ └────────────────┘  │
 │                       │  severity, conflict rules    │ verdict  │   │                     │
 │                       └──────────────────────────────┘          │   └──────────┬──────────┘
 └────────────────────────────────┬────────────────────────────────┘              │ difficulty:int
                                  │ grader.sock                                   │ (ONLY signal
                       ┌──────────▼─────────┐                                     │  to runtime)
                       │ PROCESS:           │                    ┌────────────────▼────────────┐
                       │ rehearsal-grader   │                    │  CONTENT / SCENARIO PLANE   │
                       │ Gemma 12B q        │                    │  ┌───────────────────────┐  │
                       │ (MLX | llama.cpp)  │                    │  │ SCENARIO BANK         │  │
                       └────────────────────┘                    │  │ CLINICAL STATE GRAPH  │  │
                                                                 │  │ TERM MANIFEST         │  │
 ┌─────────────────────── STORE (embedded) ───────────────────┐  │  └───────────────────────┘  │
 │  SQLite (WAL)  ~/.rehearsal/rehearsal.db                   │  └─────────────────────────────┘
 │  Content-addressed blobs  ~/.rehearsal/blobs/sha256/ab/cd/ │
 └────────────────────────────────────────────────────────────┘
```

Read the diagram in one sentence: **the orchestrator is the only thing that decides anything; models are called by it, never the reverse; and everything either of them does lands in an append-only log before it is believed.**

---

## 4. Repository and module layout

```
src/rehearsal/
├── cli.py                      # `rehearsal <up|session|replay|gc|calibrate|doctor>`
├── config.py                   # SessionConfig, RuntimeConfig; no network config exists
├── orchestrator/
│   ├── loop.py                 # SessionOrchestrator — §6
│   ├── states.py               # SessionState enum + TRANSITIONS table — §8
│   ├── scheduler.py            # TurnScheduler, overlap policy
│   ├── budget.py               # TurnBudget, BudgetGuard, DegradeLevel
│   ├── seeds.py                # SeedLedger, derive_seed()
│   └── resume.py               # fold(events) -> SessionView, crash-resume rules
├── runtime/
│   ├── audio_in.py             # capture, VAD, endpointing  (see docs/05-voice-pipeline.md)
│   ├── tts.py                  # TTSRouter: en-US / es-MX, streamed, interruptible
│   ├── agents/
│   │   ├── clinician.py        # ClinicianAgent
│   │   ├── patient.py          # PatientAgent
│   │   └── context.py          # ContextAssembler — the isolation chokepoint, §12
│   └── hosts.py                # ModelHostClient (UNIX socket), health probes, restart
├── scoring/
│   ├── extractors/             # numbers.py dosage.py frequency.py negation.py
│   │                           # laterality.py allergy.py temporal.py
│   ├── grader.py               # one structured call, typed output
│   ├── merge.py                # VerdictMerger — deterministic
│   ├── taxonomy.py             # ErrorKind, Severity, Finding
│   └── queue.py                # ScoreQueue (in-process, bounded, durable via event log)
├── learner/
│   ├── model.py                # LearnerModel (per-category EWMA + counts)
│   └── coach.py                # CoachAgent, suppression rules
├── content/
│   ├── bank.py                 # ScenarioBank
│   ├── graph.py                # ClinicalStateGraph, NodeId, advance()
│   └── terms.py                # TermManifest for the bound scenario
├── store/
│   ├── db.py                   # connection, WAL pragmas, migrations runner
│   ├── events.py               # EventLog.append / iter / fold
│   ├── blobs.py                # BlobStore (content-addressed)
│   ├── projections.py          # rebuildable tables from the event log
│   └── migrations/0001_init.sql …
├── api/
│   ├── app.py                  # FastAPI factory, static mount for the built frontend
│   ├── ws.py                   # /ws/session/{session_id}
│   └── routes_sessions.py routes_reports.py routes_review.py
└── evals/                      # harnesses; see docs/08-evals.md
frontend/                       # vanilla-JS SPA, built to frontend/dist, served by the API
```

---

## 5. Component catalogue

The required summary table. Every row is expanded in §6–§11.

| Component | Responsibility | Deterministic or model | Critical path? | Failure mode |
|---|---|---|---|---|
| `SessionOrchestrator` | Owns the session state machine, turn order, seeds, budgets, degradation | **Deterministic** | Yes | Bug or unhandled exception aborts the session cleanly (`session.aborted`, reason `orchestrator_fault`); log stays valid and replayable |
| `TurnScheduler` | Decides when scoring for turn *N* is launched relative to capture of *N+1* | **Deterministic** | Yes | Mis-schedule leaks grader latency into the human's perceived pause; caught by the turn-gap eval in `docs/08-evals.md` |
| `SeedLedger` | Draws and records the root seed and every derived seed | **Deterministic** | Yes | Missing seed record makes a session non-reproducible; append is on the same transaction as the turn open, so this cannot silently happen |
| `BudgetGuard` | Enforces per-stage deadlines, triggers the degradation ladder | **Deterministic** | Yes | Too-tight budget truncates agent replies mid-sentence; too-loose stalls the loop. Deadlines are config, measured per machine by `rehearsal doctor` |
| `ContextAssembler` | Builds every model context from a per-role field allowlist | **Deterministic** | Yes | A leak here invalidates the project's central claim; enforced by `IsolationViolation` at runtime and the leakage A/B (L8) |
| `ClinicianAgent` | Speaks English in role, driven by the clinical state graph | **Model** (live, E4B) | Yes | Drifts persona or answers in Spanish → persona-consistency eval (L5); a hard schema-validation failure re-prompts once, then falls back to the node's scripted line |
| `PatientAgent` | Speaks Spanish in role, holds the patient's symptom state | **Model** (live, E4B) | Yes | Same as clinician; additionally may leak clinician-only facts → checked by the fact-containment test in `docs/08-evals.md` |
| `AudioCapture` | Mic capture, VAD, endpointing, barge-in detection | **Deterministic** (DSP) | Yes | Device loss → `capture_lost`; >10 s unrecoverable triggers `session.aborted` reason `audio_device`. Echo (no headphones) scores the TTS voice as the trainee — detected by an energy-correlation guard, hard-warned in UI |
| `TTSRouter` | Two voices, streamed, interruptible within 120 ms | **Model or system voices** | Yes | Neural TTS stall → fall back to macOS `say` voices (DegradeLevel 3), event `degraded.entered` |
| `ModelHostClient` | UNIX-socket RPC to the two model host processes, health probes, restart | **Deterministic** | Yes (live host) | Socket death → one automatic restart with a 20 s health probe; second failure inside a session aborts the session rather than limping |
| `rehearsal-live` host | Holds the E4B weights, native audio in | **Model** | Yes | OOM or Metal fault kills only this process; the orchestrator and event log survive |
| `rehearsal-grader` host | Holds the 12B weights | **Model** | **No** | May be killed under memory pressure; scoring degrades to extractor-only, verdicts marked `partial` |
| Deterministic extractors | Hard-check numbers, dosage, frequency, negation, laterality, allergy, temporal | **Deterministic** | No | A miss is a false negative on the critical error class — the most costly failure in the system; covered by per-extractor unit suites and critical-error recall in `SETUP.md` §6.7 |
| `Grader` | One structured call for the semantic residue only | **Model** (12B) | No | Invalid JSON → one retry at temp 0 with the schema echoed, then the turn is scored extractor-only and flagged `grader_unavailable` |
| `VerdictMerger` | Combines deterministic and semantic findings into the single verdict | **Deterministic** | No | Wrong precedence rule silently changes reported scores; every rule has a table-driven test in `docs/06-scoring-engine.md` |
| `LearnerModel` | Per-category EWMA of performance, drives difficulty | **Deterministic** | No | Over-reactive smoothing whipsaws difficulty; α is config, defaulted conservatively |
| `CoachAgent` | Between-turn feedback phrasing from a merged verdict | **Model** (grader host, low priority) | No | Suppressed entirely under DegradeLevel ≥1; a missing hint is invisible to the loop |
| `ScenarioBank` | Serves a scenario, its state graph and term manifest | **Deterministic** | No (pre-session) | Empty or corrupt bank blocks session start with a named error from `make scenarios` |
| `ClinicalStateGraph` | Legal next nodes, encounter arc, persona invariants | **Deterministic** | Yes (per turn) | A dead-end node strands the encounter; graph validity is checked at ingest, not at runtime |
| `EventLog` | Append-only, hash-chained record of everything | **Deterministic** | Yes (append is on-path) | Disk full → session pauses at the turn boundary rather than continuing unlogged. An unlogged session is worse than a stopped one |
| `BlobStore` | Content-addressed audio and canonical text | **Deterministic** | Write is off-path | Hash mismatch on read → blob quarantined, turn marked `blob_corrupt`, transcripts still usable |
| `API gateway / WS hub` | Serves the SPA, fans runtime events to the browser | **Deterministic** | Yes (UI feedback) | WS drop degrades to a stale UI; the session keeps running headless and the UI re-syncs by folding the event log |
| `ReviewGate` | Trainer/trainee confirmation and override of verdicts | **Human** + deterministic | No | Never blocks a session; unreviewed sessions are reported as `unreviewed`, never as `agreed` |
| `Replayer` | Rebuilds any session from the event log; re-scores under a new grader version | **Deterministic** | No | A replay divergence is a finding, not a crash — it is reported by `rehearsal replay --verify` |

---

## 6. The deterministic orchestrator

**The orchestrator is not a model, does not call a model to decide anything, and contains no natural-language reasoning.** It is a typed asyncio state machine of roughly 600 lines. This is deliberate: the parts of the system that can be wrong in interesting ways (agents, grader) are surrounded by a part that can only be wrong in boring, testable ways.

What it owns: turn order, seeds, deadlines, state transitions, persistence ordering, degradation. What it never does: decide what a speaker says, decide whether an interpretation was correct, or decide whether feedback is warranted.

### 6.1 Core signatures

```python
# src/rehearsal/orchestrator/loop.py

class SessionOrchestrator:
    def __init__(
        self,
        store: Store,                  # EventLog + BlobStore + projections
        hosts: ModelHosts,             # live + grader clients
        bank: ScenarioBank,
        audio: AudioIO,
        clock: Clock,                  # injectable; replay uses a LogicalClock
    ) -> None: ...

    async def run(self, cfg: SessionConfig) -> SessionOutcome: ...
    async def resume(self, session_id: SessionId) -> SessionOutcome: ...
    async def abort(self, reason: AbortReason) -> None: ...
```

```python
# src/rehearsal/config.py

@dataclass(frozen=True, slots=True)
class SessionConfig:
    scenario_id: str
    trainee_id: str
    direction_policy: Literal["alternating", "graph"]  # who speaks next
    max_turns: int = 24
    root_seed: int | None = None        # None -> drawn from os.urandom and recorded
    difficulty: int = 2                 # 1..5, learner plane may move this between sessions
    degrade_floor: DegradeLevel = DegradeLevel.L4   # below this, abort instead of limping
```

```python
# src/rehearsal/orchestrator/scheduler.py

@dataclass(frozen=True, slots=True)
class TurnPlan:
    turn_index: int
    speaker: Literal["clinician", "patient"]
    direction: Literal["en->es", "es->en"]
    node_id: NodeId
    seed: int
    budget: TurnBudget
```

### 6.2 Turn scheduling — the overlap that makes this feasible

One turn, in order. Stage names are the event kinds in §10.2.

```
turn N          ┌ source.emitted ─ tts.started ══════ tts.finished ┐
(runtime)       │                                                  │
                └──────────────────────► capture.started ══════════════ capture.ended ─ rendering.emitted ─┐
                                                                                                            │
turn N scoring                                          ┌── extractors ──┬── grader call ──┬── merge ──┐    │
(scoring plane)                                         │  (~40 ms)      │  (~2.0–3.0 s)   │ (~2 ms)   │    │
                                                        └────────────────┴─────────────────┴───────────┘    │
                                                        ▲                                                   │
                                                        │ launched the instant rendering.emitted lands ─────┘
turn N+1        ┌ source.emitted ─ tts ══════ ┐
(runtime)       └───────────► capture ════════════════════ (the trainee is speaking here)
                                    ▲
                                    └── this is the grader's latency budget: the human's own speaking time
```

The scheduler's single rule: **scoring for turn *N* must complete before `capture.ended` of turn *N+1*.** If it does not, the verdict simply lands late and the coach hint for turn *N* is dropped (`coach.suppressed`); nothing blocks. Sustained lateness (queue depth ≥ 2) escalates the degradation ladder.

```python
class TurnScheduler:
    def next_plan(self, view: SessionView, node: GraphNode) -> TurnPlan: ...
    def should_shed(self, queue_depth: int, ewma_grader_ms: float) -> DegradeLevel: ...
```

### 6.3 Seed control

Every stochastic draw in a session derives from one recorded 64-bit root seed. No component calls a global RNG.

```python
# src/rehearsal/orchestrator/seeds.py

def derive_seed(root_seed: int, namespace: str, turn_index: int) -> int:
    h = hashlib.blake2b(
        f"{root_seed}:{namespace}:{turn_index}".encode(), digest_size=8
    )
    return int.from_bytes(h.digest(), "big")

NAMESPACES: Final = (
    "scenario_selection",   # which scenario, which entry node
    "graph_walk",           # which legal successor node
    "clinician_sampling",
    "patient_sampling",
    "coach_sampling",
    "distractor_injection", # difficulty knobs: speed, overlap, numeric density
)
```

The grader is always called at temperature 0 with a fixed decode configuration and therefore takes no seed; if the runtime is ever changed to sample in the grader, that is a scoring-plane change and must be re-calibrated against `SETUP.md` §6.

**Honest limit [decided, stated everywhere it matters]:** identical seeds guarantee identical *inputs*, not bit-identical model *outputs*. Metal and llama.cpp kernels can reorder floating-point reductions across runs and across machine states. Rehearsal therefore claims **input-level reproducibility** — any session can be replayed with exactly the prompts, audio and parameters it originally used — and measures output stability separately (`rehearsal replay --verify` reports the divergence rate). Claiming bit-determinism we cannot deliver would violate principle 7.

### 6.4 Budget

```python
# src/rehearsal/runtime/budget.py

@dataclass(frozen=True, slots=True)
class TurnBudget:
    source_generation_ms: int = 900     # agent reply text complete
    tts_first_audio_ms:   int = 400     # from first token to first PCM frame
    barge_in_stop_ms:     int = 120     # TTS silent after trainee onset
    capture_max_ms:       int = 45_000  # hard cap on one rendering
    grader_wall_ms:       int = 3_500   # off-path; exceeding it sheds, never blocks
    persist_turn_ms:      int = 50      # event append + blob write handoff
```

`BudgetGuard` measures each stage, appends `budget.exceeded` with the stage and the overshoot, and maps sustained overshoot to a `DegradeLevel` (§14). Budgets are configuration, not constants in code: `rehearsal doctor` measures the actual machine and writes a machine-local override, because a 48 GB M-series and a 32 GB one are not the same latency environment and pretending otherwise produces either stutter or truncation.

### 6.5 Run state machine

The orchestrator is the only writer of session state. State lives in the event log; the `sessions` table is a projection. See §8 for the full state and transition tables.

---

## 7. Scoring plane

Full internals are `docs/06-scoring-engine.md`; the architectural facts are these.

**Split of labour [decided]:**

| Class | Handled by | Why |
|---|---|---|
| numbers, dosages, frequencies, negation, laterality, allergies, temporal markers | Deterministic extractors | Provably decidable from two strings plus the term manifest. These are the **critical** error class. A model is a strictly worse tool for a decidable problem |
| register, idiom, pragmatic force, first-person discipline, editorialization, role exchange, false fluency | One structured grader call | Genuinely semantic; no closed-form check exists |

**Contract:**

```python
# src/rehearsal/scoring/taxonomy.py

ErrorKind = Literal[
    "omission", "addition", "substitution", "distortion",
    "editorialization", "role_exchange", "register_shift",
    "false_fluency", "first_person_violation",
]
Severity = Literal["critical", "non_critical"]

@dataclass(frozen=True, slots=True)
class Finding:
    kind: ErrorKind
    severity: Severity
    span: tuple[int, int] | None      # char offsets into the rendering, or None for omissions
    source_span: tuple[int, int] | None
    note: str
    origin: Literal["extractor", "grader"]
    extractor_name: str | None
    confidence: float | None          # grader only; extractors do not guess
```

```python
# src/rehearsal/scoring/extractors/__init__.py

class Extractor(Protocol):
    name: str
    def __call__(self, source: str, rendering: str, ctx: TurnContext) -> list[Finding]: ...

# src/rehearsal/scoring/merge.py

def merge_verdict(
    deterministic: list[Finding],
    semantic: list[Finding],
    policy: MergePolicy,
) -> Verdict: ...
```

**Merge precedence [decided]:** where an extractor and the grader disagree on the same span, the extractor wins on the critical categories and the grader is recorded as `overruled` (kept in the record, never deleted — the disagreement rate is itself a reported number). The grader is never allowed to *downgrade* a critical extractor finding, and never allowed to *create* a `critical` severity in the extractor-owned categories.

**The rendering text problem [decided, with a named measurement obligation].** The live agents take the trainee's audio natively — there is no ASR stage in the critical path. The scoring plane nonetheless needs text. Resolution: the live agent's structured turn output carries a `heard_verbatim` field alongside its in-character reply, produced in the same forward pass, so it costs no additional critical-path latency. That verbatim string is the canonical rendering and is content-addressed as `rendering_sha`.

This is only sound if `heard_verbatim` is faithful. It is therefore measured, not assumed: transcription fidelity is evaluated against hand transcripts of the calibration audio, and reported in `docs/08-evals.md` alongside grader agreement. If fidelity is inadequate, the fallback is an off-critical-path re-transcription pass on the grader host (`rendering_source = "offpath_retranscribe"`), which costs latency the scoring plane already has and the runtime does not. **[open]** — see §16.

---

## 8. Session state machine

### 8.1 States

| State | Meaning | Durable checkpoint? |
|---|---|---|
| `init` | Session row created, nothing bound | Yes |
| `configuring` | Scenario bound, seeds drawn, hosts health-probed | Yes |
| `armed` | Everything ready, waiting for the trainee's start gesture | Yes |
| `source_speaking` | A counterpart agent's utterance is being synthesised and played | No |
| `awaiting_rendering` | Playback finished, mic open, waiting for speech onset | Yes (turn boundary) |
| `rendering_capturing` | Trainee is speaking; VAD has onset, no endpoint yet | No |
| `turn_closing` | Rendering persisted, score enqueued, graph advanced | Yes |
| `paused` | Human paused, or the orchestrator paused on a recoverable fault | Yes |
| `recovering` | Post-crash fold and reconciliation in progress | — (transient, derived) |
| `debrief` | Encounter finished; verdicts draining; report assembling | Yes |
| `review` | Human gate: trainee and/or trainer inspecting and overriding | Yes |
| `complete` | Report finalised; session immutable | Yes (terminal) |
| `aborted` | Ended early and deliberately; partial record retained and marked | Yes (terminal) |
| `failed` | Ended by an unrecoverable fault; record retained and marked | Yes (terminal) |

`DegradeLevel` is deliberately **not** a state — it is an orthogonal attribute of a live session (§14). Folding it into the state machine would multiply the state count by six and buy nothing.

### 8.2 Transitions

| From | Trigger | Guard | To | Side effects |
|---|---|---|---|---|
| `init` | `configure(cfg)` | scenario exists; both hosts healthy | `configuring` | draw root seed, append `session.created`, `seed.drawn` |
| `configuring` | bind complete | graph entry node resolved | `armed` | append `scenario.bound` |
| `configuring` | host probe fails | — | `failed` | append `session.failed` reason `host_unavailable` |
| `armed` | trainee starts | audio device present | `source_speaking` | append `session.started`, `turn.opened` |
| `source_speaking` | first PCM frame | within `tts_first_audio_ms` | `source_speaking` | append `tts.started` |
| `source_speaking` | playback complete | — | `awaiting_rendering` | append `tts.finished`, `capture.started` |
| `source_speaking` | trainee speaks over playback | barge-in enabled | `rendering_capturing` | append `tts.interrupted` (with offset), stop TTS ≤120 ms |
| `awaiting_rendering` | speech onset | VAD onset | `rendering_capturing` | — |
| `awaiting_rendering` | silence > `capture_max_ms` | — | `turn_closing` | append `rendering.emitted` with `empty: true`; turn scored as full omission |
| `rendering_capturing` | endpoint detected | — | `turn_closing` | write audio blob, append `capture.ended`, `rendering.emitted` |
| `rendering_capturing` | device lost | — | `paused` | append `capture_lost`; 10 s recovery window |
| `turn_closing` | graph has next node and `turn_index < max_turns` | — | `source_speaking` | enqueue `ScoreRequest`, advance graph, append `turn.opened` |
| `turn_closing` | graph terminal or `max_turns` reached | — | `debrief` | append `encounter.ended` |
| any live state | `pause()` | — | `paused` | append `session.paused`; TTS stops, mic closes |
| `paused` | `resume()` | hosts healthy, device present | previous durable state | append `session.resumed` |
| `paused` | 10 s device recovery elapsed | unrecoverable | `aborted` | append `session.aborted` reason `audio_device` |
| any live state | `abort(reason)` | — | `aborted` | append `session.aborted`; drain in-flight scores; keep every blob |
| any live state | unhandled exception | — | `failed` | append `session.failed` with traceback digest (not the traceback text — see §12 B7) |
| `debrief` | score queue drained or grader deadline passed | — | `review` | append `report.assembled`; unscored turns explicitly listed |
| `review` | human confirms | — | `complete` | append `review.signed`; session becomes immutable |
| `review` | human overrides a finding | — | `review` | append `review.override` (original verdict untouched) |
| process start | orphaned live session found | log folds cleanly | `recovering` | see §8.3 |

### 8.3 Crash-resume

The rule that makes resume simple: **a turn boundary is the only resumable checkpoint.**

On startup, `rehearsal-api` scans for sessions whose last event is not terminal and enters `recovering`:

1. `fold(events) -> SessionView` — pure function, no I/O beyond the log read.
2. If the last event is a durable-state event, resume there directly.
3. If a turn was in flight (`turn.opened` with no matching `turn_closing`), append `turn.abandoned` and re-open the same `turn_index` **with the same derived seed**, so the replayed turn is the turn that was planned, not a new one.
4. Partially captured audio is retained as a blob and referenced by the abandoned turn, marked `partial: true`. It is never scored — a half-utterance scored as a whole one manufactures a fake omission, which is exactly the failure mode this system exists to detect.
5. TTS for a completed turn is never re-played on resume. Re-speaking a line the trainee already interpreted corrupts the encounter.
6. Verdicts that were mid-flight are simply re-enqueued: scoring is idempotent by `verdict_key` (§10.4), so a duplicated request is a cache hit, not a double write.

```python
# src/rehearsal/orchestrator/resume.py
def fold(events: Iterable[Event]) -> SessionView: ...
def resumable_state(view: SessionView) -> SessionState: ...
```

### 8.4 Abort paths

| Path | Trigger | Record left behind |
|---|---|---|
| Trainee abort | UI stop button | `session.aborted` reason `user`; all completed turns scored and reported normally |
| Watchdog abort | live host failed twice in one session | reason `host_unavailable`; report marked partial |
| Device abort | audio device unrecoverable after 10 s | reason `audio_device` |
| Storage abort | disk full on event append | reason `store_full`; **the session pauses first and only aborts if the append still fails** — an unlogged session is treated as a failure, not as a session |
| Degrade-floor abort | required `DegradeLevel` exceeds `cfg.degrade_floor` | reason `degrade_floor`; the system refuses to produce numbers it cannot stand behind |

Every abort leaves a complete, valid, replayable log prefix. There is no code path that ends a session by deleting anything.

---

## 9. Content / scenario plane

The plane that makes principle 2 true. The system generates the source utterance, so it knows exactly what was said — scoring is "compare known source to trainee rendering", never "judge quality".

| Component | Contract |
|---|---|
| `ScenarioBank` | `get(scenario_id) -> Scenario`; `sample(difficulty, seed) -> Scenario`. Built by `make scenarios`; sources and licences in `docs/07-data-and-scenarios.md` |
| `ClinicalStateGraph` | `entry(seed) -> NodeId`; `successors(node_id) -> list[NodeId]`; `advance(node_id, seed) -> NodeId`. A node carries: speaker, intent, persona invariants, required clinical facts, an optional scripted fallback line, and the difficulty features it exercises |
| `TermManifest` | The scenario's numbers, dosages, frequencies, allergies, laterality and temporal markers, in both languages. **The extractors' ground truth**, produced with the scenario, not inferred from it |

The agents improvise wording; the graph owns the clinical facts. That division is what lets an extractor say "the source contained *500 mg every eight hours* and the rendering contains no frequency" with certainty rather than with a model's opinion.

Scenario text is **untrusted data**, even though we generated the bank — see §12, boundary B3.

---

## 10. Event log, projections and replay

### 10.1 The rule

**The event log is the truth. Every table other than `events` and `blobs` is a projection that can be dropped and rebuilt.** This is what makes "any session is replayable" a structural property rather than a feature someone has to maintain.

```bash
rehearsal replay <session_id>                  # reconstruct the session record from events
rehearsal replay <session_id> --rebuild        # drop and regenerate all projections
rehearsal replay <session_id> --rescore        # re-run scoring under the current grader version
rehearsal replay <session_id> --verify         # compare a fresh run to the recorded one; report divergence
```

`--rescore` is the mechanism behind L10 prompt optimisation: an improved grader prompt is evaluated by re-scoring recorded sessions and the calibration set, never by re-running live sessions with humans in them.

### 10.2 Event kinds

| Group | Kinds |
|---|---|
| Session | `session.created` `session.configured` `seed.drawn` `scenario.bound` `session.started` `session.paused` `session.resumed` `session.aborted` `session.failed` `session.completed` |
| Turn | `turn.opened` `source.requested` `source.emitted` `tts.started` `tts.finished` `tts.interrupted` `capture.started` `capture.ended` `rendering.emitted` `turn.closed` `turn.abandoned` |
| Scoring | `score.enqueued` `extractors.completed` `grader.started` `grader.completed` `grader.failed` `verdict.merged` |
| Learner | `learner.updated` `coach.emitted` `coach.suppressed` `difficulty.changed` |
| Health | `budget.exceeded` `degraded.entered` `degraded.exited` `host.restarted` `capture_lost` `blob_quarantined` |
| Human | `review.opened` `review.override` `review.signed` `export.requested` |

### 10.3 Event schema

```sql
CREATE TABLE events (
  seq         INTEGER PRIMARY KEY AUTOINCREMENT,  -- global monotonic order
  session_id  TEXT    NOT NULL,
  turn_index  INTEGER,                            -- NULL for session-scoped events
  ts_ms       INTEGER NOT NULL,                   -- wall clock, ms since epoch
  mono_ms     INTEGER NOT NULL,                   -- monotonic clock; latency maths uses this one
  kind        TEXT    NOT NULL,
  payload     TEXT    NOT NULL,                   -- canonical JSON (sorted keys, no whitespace)
  prev_hash   TEXT    NOT NULL,                   -- hash of the previous event in this session
  hash        TEXT    NOT NULL                    -- sha256(prev_hash || kind || canonical payload)
) STRICT;

CREATE INDEX idx_events_session_seq ON events(session_id, seq);
CREATE INDEX idx_events_kind        ON events(kind);
```

The hash chain costs one `sha256` per append (microseconds) and buys a property the project needs: a reported number can be traced to a specific chain of events, and a silently edited record is detectable by `rehearsal replay --verify`. Given that the whole product's credibility is the honesty of its measurements, tamper-evidence at that price is not over-engineering.

Wall clock and monotonic clock are both recorded because they answer different questions: `ts_ms` says when a session happened, `mono_ms` is the only sound basis for latency arithmetic across sleep/wake.

### 10.4 Projections (SQLite DDL)

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA synchronous  = NORMAL;

CREATE TABLE sessions (
  session_id   TEXT PRIMARY KEY,
  trainee_id   TEXT NOT NULL,
  scenario_id  TEXT NOT NULL,
  root_seed    INTEGER NOT NULL,
  state        TEXT NOT NULL,          -- SessionState
  degrade_max  INTEGER NOT NULL DEFAULT 0,
  started_ms   INTEGER,
  ended_ms     INTEGER,
  abort_reason TEXT,
  grader_model TEXT,                   -- resolved model id + quantisation
  live_model   TEXT,
  prompt_ver   TEXT NOT NULL           -- grader prompt version; see docs/06-scoring-engine.md
) STRICT;

CREATE TABLE turns (
  session_id    TEXT NOT NULL REFERENCES sessions(session_id),
  turn_index    INTEGER NOT NULL,
  speaker       TEXT NOT NULL,         -- clinician | patient
  direction     TEXT NOT NULL,         -- en->es | es->en
  node_id       TEXT NOT NULL,
  seed          INTEGER NOT NULL,
  source_sha    TEXT NOT NULL REFERENCES blobs(sha256),
  rendering_sha TEXT     REFERENCES blobs(sha256),   -- NULL if empty/abandoned
  audio_sha     TEXT     REFERENCES blobs(sha256),
  rendering_src TEXT NOT NULL DEFAULT 'live_verbatim',  -- | offpath_retranscribe
  partial       INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (session_id, turn_index)
) STRICT;

CREATE TABLE verdicts (
  verdict_key   TEXT PRIMARY KEY,      -- sha256(prompt_ver|grader_model|source_sha|rendering_sha)
  session_id    TEXT NOT NULL,
  turn_index    INTEGER NOT NULL,
  status        TEXT NOT NULL,         -- complete | partial | grader_unavailable
  n_critical    INTEGER NOT NULL,
  n_non_critical INTEGER NOT NULL,
  extractor_ms  INTEGER NOT NULL,
  grader_ms     INTEGER,
  created_ms    INTEGER NOT NULL,
  FOREIGN KEY (session_id, turn_index) REFERENCES turns(session_id, turn_index)
) STRICT;

CREATE TABLE findings (
  finding_id     INTEGER PRIMARY KEY AUTOINCREMENT,
  verdict_key    TEXT NOT NULL REFERENCES verdicts(verdict_key),
  kind           TEXT NOT NULL,
  severity       TEXT NOT NULL,
  origin         TEXT NOT NULL,        -- extractor | grader
  extractor_name TEXT,
  span_start     INTEGER, span_end     INTEGER,
  src_start      INTEGER, src_end      INTEGER,
  confidence     REAL,
  overruled      INTEGER NOT NULL DEFAULT 0,
  note           TEXT NOT NULL DEFAULT ''
) STRICT;

CREATE TABLE reviews (
  review_id    INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id   TEXT NOT NULL REFERENCES sessions(session_id),
  finding_id   INTEGER REFERENCES findings(finding_id),   -- NULL = session-level note
  action       TEXT NOT NULL,          -- agree | reject | reclassify | add
  new_kind     TEXT, new_severity TEXT,
  reviewer     TEXT NOT NULL,          -- trainee | trainer:<id>
  rationale    TEXT NOT NULL DEFAULT '',
  created_ms   INTEGER NOT NULL
) STRICT;

CREATE TABLE learner_state (
  trainee_id  TEXT NOT NULL,
  kind        TEXT NOT NULL,           -- ErrorKind
  ewma_rate   REAL NOT NULL,
  n_observed  INTEGER NOT NULL,
  updated_ms  INTEGER NOT NULL,
  PRIMARY KEY (trainee_id, kind)
) STRICT;

CREATE TABLE blobs (
  sha256     TEXT PRIMARY KEY,
  bytes      INTEGER NOT NULL,
  media_type TEXT NOT NULL,            -- audio/opus | text/plain; charset=utf-8 | application/json
  created_ms INTEGER NOT NULL
) STRICT;
```

`verdict_key` is the idempotency key that makes re-scoring free and re-runs honest: the same source text, the same rendering text, the same model and the same prompt version can only produce one verdict row. Changing the prompt version produces a *new* row rather than overwriting the old one, so before/after comparisons in `docs/08-evals.md` are reads, not reruns.

`reviews` never mutates `findings`. A trainer override is an additional fact about a finding, not a replacement of it — which is what makes trainer-override rate (the L7 eval) measurable at all.

### 10.5 Content-addressed storage

```
~/.rehearsal/blobs/sha256/
├── 3f/
│   └── a9/
│       ├── 3fa9c1…e07.opus     # trainee rendering audio, 16 kHz mono
│       └── 3fa9c1…e07.meta.json
└── 7b/…
```

| Property | Decision |
|---|---|
| Hash | `sha256` of the raw bytes; 2/2 hex path sharding |
| Immutability | Blobs are write-once. A write to an existing path is a verified no-op, not an overwrite |
| What is stored | Trainee rendering audio (opus, 16 kHz mono), the canonical source text, the canonical rendering text, and the assembled grader input for that turn |
| Why text is content-addressed too | A verdict references `source_sha` and `rendering_sha`. Re-scoring is then provably about *the same strings*, and no later edit to a transcript can silently change what a published number was computed over |
| Synthesised TTS audio | Not stored [decided]. It is regenerable from the source text plus the recorded voice id, and it is the bulk of the bytes. Recorded as a reference, not a blob |
| Verification | Read path verifies the hash; a mismatch quarantines the blob (`blob_quarantined`) and marks the turn, rather than returning corrupt audio to a trainer |
| Reclamation | `rehearsal gc --dry-run` mark-and-sweep over references in `turns`, `events` and `reviews`. Unreferenced blobs older than a retention floor are listed; deletion requires a second, explicit invocation |
| Privacy | Blobs never leave the machine. Export is a human-initiated action with a redaction pass (§12, boundary B7) |

---

## 11. Learner-model plane and the human gates

`LearnerModel` is deterministic arithmetic — a per-category EWMA of error rate plus observation counts. It is not a model call, and it deliberately does not attempt to explain the trainee's behaviour.

```python
class LearnerModel:
    def update(self, trainee_id: str, verdict: Verdict) -> LearnerDelta: ...
    def difficulty(self, trainee_id: str) -> int: ...   # 1..5, the ONLY value the runtime sees
    def weak_categories(self, trainee_id: str, k: int = 3) -> list[ErrorKind]: ...
```

`CoachAgent` turns a merged verdict into feedback the trainee can act on. It runs on the grader host at lower priority, only at turn boundaries, and is the first thing dropped under load. It never sees future turns and never speaks during capture.

**Human gates (L7):** the trainee is the gate during the session (start, pause, abort, and the debrief where they see each turn against its source), and the trainer is the gate after it (`review` state). Nothing the system produces is presented as a final assessment until a human has passed it, and the override record is retained as data. The AI drafts; the human decides.

---

## 12. Trust boundaries

Numbered because they get cited in code comments and in test names.

| ID | Boundary | What must never cross | Enforcement |
|---|---|---|---|
| **B1** | Scoring/learner plane → counterpart agents | The rubric, the error taxonomy, any verdict, any finding, any learner state, any past-performance summary. The only permitted signal is `difficulty: int` | `ContextAssembler` builds every agent context from a per-role field allowlist; a disallowed key raises `IsolationViolation`. Unit test asserts rubric vocabulary is absent from every assembled live context. Measured end-to-end by the leakage A/B (L8) in `docs/08-evals.md` |
| **B2** | Counterpart agents → grader | Agent hidden state, agent self-assessment, the other agent's private facts, the learner model | Grader context is constructed from `(source_text, rendering_text, direction, term_manifest_slice)` only. A grader that knows the trainee is "usually weak on numbers" is a biased instrument |
| **B3** | Scenario/dataset text → any prompt | Instructions. Ingested corpus text is **data** | All external text enters through delimited data slots; instruction regions are code-owned string constants. Ingestion strips control characters and normalises Unicode. No component ever executes or follows text that came from a dataset, a filename, or a model output |
| **B4** | Process → network | Everything, in the core loop | No outbound HTTP client is imported by any module under `runtime/`, `scoring/`, `orchestrator/`. Model hosts bind UNIX sockets, not TCP. `rehearsal doctor --offline` asserts a session completes with networking disabled. Model download and dataset ingest are separate, explicitly online, pre-session commands |
| **B5** | Model output → system state | Free-form text becoming a decision or a write | Every model call returns a validated schema instance. Models never write to the database, never choose a state transition, never set a severity in the extractor-owned categories, never emit SQL or paths |
| **B6** | System verdict → the record of record | An unreviewed verdict presented as agreed | Session reports state review status explicitly; `reviews` rows are additive; `review.signed` is required to reach `complete` |
| **B7** | Local store → outside the machine | Trainee audio, transcripts, identity | Export is human-initiated, writes to `~/.rehearsal/exports/`, and runs a redaction pass (trainee id → pseudonym, audio excluded unless separately confirmed). Failure records store a traceback *digest*, not traceback text, because tracebacks can carry utterance fragments |

**Why B1 is load-bearing.** An agent that can see the rubric will, without being told to, produce utterances that are easy to interpret — shorter, less idiomatic, fewer overlapping numbers. That destroys the realism the training depends on and inflates every score. This is the entire architectural justification for separate agents with separate contexts rather than one model playing both roles, and it is the reason the leakage A/B exists: the claim is settled with a measurement, not with this paragraph.

---

## 13. Process and deployment topology

Single machine, single user, no server. `rehearsal up` starts three processes.

### 13.1 Processes

| Process | What it is | Binding | Restart policy | Resident |
|---|---|---|---|---|
| `rehearsal-api` | uvicorn + FastAPI + orchestrator + scoring plane + store; serves `frontend/dist` | `127.0.0.1:8420` | Manual. It owns the event log; a surprise restart mid-session is a resume path (§8.3), not a routine event | < 500 MB |
| `rehearsal-live` | Model host: Gemma 4 E4B, quantised, native audio input | `~/.rehearsal/run/live.sock` | Auto-restart once per session, then abort | ~6–8 GB |
| `rehearsal-grader` | Model host: Gemma 12B, quantised | `~/.rehearsal/run/grader.sock` | Auto-restart; may be killed under memory pressure without ending the session | ~8–10 GB |

Plus TTS: in-process with `rehearsal-api` for system voices, or a fourth child process for a local neural TTS backend (~1–2 GB). See `docs/05-voice-pipeline.md`.

Total resident ~20–24 GB on a 48 GB machine, matching `SETUP.md` §4, leaving headroom for the OS, the browser and audio buffers.

**Why the model hosts are separate processes** (and why that is not a microservice architecture): memory isolation and independent kill. A Metal OOM in the 12B grader must not take down the process holding the append-only log, and under memory pressure we must be able to kill the grader specifically and keep the session running. Two extra processes buy two concrete failure-containment properties. That is the entire justification; no other component gets its own process.

**Why UNIX sockets, not localhost TCP:** filesystem permissions instead of a listening port, no accidental exposure on a shared network, and no port collisions with the developer's other local services.

### 13.2 Startup ordering (dependency, not schedule)

```
store: open db → run migrations → verify blob root writable
  └─► model hosts: spawn → load weights → health probe (one tiny inference each)
        └─► content: load scenario bank → validate state graphs
              └─► api: mount routes → mount frontend/dist → open WS hub
                    └─► ready: `rehearsal doctor` green
```

A failure at any rung stops the chain with a named error. `rehearsal doctor` runs the same chain non-destructively and additionally measures the machine's actual latencies to write the local budget override (§6.4).

### 13.3 Interfaces

```
HTTP
  POST /api/sessions                 -> {session_id}          create from SessionConfig
  POST /api/sessions/{id}/start
  POST /api/sessions/{id}/pause      POST /api/sessions/{id}/resume
  POST /api/sessions/{id}/abort      {reason}
  GET  /api/sessions/{id}            -> folded SessionView
  GET  /api/sessions/{id}/report     -> report projection (turns, verdicts, review status)
  POST /api/reviews                  -> append review.override / review.signed
  GET  /api/blobs/{sha256}           -> bytes, hash-verified   (127.0.0.1 only)

WebSocket  /ws/session/{session_id}
  server -> client  {"t": <event.kind>, "seq": int, "turn": int|null, "d": {...}}
  client -> server  {"t": "start"|"pause"|"resume"|"abort"|"ack", "d": {...}}
```

The WS stream is a **projection of the event log, not a second channel**. Every message carries the event `seq`; a reconnecting client sends its last seen `seq` and receives the gap. There is no runtime state that exists only in the browser, which is why a dropped socket degrades the UI and not the session.

### 13.4 Filesystem layout

```
~/.rehearsal/
├── rehearsal.db              # SQLite (WAL: -wal, -shm alongside)
├── blobs/sha256/ab/cd/…      # content-addressed, write-once
├── run/                      # live.sock, grader.sock, *.pid
├── models/                   # weights (REHEARSAL_MODEL_DIR override)
├── logs/                     # structured JSONL app logs (not the event log)
├── exports/                  # human-initiated, redacted
└── budget.local.json         # machine-measured deadline overrides
```

Application logs and the event log are different things and are never conflated: logs are for operators and are droppable; the event log is the record and is not.

---

## 14. Degradation ladder

Every level is entered by a deterministic rule, emits `degraded.entered` with the trigger, and is **visible in the UI**. Nothing degrades silently — a trainee who does not know the grader was shed will read a clean score as a clean performance.

| Level | Trigger | Behaviour | What the trainee sees |
|---|---|---|---|
| **L0** nominal | — | Full loop | Normal |
| **L1** hint shed | Score queue depth ≥ 2 | Coach hints suppressed; scoring continues | "Feedback catching up" indicator |
| **L2** grader shed | Grader p95 > `grader_wall_ms` sustained, or grader host down | Extractor-only scoring; verdicts `partial`; semantic categories reported as *not assessed*, never as *no error found* | Explicit "critical checks only" banner |
| **L3** TTS fallback | Neural TTS stall or load failure | System voices (`say`) | Voice change, noted in the debrief |
| **L4** text mode | Audio device unavailable and trainee opts to continue | Source shown as text, rendering typed | Mode banner; the session is marked `text_mode` and excluded from voice-latency stats |
| **L5** stop | Below `cfg.degrade_floor`, or store unwritable | Clean abort with a complete log prefix | Explicit failure message with the reason |

Reported metrics always carry the maximum degrade level the session reached (`sessions.degrade_max`). A number produced at L2 is not comparable to a number produced at L0, and the schema makes it impossible to lose that distinction.

---

## 15. Why not X

### Why no agent framework (LangChain, CrewAI, or similar)

The product's credibility *is* its inspectability. Three specific things a framework would take away:

1. **Seed and prompt control.** Every stochastic draw must derive from one recorded root seed (§6.3) and every assembled context must be reconstructable byte-for-byte from the log. Frameworks own prompt assembly and hide it behind template layers and implicit memory.
2. **The isolation boundary.** B1 is the project's central claim. Frameworks are built around convenient shared memory and automatic context propagation between agents — precisely the mechanism that would leak the rubric into the counterpart agents and destroy training realism. We would be fighting the framework's happiest path.
3. **Latency accounting.** Principle 5 requires knowing exactly which milliseconds belong to which stage. That requires owning the call path.

Cost, stated plainly: roughly 600 lines of orchestration we maintain ourselves, plus retries, timeouts and schema validation. Accepted, because those lines are the ones a reviewer needs to read to believe the results. The rule from the project stack: raw API until the framework's hidden parts are reconstructable — and then adopt only by naming the exact pain removed. No such pain is currently named.

### Why no cloud inference in the core loop

| Reason | Detail |
|---|---|
| Content sensitivity | Sessions contain clinically-shaped speech recorded in and around safety-net clinics. The strongest possible privacy statement is architectural: audio has nowhere to go |
| Latency determinism | A conversational loop budgeted in hundreds of milliseconds cannot depend on a network whose tail latency it does not control |
| Cost per practice minute | The product's promise is *unlimited* private practice. Per-token pricing makes unlimited practice a lie |
| Reproducibility | A pinned local quantised checkpoint is the same instrument next month. A hosted endpoint silently changes underneath a calibration set, invalidating every published number |
| Deployment reality | Watsonville and Pajaro Valley clinic settings cannot be assumed to have reliable bandwidth during a training session |

Trade-off, stated honestly: a local E4B/12B pair is weaker than a frontier model. That is exactly why the calibration set exists — the claim "this grader is good enough" is a measured number against human labels (`SETUP.md` §6), not an assertion. A frontier API key remains permitted for *offline second-opinion analysis during calibration only*, never in the runtime.

### Why no microservices

One user, one machine, one session at a time. A network hop between the orchestrator and the scoring plane would add latency, a serialisation boundary and a new failure mode, in exchange for scaling we have explicitly excluded (no horizontal multi-tenant fleet — an out-of-scope decision, not an oversight). SQLite in WAL mode absorbs the write volume comfortably: a session generates on the order of 40–120 event appends per minute.

Process separation is used exactly where it buys measurable failure containment (§13.1) and nowhere else. That is the difference between decomposition with a reason and decomposition by default.

### Why no vector database or retrieval in the live loop

Ground truth is by construction (principle 2). The scenario, its facts and its term manifest are generated by the content plane and fit in context. Retrieval would inject a nondeterministic component into the one loop whose entire epistemic advantage is knowing exactly what was said.

### Why no fine-tuning, LoRA, or RL

Out of scope by decision, and the reason is measurement discipline rather than difficulty: the calibration set is 40 human-labelled items — the right size to *measure* an instrument with and far too small to train one on. Training on it would consume the only external anchor the project has. Improvement therefore happens at the prompt level (L10), optimised against DEV and reported on the sealed TEST split.

### Why no separate speech-recognition stage in the critical path

An ASR hop before the live model adds a full serial stage to the tightest budget in the system and introduces a second transcription error surface between the trainee and the agent. The audio-native model removes it. The obligation this creates — proving `heard_verbatim` is faithful enough to score against — is discharged by measurement, not assumption (§7).

### Why the orchestrator is not an agent

An LLM-driven controller would make turn order, budgets and state transitions stochastic and unauditable. Everything the orchestrator decides is decidable by code, and principle 1 says decidable things are decided by code. There is no interesting judgement in "is it this speaker's turn"; there is only the opportunity to be nondeterministically wrong about it.

---

## 16. Open questions

| # | Question | Status | What would settle it |
|---|---|---|---|
| 1 | Is the live model's `heard_verbatim` faithful enough to be the canonical rendering? | **[open]** — default is `live_verbatim`, fallback `offpath_retranscribe` is implemented behind a config flag | Word-error-rate of `heard_verbatim` against hand transcripts of the calibration audio, plus grader agreement measured under both settings on the DEV split |
| 2 | Overlap policy when a trainee begins interpreting before the source finishes | **[proposed]** — barge-in stops TTS at ≤120 ms and the partial source is still the scoring source | Trainer judgement on recorded cases; if partial-source scoring produces spurious omissions, the turn must be marked rather than scored |
| 3 | Does the grader benefit from seeing the term manifest slice, or does it bias it toward extractor territory? | **[open]** | A/B on the DEV split: grader precision/recall on semantic categories with and without the manifest slice |
| 4 | Whether coach hints should ever appear mid-encounter or only at debrief | **[proposed]** — turn-boundary only, suppressed under load | Completion rate and trainee-reported disruption in the L7 pipeline eval |
| 5 | Retention default for rendering audio | **[proposed]** — keep indefinitely locally, `rehearsal gc` requires explicit deletion | Trainer and clinic-partner input; the redaction path exists either way |
| 6 | EWMA α for the learner model | **[proposed]** — conservative default, config-driven | Difficulty-oscillation rate across multi-session traces |

---

## 17. Definition of done for this architecture

A change to any component is complete when:

- [ ] The component's row in §5 is still accurate, including its failure mode
- [ ] Any new model call goes through `ContextAssembler` with an explicit allowlist (B1) and returns a validated schema (B5)
- [ ] Any new stochastic draw takes a derived seed from a declared namespace (§6.3)
- [ ] Any new consequential state lands in the event log before it is acted on (§10.1)
- [ ] Projections can still be dropped and rebuilt: `rehearsal replay <id> --rebuild --verify` is clean
- [ ] The eval that covers the component still runs, and its number is recorded in `plans/metrics-snapshot.md` per `SETUP.md` §9
- [ ] Nothing new imports an HTTP client under `runtime/`, `scoring/` or `orchestrator/` (B4)

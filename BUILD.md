# BUILD — Rehearsal master build orchestration

> **You are the build orchestrator.** Read this file top to bottom, then execute it. Your job is not to write the code yourself — it is to spawn the right sub-agents, in the right order, each pointed at the right spec, hand them frozen contracts so their work fits together, bridge their outputs, and run a review gate at the end. When the user says **"go"**, begin at §10 (Execution).

This is the only file the user hands you. Everything else is either a **spec** (in `misc/docs/`, the source of truth for *what* to build) or an **output** (code you and the agents produce). This file is the *how, who, and in what order*.

---

## 0. What "go" means

On "go", you:

1. Read the specs listed in §2 for the phase you are entering (do not read all of them at once — read per workstream, as you dispatch it).
2. Create the repo skeleton (§3) if it does not exist.
3. Broadcast the frozen interface contracts (§4) — every agent builds against these, never against each other.
4. Execute the phases (§6) in dependency order. Within a phase, dispatch the parallel workstreams **in a single message** so they run concurrently.
5. After each phase, run its **gate** (§7). Do not enter the next phase until the gate passes.
6. Bridge outputs yourself between workstreams — you own integration; the agents own their slices.
7. Run the final **review gate** (§8) before declaring the build complete (§9).

You are allowed to re-dispatch an agent whose output fails its Definition of Done. You are not allowed to mark a workstream done because it "looks done" — DoD is a *measured or passing* result (§1).

---

## 0a. Git discipline — commit per workstream, push per phase

The repository already exists at `origin` (private, `main` branch, currently holding only `.gitignore`).

**Commit granularity is the workstream, not the phase.** Each workstream lands as its own commit the moment *its own* Definition of Done passes — do not hold it until the whole phase's gate closes, and do not bundle two workstreams into one commit even if they finished at the same time. A phase's gate (§7) is a checkpoint for advancing to the next phase; it is not a commit boundary. This keeps history bisectable: a regression in one workstream is isolated from every other workstream that happened to land nearby, and the log reads as real engineering history rather than six giant lumps.

- **One commit = one workstream's completed, DoD-passing output.** Only `git add` the paths that workstream owns (§6's ownership table) — never sweep in another workstream's in-progress files.
- Commit messages describe what that workstream added, e.g. `Add neuro-symbolic scoring engine and extractor fixtures` (WS1), `Add clinical state graph and scenario bank` (WS7), `Add voice pipeline and session orchestration` (WS4). No workstream codes needed in the message if the content is clear.
- **Never add Claude as a co-author or author.** Commits are the user's. Do not append `Co-Authored-By` lines or any "generated with" trailer.
- **Never commit anything `.gitignore` excludes** — verify with `git status` before every commit; calibration raw data, session audio, model weights and secrets must never be pushed.
- Before the first commit, and periodically thereafter, verify no forbidden strings entered any file: `grep -riE "cruzhacks|hackathon" src/ frontend/ docs/` returns nothing.
- **Push after each phase completes** (not after every individual workstream commit) — so `origin` receives one clean batch of workstream commits per phase, but the commits themselves stay separated by workstream within that push.

Sequence per workstream: its DoD passes → `git add` only its owned paths → `git status` (confirm nothing ignored slipped in, confirm nothing from another workstream is staged) → `git commit` (user identity, no co-author). Sequence per phase: all its workstreams committed → `git push origin main`.

---

## 1. Golden rules — every agent inherits these

Put these at the top of every sub-agent prompt you write. A change that violates one is wrong by definition.

1. **The model generates and extracts. Deterministic code decides anything consequential. The human decides ultimately.** No model output reaches a `critical` finding, a stored score, or a user without a deterministic check or a human gate in front of it.
2. **Ground truth by construction** — never ask a model to judge what code can check.
3. **Every layer ships an eval or a test.** No capability is "done" without a passing test (software) or a measured number (model quality).
4. **Honest reporting.** Rates and uncertainty, never false precision. No fabricated numbers, ever — if a metric has not been measured, it is `—`, not a plausible guess. (`misc/plans/metrics-snapshot.md` is the only place real numbers live.)
5. **Prompts are code** — versioned, diffed, and any change reruns the eval suite.
6. **Money-and-severity paths use `Decimal` and typed enums, never floats or bare strings.** Python 3.12, full type hints, `ruff` clean, `mypy` clean.
7. **Build against the frozen contract (§4), not against a sibling workstream.** If you need a contract changed, stop and raise a contract-change note to the orchestrator — do not fork the schema.
8. **Own only your paths (§6).** Never edit a file owned by another workstream. If two workstreams need the same file, that is an orchestration bug — raise it.

---

## 2. Source-of-truth specs — where each agent reads *what* to build

Each workstream's agent is pointed at exactly the docs it needs. Do not make an agent read the whole set.

| Spec | Defines | Feeds workstream |
|---|---|---|
| `misc/docs/03-system-architecture.md` | Planes, components, session state machine, trust boundaries, event log | ALL (read first, by you) |
| `misc/docs/15-workstreams.md` | The authoritative workstream breakdown, file ownership, frozen contracts | ALL (this file operationalises it) |
| `misc/docs/06-scoring-engine.md` | Neuro-symbolic scorer, extractors, merge logic, worked examples | WS1 |
| `misc/docs/07-data-and-scenarios.md` | Clinical state graph, scenario schema, scenario bank | WS2, WS7 |
| `misc/docs/04-ai-engineering.md` | Agent roster, information isolation, context assembly, prompt-opt | WS3, WS5, WS6 |
| `misc/docs/05-voice-pipeline.md` | Latency budget, barge-in, turn-taking, memory layout, degradation | WS4 |
| `misc/docs/11-backend-api.md` | Endpoints, real-time protocol, SQLite schema | WS-API |
| `misc/docs/09-ui-ux.md` + `misc/docs/10-frontend-spec.md` | Screens, design tokens, component states, accessibility | WS8 |
| `misc/docs/08-evals.md` | Every metric, gate, the eval harness | WS9 |
| `misc/docs/14-testing-strategy.md` | Software test strategy (distinct from model evals) | WS-TEST + every agent |
| `misc/docs/12-security-privacy.md` | Threat model, data inventory, responsible use | Review gate (§8) |
| `misc/docs/13-deployment-ops.md` | Packaging, CI, release gates, runbooks | WS-OPS |
| `misc/SETUP.md` §6 | The calibration protocol — **human-only** (§5) | Human, not an agent |
| `misc/CONTRIBUTING.md` | Code standards, how to add an extractor/scenario/prompt | Every agent |

---

## 3. Repo skeleton (Phase 0 — create before anything else)

Dispatch **`engineering-backend-architect`** to scaffold this exactly (paths are load-bearing — the ownership map in §6 depends on them):

```
rehearsal/
├── pyproject.toml                 # deps, ruff, mypy, pytest config
├── Makefile                       # already exists in misc/ — move to root, it is the command surface
├── src/rehearsal/
│   ├── contracts/                 # §4 frozen schemas as Python types — the shared spine
│   ├── scoring/                   # WS1: extractors/, taxonomy.py, merge.py, engine.py
│   ├── scenarios/                 # WS7: state graph, bank, composer
│   ├── agents/                    # WS3+WS5: clinician, patient, coach, grader, isolation
│   ├── voice/                     # WS4: capture, stt, tts, turn-taking, budget  (NOTE: budget.py lives in runtime/, see docs)
│   ├── runtime/                   # WS4: budget.py, scheduler, model residency
│   ├── orchestrator/              # WS4: session FSM, event log, turn scheduling
│   ├── store/                     # WS-API: SQLite, content-addressed blobs
│   ├── api/                       # WS-API: FastAPI app, real-time channel
│   ├── optimise/                  # WS6: prompt-optimisation loop, metric.py
│   ├── evals/                     # WS9: harness, calibrate, leakage_ab, latency
│   └── cli.py                     # session/report entry points
├── frontend/                      # WS8: the SPA
├── data/                          # git-ignored: calibration/, sessions/, fixtures/, scenarios/
├── tests/                         # WS-TEST + per-workstream tests
└── docs/  misc/  README.md        # already present
```

**Gate P0:** `pyproject.toml` installs clean; `ruff`, `mypy`, `pytest` run (empty is fine); the tree matches above. Then you personally write `src/rehearsal/contracts/` from §4 and commit it — this is the one thing you do not delegate, because everything builds against it.

---

## 4. FROZEN INTERFACE CONTRACTS — freeze these before any parallel work

These are the seams between workstreams. Write them as typed, immutable Python (`@dataclass(frozen=True, slots=True)` + enums) in `src/rehearsal/contracts/`. **Once broadcast, they do not change without a contract-change note re-broadcast to every affected agent.** The full authoritative schemas are in `misc/docs/15-workstreams.md` and `misc/docs/11-backend-api.md`; the shapes below are the binding summary.

```python
# The taxonomy — a closed enum, nine values (misc/docs/06 §3)
class ErrorType(Enum):
    OMISSION; ADDITION; SUBSTITUTION; DISTORTION; EDITORIALIZATION
    ROLE_EXCHANGE; REGISTER_SHIFT; FALSE_FLUENCY; FIRST_PERSON_VIOLATION

class Severity(Enum): CRITICAL; NON_CRITICAL

# A single finding — the atom of scoring output (misc/docs/06)
Finding = { type: ErrorType, severity: Severity,
            source_span: Span|None, rendering_span: Span|None,
            note: str, provenance: "extractor"|"model", confidence: float }

# One interpreted turn (misc/docs/03, 11)
TurnRecord = { turn_id, session_id, direction: "en_to_es"|"es_to_en",
               source_utterance: str, source_lang, rendering_transcript: str,
               audio_blob_hash: str|None, timestamps: {...} }

# The scorer's output for a turn (misc/docs/06, 08)
ScoreRecord = { turn_id, findings: list[Finding],
                extractor_findings: list[Finding], model_findings: list[Finding],
                grader_prompt_version: str, model_versions: {...}, seed: int }

# A scenario (misc/docs/07)
ScenarioRecord = { scenario_id, schema_version: "1.0.0", clinical_state: ClinicalState,
                   difficulty: {...}, term_manifest: [...], review: {status, reviewer} }

# The clinical state graph that drives the patient agent (misc/docs/07)
ClinicalState = { condition, medications:[{name,dose,unit,route,frequency_per_day,duration}],
                  symptom_timeline:[{offset, symptom}], allergies:[{substance}],
                  emotional_state, health_literacy, language_variety, onset }

# Real-time channel messages (misc/docs/11)
SessionEvent = one of: turn_started | partial_transcript | turn_committed
             | score_ready | coach_interjection | session_ended
```

**Contract rule for agents:** you import from `rehearsal.contracts`. You never redefine these shapes locally. A field you wish existed is a contract-change request, not a local addition.

---

## 5. The one task no agent may do — human calibration labels

`misc/SETUP.md` §6 defines 40 hand-labelled interpreting turns (25 dev / 15 sealed test) that anchor every accuracy number the system reports. **If a model generates these labels, the evaluation is circular and every downstream number is worthless.**

- You (the orchestrator) may build everything up to and including the eval *harness* (WS9) and the *fixtures* for the deterministic extractors.
- You may **not** generate the calibration labels, and you may not let any agent do so.
- Any DoD that reads "reports κ / critical-recall" is **gated on the human calibration set existing**. Until it does, mark those DoDs `BLOCKED-ON-HUMAN` and the metric cells stay `—`. This is expected, not a failure.

Surface this to the user explicitly when you reach WS9: *"the eval harness is built and green on synthetic fixtures; the accuracy numbers await your 40 hand-labelled turns per misc/SETUP.md §6."*

---

## 6. The workstreams — agent, ownership, contract, DoD

Each block is a dispatch spec. When you launch a workstream, its prompt = Golden Rules (§1) + its spec docs (§2) + the frozen contracts (§4) + the block below.

### WS1 — Scoring engine  ·  agent: `engineering-ai-engineer`
- **Owns:** `src/rehearsal/scoring/**`, `tests/scoring/**`, `data/fixtures/extractors/**`
- **Reads:** `misc/docs/06-scoring-engine.md`, `misc/docs/08-evals.md` §extractors
- **Consumes:** `contracts` (Finding, ScoreRecord, TurnRecord)
- **Produces:** the neuro-symbolic scorer: deterministic extractors (`entities, numbers, dosage, frequency, negation, laterality, allergy` — **NOT `temporal`; it is specified-but-unimplemented, capped at `non_critical` per the banner in 06 §4.10**), the single structured model call for semantic residue, `merge.py`, `engine.py`.
- **DoD (measured):** `extractor_conformance = 1.00` on the fixture grid (every extractor, both languages, incl. Spanish-diacritic / decimal-comma / negation-scope / laterality traps); property tests pass (every finding quotes real text; critical severity never silently downgraded; no finding without a span); `ruff`+`mypy` clean.
- **Blocks:** WS9, and the whole scoring path. **Build first.**

### WS7 — Data & scenario bank  ·  agent: `engineering-data-engineer`
- **Owns:** `src/rehearsal/scenarios/**`, `data/scenarios/**`, `tests/scenarios/**`
- **Reads:** `misc/docs/07-data-and-scenarios.md`
- **Consumes:** `contracts` (ScenarioRecord, ClinicalState)
- **Produces:** the clinical-state schema + validator; the `TermManifest` generator (rule-based surface-form expansion — **a model never authors a manifest entry**); the scenario bank loader with the hard gate `ScenarioBank.get()` raising `ScenarioNotApproved` (no `--force`, no override flag); 3–5 seed scenarios, human-review-gated.
- **DoD:** a scenario round-trips through validation; an unapproved scenario cannot load (test proves it); the manifest generator's output feeds WS1's extractors as ground truth (contract test). *Note the open research gap:* corpus sourcing for realism is unresolved (`docs/01-research.md` §6) — seed scenarios are hand-authored until it is.
- **Blocks:** WS3 (patient agent needs clinical state), WS9 (evals need scenarios).

### WS3 — Counterpart & coach agents  ·  agent: `engineering-ai-engineer`
- **Owns:** `src/rehearsal/agents/clinician.py`, `patient.py`, `coach.py`, `prompts/**`, `tests/agents/**`
- **Reads:** `misc/docs/04-ai-engineering.md`
- **Consumes:** `contracts` (ClinicalState, SessionEvent), WS7's state graph
- **Produces:** the raw-loop clinician & patient agents driven by clinical state (they *verbalise* state, never invent clinical fact), the coach agent, versioned prompts.
- **DoD (measured):** persona-consistency rate (deterministic check against the state graph over a full session — did the agent contradict its own med list?); clinical-fact-invention rate = 0 (any non-zero is a defect). Prompts carry version front-matter.
- **Blocks:** WS4 (orchestration needs the agents), WS5.

### WS5 — Multi-agent isolation  ·  agent: `engineering-ai-engineer` (or `security-appsec-engineer` for the isolation test)
- **Owns:** `src/rehearsal/agents/isolation.py`, `tests/agents/test_leakage.py`
- **Reads:** `misc/docs/04-ai-engineering.md` §isolation, `misc/docs/08-evals.md` §leakage
- **Produces:** the enforced context-allowlist boundary (clinician/patient agents structurally cannot see the rubric or learner model) + the **leakage A/B test** that proves it (induced error rate with vs without rubric exposure).
- **DoD (measured):** the allowlist is enforced in code (a test proves the patient agent's context never contains rubric text); the leakage A/B harness runs and reports both arms. If the two arms are equal, that is reported honestly as "isolation not yet shown to matter," not hidden.
- **Blocks:** nothing downstream, but gates the multi-agent claim.

### WS4 — Voice pipeline + session orchestration  ·  agent: `engineering-backend-architect` (voice/runtime) + bridge
- **Owns:** `src/rehearsal/voice/**`, `src/rehearsal/runtime/**`, `src/rehearsal/orchestrator/**`, `tests/runtime/**`
- **Reads:** `misc/docs/05-voice-pipeline.md`, `misc/docs/03-system-architecture.md` §state-machine
- **Consumes:** `contracts` (TurnRecord, SessionEvent), WS3 agents, WS1 scorer
- **Produces:** STT-in / TTS-out pipeline, barge-in, endpointing, `runtime/budget.py` (the single latency-budget source), the deterministic scheduler that runs the grader **off the critical path**, the session FSM (`CAPTURED→EXTRACTED→REVIEWED→COMPUTED→REPORT`) with crash-resume, the append-only event log.
- **DoD (measured):** latency conformance to `runtime/budget.py` on reference hardware (p95 turn latency within budget); grader completes before the next turn commits; FSM property test proves **no path reaches a scored REPORT without the human-confirmation event**; fault-injection tests land in named safe states.
- **Blocks:** WS-API (API needs the orchestrator), WS8 (frontend needs live events).

### WS-API — Backend & persistence  ·  agent: `engineering-backend-architect`
- **Owns:** `src/rehearsal/store/**`, `src/rehearsal/api/**`, `tests/api/**`
- **Reads:** `misc/docs/11-backend-api.md`
- **Consumes:** `contracts` (all), WS4 orchestrator
- **Produces:** the SQLite schema (sessions, turns, findings, scenarios, clinical_states, learners, skill_estimates, calibration_items, eval_runs, audio_blobs), content-addressed audio storage, the FastAPI surface, the real-time SSE/WebSocket channel emitting `SessionEvent`s.
- **DoD:** every endpoint has a contract test (request/response schema); the real-time channel replays a session from the event log; DB migrations run clean; no network egress in the core loop (boundary test).
- **Blocks:** WS8.

### WS8 — Frontend  ·  agent: `engineering-frontend-developer` (design already specced)
- **Owns:** `frontend/**`
- **Reads:** `misc/docs/09-ui-ux.md`, `misc/docs/10-frontend-spec.md`
- **Consumes:** WS-API endpoints + real-time channel (build against the API contract, mock it if WS-API lags)
- **Produces:** the SPA — scenario picker, pre-flight (incl. the headphone check), the three-panel encounter view with the directional cue, turn review, session report (radar **+ mandatory bar-chart alternative**), progress dashboard, trainer review queue, settings incl. transcript-only mode. Design tokens from `09-ui-ux.md` §2. Bilingual (`lang` per node), WCAG 2.1 AA.
- **DoD:** automated a11y scan clean (axe-class) + scripted keyboard-only path + screen-reader reading-order check on the encounter view; every component's states (default/loading/streaming/error/empty/disabled) present; no missing-string i18n leak; renders against the mocked API contract.
- **Blocks:** nothing.

### WS9 — Evaluation harness  ·  agent: `engineering-ai-engineer`
- **Owns:** `src/rehearsal/evals/**`, `tests/evals/**`
- **Reads:** `misc/docs/08-evals.md`
- **Consumes:** `contracts`, WS1 scorer, WS7 scenarios, the (human) calibration set
- **Produces:** `calibrate` (grader vs human labels → κ, per-category precision/recall, false-positive rate, all beside the human ceiling), `critical_recall` (the safety gate), the leakage A/B runner (with WS5), latency conformance, the append-only eval registry, `make evals` with the snapshot-diff reminder.
- **DoD:** harness runs green on **synthetic fixtures**; the DEV/TEST split discipline is enforced in code (TEST cannot be read during optimisation); **the accuracy numbers themselves are `BLOCKED-ON-HUMAN` until the calibration set exists (§5).**
- **Blocks:** WS6, and every public accuracy claim.

### WS6 — Prompt-optimisation loop  ·  agent: `engineering-prompt-engineer`
- **Owns:** `src/rehearsal/optimise/**`, `tests/optimise/**`
- **Reads:** `misc/docs/08-evals.md` §5 (the objective is defined *once*, there — do not restate it)
- **Consumes:** WS9 harness, the calibration DEV split
- **Produces:** the DSPy/GEPA-style loop that optimises the grader prompt against `optimisation_metric()` (hard `critical_recall` floor + weighted objective), optimising on DEV, reporting on the sealed TEST split.
- **DoD:** the loop runs and records (optimiser, trial count, DEV trajectory, prompt versions) to the eval registry; **the before/after delta is `BLOCKED-ON-HUMAN`** until the calibration set exists; no TEST leakage (test proves it).
- **Blocks:** nothing.

### WS-OPS — Packaging & CI  ·  agent: `engineering-devops-automator`
- **Owns:** `.github/**`, packaging config, `misc/docs/13` runbook stubs
- **Reads:** `misc/docs/13-deployment-ops.md`
- **Produces:** the CI pipeline (lint → types → unit → contract → evals-on-fixtures, in dependency order), the release gate wiring (the eval gates from `08-evals.md`), the model fetch-and-verify step, the offline-install bundle path. Observability without telemetry (local logs only).
- **DoD:** `make check` is the green pre-commit gate; CI blocks on any gate failure; no telemetry egress.

### WS-TEST — Cross-cutting test strategy  ·  agent: `test-writer`
- **Owns:** shared fixtures, `tests/conftest.py`, the fault-injection harness
- **Reads:** `misc/docs/14-testing-strategy.md`
- **Note:** each workstream writes its *own* unit/property tests (Golden Rule 3). This agent owns the *shared* surface: cross-workstream contract tests, the fault-injection fixtures, the a11y/i18n test rigs, and the flaky-test policy. Dispatch it alongside Phase 3 so it can build the integration test surface as the pieces land.

---

## 7. Phases, parallelism, and gates

Dispatch each phase's workstreams **concurrently** (one message, multiple agent calls). Do not start a phase until the prior gate is green. You bridge between workstreams — when WS3 produces an agent interface WS4 consumes, you wire it, you don't ask an agent to reach into another's files.

| Phase | Workstreams (parallel) | Gate to advance |
|---|---|---|
| **P0 Scaffold** | skeleton (§3) → then you write `contracts/` | tree present; `contracts/` committed; toolchain runs |
| **P1 Foundations** | WS1 (scoring) ‖ WS7 (data) | `extractor_conformance = 1.00`; scenario approval-gate test passes |
| **P2 Agents & runtime** | WS3 (agents) ‖ WS4 (voice/orchestration) ‖ WS5 (isolation) | persona-consistency measured; FSM human-gate invariant proven; latency within budget; leakage A/B runs |
| **P3 Surface** | WS-API ‖ WS8 (frontend) ‖ WS-TEST | endpoint contract tests green; a11y scan clean; real-time replay works |
| **P4 Measurement** | WS9 (evals) ‖ WS6 (prompt-opt) ‖ WS-OPS (CI) | harness green on fixtures; DEV/TEST split enforced; `make check` green *(accuracy numbers `BLOCKED-ON-HUMAN`)* |
| **P5 Review** | the review gate (§8) | all of §8 green |

**Bridging is your job at each seam:** scorer→orchestrator, agents→orchestrator, orchestrator→API, API→frontend, scorer+scenarios→evals. If a bridge reveals a contract gap, issue a contract-change note (§4) and re-broadcast — never let one agent silently adapt another's schema.

---

## 8. The review gate — run at the end, before "complete"

Dispatch these **in parallel**, each over the full working tree / diff. Collect all findings, then you triage and dispatch fixes.

1. **`code-reviewer`** — correctness, the Golden Rules (§1) actually enforced in code (especially Rule 1: no model output reaching a consequential decision unguarded), needless complexity. Report most-severe-first.
2. **`security-appsec-engineer`** — against `misc/docs/12-security-privacy.md`: prompt-injection defence (untrusted scenario/corpus text can't trigger actions — schema-constrained outputs, closed tool vocabularies), no network egress in the core loop, no secrets, local-store encryption, the "no real patient data" enforcement.
3. **`test-writer`** — coverage audit: every deterministic extractor table-driven; the FSM human-gate invariant tested; fault-injection lands in named states; contract tests exist at every seam. Fill the gaps it finds.
4. **`critic`** — one adversarial pass: "where does the build quietly diverge from the docs, and where does a claim (a comment, a metric, a DoD) outrun what the code/tests actually establish?" This is the coherence check that caught the taxonomy and fabricated-metric problems in the docs; run it on the code too.

**Then verify the release gates from `misc/docs/08-evals.md` mechanically:** `extractor_conformance = 1.00`; `make check` green; the FSM invariant test green; no-egress test green. Accuracy gates (`critical_recall`, κ) remain `BLOCKED-ON-HUMAN` and are reported as such, not faked.

Loop: apply fixes → re-run the relevant reviewer → until each returns clean or an accepted-risk note.

---

## 9. Definition of "build complete"

☐ Repo skeleton + `contracts/` committed, matching §3–§4
☐ P1–P4 gates all green
☐ `make check` green (lint, types, unit, contract, evals-on-fixtures)
☐ `extractor_conformance = 1.00`
☐ FSM human-gate invariant proven by test; no path to a scored REPORT bypasses it
☐ Leakage A/B harness runs; isolation enforced in code
☐ Frontend a11y scan clean; bilingual; renders against the API contract
☐ Review gate (§8) returns clean or accepted-risk notes on all four agents
☐ No telemetry egress; no secrets; no real patient data path
☐ Accuracy metrics correctly showing `—` / `BLOCKED-ON-HUMAN` (not fabricated), with the surfaced note pointing the user to `misc/SETUP.md` §6
☐ `git status` clean of anything `.gitignore` should catch (calibration raw, audio, secrets)

When all of the above hold, report to the user: what was built, what each review agent found and how it was resolved, and the one remaining human action (the 40 calibration labels) that unblocks the accuracy numbers.

---

## 10. Execution (this is what you do on "go")

1. **Read** `misc/docs/03-system-architecture.md` and `misc/docs/15-workstreams.md` — the two orientation docs.
2. **P0:** dispatch `engineering-backend-architect` to scaffold §3. On its return, you write `src/rehearsal/contracts/` from §4, commit it as its own commit, and broadcast the contracts.
3. **P1:** dispatch WS1 + WS7 concurrently. As each workstream's DoD passes, commit it separately (§0a) — do not wait for the other to finish. Gate. Push.
4. **P2:** dispatch WS3 + WS4 + WS5 concurrently. Bridge scorer↔orchestrator, agents↔orchestrator. Commit each workstream separately as it passes DoD. Gate. Push.
5. **P3:** dispatch WS-API + WS8 + WS-TEST concurrently. Bridge orchestrator↔API↔frontend. Commit each workstream separately as it passes DoD. Gate. Push.
6. **P4:** dispatch WS9 + WS6 + WS-OPS concurrently. Commit each workstream separately as it passes DoD. Gate (accuracy `BLOCKED-ON-HUMAN`). Push.
7. **P5:** run the review gate (§8), triage, fix, re-review. Commit fixes per the reviewing agent that prompted them, not as one bulk commit.
8. **Report** per §9.

Never fabricate a number to fill a gate. Never let a model decide a `critical` finding. Never let an agent edit another's files. Bridge, gate, review — that is the whole job.

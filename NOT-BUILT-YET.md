# Not built yet

Tracked separately from BUILD.md so real hardware/host/model gaps don't get lost in commit messages. Update this file whenever a phase finishes with a deliberately deferred piece — do not silently let it disappear once the surrounding code "looks done."

---

## P0 — Scaffold

Nothing deferred.

## P1 — Foundations (WS1 scoring, WS7 data)

- **No `temporal` extractor.** Specified in `misc/docs/06-scoring-engine.md` §4.10 as specified-but-unimplemented, capped at `non_critical` if ever stubbed. Dosage-timing distortions outside the 6 implemented categories (numbers, dosage, frequency, negation, laterality, allergy, entities) aren't caught.
- **All 5 seed scenarios are `review.status="pending"`, agent-authored, unreviewed.** `ScenarioBank.load_all()` returns nothing until a human reviews and approves them (hard gate, no override — by design, per BUILD.md §5). Nobody has done this yet.
- **Extractors compare source-text-as-ground-truth vs rendering, not manifest-vs-rendering** — `TurnRecord` in the frozen contract carries no manifest field yet, so the "real" ground-truth-by-construction comparison against a scenario's term manifest isn't wired.
- **`entities`/`allergy`/`laterality` extractors use a small built-in bilingual lexicon** standing in for a real `TermManifestSlice` from the scenario/content plane.
- **Grader is a `Protocol` + `StubGraderClient` only** — no live model call. Merge policy currently forces every grader-origin finding to `non_critical` unconditionally, since there's no manifest-anchoring yet to conditionally admit a grader-critical finding.

## P2 — Agents & runtime (WS3 agents, WS4 voice/orchestration, WS5 isolation)

- **No real model host anywhere.** No MLX, no llama.cpp, no `rehearsal-live`/`rehearsal-grader` processes. `ClinicianAgent`/`PatientAgent` run against a `ScriptedModelClient` — deterministic templates over `ClinicalState`, not an actual model. The `LiveModelClient` Protocol is the seam a real implementation fills in later.
- **No real audio I/O.** No CoreAudio/sounddevice, no microphone, no speaker output. `AudioIO` is a Protocol with a `FakeAudioIO` for tests only.
- **No real VAD.** No Silero/ONNX, no RMS-based fallback. `EndpointPolicy`/`Endpointer` are driven by synthetic `P(speech)` float streams in tests, never real audio frames.
- **No real TTS.** No neural backend, no `SystemVoiceTTS` fallback. `SourceChunker` (text → speakable chunks) is built and tested, but nothing synthesizes audio from a chunk.
- **No real barge-in detection, no EchoGuard, no headphone/echo-coupling check.** All of §7 and §9 of `misc/docs/05-voice-pipeline.md` (echo, feedback, barge-in cancellation sequence) is unimplemented — the FSM has the *states* for it (`source_speaking` → `rendering_capturing` on barge-in) but nothing produces that trigger from real audio.
- **No GPU admission control, no host process model, no memory-layout enforcement.** `misc/docs/05` §8/§10 — the scheduling machinery that keeps a real grader off the critical path when there's an actual GPU to contend for.
- **No real latency numbers.** `runtime/budget.py`'s `BudgetGuard` logic is proven correct against a synthetic/fake clock only. There is no p95 `T_gap`, no `barge_in_stop_ms`, no measurement on any reference hardware. Every number in `misc/docs/05` §3 is still aspirational.
- **`rehearsal.config.SessionConfig` doesn't exist yet.** `orchestrator/loop.py` uses a local `RunConfig` stand-in with matching field names — a one-line swap once the real module lands, but nothing currently imports a frozen `SessionConfig`.
- **`ClinicalStateGraph`/`GraphNode` traversal doesn't exist yet.** WS7 shipped `ClinicalState` (the flat fact set) and validation, but not graph nodes/edges/traversal per `misc/docs/07-data-and-scenarios.md` §4. `scheduler.py`/`loop.py`/`agents/model_client.py`'s `ConversationNode` are minimal structural stand-ins (just enough fields to compile and test against), not the real graph.
- **Leakage A/B has no behavioral number.** WS5's harness proves the isolation *mechanism* works (allowlist enforced, canary catches crude injection, `context_sha` differs between arms) but cannot report a session-level fidelity delta without a live model host to actually run sessions through both arms. Reported honestly as `—`, not fabricated.

## P3 — Surface (WS-API, WS8 frontend, WS-TEST)

- **Frontend is UI-shell only, not wired to a live backend.** `main.ts` only routes `#/encounter` against a fresh empty `SessionStore` — no WebSocket session actually runs end-to-end through the browser yet. `#/report` isn't routed; report rendering is exercised directly by tests (`mountReportView(container, report)`), not through real navigation.
- **6 of the ~8 planned views are landmark-correct empty stubs** (`stub-view.ts`): scenario-picker, preflight, progress, library, review, settings. Only encounter and report are built full-depth.
- **`components/progress/**` and `components/review/**` are empty**, unwired to any route.
- **Charts are hand-written inline SVG, not `uplot`** (a declared dependency) — jsdom has no `<canvas>` 2D context and this repo doesn't install the native `canvas` package, so a canvas-based chart would fail under the mandated jsdom test environment. Revisit if/when tests move to a real browser environment.
- **No error-span highlighting in the turn-by-turn diff.** `mark.span` CSS classes exist in `base.css`, unused — the report view shows findings as a list, not inline-marked in the source/rendering text.
- **Settings view isn't wired to `store/settings.ts`'s theme/locale toggles** — lowest priority, nothing depends on it yet.
- **No SQLite migrations tooling, no `rehearsal doctor`.** WS-API built the event store, blob store, and projections directly; a formal migration runner wasn't in scope.

## P4 — Measurement (WS9 evals, WS6 prompt-opt, WS-OPS CI)

- **EV-01 (κ), EV-02 (critical_recall), EV-03 (human ceiling) are BLOCKED-ON-HUMAN.** `data/calibration/dev.jsonl`, `test.jsonl`, `relabel.jsonl`, `rater2.jsonl` don't exist — only unlabelled `items.jsonl`. Every accuracy number in the project is downstream of this. Unblocks via `misc/SETUP.md` §6 (a human labels 40 items) — see `data/calibration/README.md` and `tools/label_quiz*.py`, already built.
- **The prompt-optimisation loop has never run a real search.** WS6 built and proved the engineering (floor enforcement, regression rejection, no-TEST-leakage, honest 4-cell reporting) against synthetic candidates. There is no real `GraderProgram` search against real DEV data, because there's no real DEV data and no live grader model.
- **The eval registry has never recorded a real (non-fixture) run.** SQLite append-only mechanism is proven correct; `data/evals/registry.db` doesn't persist any committed run yet.
- **CI covers 6 of the 12 documented stages** (lint, types, test, frontend, evals-on-fixtures, a static no-egress check). Not built: `migrations` (no migration runner exists), `integration` (no dedicated stub-host session-flow test dir), `package`/`offline-install`/`smoke` (no wheel, no bundle, no `rehearsal doctor`/`replay --verify`), `evals-full` (no reference hardware, no model weights). None of these are faked — CI simply doesn't claim to run them.
- **`.gitignore` doesn't cover `data/evals/registry.db`/`data/evals/runs/`.** A real eval run leaves `data/evals/` untracked-but-visible in `git status`. Noticed by WS9, not fixed (outside its ownership) — small gap, fix when someone runs a real eval locally and notices the clutter.

## P5 — Review gate (code-reviewer, security-appsec-engineer, test-writer, critic)

- **The out-of-scope Ollama commit (536fbcb) has now been reviewed and its findings fixed** — see below, this replaces the old "not yet checked" P-extra note.
- **WS-API (`src/rehearsal/api/`, `src/rehearsal/store/`) had zero contract tests**, despite BUILD.md's WS-API DoD explicitly requiring them. This landed in the same out-of-band interruption window as the Ollama commit and never went through a proper WS-API dispatch — I only did lint/type/permission fixes on it, never built the contract-test suite its own DoD requires. Found by test-writer during P5, dispatched as its own follow-up pass. Store-layer tests (`tests/store/`) are done and committed; REST/WS endpoint tests (`tests/api/`) are in progress as of this note (needed `httpx` added as a dev dependency — user-approved — for `starlette.testclient.TestClient`).
- **Bug found while building the store tests: the event hash index is global, not scoped to `(session_id, hash)`.** `store/eventstore.py`'s `hash = sha256(prev_hash || kind || canonical_payload)` doesn't include `session_id`, but `0001_init.sql`'s `idx_events_hash` is a global `UNIQUE` index. Two sessions with byte-identical event histories up to some point (same kind, same payload — e.g. two `session.paused` events, which carry no distinguishing payload) would collide and the second `append()` raises `sqlite3.IntegrityError`, even though `verify()` is explicitly per-session-scoped. Practical risk is low today (`session.created` always carries a random 64-bit seed, which is most of what happens early in a session), but it's real. Documented via a locked-in reproduction test (`tests/store/test_eventstore.py::test_BUG_identical_payloads_across_sessions_collide_on_global_hash_index`), not fixed — the fix is a new migration changing the index to `UNIQUE(session_id, hash)`, a schema change, not a test-writer's call to make.
- **PHI-shape scanner is a cheap static regex sweep, not the layered ingest-gate defense misc/docs/12-security-privacy.md §6.2 describes.** `tests/test_no_phi_shaped_content.py` catches obvious SSN/MRN/phone/DOB-shaped strings in committed files only — no ingest-time gate, no UI affirmation step. Current content verified clean.
- **No CSP/`X-Content-Type-Options` headers on the API**, and the documented blob-serving endpoint (`GET /api/blobs/{sha256}`) doesn't exist. Low priority since the frontend isn't wired to a live backend yet (already tracked above), but should land before that wiring happens.
- **Consent/deletion machinery (misc/docs/12 §7) is entirely unimplemented** — no `consents` table, no `rehearsal forget`/`export`/`gc`. Likely legitimate current-phase scope (no workstream owns it yet), flagged so it isn't mistaken for done.

## Resolved at P5 — commit 536fbcb (Ollama model host + demo CLI)

Landed autonomously during a session interruption, never dispatched as a workstream, wasn't gate-checked before P5. Per the user's decision (2026-07-27) it was left in place and reviewed at the P5 gate rather than reverted. Findings and fixes (commit `88c4999`):

- **[Fixed, was HIGH]** The Ollama host string was unvalidated — a non-loopback host would send trainee speech over cleartext HTTP to wherever it pointed. `_ensure_loopback()` now refuses before any network call.
- **[Fixed, was MEDIUM-HIGH]** `OllamaLiveClient` bypassed `agents/isolation.py`'s single context-construction chokepoint entirely (hand-formatted prompt string). Now routes through `assemble()`, so the allowlist and rubric-vocabulary canary apply.
- **[Fixed, was MEDIUM]** The grader asked the model for raw character offsets (unreliable, and asking a model to supply something code should compute is a Golden Rule 1 smell); `merge.py`'s territory-overlap dedup silently no-ops on spanless findings, so real (non-fixture) grader findings never got deduped against extractor findings. The grader now asks for a verbatim quote and the span is computed in code via string search; `merge.py` drops any grader finding with no span at all.
- **[Fixed, was MEDIUM]** A live model's utterance was used as scoring ground truth with no check it actually conveys the facts it was asked to — undermining the "ground truth by construction" premise the whole scoring model depends on for anything but `ScriptedModelClient`. `check_facts_present()` is a coarse keyword-presence heuristic (NOT a replacement for real ground-truth-by-construction — it can miss a paraphrased dose that keeps every keyword) that flags likely-dropped facts; `cli.py`'s demo loop surfaces the warning visibly rather than silently trusting the output.
- **[Fixed, was MEDIUM]** Store/blob directories and files were created with default umask, not the `0700`/`0600` misc/docs/12 §3 T1 describes. Fixed in `store/db.py`/`store/blobs.py`.
- **[Fixed, was LOW]** `PITCH-STATS.md`'s one-liner claimed "we can prove our scoring agrees with human experts" in present tense — no calibration labels exist. Reworded, matching README's discipline.
- **[Still true, by design]** `merge.py`'s S11/S12 severity-forcing holds regardless of which grader client is used — a coaxed/malicious grader output can never reach `critical` severity. Verified end-to-end during review, not just by inspection.
- **[Known limitation, unresolved]** `check_facts_present` is a heuristic, not a guarantee — `ClinicianAgent`/`PatientAgent`'s "never invents a fact" docstring is proven true for `ScriptedModelClient` (by construction) but only checked-with-a-heuristic for `OllamaLiveClient`. No test coverage exists proving the guarantee holds for the live client the way it does for the scripted one.

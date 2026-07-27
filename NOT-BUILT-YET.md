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

## P-extra — out-of-scope work that landed without going through the workstream process

Commit `536fbcb` ("Add Ollama model host and text-mode demo CLI") landed autonomously during a session interruption, was never dispatched as a workstream, and wasn't gate-checked by the orchestrator before this note. Per the user's decision (2026-07-27), it's being left in place for now and will get scrutiny at the P5 review gate rather than being reverted or fixed ad hoc. Known facts about it, not yet verified:

- Adds `src/rehearsal/hosts/ollama.py` — a real live-model client wired to Ollama, contradicting every P1/P2 workstream's explicit "no real model host exists yet" scoping.
- Adds `rehearsal review` (scenario approval front door) and `rehearsal demo` (text-mode end-to-end session) CLI commands.
- Adds `ROADMAP.md`.
- Touches `src/rehearsal/cli.py`, which BUILD.md §3.1 assigns to WS4 — nobody on WS4 wrote this.
- Not yet checked against BUILD.md §1 golden rules (e.g. does the Ollama client's output reach a `critical` finding or a stored score without a deterministic check in front of it? Is there a human gate anywhere in the `rehearsal demo` path?).
- Not yet lint/type/test verified in isolation the way every other workstream's commit was.

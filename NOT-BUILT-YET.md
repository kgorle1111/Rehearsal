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

_(fill in as P3 lands)_

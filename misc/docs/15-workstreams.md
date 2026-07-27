# 15 — Workstreams & Interface Contracts

How several contributors — human engineers and AI coding agents — build Rehearsal in parallel without editing the same files, without waiting on each other, and without discovering at integration time that two halves of the system disagree about what a "turn" is.

This document contains no dates, no estimates and no schedule. Work is ordered by **dependency** only. A workstream is ready when the things it consumes exist; it is done when a **measured number** says so.

Sibling documents referenced here and never duplicated: `docs/03-system-architecture.md` (component catalogue, event log, state machine), `docs/06-scoring-engine.md` (merge rules, extractor semantics), `docs/05-voice-pipeline.md` (latency budgets, barge-in), `docs/08-evals.md` (every eval id, gate and statistical convention), `docs/09-ui-ux.md` (screens, design system application), `SETUP.md` §6 (the calibration set protocol).

---

## 1. The organising rule

> **A workstream owns files. A contract owns boundaries. Nothing else is shared.**

Three consequences, and they are the whole discipline:

1. **Exactly one workstream may write to any given path.** Not "should not" — the ownership table in §3 is the authority, and `make check` enforces it mechanically (§10.2). A contributor who needs a change in someone else's file files a contract-change note (§10.4) or opens an issue; they do not edit it.
2. **Workstreams build against the frozen schemas in §5, never against each other's code.** WS-1 does not import from WS-2. It imports from `rehearsal.contracts`. Every workstream can therefore be developed, tested and measured against fixtures before its neighbours exist.
3. **A workstream is done when its number exists, not when its author is satisfied.** Every Definition of Done in §3 is a value produced by a named eval on a named split. "Implemented" is not a state this project recognises.

This is the same rule that governs the runtime (principle 1: deterministic code decides anything consequential). Ownership and contracts are the deterministic layer of the *project*; the contributors are the stochastic part.

---

## 2. Workstream map

```
                        ┌──────────────────────────────┐
                        │ WS-0  Contracts & Store      │  must land alone, first
                        │ contracts/ store/ config.py  │
                        └───────────────┬──────────────┘
                                        │ (frozen schemas)
        ┌────────────┬──────────────┬───┴───────┬──────────────┬─────────────┐
        │            │              │           │              │             │
   ┌────▼────┐  ┌────▼─────┐  ┌─────▼────┐ ┌────▼─────┐  ┌─────▼────┐  ┌─────▼────┐
   │ WS-7    │  │ WS-1     │  │ WS-2     │ │ WS-3     │  │ WS-9     │  │ WS-8     │
   │ Data &  │  │ Scoring  │  │ Counter- │ │ Voice    │  │ Eval     │  │ Frontend │
   │ Scenario│  │ engine   │  │ part +   │ │ pipeline │  │ harness  │  │ + API    │
   │ bank    │  │ (L4)     │  │ state(L5)│ │          │  │          │  │          │
   └────┬────┘  └────┬─────┘  └────┬─────┘ └────┬─────┘  └─────┬────┘  └─────┬────┘
        │            │             │            │              │             │
        └────────────┴──────┬──────┴────────────┘              │             │
                            │                                  │             │
                    ┌───────▼────────┐                         │             │
                    │ WS-4  Session  │◄────────────────────────┘             │
                    │ orchestration  │                                       │
                    │ + skill (L6/L7)│───────────────────────────────────────┘
                    └───────┬────────┘
                            │
              ┌─────────────┴─────────────┐
              │                           │
      ┌───────▼────────┐         ┌────────▼─────────┐
      │ WS-5 Isolation │         │ WS-6 Prompt      │
      │ + coach (L8)   │         │ optimisation(L10)│
      └────────────────┘         └──────────────────┘

   ┌──────────────────────────────────────────────────────────────────┐
   │ HUMAN-ONLY, NON-DELEGABLE, BLOCKS WS-1 / WS-6 / WS-9 headline    │
   │ Calibration labelling — SETUP.md §6                              │
   └──────────────────────────────────────────────────────────────────┘
```

Arrows are dependency, not sequence. WS-1, WS-2, WS-3, WS-7, WS-8 and WS-9 run genuinely concurrently once WS-0 is frozen.

---

## 3. The workstream table

| # | Workstream | Owns (paths — exclusive write access) | Consumes | Produces | Definition of Done (measured) | Blocked by |
|---|---|---|---|---|---|---|
| **WS-0** | **Contracts & store** | `src/rehearsal/contracts/**`, `src/rehearsal/store/**` (incl. `migrations/`), `src/rehearsal/config.py`, `schemas/*.schema.json`, `docs/15-workstreams.md` | The frozen product spec; `docs/03-system-architecture.md` §9–§10 | The five frozen schemas (§5), generated typed models, `EventLog`, `BlobStore`, projections, migration `0001_init.sql` | Round-trip property test: 10 000 generated records for each of the five schemas serialise → persist → fold → deserialise identically (`pytest -k contracts_roundtrip`, 0 failures); hash-chain verification passes on a 500-event synthetic log; `rehearsal doctor --store` exits 0 | Nothing. This is the only workstream with no upstream. |
| **WS-1** | **Scoring engine (L4)** | `src/rehearsal/scoring/**` | `contracts.TurnRecord`, `contracts.ScenarioRecord.term_manifest`, `data/calibration/dev.jsonl`, `data/fixtures/extractors/*.jsonl` | `ScoreRecord` + `Finding[]`; the extractor suite; the single structured grader call; `VerdictMerger` | `extractor_conformance = 1.00` on the EV-00 fixture grid (no exceptions, per `docs/08-evals.md` §1.1); `critical_recall ≥ 0.90` and `kappa_macro ≥ 0.60` on **DEV**, both reported with intervals and beside `kappa_intra`; `fp_rate_clean ≤ 0.15` on DEV | WS-0; calibration DEV split (§6) |
| **WS-2** | **Counterpart agent + clinical state (L5)** | `src/rehearsal/runtime/agents/clinician.py`, `src/rehearsal/runtime/agents/patient.py`, `src/rehearsal/content/graph.py`, `prompts/clinician/`, `prompts/patient/` | `contracts.ScenarioRecord` (graph + personas), `ModelHostClient` (WS-3), `ContextAssembler` interface stub (WS-5) | `SourceUtterance` per turn incl. `heard_verbatim`; graph advance decisions; persona invariants | `persona_consistency ≥ 0.95` turn-level on EV-04 across ≥ 3 seeds, reported as a distribution; **rubric-vocabulary canary = 1.00** (binary, no tolerance); structured-output schema-validation failure rate ≤ 0.02 with the scripted-line fallback exercised in test | WS-0; WS-7 (at least one validated scenario); WS-3 (host client only) |
| **WS-3** | **Voice pipeline** | `src/rehearsal/runtime/audio_in.py`, `src/rehearsal/runtime/tts.py`, `src/rehearsal/runtime/hosts.py`, `src/rehearsal/runtime/budget.py` | Audio devices; MLX / llama.cpp runtimes; `contracts.SessionEvent` for `capture.*` / `tts.*` | `ModelHostClient`, `TTSRouter` (en-US / es-MX), VAD + endpointing, barge-in detection, `TurnBudget` constants measured per host class | `p95_first_audio_ms` and `p99_barge_in_stop_ms` both within the budget constants exported by `runtime/budget.py`, measured by EV-07 on the reference host class over ≥ 200 turns; `turn_capture_loss_rate ≤ 0.02`; echo-guard true-positive rate reported on a deliberate no-headphones fixture | WS-0 |
| **WS-4** | **Session orchestration + skill packaging (L6/L7)** | `src/rehearsal/orchestrator/**`, `skills/session-protocol/**`, `src/rehearsal/cli.py` | Everything above via contracts + interfaces; `ScoreQueue` handle (WS-1); `SourceUtterance` (WS-2); `AudioIO` (WS-3) | `SessionOrchestrator`, state machine, `SeedLedger`, `BudgetGuard`, `TurnScheduler`, crash-resume, the versioned session skill definition | `session_completion_rate ≥ 0.90` on EV-08 replay + live runs; `grader_backlog_rate ≤ 0.05` (proves principle 5 holds in practice); crash-resume determinism: 20 injected mid-turn kills replay to byte-identical event logs; `skill_delta` lower CI bound ≥ −0.02 on EV-06 | WS-0, WS-1, WS-2, WS-3 |
| **WS-5** | **Multi-agent isolation + coach (L8)** | `src/rehearsal/runtime/agents/context.py`, `src/rehearsal/learner/**`, `prompts/coach/` | `contracts.*` role allowlists; `ScoreRecord` (WS-1); session events (WS-4) | `ContextAssembler` (the single chokepoint every model context passes through), `IsolationViolation`, `LearnerModel`, `CoachAgent`, suppression rules | Static + runtime leak test: 0 rubric/learner tokens present in any clinician or patient context over a full EV-05 run (assertion, not sampling); `leakage_delta` reported as a **pre-registered** effect size with permutation p-value and CI on EV-05 — a null result is a reportable outcome, not a failure | WS-0, WS-2, WS-4 |
| **WS-6** | **Prompt-optimisation loop (L10 rung 1)** | `src/rehearsal/optimise/**`, `prompts/grader/**`, `plans/optimisation-log.md` | `data/calibration/dev.jsonl` as the metric; EV-01/EV-02 as the objective; the eval registry (WS-9) | A DSPy/GEPA-style optimiser over the grader prompt; versioned prompt files `grader/v1.md … vN.md`; before/after report | Before/after `kappa_macro` on the **sealed TEST split**, unsealed exactly once via `rehearsal-evals unseal --reason`, with the unseal recorded in `data/calibration/TEST_ACCESS.log`; the promotion is rejected if `critical_recall` regresses at all, regardless of κ gain | WS-0, WS-1, WS-9; calibration DEV split |
| **WS-7** | **Data + scenario bank** | `src/rehearsal/content/bank.py`, `src/rehearsal/content/terms.py`, `data/scenarios/**`, `data/fixtures/**`, `data/calibration/**` (files; **labels are human-produced only**, §6) | Clinical source material; the error taxonomy; `contracts.ScenarioRecord` | Validated scenarios with state graphs + term manifests; the extractor fixture grid; the calibration files as artefacts | `make scenarios` validates 100 % of the bank against the `ScenarioRecord` schema **and** the graph invariants (no dead-end node, every node reachable, every persona fact assigned to exactly one role); ≥ 1 scenario per encounter archetype in the bank; fixture grid covers every extractor × every documented edge case with 0 uncovered rows in the EV-00 coverage report | WS-0 |
| **WS-8** | **Frontend + API** | `frontend/**`, `src/rehearsal/api/**` | `contracts.SessionEvent` stream over `/ws/session/{id}`; `ScoreRecord` for the report view | The SPA (session view, review gate, fidelity report), the FastAPI surface, WS event fan-out and gap replay | Contract-driven: the SPA renders a full session from a **recorded event log fixture with no backend running** (fixture-replay test, 0 console errors); WCAG 2.1 AA automated audit passes with 0 violations on every screen in light **and** dark; keyboard-only traversal of the review gate completes without a mouse (recorded test); reconnect test recovers a 500-event gap with 0 dropped events | WS-0 (schemas only — deliberately *not* blocked by any runtime workstream) |
| **WS-9** | **Evaluation harness** | `src/rehearsal/evals/**`, `data/evals/**`, `plans/metrics-snapshot.md` | `EvalResult` contract; every workstream's outputs; calibration splits | `rehearsal-evals` CLI, the ten suites EV-00…EV-09, `metrics.py`, `seal.py`, the append-only run registry | Every suite in `docs/08-evals.md` §2.1 exists and returns a well-formed `EvalResult` **or** `SKIPPED` with a stated reason — no suite may be silently absent; the seal guard provably refuses TEST access without an `unseal` call (adversarial test asserts `SealViolation`); `record_run` refuses a dirty tree for `test`/`live` splits (asserted); registry append-only triggers verified by an attempted UPDATE and DELETE | WS-0 |

### 3.1 Cross-cutting files nobody owns exclusively

Four paths cannot be assigned to one workstream. They get a different rule, not an exception.

| Path | Rule |
|---|---|
| `pyproject.toml` | **Append-only within your own section.** Dependencies are added under a comment banner naming the workstream (`# WS-3: audio`). Never re-sort, never re-format the file. A new third-party dependency additionally requires a contract-change note (§10.4) — the stack in the spec is deliberate and stdlib-first. |
| `Makefile` | Append-only; one target block per workstream, banner-commented. Never edit another workstream's target. |
| `src/rehearsal/cli.py` | Owned by WS-4. Other workstreams expose an entry point in their own package and file a one-line contract-change note asking WS-4 to wire it. |
| `plans/metrics-snapshot.md` | Owned by WS-9. It is the single place headline numbers live; updated in the same working session as the run that changed them (`SETUP.md` §9). Nobody else writes numbers into it. |

---

## 4. What each workstream may and may not import

Import direction is a contract too, and it is the cheapest possible integration test.

| Workstream package | May import | Must never import |
|---|---|---|
| `rehearsal.contracts` | stdlib, `pydantic` | anything else in `rehearsal` |
| `rehearsal.store` | `rehearsal.contracts`, stdlib | any runtime, scoring, api or eval module |
| `rehearsal.scoring` | `rehearsal.contracts`, `rehearsal.store` (read models only) | `rehearsal.runtime`, `rehearsal.orchestrator`, `rehearsal.api` |
| `rehearsal.runtime` | `rehearsal.contracts`, `rehearsal.content` | `rehearsal.scoring`, `rehearsal.evals`, `rehearsal.learner` **(see §7 — this one is load-bearing)** |
| `rehearsal.content` | `rehearsal.contracts` | everything else |
| `rehearsal.orchestrator` | all of the above | `rehearsal.api`, `rehearsal.evals` |
| `rehearsal.api` | `rehearsal.contracts`, `rehearsal.store`, `rehearsal.orchestrator` | `rehearsal.runtime` internals (goes through the orchestrator) |
| `rehearsal.evals` | everything | — (it is the top of the graph) |
| `rehearsal.optimise` | `rehearsal.evals`, `rehearsal.scoring`, `rehearsal.contracts` | `rehearsal.runtime` |

Enforced by an import-linter rule run in `make check`. A violation is a build failure, not a review comment. The `runtime → scoring` ban is the one that matters most: it is the architectural expression of information isolation (principle 4), and it is checked by a machine rather than by a reviewer's memory.

---

## 5. Frozen interface contracts

These five schemas are agreed **before** parallel work begins. They live at `schemas/*.schema.json` (JSON Schema draft 2020-12) with generated Pydantic models in `src/rehearsal/contracts/`. Generation is one-way: edit the JSON Schema, run `make contracts`, commit both. Hand-editing the generated Python is a build failure.

Every schema is `"additionalProperties": false`. This is deliberate: a workstream that quietly adds a field is a workstream that has changed the contract without saying so.

### 5.1 Turn record

The unit of everything. Produced by WS-4 (orchestrator) with content from WS-2 (source) and WS-3 (capture); consumed by WS-1 (scoring), WS-8 (display), WS-9 (evals).

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://rehearsal.local/schemas/turn_record.schema.json",
  "title": "TurnRecord",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "turn_id", "session_id", "turn_index", "scenario_id", "node_id",
    "direction", "speaker_role", "source", "rendering", "seed", "timings", "status"
  ],
  "properties": {
    "turn_id":     { "type": "string", "pattern": "^trn_[0-9A-HJKMNP-TV-Z]{26}$" },
    "session_id":  { "type": "string", "pattern": "^ses_[0-9A-HJKMNP-TV-Z]{26}$" },
    "turn_index":  { "type": "integer", "minimum": 0 },
    "scenario_id": { "type": "string" },
    "scenario_version": { "type": "integer", "minimum": 1 },
    "node_id":     { "type": "string", "description": "Clinical state graph node that produced the source utterance" },
    "direction":   { "enum": ["en_to_es", "es_to_en"] },
    "speaker_role":{ "enum": ["clinician", "patient"] },

    "source": {
      "type": "object",
      "additionalProperties": false,
      "required": ["text", "lang", "text_sha256", "origin"],
      "description": "GROUND TRUTH BY CONSTRUCTION. The system generated this, so it is known exactly.",
      "properties": {
        "text":        { "type": "string", "minLength": 1 },
        "lang":        { "enum": ["en-US", "es-MX"] },
        "text_sha256": { "type": "string", "pattern": "^[a-f0-9]{64}$" },
        "origin":      { "enum": ["agent_generated", "scripted_fallback", "fixture"] },
        "audio_sha256":{ "type": ["string", "null"], "pattern": "^[a-f0-9]{64}$" },
        "term_ids":    { "type": "array", "items": { "type": "string" },
                         "description": "Term manifest entries the generator deliberately placed in this utterance" }
      }
    },

    "rendering": {
      "type": "object",
      "additionalProperties": false,
      "required": ["text", "lang", "text_sha256", "rendering_source"],
      "description": "What the trainee actually said.",
      "properties": {
        "text":            { "type": "string" },
        "lang":            { "enum": ["en-US", "es-MX"] },
        "text_sha256":     { "type": "string", "pattern": "^[a-f0-9]{64}$" },
        "audio_sha256":    { "type": ["string", "null"], "pattern": "^[a-f0-9]{64}$" },
        "rendering_source":{ "enum": ["native_verbatim", "offpath_retranscribe", "human_transcript"],
                             "description": "native_verbatim = heard_verbatim from the live agent's forward pass; see docs/03-system-architecture.md §7" },
        "verbatim_confidence": { "type": ["number", "null"], "minimum": 0, "maximum": 1 }
      }
    },

    "seed": { "type": "integer", "description": "Derived seed for this turn; from SeedLedger. Replay uses this exact value." },

    "timings": {
      "type": "object",
      "additionalProperties": false,
      "required": ["turn_opened_ms", "source_emitted_ms", "capture_started_ms", "capture_ended_ms"],
      "properties": {
        "turn_opened_ms":      { "type": "integer" },
        "source_emitted_ms":   { "type": "integer" },
        "first_audio_ms":      { "type": ["integer", "null"] },
        "capture_started_ms":  { "type": "integer" },
        "capture_ended_ms":    { "type": "integer" },
        "barge_in_stop_ms":    { "type": ["integer", "null"] }
      }
    },

    "status": { "enum": ["complete", "abandoned", "capture_lost", "blob_corrupt"] },
    "degrade_level": { "type": "integer", "minimum": 0, "maximum": 3 }
  }
}
```

**Why `source` and `rendering` are separate objects with separate hashes:** scoring is "compare known source to trainee rendering" (principle 2). Any code path that lets those two blur — a shared text field, a merged transcript — destroys the thing that makes the problem tractable. The schema makes the blur impossible to express.

### 5.2 Finding record

Produced by WS-1 (both extractors and grader); overridden by humans through WS-8; counted by WS-9. Mirrors `src/rehearsal/scoring/taxonomy.py` exactly — the Python dataclass and this schema are generated from the same source.

```json
{
  "$id": "https://rehearsal.local/schemas/finding.schema.json",
  "title": "Finding",
  "type": "object",
  "additionalProperties": false,
  "required": ["finding_id", "kind", "severity", "note", "origin"],
  "properties": {
    "finding_id": { "type": "string", "pattern": "^fnd_[0-9A-HJKMNP-TV-Z]{26}$" },
    "kind": {
      "enum": ["omission", "addition", "substitution", "distortion",
               "editorialization", "role_exchange", "register_shift",
               "false_fluency", "first_person_violation"]
    },
    "severity": {
      "enum": ["critical", "non_critical"],
      "description": "critical = could change clinical action: dosage, frequency, allergy, negation, laterality, symptom onset"
    },
    "span": {
      "type": ["array", "null"], "minItems": 2, "maxItems": 2,
      "items": { "type": "integer", "minimum": 0 },
      "description": "Char offsets into rendering.text. null for omissions — nothing was said."
    },
    "source_span": {
      "type": ["array", "null"], "minItems": 2, "maxItems": 2,
      "items": { "type": "integer", "minimum": 0 },
      "description": "Char offsets into source.text. Required when kind = omission."
    },
    "note": { "type": "string", "maxLength": 400 },
    "origin": { "enum": ["extractor", "grader", "human"] },
    "extractor_name": {
      "type": ["string", "null"],
      "enum": ["numbers", "dosage", "frequency", "negation", "laterality", "allergy", "temporal", null]
    },
    "confidence": {
      "type": ["number", "null"], "minimum": 0, "maximum": 1,
      "description": "Grader only. Extractors do not guess — an extractor finding is decidable or absent."
    },
    "status": {
      "enum": ["active", "overruled", "human_removed", "human_added"],
      "default": "active",
      "description": "Nothing is ever deleted. An overruled grader finding stays in the record; the disagreement rate is itself a reported number."
    },
    "overruled_by": { "type": ["string", "null"], "description": "finding_id of the winning finding" }
  },
  "allOf": [
    { "if":   { "properties": { "kind": { "const": "omission" } } },
      "then": { "required": ["source_span"] } },
    { "if":   { "properties": { "origin": { "const": "extractor" } } },
      "then": { "required": ["extractor_name"], "properties": { "confidence": { "const": null } } } }
  ]
}
```

The two `allOf` clauses are the schema doing work that would otherwise be a convention nobody remembers: an omission with no source span is unlocatable, and an extractor that emits a confidence has stopped being deterministic.

### 5.3 Score record

One per turn. Produced by WS-1, consumed by WS-4 (coach gating), WS-5 (learner model), WS-8 (report), WS-9 (agreement metrics).

```json
{
  "$id": "https://rehearsal.local/schemas/score_record.schema.json",
  "title": "ScoreRecord",
  "type": "object",
  "additionalProperties": false,
  "required": ["score_id", "turn_id", "session_id", "findings", "counts", "status", "provenance"],
  "properties": {
    "score_id":   { "type": "string", "pattern": "^scr_[0-9A-HJKMNP-TV-Z]{26}$" },
    "turn_id":    { "type": "string" },
    "session_id": { "type": "string" },

    "findings": { "type": "array", "items": { "$ref": "finding.schema.json" } },

    "counts": {
      "type": "object", "additionalProperties": false,
      "required": ["critical", "non_critical", "by_kind"],
      "properties": {
        "critical":     { "type": "integer", "minimum": 0 },
        "non_critical": { "type": "integer", "minimum": 0 },
        "by_kind":      { "type": "object", "additionalProperties": { "type": "integer", "minimum": 0 } }
      },
      "description": "Derived, never authored. WS-9 recomputes from findings and asserts equality."
    },

    "status": {
      "enum": ["complete", "extractor_only", "partial", "failed"],
      "description": "extractor_only = grader host unavailable; the turn is still scored on the critical class, and says so."
    },
    "unreliable_kinds": {
      "type": "array", "items": { "type": "string" },
      "description": "Categories whose measured recall < 0.50. The UI must label these 'not reliably detected' — docs/08-evals.md §1.1."
    },

    "merge": {
      "type": "object", "additionalProperties": false,
      "properties": {
        "policy_version":  { "type": "string" },
        "overrule_count":  { "type": "integer", "minimum": 0 },
        "conflicts":       { "type": "array", "items": {
            "type": "object", "additionalProperties": false,
            "required": ["extractor_finding_id", "grader_finding_id", "resolution"],
            "properties": {
              "extractor_finding_id": { "type": "string" },
              "grader_finding_id":    { "type": "string" },
              "resolution":           { "enum": ["extractor_wins", "grader_wins", "both_kept"] }
            } } }
      }
    },

    "provenance": {
      "type": "object", "additionalProperties": false,
      "required": ["grader_model_id", "grader_prompt_version", "extractor_suite_version", "seed"],
      "properties": {
        "grader_model_id":         { "type": "string" },
        "grader_model_quant":      { "type": "string" },
        "grader_prompt_version":   { "type": "string", "description": "e.g. 'grader/v7'" },
        "grader_prompt_sha256":    { "type": "string", "pattern": "^[a-f0-9]{64}$" },
        "extractor_suite_version": { "type": "string" },
        "seed":                    { "type": "integer" },
        "temperature":             { "type": "number" },
        "latency_ms":              { "type": "integer" },
        "scored_off_critical_path":{ "type": "boolean", "const": true }
      }
    },

    "review": {
      "type": "object", "additionalProperties": false,
      "properties": {
        "state":       { "enum": ["unreviewed", "reviewed", "signed"], "default": "unreviewed" },
        "reviewer_id": { "type": ["string", "null"] },
        "override_count": { "type": "integer", "minimum": 0 }
      },
      "description": "An unreviewed verdict is never presented as agreed. docs/03-system-architecture.md B6."
    }
  }
}
```

`scored_off_critical_path` is a `const: true` rather than a boolean anyone can set. If a code path ever produces a score synchronously inside the turn loop, it cannot construct a valid `ScoreRecord` — principle 5 becomes a type error rather than a code-review argument.

### 5.4 Scenario record

Produced by WS-7, consumed by WS-2 (graph + personas), WS-1 (term manifest), WS-4 (binding), WS-9 (pairing in A/B evals).

```json
{
  "$id": "https://rehearsal.local/schemas/scenario_record.schema.json",
  "title": "ScenarioRecord",
  "type": "object",
  "additionalProperties": false,
  "required": ["scenario_id", "version", "title", "encounter_type", "locale", "personas", "graph", "term_manifest", "provenance"],
  "properties": {
    "scenario_id":    { "type": "string", "pattern": "^scn_[a-z0-9_]{3,48}$" },
    "version":        { "type": "integer", "minimum": 1 },
    "title":          { "type": "string" },
    "encounter_type": { "enum": ["intake", "medication_counselling", "diagnosis_delivery",
                                 "discharge_instructions", "consent", "triage_callback", "follow_up"] },
    "locale": {
      "type": "object", "additionalProperties": false,
      "required": ["clinician_lang", "patient_lang"],
      "properties": {
        "clinician_lang": { "const": "en-US" },
        "patient_lang":   { "const": "es-MX" },
        "register_note":  { "type": "string",
                            "description": "Free text on the patient's register, e.g. Pajaro Valley agricultural-worker idiom." }
      }
    },

    "personas": {
      "type": "object", "additionalProperties": false,
      "required": ["clinician", "patient"],
      "properties": {
        "clinician": { "$ref": "#/$defs/persona" },
        "patient":   { "$ref": "#/$defs/persona" }
      }
    },

    "graph": {
      "type": "object", "additionalProperties": false,
      "required": ["entry_node", "nodes", "edges"],
      "properties": {
        "entry_node": { "type": "string" },
        "nodes": {
          "type": "array", "minItems": 2,
          "items": {
            "type": "object", "additionalProperties": false,
            "required": ["node_id", "speaker", "intent", "must_convey"],
            "properties": {
              "node_id":     { "type": "string", "pattern": "^n_[a-z0-9_]+$" },
              "speaker":     { "enum": ["clinician", "patient"] },
              "intent":      { "type": "string", "description": "What this turn must accomplish. NOT the literal line." },
              "must_convey": { "type": "array", "items": { "type": "string" },
                               "description": "Term manifest ids that MUST appear. Deterministically checkable." },
              "scripted_fallback": { "type": "string",
                               "description": "Used verbatim if structured generation fails schema validation twice." },
              "terminal":    { "type": "boolean", "default": false }
            }
          }
        },
        "edges": {
          "type": "array",
          "items": {
            "type": "object", "additionalProperties": false,
            "required": ["from", "to"],
            "properties": {
              "from":      { "type": "string" },
              "to":        { "type": "string" },
              "condition": { "type": ["string", "null"], "description": "Deterministic predicate id; null = unconditional" }
            }
          }
        }
      }
    },

    "term_manifest": {
      "type": "array",
      "items": {
        "type": "object", "additionalProperties": false,
        "required": ["term_id", "kind", "en", "es", "critical"],
        "properties": {
          "term_id":  { "type": "string" },
          "kind":     { "enum": ["dosage", "frequency", "allergy", "negation", "laterality",
                                 "temporal", "number", "anatomy", "condition", "idiom", "register_marker"] },
          "en":       { "type": "string" },
          "es":       { "type": "string" },
          "critical": { "type": "boolean",
                        "description": "true = omission or distortion of this term is a critical finding by construction" },
          "acceptable_renderings": { "type": "array", "items": { "type": "string" },
                        "description": "Known-good variants. Prevents extractor false alarms on legitimate synonymy." }
        }
      }
    },

    "difficulty": {
      "type": "object", "additionalProperties": false,
      "properties": {
        "target_index":   { "type": "number", "minimum": 0, "maximum": 1 },
        "tags":           { "type": "array", "items": { "type": "string" } }
      }
    },

    "provenance": {
      "type": "object", "additionalProperties": false,
      "required": ["author", "clinically_reviewed"],
      "properties": {
        "author":              { "type": "string" },
        "clinically_reviewed": { "type": "boolean" },
        "reviewer_note":       { "type": "string" },
        "source_note":         { "type": "string", "description": "Where the clinical content came from. Never a real patient." }
      }
    }
  },
  "$defs": {
    "persona": {
      "type": "object", "additionalProperties": false,
      "required": ["display_name", "voice_id", "facts"],
      "properties": {
        "display_name": { "type": "string" },
        "voice_id":     { "type": "string", "description": "TTSRouter voice key" },
        "facts": {
          "type": "array",
          "items": {
            "type": "object", "additionalProperties": false,
            "required": ["fact_id", "text", "known_to"],
            "properties": {
              "fact_id":  { "type": "string" },
              "text":     { "type": "string" },
              "known_to": { "type": "array", "items": { "enum": ["clinician", "patient"] },
                            "description": "Fact containment. A fact known_to ONLY the patient may never appear in the clinician's context." }
            }
          }
        },
        "invariants": { "type": "array", "items": { "type": "string" },
                        "description": "Deterministic persona checks for EV-04, e.g. 'never speaks English'." }
      }
    }
  }
}
```

`facts[].known_to` is the mechanism behind the fact-containment test in `docs/08-evals.md`, and it is why WS-7 and WS-5 can work independently: WS-7 authors the partition, WS-5 enforces it, neither needs the other's code.

### 5.5 Session event

The append-only spine. Written by WS-4, read by everyone. Event names are exactly the ones catalogued in `docs/03-system-architecture.md` §10 — this schema is the envelope, not a second list.

```json
{
  "$id": "https://rehearsal.local/schemas/session_event.schema.json",
  "title": "SessionEvent",
  "type": "object",
  "additionalProperties": false,
  "required": ["seq", "session_id", "type", "ts_ms", "payload", "prev_hash", "hash"],
  "properties": {
    "seq":        { "type": "integer", "minimum": 1, "description": "Monotonic per session. No gaps. The WS reconnect cursor." },
    "session_id": { "type": "string", "pattern": "^ses_[0-9A-HJKMNP-TV-Z]{26}$" },
    "type": {
      "type": "string",
      "pattern": "^(session|seed|scenario|turn|source|tts|capture|rendering|score|extractors|grader|verdict|degraded|review|export|host)\\.[a-z_]+$",
      "description": "Namespaced. The authoritative name list is docs/03-system-architecture.md §10; this pattern only constrains the shape."
    },
    "ts_ms":      { "type": "integer", "description": "Monotonic clock ms since session start. Injectable; replay uses LogicalClock." },
    "turn_index": { "type": ["integer", "null"], "minimum": 0 },
    "payload":    { "type": "object", "description": "Type-specific. Validated by the per-type model in rehearsal.contracts.events." },
    "prev_hash":  { "type": "string", "pattern": "^[a-f0-9]{64}$", "description": "sha256 of the previous event's hash field; genesis = 64 zeros." },
    "hash":       { "type": "string", "pattern": "^[a-f0-9]{64}$", "description": "sha256 over the canonical JSON of every field except hash." },
    "emitter":    { "enum": ["orchestrator", "scoring", "runtime", "api", "human", "replayer"] }
  }
}
```

Two rules that make this contract safe to build against concurrently:

- **Adding a new event `type` is not a contract change.** Consumers must ignore unknown types. This is what lets WS-3 emit new `capture.*` diagnostics without touching WS-8.
- **Changing the `payload` shape of an existing type *is* a contract change** and requires a note (§10.4), because the frontend and the eval harness both fold on it.

---

## 6. The one non-delegable task

**Human calibration labelling. Full protocol: `SETUP.md` §6.**

40 interpreting turns, hand-labelled by a human against the error taxonomy, DEV 25 / TEST 15, test split sealed, labelled blind, with a delayed re-label pass producing intra-rater agreement.

No workstream owns this, because it is not engineering work and no agent may perform it. It appears in the ownership table only as an artefact path (`data/calibration/**`, WS-7) — WS-7 owns the *files*, the *labels* come from a person.

### 6.1 Why a model cannot do it

The calibration set is the **external anchor** of the entire measurement system. Every number this project reports is, directly or transitively, an agreement statistic against it:

| Number | Depends on the labels how |
|---|---|
| `kappa_macro` (headline) | Is literally agreement with the labels |
| `critical_recall` (safety) | Denominator is the human-labelled critical errors |
| `kappa_intra` / `kappa_inter` (ceiling) | Is the human labelling itself, measured against itself |
| WS-6 optimisation result | The labels are the optimiser's metric |
| `trainer_override_rate` | Interpreted against the labels' definition of an error |
| Every rung sign-off in `docs/08-evals.md` §1.2 | Reads one of the above |

If a model produces the labels, then `kappa_macro` measures agreement between a 12B model and a 4B model — or, worse, between a model and itself. It is no longer an estimate of whether the scorer is *right*; it is an estimate of whether two stochastic processes are *correlated*. Those are different quantities and only one of them means anything to a trainee whose interpretation of a dosage instruction was marked correct.

Three specific failure modes, each of which silently inflates the headline:

1. **Shared blind spots.** Both models are Gemma. Errors the family systematically misses are missing from the gold labels *and* from the predictions, so they never appear as false negatives. Critical-error recall goes up while clinical safety goes down. This is the failure that could actually hurt someone.
2. **The ceiling collapses.** `kappa_intra` on a model at temperature 0 is 1.00 by construction. The honest human ceiling — the thing that tells you whether κ = 0.62 is excellent or mediocre — is replaced by a number that means nothing. A headline with no interpretable ceiling is uninterpretable (`docs/08-evals.md` §1.1).
3. **The ambiguous items stop working.** `SETUP.md` §6 deliberately includes items where competent humans disagree. Their entire purpose is to establish where the task's irreducible ambiguity sits. A model asked to label them produces a confident answer, which erases exactly the information the items were included to capture.

### 6.2 What agents may and may not do around it

| Task | Allowed |
|---|---|
| Draft candidate turns / stimuli for labelling | Yes |
| Shuffle, anonymise, and blind the items | Yes |
| Validate label files against the schema, check split integrity, compute κ | Yes |
| Detect a hash mismatch against `CHANGELOG.md` | Yes |
| Pre-fill, suggest, or "check" a label before the human writes it | **No** — a suggestion the human sees is an anchor, and an anchored label is a contaminated label |
| Produce any label in `dev.jsonl`, `test.jsonl`, `relabel.jsonl`, `rater2.jsonl` | **No** |
| Open `test.jsonl` for any purpose other than the sealed EV run | **No** — `seal.py` enforces this; `TEST_ACCESS.log` records every exception |

WS-1 and WS-6 are blocked on the **DEV split only**. They are permitted to start against the extractor fixture grid, which is synthetic by design and carries no agreement claim.

---

## 7. Isolation is a build-time property, not just a runtime one

Principle 4 says the clinician and patient agents never see the scoring rubric or the learner model. That claim survives parallel development only if it is enforced where contributors work, not only where the process runs:

- **Prompt directory ownership is split** (`prompts/clinician/`, `prompts/patient/` → WS-2; `prompts/grader/` → WS-6; `prompts/coach/` → WS-5). No contributor holds write access to both a counterpart prompt and the rubric prompt in the same change.
- **The import ban in §4** (`rehearsal.runtime` must not import `rehearsal.scoring` or `rehearsal.learner`) means a leak cannot be introduced by an ordinary refactor — it requires deliberately editing the import-linter config, which is a reviewed, contract-note-bearing change.
- **`ContextAssembler` is a single file** owned by WS-5 and is the only place a model context is constructed. Everything else passes structured fields to it. A workstream that wants a new field in an agent's context asks WS-5 to add it to the role allowlist; the allowlist diff *is* the leak review.
- **The rubric-vocabulary canary** (EV-04, gate = 1.00) is the runtime backstop: if taxonomy vocabulary ever reaches a counterpart agent, the number moves.

---

## 8. Integration order

Integration before these land is not integration; it is three components discovering they disagree.

| Stage | What must be true before it starts | What it proves |
|---|---|---|
| **I-0 — Contracts frozen** | WS-0 round-trip test green; `schemas/` tagged; §5 committed | Every other workstream can build against a stable target. Nothing else may start. |
| **I-1 — Scoring on fixtures** | WS-1 at `extractor_conformance = 1.00`; WS-7 fixture grid complete | The provable tier holds. The neuro-symbolic split is sound before anything stochastic is added on top. |
| **I-2 — Scoring on DEV** | I-1 + human DEV labels exist | The headline and safety metrics have their first real values. The project has an anchor. |
| **I-3 — Silent session** | WS-2 + WS-3 + WS-4 land; scoring stubbed to a no-op | The loop runs end to end: graph advances, agents speak, audio captures, events append, crash-resume replays. Latency budgets are measurable. No scores are shown to anyone. |
| **I-4 — Scored session** | I-2 + I-3 | Principle 5 is tested for the first time: `grader_backlog_rate` says whether grading really fits inside human speaking time. This is the first moment the architecture can be falsified. |
| **I-5 — Human gates** | I-4 + WS-8 review gate | `session_completion_rate` and `trainer_override_rate` exist. L7 signs off. |
| **I-6 — Isolation A/B** | I-4 + WS-5 | `leakage_delta` with its interval. L8's claim is settled by measurement or reported as null. |
| **I-7 — Optimisation** | I-2 + WS-9 registry + a frozen baseline | Before/after on the sealed TEST split, unsealed once. L10 rung 1. |

Two ordering rules that are easy to get wrong:

- **I-3 deliberately precedes I-4.** Running the loop with scoring stubbed out separates conversational-realism failures from scoring failures. Debugging both at once means debugging neither.
- **I-7 must not precede a frozen baseline.** An optimiser with nothing to regress against will happily trade `critical_recall` for `kappa_macro`, and the trade will look like progress.

**Not on the integration path, deliberately:** model weight training, fine-tuning, RL and LoRA adapters (out of scope by decision — prompt-level optimisation only); building an inference server (MLX and llama.cpp exist and are adequate); any multi-tenant or fleet concern (the product is a local, single-machine training tool, and horizontal scaling would buy nothing while costing the reproducibility that is the product's credibility).

---

## 9. Fixtures: how a workstream works before its neighbours exist

Every workstream ships and consumes fixtures so that no one waits.

| Fixture | Produced by | Path | Unblocks |
|---|---|---|---|
| Synthetic event log, 500 events, full session arc | WS-0 | `data/fixtures/sessions/golden_intake.json` | WS-8 renders a full session with no backend; WS-9 tests folding |
| Extractor grid | WS-7 | `data/fixtures/extractors/*.jsonl` | WS-1 reaches its tier-0 gate with no models running |
| Recorded agent turns (source + audio + `heard_verbatim`) | WS-2 | `data/fixtures/turns/*.jsonl` | WS-1 scores against real generations offline; WS-9 builds EV-01 |
| Silent-mode `AudioIO` and stub `TTSRouter` | WS-3 | `src/rehearsal/runtime/testing.py` | WS-4 exercises the whole state machine with no microphone |
| `ScoreRecord` samples across all four `status` values | WS-1 | `data/fixtures/scores/*.json` | WS-8 builds the report view; WS-5 builds the learner model |
| Validated minimal scenario | WS-7 | `data/scenarios/scn_intake_minimal.json` | WS-2 and WS-4 from day one |

A fixture is only useful if it is schema-valid: `make check` validates every file under `data/fixtures/` against `schemas/`. A stale fixture is caught by the build, not by a confused contributor.

---

## 10. Conflict-avoidance protocol for parallel agent work

Written for AI agents specifically, because they are fast, literal, and prone to helpful drive-by edits in files they do not own.

### 10.1 File ownership

- The table in §3 is authoritative. If a path is not listed, it is unowned; claim it by adding a row in the same change that creates it.
- **One workstream per branch.** Branch names: `ws1/<topic>`, `ws3/<topic>`. A branch that touches two workstreams' paths is rejected before review.
- **An agent working on WS-*n* may read the whole repository and write only WS-*n* paths.** Reading widely is encouraged — the failure mode is not knowing enough, it is editing too much.

### 10.2 Mechanical enforcement

```
tools/check_ownership.py           # WS-0 owns this file
  - reads OWNERS.toml (generated from §3; regenerate with `make owners`)
  - diffs the branch against its merge base
  - fails if changed paths span more than one workstream,
    unless the commit message contains a CONTRACT-CHANGE trailer
```

Wired into `make check` and the pre-commit gate. This is the deterministic guard on the human/agent process — the same pattern the runtime uses on models.

### 10.3 No cross-workstream edits

Concretely banned, each with the correct alternative:

| Tempting edit | Do this instead |
|---|---|
| "The scoring module needs one more field on `TurnRecord`" | Contract-change note (§10.4). Do not add it to `contracts/`. |
| "This function in another workstream has an obvious bug" | Open an issue with a failing test **in your own package's test directory**. Do not fix it. |
| "I'll just reformat this file while I'm here" | No. Formatting churn in someone else's file is an invisible merge conflict. |
| "I need a helper that lives in another workstream" | If it is trivial, write your own. If it is not, request that it be exported through that workstream's public surface. |
| "The prompt in another workstream would be better if…" | Prompt directories are ownership boundaries for isolation reasons (§7). Note, do not edit. |
| "I'll add my CLI subcommand to `cli.py`" | Expose the entry point in your package; note asks WS-4 to wire it. |

### 10.4 Contract changes require an explicit note

Any change to `schemas/**`, `src/rehearsal/contracts/**`, an existing event payload shape, a public function signature another workstream imports, or `pyproject.toml` dependencies:

1. Append an entry to **`plans/contract-changes.md`** using the template below.
2. Land the schema change **alone**, in its own change, touching no workstream implementation.
3. Consumers migrate in follow-up changes on their own branches.

```markdown
## CC-0007 — TurnRecord.rendering gains `verbatim_confidence`

- **Contract:** schemas/turn_record.schema.json
- **Kind:** additive-optional        # additive-optional | additive-required | narrowing | breaking
- **Requested by:** WS-1
- **Owner of the contract:** WS-0
- **Why:** the scorer must down-weight findings on low-confidence renderings;
  without this it cannot distinguish an interpreting error from a capture artefact.
- **Consumers affected:** WS-1 (reads), WS-3 (writes), WS-8 (displays), WS-9 (stratifies EV-01)
- **Migration:** nullable, defaults to null; existing fixtures remain valid.
  WS-3 populates it; nothing blocks on that landing.
- **Fixtures to regenerate:** data/fixtures/turns/*.jsonl
- **Rollback:** drop the field; no persisted data depends on it.
- **Status:** decided
```

Rules on the `Kind` field:

- `additive-optional` — the common case; consumers need not change.
- `additive-required` / `narrowing` / `breaking` — require every named consumer to acknowledge in the note before the schema lands. A breaking change during parallel work is a coordination event and is treated as one, not slipped in.

### 10.5 Working-state hygiene for agents

- **State your workstream in the first line of every change description.** `WS-3: measure barge-in stop under Metal contention`.
- **Never leave a schema and its generated model out of sync.** `make contracts` and commit both, or the build fails for everyone else.
- **Never commit a metric you did not run.** `plans/metrics-snapshot.md` is WS-9's, and a number from a dirty tree is refused by `record_run` for exactly this reason.
- **Never widen a gate to make your change pass.** Gate changes are contract changes and go through §10.4 with a stated rationale. This one is worth saying explicitly because it is the single easiest way for an agent to make a failing number disappear.

---

## 11. Status register

| Item | Status |
|---|---|
| Workstream boundaries and path ownership (§3) | **Decided** |
| The five frozen schemas (§5) | **Decided** — changes go through §10.4 |
| Import-direction rules (§4) | **Decided**, enforced by import-linter |
| Calibration labelling is human-only (§6) | **Decided**, non-negotiable |
| Integration order (§8) | **Decided** |
| `OWNERS.toml` generation + `check_ownership.py` | **Proposed** — the rule is decided, the tooling is not yet written |
| Whether `rehearsal.contracts` uses generated Pydantic or hand-written models validated against the schemas | **Open** — generation is assumed here; if generator output proves unreadable, the fallback is hand-written models with a schema-conformance test, which preserves every guarantee in §5 |
| Number of concurrent workstreams a single contributor can hold without the protocol degrading to serial work | **Open** — unmeasured; the protocol is designed for one workstream per contributor per branch and has not been tested under contention |
| WS-6's optimiser library choice (DSPy vs GEPA-style hand-rolled) | **Open** — owned by WS-6; either satisfies the DoD, and the framework rule applies: raw first, adopt only against a named pain |

---

## Related documents

- `docs/03-system-architecture.md` — components, event catalogue, session state machine, isolation boundaries
- `docs/05-voice-pipeline.md` — latency budgets and barge-in behaviour that WS-3's DoD is measured against
- `docs/06-scoring-engine.md` — extractor semantics and merge precedence that WS-1 implements
- `docs/08-evals.md` — every eval id, gate, split rule and statistical convention referenced in §3
- `docs/09-ui-ux.md` — the screens WS-8 builds and the design-system rules they must satisfy
- `SETUP.md` §6 — the calibration protocol; the non-delegable task in §6 of this document

# 04 — AI Engineering

Every model-facing decision in Rehearsal: which models exist, what each one is allowed to see, what it must return, how that return is enforced, how prompts are versioned and optimised, and what happens deterministically when a model does something wrong.

This document is the contract for anything that touches a model. It is deliberately narrow in one direction and exhaustive in the other: it does not re-specify the system's plumbing, but within the model layer it aims to leave nothing for a new engineer to guess.

| For | Read instead |
|---|---|
| Planes, processes, event log, session state machine, trust boundaries | `docs/03-system-architecture.md` |
| Audio capture, VAD, barge-in, TTS streaming, latency measurement method | `docs/05-voice-pipeline.md` |
| Extractor internals, rubric text, merge precedence, worked scoring examples | `docs/06-scoring-engine.md` |
| Scenario bank, clinical state graph authoring, term manifest generation | `docs/07-data-and-scenarios.md` |
| Every metric, gate, split rule and the optimisation reporting protocol | `docs/08-evals.md` |
| Calibration set construction, DEV/TEST split, human ceiling | `SETUP.md` §6 |
| Prompt-injection surface, export redaction, offline guarantees | `docs/12-security-privacy.md` |

Status labels, used identically to `docs/03-system-architecture.md`: **[decided]** — implement as written. **[proposed]** — current default, cheap to change, no measurement yet. **[open]** — genuinely undecided; listed in §13.

---

## 1. The five rules this layer exists to enforce

Everything below is downstream of five commitments. They are stated first so that any decision in this document can be checked against them.

| # | Rule | Concrete mechanism in this document |
|---|---|---|
| R1 | **A model never decides anything consequential.** It generates text and extracts structure; deterministic code turns that into a score, a state transition or a database write. | §4 output schemas contain no verdicts, no severities in extractor-owned categories, no state names, no SQL, no paths. §7 rejects anything off-schema. |
| R2 | **A model never sees what would corrupt it.** Every context is built from a per-role field allowlist, not by removing fields from a general context. | §5 `ContextAssembler`, `IsolationViolation`, §6 per-agent context specs |
| R3 | **Every context is dumpable.** If a model misbehaves, the first debugging step is reading the exact bytes it saw — not editing the prompt. | §6.5 `rehearsal dump-context`, `context_sha` on every model event |
| R4 | **Prompts are code.** Versioned files, diffed, reviewed, hash-pinned in the event log. Never a string edited in place, never a value typed into a UI. | §9 prompt-as-code discipline |
| R5 | **The smallest model that passes its eval wins.** Model tier is a measured choice with a named eval, re-checkable, and enforced in code rather than by convention. | §3 right-sizing, §3.4 the `tier` guard |

---

## 2. Model inventory

Three model artifacts, two host processes, five agent roles — four of them session-time (clinician, patient, grader, coach) plus the off-session `ScenarioComposer`. No cloud inference exists anywhere in the core loop; there is no API key, no HTTP client and no network config in any module under `runtime/`, `scoring/` or `orchestrator/` (boundary **B4**, `docs/03-system-architecture.md` §12).

| Artifact | Role served | Host process | Precision | Resident | Context window used | Native audio in |
|---|---|---|---|---|---|---|
| **Gemma 4 E4B class, quantised** | clinician, patient | `rehearsal-live` | 4-bit weights, 16-bit KV cache **[proposed]** | ~6–8 GB | ≤ 4 k tokens by policy (§6) | **Yes** — trainee audio enters the model directly |
| **Gemma 12B class, quantised** | grader, coach, scenario-composer | `rehearsal-grader` | 4-bit weights **[proposed]** | ~8–10 GB | ≤ 8 k tokens by policy | No — text only |
| **Local TTS voices (en-US, es-MX)** | speech output | in-process, or a child process for a neural backend | n/a | ~1–2 GB if neural | n/a | n/a |

Total resident ~20–24 GB on a 48 GB machine. Runtime is MLX on Apple Silicon with llama.cpp as the portable fallback; both are driven through one `ModelHostClient` interface so that no agent code knows which is underneath.

**Two hosts, not one, and not five.** Two buys exactly two properties: (a) the 12 B grader can be killed under memory pressure without touching the process that is holding the live conversation, and (b) the live host's KV cache is never evicted by a grader call. Any further process split buys nothing and costs a socket.

**Three roles share the grader host.** Grader, coach and scenario-composer all run on `rehearsal-grader`. They are not on the critical path, they are never concurrent with each other by construction (§3.3 priority lanes), and giving each its own weights copy would cost ~8 GB apiece for no isolation benefit — the isolation that matters here is *context* isolation, which is enforced per call (§5), not per process.

---

## 3. Model right-sizing

### 3.1 The rule

**The live path gets the smallest model that can hold a persona and take audio natively. The off-path work gets the largest model the memory budget allows.** This inverts the naive allocation, and the inversion is the whole reason a multi-model real-time system fits on one laptop.

The justification is that the two jobs have opposite shapes:

| | Live agents (clinician, patient) | Grader |
|---|---|---|
| Latency budget | ~900 ms to a complete reply, inside a human turn-taking gap | ~3.5 s, spent while the trainee is still speaking (principle 5) |
| Task | Stay in character, advance one graph node, speak naturally | Fine-grained semantic comparison against a rubric |
| Cost of a mediocre output | A slightly stilted utterance — the trainee still gets a valid interpreting task | A wrong score — the product's core claim fails |
| Ground truth available | n/a | Yes, by construction (principle 2) |
| Measured by | EV-04 persona consistency | EV-01 κ, EV-02 critical recall |

A larger live model would buy prose quality the training task does not need, at a latency cost the training task cannot absorb. A smaller grader would buy latency the grader does not need, at an accuracy cost the product cannot absorb.

### 3.2 How the tier claim is falsifiable

Right-sizing is a claim, so it carries an eval and a re-check trigger:

| Claim | Eval that could refute it | What we do if refuted |
|---|---|---|
| E4B is sufficient for the live agents | EV-04 persona-consistency rate against the state graph (`docs/08-evals.md` §4.5) | Promote the live agents to the 12 B tier only if the latency budget still holds on the target machine; otherwise reduce persona complexity, which is the cheaper lever |
| 12 B is necessary for the grader | Run EV-01 with the E4B grader prompt on DEV. If κ is within the E4B run's interval of the 12 B run, the larger model is not earning its memory | Demote the grader to E4B, free ~8 GB, and remove a host process. This would be a good outcome and is checked, not assumed |
| The coach does not need the grader tier | EV-06 skill A/B is indifferent to coach tier; coach output is human-read and never scored | Coach is the first candidate for demotion if memory pressure forces a choice |

The E4B-grader comparison is a standing item in the eval registry, not a one-off: it is re-run whenever the grader prompt version changes materially, because a better prompt can close a model gap.

### 3.3 Priority lanes on the grader host

The grader host serves three roles that must never contend. Contention is prevented deterministically, not by hoping:

```python
# src/rehearsal/runtime/hosts.py

class Lane(IntEnum):
    GRADER   = 0   # highest; the only lane with a session-facing deadline
    COACH    = 1   # dropped entirely at DegradeLevel >= 1
    COMPOSER = 2   # off-session only; refused while a session is active
```

`ModelHostClient.submit(req, lane=...)` maintains one FIFO per lane and drains strictly in lane order. `COMPOSER` submissions raise `HostBusy` if `SessionOrchestrator` reports any session not in a terminal state — scenario composition is an authoring-time activity and is not allowed to compete with a trainee.

### 3.4 Enforcing tier in code, not in convention

Every model call goes through a typed request that names its tier, and the host refuses a mismatch. This is what stops the classic drift where "just this one call" quietly moves to the big model and the latency budget dies six weeks later.

```python
# src/rehearsal/runtime/hosts.py

Tier = Literal["live", "grader"]

@dataclass(frozen=True, slots=True)
class ModelRequest:
    role: Role                    # "clinician" | "patient" | "grader" | "coach" | "composer"
    tier: Tier                    # must match ROLE_TIER[role]; checked before dispatch
    prompt_id: PromptId           # e.g. "patient/v3" — resolved from the prompt registry
    context: AssembledContext     # produced ONLY by ContextAssembler (§5)
    schema: type[BaseModel]       # the response model; drives constrained decoding (§7)
    decode: DecodeConfig
    lane: Lane
    deadline_ms: int

ROLE_TIER: Final[dict[Role, Tier]] = {
    "clinician": "live",
    "patient":   "live",
    "grader":    "grader",
    "coach":     "grader",
    "composer":  "grader",
}

class TierViolation(RuntimeError): ...
```

`ModelHostClient.submit()` raises `TierViolation` when `req.tier != ROLE_TIER[req.role]`, and each host process additionally rejects requests whose `tier` does not match the weights it loaded. A unit test asserts the table is total over `Role`, so adding a role without deciding its tier fails the build rather than defaulting to the big model.

### 3.5 Decode configuration per role

Decode parameters are part of the versioned prompt artifact (§9), not scattered call-site literals.

| Role | Temperature | top_p | Max new tokens | Seeded | Rationale |
|---|---|---|---|---|---|
| `clinician` | 0.7 | 0.9 | 160 | `clinician_sampling` | Needs natural variation across sessions; the state graph, not the sampler, controls clinical content |
| `patient` | 0.8 | 0.9 | 160 | `patient_sampling` | Slightly higher: patients are less scripted, more idiomatic, and register variation is part of the training value |
| `grader` | **0.0** | 1.0 | 700 | — (greedy) | A measuring instrument must return the same reading for the same input. Any move off 0.0 is a scoring-plane change and re-triggers calibration (`SETUP.md` §6) |
| `coach` | 0.4 | 0.9 | 220 | `coach_sampling` | Phrasing variety so feedback does not read as a template; content is fully determined by the verdict it is handed |
| `composer` | 0.9 | 0.95 | 1400 | `scenario_selection` | Authoring-time diversity is the point; every output is human-gated before entering the bank |

Seed namespaces are the ones defined in `docs/03-system-architecture.md` §6.3. The grader takes no seed because it does not sample.

---

## 4. The agent roster

Five roles. Each subsection states the same six things: what it is for, exactly what it receives, exactly what it returns, its whitelisted tools, its tier, and how it fails.

A note on the word *agent*. Only the clinician and patient are agents in the loop sense — they hold a role across turns and choose what to say next within graph constraints. The grader, coach and composer are single structured calls with no autonomy, no loop and no tools; they are listed here because they are model-facing and share the same context and schema discipline. The orchestrator is **not** an agent and never was (see `docs/03-system-architecture.md` §15).

### 4.1 `ClinicianAgent` — the English-speaking counterpart

**Purpose.** Play a clinician conducting a real encounter in English, advancing one node of the clinical state graph per turn. Must be *hard to interpret in realistic ways*: natural numbers, negation, laterality, occasional false starts, clinical register.

**Tier.** `live` (E4B). It has one job it must do fast, and prose polish is not the training variable.

**Inputs — the complete set.**

```python
# src/rehearsal/runtime/agents/context.py

@dataclass(frozen=True, slots=True)
class CounterpartContext:
    role_card: str                  # persona: specialty, communication style, name — from the scenario
    node: GraphNodeView             # intent, required clinical facts, persona invariants, scripted fallback
    encounter_summary: str          # <= 400 chars, deterministic template over closed nodes; NOT model-written
    recent_turns: tuple[TurnLine, ...]   # last 6 lines: (speaker, text). Interpreted renderings only
    difficulty: int                 # 1..5 — the ONLY signal that crosses from the learner plane
    style_directives: tuple[str, ...]    # from difficulty: numeric density, speech rate, clause depth
    audio_ref: BlobRef | None       # the trainee's rendering audio for this turn, fed natively
```

`recent_turns` contains what was *said in the room* — the counterpart's own prior utterances and the trainee's renderings. It does not contain the other counterpart's source utterances in their original language, because in a real triadic encounter the clinician did not hear the patient's Spanish; they heard the interpreter. Reproducing that asymmetry is what makes an omission actually cost something in the conversation.

**Output.**

```python
# src/rehearsal/runtime/agents/schemas.py

class CounterpartTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    heard_verbatim: str = Field(max_length=1200)
    """Literal transcription of what the trainee just said, in the trainee's language.
    Produced in the same forward pass as the reply, so it costs no extra critical-path
    latency. This string is the canonical rendering for scoring (docs/03 §7)."""

    heard_confidence: Literal["clear", "partial", "unintelligible"]

    reply_text: str = Field(max_length=600)
    """What the clinician says next, in English. Plain speech: no stage directions,
    no markdown, no names of speakers, no bracketed asides."""

    node_satisfied: bool
    """Self-report that the node's communicative intent was expressed. ADVISORY ONLY —
    graph advance is decided by ClinicalStateGraph.advance(), never by this field."""

    repair_request: bool
    """True when the clinician is asking for repetition/clarification in character."""
```

`node_satisfied` is a deliberate example of R1: the model is allowed to *report* and never to *decide*. The field is logged and used as an eval signal (its disagreement rate with the deterministic advance is a persona-drift indicator), and it is not read by the state machine.

**Whitelisted tools.** None. The clinician has no tool access of any kind — no retrieval, no calculator, no clock, no scenario lookup. Everything it may know is already in its context, and every fact that matters clinically is owned by the graph and the term manifest, not by the model. A retrieval tool here would break ground-truth-by-construction: the system could no longer state with certainty what the source utterance contained.

**Failure modes.** Persona drift, language drift (answering in Spanish), schema violation, deadline overrun — all handled in §11.

### 4.2 `PatientAgent` — the Spanish-speaking counterpart

**Purpose.** Play the patient in Spanish (es-MX, with regional and health-literacy variation drawn from the scenario), holding a symptom state that must stay internally consistent across the encounter.

**Tier.** `live` (E4B). Same reasoning as the clinician.

**Inputs.** The same `CounterpartContext` type, assembled from a *different* allowlist. The differences are load-bearing:

| Field | Clinician | Patient |
|---|---|---|
| `role_card` | Clinician persona | Patient persona: age, literacy, dialect, emotional state, family context |
| `node.required_facts` | The clinical facts the clinician must convey (dose, frequency, follow-up) | The symptom facts the patient holds (onset, laterality, severity, what they took) |
| Private state | Clinician's plan for the encounter | **Patient's undisclosed facts** — things a real patient would not volunteer until asked |
| `recent_turns` | Trainee's English renderings + own prior English | Trainee's Spanish renderings + own prior Spanish |

**Cross-agent containment.** The patient must never state a clinical fact that only the clinician holds (a diagnosis not yet given, a dose not yet prescribed), and the clinician must never state an undisclosed patient fact before the patient discloses it. This is not enforced by instruction — instruction is not enforcement. The scenario's fact set is partitioned in the bank into `clinician_facts`, `patient_facts` and `shared_facts`, the assembler only ever puts a partition into the agent that owns it, and the fact-containment test in `docs/08-evals.md` scans generated utterances for the other partition's terms.

**Output.** `CounterpartTurn`, identical schema, `reply_text` in Spanish. A language check runs on the output (§11.3).

**Whitelisted tools.** None, for the same reason as the clinician.

### 4.3 `Grader` — the semantic residue scorer

**Purpose.** Score exactly the part of fidelity that is not decidable by code: register, idiom, pragmatic force, first-person discipline, editorialization, role exchange, false fluency, and semantic omission/addition that no extractor covers. It does **not** score numbers, dosages, frequencies, negation, laterality, allergies or temporal markers — those belong to deterministic extractors and the grader is structurally prevented from creating a `critical` severity in them (`docs/06-scoring-engine.md`).

**Tier.** `grader` (12 B). It is the instrument the product's headline number is computed from, it runs off the critical path, and its 3.5 s budget is the trainee's own speaking time.

**Inputs — the complete set, and nothing else.**

```python
@dataclass(frozen=True, slots=True)
class GraderContext:
    direction: Literal["en->es", "es->en"]
    source_text: str            # the utterance the system generated — ground truth by construction
    rendering_text: str         # heard_verbatim, or the off-path re-transcription
    term_manifest_slice: TermSlice   # only the terms present in THIS source utterance
    deterministic_findings: tuple[FindingSummary, ...]  # kind + span only; no severities, no notes
    rubric_version: str
```

`deterministic_findings` is passed so the grader does not waste output on ground already covered, and it is passed *stripped* — kinds and spans only — so the grader cannot anchor its semantic judgement on the extractors' severity calls. Whether passing them at all helps or hurts is an A/B on DEV, not a matter of taste **[open, §13]**.

**What the grader never receives**, and why each one would bias the instrument:

| Withheld | If it saw it |
|---|---|
| Trainee identity, learner model, past performance | A grader that knows the trainee is "usually weak on numbers" is measuring its prior, not this turn |
| The other turns of the session | Halo effect: a strong turn 3 makes turn 4 look better |
| Coach output, review history, any prior verdict for this turn | Self-confirmation; re-scoring a session would no longer be independent |
| Agent hidden state or the agents' own self-assessments | Boundary **B2** (`docs/03-system-architecture.md` §12) |
| Audio | Prosody is not in the rubric, and text-only keeps the instrument reproducible from the event log alone |

**Output.**

```python
class GraderFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["omission", "addition", "substitution", "distortion",
                  "editorialization", "role_exchange", "register_shift",
                  "false_fluency", "first_person_violation"]
    severity: Literal["critical", "non_critical"]
    source_span: tuple[int, int] | None
    rendering_span: tuple[int, int] | None
    note: str = Field(max_length=240)     # why it matters, in one sentence
    confidence: float = Field(ge=0.0, le=1.0)

class GraderVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    findings: list[GraderFinding] = Field(max_length=12)
    clean: bool                  # explicit "no semantic errors" — see below
    unscorable_reason: Literal["empty_rendering", "unintelligible", "off_topic"] | None
```

Two schema choices are deliberate. **`clean` is an explicit boolean rather than an empty list** because an empty list is ambiguous between "found nothing" and "produced nothing", and the false-alarm rate on clean calibration items (`fp_rate_clean`) is a reported metric that needs that distinction to be unambiguous. **`unscorable_reason` exists** so that "I cannot score this" is a first-class, structured output rather than a refusal in prose (§11.1).

Spans are character offsets validated against the actual strings by deterministic code; an out-of-range span is a schema failure, not a rounding matter. The grader's `severity` is advisory in the extractor-owned categories: `VerdictMerger` applies merge precedence and records overrules (`docs/06-scoring-engine.md`).

**Whitelisted tools.** None. The grader is one structured call. The temptation to give it a dictionary lookup or a term-search tool is real and is refused: a tool call inside the instrument makes the instrument's output depend on tool latency and tool version, and the term manifest is already in the context.

### 4.4 `CoachAgent` — feedback phrasing

**Purpose.** Turn a merged, already-decided verdict into one or two sentences a trainee can act on, at turn boundaries only. It phrases; it does not assess. Everything it says is determined by the verdict it is handed.

**Tier.** `grader` (12 B), lane `COACH`. It shares the host because phrasing quality is genuinely a language task and it is free to run there off-path — and it is the first thing dropped under load.

**Inputs.**

```python
@dataclass(frozen=True, slots=True)
class CoachContext:
    verdict_summary: tuple[FindingSummary, ...]   # merged verdict: kind, severity, short quote pair
    weak_categories: tuple[ErrorKind, ...]        # from LearnerModel, max 3
    turns_remaining: int
    tone: Literal["neutral", "encouraging"]       # user setting, default neutral
```

The coach is the one role that legitimately sees learner state — because it is speaking *to the learner*, not generating the task or measuring it. It runs strictly after the verdict is merged, so learner state cannot influence what was scored.

**Output.**

```python
class CoachHint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hint: str = Field(max_length=200)
    references_finding_index: int | None   # must index into verdict_summary, validated
    suppress: bool                         # model may decline to speak
```

A hint whose `references_finding_index` is `None` while `verdict_summary` is non-empty is dropped by deterministic code: unanchored encouragement is noise, and every hint must trace to a finding the trainee can look at.

**Whitelisted tools.** None.

**Suppression rules [decided].** No hint during capture, ever. No hint at `DegradeLevel >= 1`. No hint on a `partial` verdict where the semantic pass was shed — the trainee would receive advice generated from half a picture. At most one hint per two turns.

### 4.5 `ScenarioComposer` — authoring-time scenario generation

**Purpose.** Draft candidate scenarios for the bank: encounter arc, clinical state graph skeleton, personas, and the paired term manifest. Runs off-session, at authoring time, and **every output is human-gated before it can enter the bank** — this is an L7-style gate applied to content, not to sessions.

**Tier.** `grader` (12 B), lane `COMPOSER`, refused while any session is live (§3.3).

**Inputs.**

```python
@dataclass(frozen=True, slots=True)
class ComposerContext:
    seed_material: str          # a delimited clinical source excerpt (docs/07-data-and-scenarios.md)
    target_difficulty: int      # 1..5
    required_features: tuple[str, ...]   # e.g. ("dosage", "negation", "laterality")
    setting: str                # e.g. "primary care, agricultural worker health, Pajaro Valley"
    existing_titles: tuple[str, ...]     # for de-duplication only; no existing scenario bodies
```

`seed_material` is **untrusted data** (boundary **B3**). It enters through a delimited data slot inside a code-owned instruction region, is Unicode-normalised and control-character-stripped at ingest, and no instruction inside it is ever followed. `existing_titles` carries titles only — feeding whole existing scenarios back in produces convergent, samey banks.

**Output.**

```python
class ComposedScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(max_length=90)
    setting: str
    clinician_persona: PersonaSpec
    patient_persona: PersonaSpec
    nodes: list[ComposedNode] = Field(min_length=6, max_length=24)
    clinician_facts: list[ClinicalFact]
    patient_facts: list[ClinicalFact]
    shared_facts: list[ClinicalFact]
    term_manifest: list[TermEntry]   # numbers, dosages, frequencies, allergies, laterality, temporal
    difficulty_features: list[str]
```

**Whitelisted tools.** None at model level. Validation is deterministic and runs *after* generation, in `content/graph.py`: graph connectivity and reachability, no dead-end nodes, every `term_manifest` entry actually appearing in some node's text, dosage plausibility bounds, bilingual coverage of every term. A scenario failing any check is rejected before a human ever reviews it, so reviewer time is spent on clinical judgement rather than on structural defects.

**The human gate [decided].** A composed scenario enters the bank only after a human marks it `approved` with an attributed reviewer id. Clinical plausibility is not a property a language model can certify, and a scenario with an implausible dose would teach a trainee to normalise an implausible dose. See `docs/07-data-and-scenarios.md` for the review queue.

### 4.6 The roster table

| Agent | Model tier | Sees | Never sees | Tools | On critical path |
|---|---|---|---|---|---|
| `ClinicianAgent` | Live — Gemma 4 E4B, quantised, native audio in | Clinician role card; current graph node (intent, `clinician_facts`, `shared_facts`, persona invariants, scripted fallback); deterministic encounter summary (≤400 chars); last 6 spoken lines; `difficulty:int`; style directives; trainee's rendering audio | Rubric, error taxonomy, any verdict or finding, learner model, past-performance summaries, the trainee's identity, `patient_facts` not yet disclosed, the patient's Spanish source utterances, the grader's or coach's output, future graph nodes | **None** | **Yes** |
| `PatientAgent` | Live — Gemma 4 E4B, quantised, native audio in | Patient role card (age, literacy, dialect, affect); current graph node with `patient_facts` + `shared_facts`; encounter summary; last 6 spoken lines; `difficulty:int`; style directives; trainee's rendering audio | Same withheld set as the clinician, plus `clinician_facts` not yet stated, and the clinician's English source utterances | **None** | **Yes** |
| `Grader` | Off-path — Gemma 12B, quantised, temp 0 | `direction`; `source_text`; `rendering_text`; the term-manifest slice for this utterance; stripped deterministic finding kinds+spans; `rubric_version` | Trainee identity, learner model, past performance, other turns of the session, coach output, prior verdicts for this turn, agent hidden state, audio | **None** | **No** — runs during the trainee's next speaking turn |
| `CoachAgent` | Off-path — Gemma 12B, quantised, lane `COACH` | Merged verdict summary for the just-closed turn; `weak_categories` (≤3); `turns_remaining`; tone setting | Raw source/rendering text beyond the quoted spans, the rubric text itself, any future turn, any other trainee's data | **None** | **No** — suppressed at `DegradeLevel ≥ 1` |
| `ScenarioComposer` | Off-path, off-session — Gemma 12B, quantised, lane `COMPOSER` | One delimited untrusted clinical source excerpt; target difficulty; required features; setting; existing scenario **titles** only | Any session data, any trainee data, any verdict, any learner model, existing scenario bodies | **None** (deterministic post-validators in `content/graph.py`; human approval gate) | **No** — refused while a session is active |

**Zero tools, everywhere, is a decision and not an omission.** Tools would buy retrieval and arithmetic. Retrieval breaks principle 2: if an agent can pull in a fact the system did not author, the system no longer knows exactly what the source utterance contained, and scoring stops being "compare known source to rendering". Arithmetic belongs to the extractors, which are provably correct and 40 ms. The one place tool use would be defensible — the composer looking up drug dosing — is instead handled by deterministic post-validation plus human review, which is stronger, because it fails closed.

---

## 5. Information isolation

Principle 4, implemented. This is the section to read before changing anything about what goes into a prompt.

### 5.1 The claim being protected

A counterpart agent that can see the scoring rubric will, without being instructed to, produce utterances that are easier to interpret: shorter, fewer stacked numerals, less idiom, cleaner clause boundaries, helpful pauses. Nothing in the model intends this; it is ordinary instruction-following bleed. The consequence is that the *task itself* becomes easier while the *measurement* stays the same, so every score inflates and the training stops resembling the work.

That is the entire architectural justification for separate agents with separate contexts rather than one model narrating both sides. It is a claim, so it is measured, not asserted — EV-05 in `docs/08-evals.md` §4.6.

### 5.2 Threat model

Leakage is a data-flow problem, so it is enumerated as one: channel, mechanism, what it corrupts, and the control.

| # | Channel | How it leaks | What it corrupts | Control |
|---|---|---|---|---|
| **T1** | Rubric text into a counterpart prompt | A shared prompt template or a "helpful" context field carrying the taxonomy | Utterance difficulty collapses; all scores inflate; the product measures nothing | Per-role allowlist (§5.3); vocabulary canary test asserting no taxonomy term appears in any assembled live context |
| **T2** | Verdicts or findings into a counterpart prompt | Feeding "the trainee omitted the dose" back to make the agent "adapt" | Agent compensates for known weaknesses; the trainee is never re-tested on the thing they failed | `Finding`/`Verdict` types are not importable in `runtime/agents/` — enforced by an import-boundary test, not just by review |
| **T3** | Learner model into a counterpart prompt | Passing `weak_categories` to "personalise difficulty" | Same as T2, plus it makes difficulty non-reproducible from the seed | Only `difficulty: int` crosses (boundary **B1**). `LearnerModel.difficulty()` returns the sole exported scalar |
| **T4** | Learner model or trainee identity into the **grader** | Passing trainee id "for logging" | The instrument develops a prior; κ against human labels becomes uninterpretable | `GraderContext` has no identity field; the grader host receives no session id |
| **T5** | Cross-agent fact bleed | Both agents built from one undifferentiated scenario blob | Patient states a diagnosis not yet given; the encounter stops being a realistic information asymmetry | Fact partitioning in the bank + fact-containment scan (`docs/08-evals.md`) |
| **T6** | Session history into a grader call | Passing "the last three turns" for context | Halo/anchoring across turns; a re-score of the same turn is no longer independent | Grader context is single-turn by type. There is no field to put history in |
| **T7** | Scenario text carrying instructions | Ingested corpus text containing "ignore previous instructions" | Arbitrary prompt behaviour, including rubric disclosure | Boundary **B3**: delimited data slots, code-owned instruction regions, control-character stripping, Unicode normalisation at ingest |
| **T8** | Model output re-entering a prompt unvalidated | `heard_verbatim` (which contains trainee speech) pasted into the next agent context raw | Injection through the trainee's own microphone; also unbounded context growth | Model outputs re-enter only through typed fields with length caps, inside data slots |
| **T9** | Coach hint leaking rubric vocabulary into the room | Hint text spoken aloud during capture and heard by the live agent's audio input | A slow-motion T1 through the audio channel | Coach never speaks during capture; hints are text-only in the UI, never TTS |
| **T10** | Debug tooling | A context dump written into a log that a later prompt reads | Any of the above | Context dumps go to `~/.rehearsal/logs/` and nothing in `runtime/` or `scoring/` reads that directory |

T9 deserves emphasis because it is the non-obvious one: the live agents take audio natively, so anything audible in the room is potentially in a model's context. The isolation boundary is physical as well as logical.

### 5.3 The enforcement point

There is exactly one function that may construct a model context. Everything else is a `TypeError`.

```python
# src/rehearsal/runtime/agents/context.py

class IsolationViolation(RuntimeError):
    """Raised when a context assembly attempts a field its role does not allow.
    This is a hard runtime error, never a warning, and it aborts the turn."""

FIELD_ALLOWLIST: Final[dict[Role, frozenset[str]]] = {
    "clinician": frozenset({
        "role_card", "node", "encounter_summary", "recent_turns",
        "difficulty", "style_directives", "audio_ref",
    }),
    "patient": frozenset({
        "role_card", "node", "encounter_summary", "recent_turns",
        "difficulty", "style_directives", "audio_ref",
    }),
    "grader": frozenset({
        "direction", "source_text", "rendering_text",
        "term_manifest_slice", "deterministic_findings", "rubric_version",
    }),
    "coach": frozenset({
        "verdict_summary", "weak_categories", "turns_remaining", "tone",
    }),
    "composer": frozenset({
        "seed_material", "target_difficulty", "required_features",
        "setting", "existing_titles",
    }),
}

BANNED_SUBSTRINGS: Final[frozenset[str]] = frozenset({
    # taxonomy vocabulary that must never appear in a LIVE context
    "omission", "addition", "substitution", "distortion", "editorialization",
    "role exchange", "register shift", "false fluency", "first person violation",
    "rubric", "severity", "critical error", "fidelity score", "kappa",
})

def assemble(role: Role, fields: Mapping[str, object]) -> AssembledContext:
    """The ONLY constructor of a model context. Allowlist, not denylist."""
    allowed = FIELD_ALLOWLIST[role]
    if extra := set(fields) - allowed:
        raise IsolationViolation(f"role={role} disallowed fields: {sorted(extra)}")
    ctx = _render(role, fields)
    if role in ("clinician", "patient"):
        lowered = ctx.text.lower()
        if hits := [t for t in BANNED_SUBSTRINGS if t in lowered]:
            raise IsolationViolation(f"role={role} rubric vocabulary in context: {hits}")
    return ctx
```

Three properties matter here:

1. **Allowlist, not denylist.** A new field added anywhere upstream is invisible to every agent until someone deliberately adds it to a role's set. Denylists fail open on exactly the change that introduces the bug.
2. **The canary is belt-and-braces.** `BANNED_SUBSTRINGS` cannot catch a paraphrased rubric, so it is not the control — the allowlist is. The canary catches the crude version loudly and cheaply, and it is the check that would have caught a hand-edited prompt file.
3. **It raises, it does not sanitise.** Silently stripping a disallowed field would let a real leak path exist and stay green. The turn aborts and the event log records `IsolationViolation` with the offending field names.

Supporting tests, all in `tests/test_isolation.py`:

| Test | Asserts |
|---|---|
| `test_allowlist_is_total_over_roles` | Every `Role` has an entry; adding a role without an allowlist fails the build |
| `test_live_context_has_no_taxonomy_vocabulary` | Assembles 200 contexts across the scenario bank; none contains a banned substring |
| `test_scoring_types_not_importable_in_runtime` | Static import-graph check: no module under `runtime/agents/` imports from `scoring/` or `learner/` except `learner.model.difficulty` |
| `test_grader_context_has_no_identity_field` | `GraderContext.__dataclass_fields__` contains no id-like or history-like field |
| `test_prompt_files_contain_no_cross_role_text` | Each prompt file under `prompts/clinician/` and `prompts/patient/` is scanned for the same canary list |

### 5.4 The leakage A/B, in one paragraph

The measurement is owned by `docs/08-evals.md` §4.6 and is not restated here. What this document owns is the *mechanism the experiment needs*: because the only legal way to build a context is `assemble()`, the leaked arm cannot be produced by editing production code. It is produced by an eval-only subclass that widens the counterpart allowlist by exactly one field, `rubric_text`, with everything else — seeds, scenarios, order, decode params, trainee-side script — held identical. That the experimental manipulation is a one-field allowlist change is what makes the arms genuinely paired.

---

## 6. Context assembly discipline

### 6.1 The shape of every context

Every assembled context has the same four regions, in the same order, for every role:

```
┌ 1. INSTRUCTION  ── code-owned, from a versioned prompt file. Never contains external text.
├ 2. ROLE STATE   ── typed fields, rendered by a deterministic template.
├ 3. DATA SLOTS   ── external/untrusted text, explicitly delimited and labelled as data.
└ 4. OUTPUT SPEC  ── the JSON schema and one worked example, generated FROM the Pydantic model.
```

Region 4 is generated from the schema rather than hand-written, so a schema change can never drift from its prompt description — a class of bug that is otherwise silent and expensive.

Ordering follows the context-engineering rule the project holds to: instructions early, volatile state late. `recent_turns` and `node` are the last things before the output spec, because they change every turn and are what the model must actually act on.

### 6.2 Per-agent context budget

Budgets are policy, enforced by an assertion in `assemble()`, not aspirations.

| Role | Instruction | Role state | Data slots | Output spec | Hard cap | Typical |
|---|---|---|---|---|---|---|
| `clinician` | ~380 tok | ~500 tok | — | ~180 tok | **4 000 tok** | ~1 200 tok + audio |
| `patient` | ~400 tok | ~520 tok | — | ~180 tok | **4 000 tok** | ~1 250 tok + audio |
| `grader` | ~900 tok (rubric residue only) | ~250 tok | source + rendering, ≤ 700 tok | ~320 tok | **8 000 tok** | ~2 200 tok |
| `coach` | ~200 tok | ~180 tok | — | ~90 tok | **2 000 tok** | ~500 tok |
| `composer` | ~700 tok | ~120 tok | seed excerpt ≤ 2 500 tok | ~600 tok | **8 000 tok** | ~4 200 tok |

Exceeding a cap raises `ContextOverflow` and the turn degrades to the node's scripted fallback line rather than silently truncating. Silent truncation removes the *end* of the context, which is exactly where the volatile state lives — a truncated context is a wrong context, not a smaller one.

The live caps are deliberately tight. `recent_turns` is capped at 6 lines and `encounter_summary` at 400 characters because the KV cache is shared with audio input on a memory-constrained host, and because a longer history measurably increases persona drift without improving the encounter (EV-04 is the check).

### 6.3 The encounter summary is not model-written

`encounter_summary` is produced by a deterministic template over closed graph nodes:

```python
# src/rehearsal/runtime/agents/context.py

def encounter_summary(view: SessionView) -> str:
    """Deterministic, <= 400 chars. No model call. Reproducible from the event log."""
```

A model-written rolling summary would be a second, unmeasured model in the critical path, would introduce a compounding error channel (summary of a summary), and would make the agent context non-reproducible from the event log. The cost is a blunter summary. That is the right trade for a system whose credibility is replayability.

### 6.4 Rendering discipline

- No markdown in any live context. The agents speak; formatting characters end up pronounced or imitated.
- Numbers are rendered exactly as the term manifest holds them (`500 mg`, `every 8 hours`), never normalised, because the extractors compare against the manifest.
- Data slots use a fixed delimiter with a labelled close tag, and the delimiter string is stripped from external text at ingest so it cannot be forged.
- Spanish text is NFC-normalised. Diacritics are never stripped: `año`/`ano` is a real semantic distinction, and stripping would silently corrupt both agent speech and scoring.

### 6.5 Dumpability

Every model call records the SHA-256 of its exact assembled context bytes in the event payload (`context_sha`), alongside `prompt_id` and the decode config hash. The bytes themselves are written to the blob store for the retention window configured in `docs/12-security-privacy.md`.

```bash
rehearsal dump-context <session_id> --turn 7 --role patient    # exact bytes the model saw
rehearsal dump-context <session_id> --turn 7 --role grader --diff-with <other_session_id>
rehearsal dump-context --sha <context_sha>                     # by hash, any session
```

This exists because of a rule the project holds without exception: **when a model misbehaves, read the document it saw before touching the prompt.** Most apparent prompt failures are context assembly failures, and editing the prompt in response to one produces a prompt that is wrong in two ways.

---

## 7. Structured output enforcement

### 7.1 Constrained decoding is the primary mechanism

Every model call is schema-constrained at the decoder, not merely asked nicely and parsed afterwards. The schema in `ModelRequest.schema` is compiled to a decoding constraint and enforced token by token.

| Runtime | Mechanism | Notes |
|---|---|---|
| MLX (primary, Apple Silicon) | JSON-schema-driven logit masking in the host process; the Pydantic model is converted to a JSON Schema and compiled once per `(schema, model)` pair and cached | Compilation is ~10–40 ms and happens at host startup for all five schemas, never on the critical path |
| llama.cpp (portable fallback) | GBNF grammar generated from the same JSON Schema | Grammar generation is deterministic and hash-checked against the schema version so the two runtimes cannot diverge |

Because the grammar is generated from the same Pydantic models the Python side validates against, "the model returned a field we do not have" is structurally impossible rather than handled.

**What constrained decoding does not guarantee:** semantic validity. A well-formed `GraderFinding` can still carry a span that does not exist in the string, a `confidence` of 1.0 on nonsense, or a `kind` that contradicts its `note`. Structure is enforced at the decoder; meaning is checked afterwards (§7.3).

### 7.2 Why not just parse and retry

Parse-and-retry costs a full extra generation on failure. On the live path that is a blown turn budget; a 900 ms budget cannot absorb a second 900 ms attempt. Constrained decoding moves the cost from "sometimes catastrophic" to "always small and bounded". The retry ladder still exists (§11.2), for the semantic failures constrained decoding cannot prevent.

### 7.3 The post-decode validation ladder

Applied in order, deterministically, to every model response:

| Step | Check | Failure action |
|---|---|---|
| 1 | Pydantic model validation (`extra="forbid"`, all length caps) | Should be unreachable under constrained decoding; if reached, log `schema_escape` — it means the grammar and the model have drifted, which is a build-level bug |
| 2 | Span validity: every span is in range and `source[a:b]` is non-empty | Drop the individual finding, record `span_invalid` with the raw value; keep the rest of the verdict |
| 3 | Cross-field coherence: `clean=True` with non-empty `findings`; `references_finding_index` out of range; `node_satisfied=True` with an empty `reply_text` | Reject the whole response, one retry (§11.2) |
| 4 | Category ownership: grader emitted `severity="critical"` in an extractor-owned category | Downgrade to `non_critical`, record `severity_overruled`. The grader is never allowed to create a critical severity in a category code owns (`docs/06-scoring-engine.md`) |
| 5 | Language check on `reply_text` (§11.3) | Retry once with an explicit language reminder; then scripted fallback |
| 6 | Canary scan of live output for taxonomy vocabulary | Reject the utterance, use the scripted fallback, record `output_canary_hit` — this is the tell that a leak exists somewhere upstream |

Every step logs to the event payload. Step counts per session are surfaced in the debrief because a session with 9 span-invalid findings and a session with 0 are not the same measurement.

### 7.4 One structured call means one

The grader is a **single** call per turn. No chain, no self-critique pass, no second opinion, no ensembling. A self-critique pass would double the grader's latency (it has budget for that) but it would also make the instrument's output depend on an unmeasured second prompt, and every calibration number would then be a number about a pipeline nobody wrote down. If a self-critique pass is ever added, it becomes part of the versioned grader artifact and requires full re-calibration against `SETUP.md` §6. **[decided]**

---

## 8. Memory model

Three kinds of state, three different lifetimes, and one deliberate absence.

| Kind | Scope | Storage | Who reads it | Survives the session |
|---|---|---|---|---|
| **Working state** | One session | Event log + folded `SessionView` in memory | Orchestrator; agents see only the ≤6-line window and the deterministic summary | The *record* survives; nothing re-enters a model context |
| **Learner model** | One trainee, all sessions | `learner_state` projection (per-category EWMA + counts) | `LearnerModel`; exports exactly one scalar to the runtime (`difficulty: int`) and `weak_categories` to the coach | **Yes** |
| **Cross-session conversational memory** | — | **Does not exist** | — | — |

### 8.1 There is no cross-session chat memory, deliberately

No agent ever sees anything from a previous session. Not a summary, not "last time you struggled with dosages", not a persona carried forward. Four reasons, in order of weight:

1. **It would breach isolation through the back door.** Any cross-session memory rich enough to be useful encodes past performance, and past performance is exactly what boundary **B1** exists to keep out of the counterpart agents (threat T2/T3).
2. **It would destroy reproducibility.** A session's inputs must be fully determined by `(scenario_id, root_seed, config, prompt versions)`. A memory blob makes every session a function of an unversioned history, and `rehearsal replay --verify` becomes meaningless.
3. **It is not what the skill needs.** Interpreting practice wants *independent* repetitions. An agent that remembers you and adapts to you gives you an easier encounter, which is the same failure the leakage A/B measures, arriving by a different route.
4. **It is a privacy liability with no compensating benefit.** A persistent conversational store of clinical role-play containing a named trainee's speech is precisely the artifact `docs/12-security-privacy.md` exists to avoid accumulating.

What legitimately persists is the **learner model**: deterministic arithmetic over verdicts, readable by a human, versioned, and exporting a single integer to the runtime. Adaptation happens through that integer and nothing else.

### 8.2 Working state inside a session

- **KV cache** is per-role and per-session on the live host. It is reset at session end, and on persona-drift recovery (§11.4), because a drifted cache is the thing that keeps producing drift.
- **The ≤6-line window** is the agents' entire episodic memory. Anything older reaches them only through the deterministic `encounter_summary`.
- **Nothing an agent "believes" is state.** The graph holds the clinical facts; the agent holds only phrasing. If the agent's implicit state and the graph disagree, the graph is right by definition, and the disagreement is a persona-drift signal (EV-04).

### 8.3 What the grader remembers

Nothing. Every grader call is independent by type (`GraderContext` is single-turn, threat T6). This is what makes `rehearsal replay --rescore` sound: re-scoring a session under a new prompt produces the same answer regardless of the order the turns are re-scored in, which is a precondition for the optimisation loop in §10 meaning anything.

---

## 9. Prompts as code

### 9.1 Layout

```
prompts/
├── registry.toml                  # role -> active version; the ONLY place a version is selected
├── clinician/
│   ├── v1.md  v2.md  v3.md        # append-only; never edited in place
│   └── decode.toml                # per-version decode config
├── patient/       v1.md v2.md decode.toml
├── grader/
│   ├── v1.md … v6.md
│   ├── rubric/                    # the semantic-residue rubric, versioned separately
│   │   └── r1.md  r2.md
│   └── decode.toml
├── coach/         v1.md v2.md decode.toml
└── composer/      v1.md decode.toml
```

The rubric is versioned separately from the grader prompt because the two change for different reasons: the rubric changes when our understanding of the professional standard changes (a substantive event requiring re-calibration), the prompt changes when we find a better way to ask (an optimisation event). Collapsing them would hide which kind of change just happened.

### 9.2 Prompt file format

Every prompt file carries a machine-readable header. It is parsed, not decorative.

```markdown
---
prompt_id: grader/v7
role: grader
schema: GraderVerdict
schema_sha: 9f2c1a...          # of the JSON Schema; a mismatch fails startup
rubric: grader/rubric/r2
supersedes: grader/v5
origin: optimiser              # hand | optimiser | revert
run_id: opt-<id>             # the optimisation run, when origin=optimiser
dev_kappa_macro: <k>          # ILLUSTRATIVE — no measurement exists
dev_critical_recall: <r>     # ILLUSTRATIVE — no measurement exists
notes: >
  Adds an explicit instruction to leave extractor-owned categories alone;
  cut false criticals on numeric spans from <before> to <after> on DEV (illustrative).
---

# Instruction
...
```

`schema_sha` pinning is what makes region 4 of the context (§6.1) trustworthy: if someone changes `GraderVerdict` without producing a new prompt version, `rehearsal doctor` fails at startup rather than the system silently running a prompt that describes a schema that no longer exists.

### 9.3 Rules

| # | Rule | Why |
|---|---|---|
| P1 | **Append-only.** A prompt file is never edited after it has produced a recorded eval number. Changes create `vN+1`. | Otherwise a number in the registry cannot be traced to text |
| P2 | **`registry.toml` is the only selector.** No code contains a version string. | One place to look, one place to diff |
| P3 | **Every model event records `prompt_id`, `prompt_sha`, `context_sha`, `decode_sha`.** | Any recorded turn is fully reconstructable |
| P4 | **A grader or rubric version change re-triggers EV-01, EV-02, EV-09.** Enforced by `make check`, which compares the active `prompt_id` against the last registry entry. | Prevents an unmeasured instrument from shipping |
| P5 | **Prompts are reviewed like code**, with the diff and the DEV numbers in the same review. | A prompt diff without its metric delta is an opinion |
| P6 | **No prompt text is ever generated at runtime.** Templates fill typed slots; they do not compose instructions. | An instruction assembled at runtime cannot be reviewed |
| P7 | **No prompt lives in a dashboard, a database row, an environment variable, or a notebook cell.** | Stated explicitly because this is the single most common way prompt discipline dies |

### 9.4 Rollback

Rollback is `registry.toml` pointing at the earlier version plus a re-run of the regression suite. Because prompt files are append-only and every recorded number carries its `prompt_id`, a rollback restores a *measured* configuration rather than an approximately-remembered one. `origin: revert` in the header of a re-promoted version records that it happened.

---

## 10. The automated prompt-optimisation loop (L10, rung 1)

The reporting protocol, split discipline and optimisation metric are owned by `docs/08-evals.md` §6 and are not restated. This section owns the *engineering*: what the optimiser can touch, what it cannot, and how it is wired.

### 10.1 Scope

**Optimised:** the grader prompt only — `prompts/grader/vN.md`, regions 1 and 4 of its context (instruction and output-spec phrasing), plus the selection and ordering of few-shot examples drawn **exclusively from the DEV split**.

**Not optimised, and structurally unreachable by the optimiser:**

| Frozen | Why |
|---|---|
| Model weights (no fine-tuning, no LoRA, no RL) | Project-wide scope exclusion. A changed weight file is not inspectable the way a diffed prompt is, and inspectability is the product's credibility |
| The rubric | The rubric encodes the professional standard. An optimiser improving agreement by editing the standard would be optimising the ruler, and the resulting number would mean nothing |
| The error taxonomy and severity definitions | Same reason, one level down |
| The deterministic extractors | They are provably correct on their fixture grid (EV-00 gate = 1.00). There is nothing to optimise |
| `VerdictMerger` precedence rules | Deterministic policy, human-decided |
| Decode config | Grader temperature is 0.0 by design; letting the optimiser move it would trade reproducibility for κ |
| The counterpart-agent prompts | Optimising them against a fidelity metric would produce agents that speak in easy-to-score ways — the leakage failure, arrived at deliberately |
| Anything in TEST | `evals/seal.py` makes this structural, not a matter of discipline |

That last row is the one worth pausing on: it is entirely possible to raise the grader's agreement score by making the *task* easier, and every mechanism above exists to make sure the optimiser cannot reach the task.

### 10.2 The program being optimised

The grader is expressed as a single typed module so that a DSPy/GEPA-style optimiser has one well-defined thing to search over.

```python
# src/rehearsal/scoring/optimise/program.py

class GraderProgram:
    """One structured call. The optimiser may rewrite `instruction` and choose
    `demos`; everything else is frozen by construction."""

    def __init__(self, instruction: str, demos: Sequence[CalibrationItem]) -> None: ...

    def __call__(self, ctx: GraderContext) -> GraderVerdict: ...
```

The search space, exactly:

| Component | Space | Bound |
|---|---|---|
| `instruction` | Free text, mutated by the optimiser's reflective-edit step | ≤ 900 tokens; longer candidates are rejected before evaluation, since context budget is a hard constraint (§6.2) |
| `demos` | Subset + ordering of DEV items | 0–4 items, ≤ 700 tokens total |
| Output-spec phrasing | Free text around a fixed generated schema block | The schema block itself is immutable |

### 10.3 Wiring

```bash
rehearsal optimise grader --budget 120 --seed 17        # DEV only; TEST is unreachable
rehearsal optimise report opt-0f31c9                    # four-cell table, DEV and TEST
```

Mechanics:

- Candidates are evaluated by **re-scoring recorded calibration items and recorded sessions**, never by running live sessions with humans in them (`rehearsal replay --rescore`, `docs/03-system-architecture.md` §10.1).
- The optimiser runs on the `rehearsal-grader` host in lane `COMPOSER` — off-session, never competing with a trainee.
- Every candidate evaluation is a row in the run record: candidate hash, DEV metrics, tokens, wall time. The full search trace is retained, not just the winner, because the trace is what tells a reader whether a gain came from 8 candidates or 400.
- The optimiser's proposer and its evaluator are the same 12 B model at temperature 0 for evaluation and a higher temperature for proposal. There is no larger "teacher" model anywhere, because there is no cloud in this project.

### 10.4 Honest reporting, in one line each

`docs/08-evals.md` §6 owns the full protocol; the parts that constrain engineering:

- The optimisation objective has a **hard floor** at `critical_recall ≥ 0.90` that returns 0.0 rather than a penalty — a penalty is a price and an optimiser will pay it; a floor is a wall.
- **One pre-registered candidate** is carried to TEST. The registry entry is written before unsealing.
- **All four cells** are reported (baseline-DEV, candidate-DEV, baseline-TEST, candidate-TEST) with intervals, and the DEV−TEST gap is printed as the overfitting estimate.
- If the TEST improvement is smaller than its interval width, the result is reported as **"no measurable improvement on the sealed split"**, even if DEV improved a lot and the new prompt reads better.
- Regressions are published with the same prominence as gains.

---

## 11. Failure handling

Every model failure has a deterministic fallback. No failure path involves a model deciding how to recover from a model.

### 11.1 Refusal

A local Gemma asked to voice a patient describing pain, or to score an utterance containing a graphic symptom description, can decline. Refusal is handled structurally rather than argued with:

| Where | Detection | Fallback |
|---|---|---|
| Counterpart agent | `reply_text` matches a refusal-shape check (assistant-voice phrases, meta-commentary about roleplay), or `reply_text` is empty | Use the node's **scripted fallback line** — every graph node carries one, authored with the scenario. Emit `agent_refusal`, continue the encounter. The trainee still gets a valid interpreting task |
| Grader | `unscorable_reason` is set, or output is a refusal shape | Verdict is marked `partial` with `semantic_unavailable`; extractor findings stand; the semantic categories are reported as **not assessed**, never as *no error found* |
| Coach | Any refusal | Silence. A missing hint is invisible to the loop |
| Composer | Any refusal | Candidate dropped, seed material flagged for human review |

The scripted fallback line is what makes counterpart refusal a non-event, and it is the reason every node must carry one — validated at scenario ingest, not at runtime.

**We do not add "you are permitted to…" prose to the prompts to argue a model out of refusing.** The refusal rate per role is measured and reported; if it is high enough to degrade sessions, the fix is the scenario framing or the model choice, both of which are inspectable, rather than a prompt that has been argued into compliance.

### 11.2 Malformed output

With constrained decoding (§7.1) syntactic malformation is close to impossible; the ladder handles semantic malformation and grammar escapes.

| Attempt | Live path (clinician/patient) | Off path (grader) |
|---|---|---|
| 1 | Constrained decode, normal params | Constrained decode, temp 0 |
| 2 | **No retry** — budget is 900 ms; a retry blows the turn. Go straight to scripted fallback | One retry at temp 0 with the failing field named and the schema echoed |
| 3 | — | Extractor-only verdict, `grader_unavailable`, verdict marked `partial` |

Events: `schema_escape`, `grader.failed`, `verdict.merged` with `partial=true`. A session's count of partial verdicts appears in the debrief, because a session scored half-deterministically is not the same measurement as a fully scored one.

### 11.3 Persona and language drift

Four deterministic detectors, all cheap, all on the live path:

| Detector | Rule | Cost |
|---|---|---|
| Language check | Character-class and stopword ratio over `reply_text` against the role's expected language; a clinician utterance scoring Spanish-dominant fails | < 1 ms, no model |
| Meta-commentary check | Output contains assistant-voice markers ("As an AI", "In this roleplay", "the interpreter should") | < 1 ms |
| Fact containment | `reply_text` contains a term from the *other* agent's fact partition that has not yet been disclosed | < 2 ms, term-set lookup |
| Node conformance | `node_satisfied=True` while the node's required facts are absent from the utterance | < 2 ms |

Escalation, deterministic:

1. **First failure in a session:** one retry with the same context plus a one-line code-owned corrective directive appended (a fixed constant, never model-generated).
2. **Second failure:** scripted fallback line, **KV cache reset for that role**. A drifted cache reproduces drift; resetting is more reliable than instructing.
3. **Third failure in the same session:** the session continues in scripted-line mode for that role and is flagged `persona_degraded` in the debrief, so the trainee knows the encounter got more mechanical.

Every failure appends an event; the per-session rate feeds EV-04 persona consistency. Drift is not treated as noise to be suppressed — it is the live-tier right-sizing claim being tested continuously (§3.2).

### 11.4 Latency overrun

| Stage | Budget | On overrun |
|---|---|---|
| Counterpart generation | 900 ms | Stop generation at the deadline. If a complete sentence exists, speak the truncated-to-sentence-boundary text; otherwise the scripted fallback. Never emit a mid-word cut to TTS |
| TTS first audio | 400 ms | Degrade to system voices (DegradeLevel 3) |
| Grader wall | 3 500 ms | Verdict lands late; the coach hint for that turn is dropped (`coach.suppressed`). Nothing blocks |
| Grader sustained | queue depth ≥ 2 | DegradeLevel 1, then 2: grader shed entirely, extractor-only scoring, explicit banner in the UI |
| Composer | none | Authoring-time; may take as long as it takes |

The ladder itself lives in `docs/03-system-architecture.md` §14. The model-facing point is that **no overrun is ever resolved by asking a model to hurry** — the parameters that could shorten generation (max tokens, temperature) are part of the versioned decode config, and changing them at runtime would mean the recorded `decode_sha` no longer describes what ran.

### 11.5 Cascading and containment

| Scenario | Containment |
|---|---|
| Live host OOM / Metal fault | Process dies alone. One auto-restart with a 20 s health probe; a second failure inside a session aborts cleanly rather than limping |
| Grader host killed under memory pressure | Session continues at DegradeLevel 2. This is a designed outcome, not an incident |
| Both hosts wedged | Clean abort with a complete, valid event-log prefix. A stopped session with an intact record beats a continuing session with a broken one |
| `IsolationViolation` at runtime | Turn aborts, session aborts, event recorded with offending fields. This is never downgraded to a warning — a leak invalidates the session's measurement, so continuing would produce a number we would have to throw away anyway |

---

## 12. What we deliberately do not use

Each row states the price we pay, because a rejection without a stated cost is marketing.

| Not used | Why not | What we pay for that |
|---|---|---|
| **Cloud inference (any provider) in the core loop** | Trainee speech in a clinical role-play is sensitive; a network round trip cannot meet the turn budget reliably; a product that stops working offline cannot be used in a clinic with poor connectivity | Smaller models, more prompt work, more failure handling |
| **Agent frameworks (LangChain, CrewAI, LlamaIndex, AutoGen, …)** | The framework's value is hiding orchestration; orchestration inspectability *is* this product's credibility. Seed control, context assembly and the isolation chokepoint are the three things a framework would obscure, and they are the three things that must stay visible | We hand-write the loop, the retries and the typed calls — roughly 600 lines of orchestrator |
| **Fine-tuning / LoRA / RL / any weight training** | Project-wide scope exclusion. A prompt diff is reviewable; a weight delta is not. Also, the calibration set is 40 items — far too small to train on and exactly the right size to *measure* against | We give up whatever accuracy tuning would buy, and we accept prompt-level ceilings |
| **A cloud "teacher" model for optimisation or label generation** | Human labels are the anchor (`SETUP.md` §6). A cloud model generating labels would replace the external anchor with a second opinion and quietly make the project a distillation exercise | Labelling is slow and human-bound |
| **Chain-of-thought / self-critique / multi-pass grading** | It makes the instrument's output a property of an unwritten pipeline. If added, it becomes part of the versioned artifact and requires full re-calibration (§7.4) | Possibly some accuracy on hard items |
| **Ensembling or multiple graders voting** | Doubles memory and makes the reported κ a property of a committee that is harder to version, diff and reproduce | Variance reduction we do not get |
| **A vector database / retrieval in the live loop** | Breaks ground-truth-by-construction: if an agent can retrieve a fact we did not author, we no longer know exactly what the source utterance contained | Agents are limited to what the scenario provides |
| **Tools for any agent** | See §4.6. Retrieval breaks principle 2; arithmetic belongs to the extractors | The composer cannot look up drug dosing; deterministic validators plus human review do it instead |
| **A separate speech-recognition stage in the critical path** | The live model takes audio natively; adding ASR adds a serial stage and a second error source inside the turn budget | We depend on `heard_verbatim` fidelity, which is therefore **measured**, with an off-path re-transcription fallback (`docs/03-system-architecture.md` §7) |
| **Cross-session conversational memory** | §8.1: breaches isolation, destroys reproducibility, makes practice easier rather than better, and accumulates a privacy liability | Agents cannot build rapport across sessions |
| **Model-written rolling summaries** | A second unmeasured model on the critical path, compounding error, non-reproducible context | A blunter deterministic summary |
| **Prompts stored anywhere but the repo** | Rule P7. Every alternative makes a recorded number untraceable to text | No hot-editing without a commit |
| **Sampling in the grader** | A measuring instrument must return the same reading for the same input | No diversity benefit we would not have to re-calibrate anyway |
| **Building our own inference server** | Project-wide scope exclusion. MLX and llama.cpp are both maintained, both fast enough, and both replaceable behind `ModelHostClient` | We inherit their bugs and their release cadence |
| **Multi-tenant / fleet serving** | Project-wide scope exclusion. One machine, one user, no server | Nothing, at this scope |

---

## 13. Open questions

Genuinely undecided. Each carries the measurement that would decide it.

| # | Question | Current default | What decides it |
|---|---|---|---|
| Q1 | Does passing stripped `deterministic_findings` into the grader help or bias it? | Passed, stripped to kind+span | A/B on DEV: κ and `fp_rate_clean` with and without the field |
| Q2 | Is `heard_verbatim` faithful enough to be the canonical rendering? | Yes, provisionally | Transcription fidelity against hand transcripts of the calibration audio (`docs/08-evals.md`); the fallback is off-path re-transcription |
| Q3 | Is the 12 B grader actually necessary, or does E4B match it? | 12 B | Run EV-01 with an E4B grader; if κ falls inside the 12 B interval, demote and free ~8 GB |
| Q4 | Does an explicit `clean` boolean reduce false alarms versus an empty list? | Explicit boolean | `fp_rate_clean` on DEV, both schemas |
| Q5 | Optimal few-shot demo count for the grader | 0, until the optimiser chooses | The optimiser's own DEV search, with the token cost counted against the context budget |
| Q6 | Should `recent_turns` be 6 lines or fewer? | 6 | EV-04 persona consistency versus context cost, swept over 2/4/6/8 |
| Q7 | Do the counterpart agents need separate KV caches per role, or is one cache with role prefixes sufficient on memory-tight machines? | Separate | Memory headroom measured by `rehearsal doctor` on the target machine |
| Q8 | Quantisation level for both tiers | 4-bit weights **[proposed]** | Per-tier eval at 4-bit vs 8-bit: EV-04 for live, EV-01/EV-02 for the grader, against measured resident memory |

---

## Related documents

`docs/03-system-architecture.md` · `docs/05-voice-pipeline.md` · `docs/06-scoring-engine.md` · `docs/07-data-and-scenarios.md` · `docs/08-evals.md` · `docs/12-security-privacy.md` · `SETUP.md` §6

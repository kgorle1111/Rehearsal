# 02 — The Capability Vertical

How Rehearsal is built: as a deliberate climb, rung by rung, where **no rung is started before the rung beneath it has produced a number**.

This document is the construction contract. For each rung it states what the rung *is* in this product concretely, what it rests on, exactly what gets built (files, signatures, artifacts), the eval that proves the rung was earned, the pass gate, what would falsify the rung, and the "why didn't you just do X?" question that the rung pre-answers with a measurement rather than an opinion.

It does not restate the eval harness — metric definitions, statistical conventions, split discipline and the registry live in `docs/08-evals.md`, and the calibration protocol that anchors everything lives in `SETUP.md` §6. This document says *why each rung exists and when it is done*; those documents say *how each number is computed*.

---

## 1. What "vertical" means here, and why it is not a schedule

A horizontal project adds surface: more scenarios, more languages, more clinics, more users. A vertical project adds *depth of capability*: each rung does something the rung below provably could not, and the added capability is demonstrated by a measurement that the lower rung would fail.

Three rules govern the climb.

**Rule 1 — Dependency, not time.** A rung is unblocked when its prerequisite has a recorded eval result, not when a period elapses. There are no dates anywhere in this project's planning material. `docs/16-roadmap.md` orders work the same way.

**Rule 2 — A rung without a number does not exist.** Principle 6 (*everything is measured*) is enforced literally: sign-off for a rung is a row in the eval registry (`data/evals/registry.db`), produced by a named suite module, on a named split, with a denominator and an interval. "Implemented" is not a state this project recognises. The states are `unbuilt`, `built / unmeasured`, `measured`, `signed off`.

**Rule 3 — Each rung answers one skeptical question with a measurement.** Every rung in this document exists because a reasonable senior engineer would ask "why is that necessary?" The answer is never architecture philosophy. It is an eval that would have come out differently if the rung were absent — and in two cases (L6, L8) the eval is explicitly allowed to come out *null*, which changes the claim rather than the architecture.

### 1.1 Why the climb starts at L4

Rungs below L4 — a single prompt, a chat wrapper, a script with a model call in it — are not skipped because they are beneath us. They are skipped because Rehearsal's first useful artifact already requires typed structured output validated against a schema, deterministic pre-checks in front of it, and a human-labelled reference set to compare against. That *is* L4. Building a chat-shaped precursor first would produce a thing with no eval attached, which by Rule 2 does not exist.

Rung L9 is likewise absent, deliberately: it is the fleet/multi-tenant scale rung, and it is declined in §10 with its reversal condition.

---

## 2. The dependency graph

Each arrow means "cannot begin until the source rung has a **recorded eval result**, not merely code". The label on the arrow is the artifact that must be measured first.

```
                         ┌──────────────────────────────────────┐
                         │  ANCHOR (not a rung — a prerequisite)│
                         │  Calibration set: 40 turns, human-   │
                         │  labelled blind, DEV 25 / TEST 15    │
                         │  SETUP.md §6                         │
                         └───────────────┬──────────────────────┘
                                         │ dev.jsonl exists,
                                         │ kappa_intra recorded
                                         ▼
   ┌───────────────────────────────────────────────────────────────────┐
   │ L4  Neuro-symbolic fidelity scorer                                 │
   │     EV-00 extractor conformance = 1.00                             │
   │     EV-01 kappa_macro   EV-02 critical_recall   EV-03 ceiling      │
   └───────┬───────────────────────────────────────────┬───────────────┘
           │ a rendering can be scored                 │ scoring exists,
           │ (verdict schema frozen)                   │ so "difficulty"
           ▼                                           │ is observable
   ┌───────────────────────────────────────────┐       │
   │ L5  Bare-hands counterpart agent           │       │
   │     driven by ClinicalStateGraph           │       │
   │     EV-04 persona_consistency              │       │
   └───────┬───────────────────────────────────┘       │
           │ agent turns are deterministically          │
           │ checkable → an A/B has a valid metric      │
           ▼                                            │
   ┌───────────────────────────────────────────┐        │
   │ L6  Packaged session skill (versioned)     │        │
   │     EV-06 skill_delta                      │        │
   └───────┬───────────────────────────────────┘        │
           │ protocol is portable + versioned →         │
           │ a full session has a defined contract      │
           ▼                                            │
   ┌───────────────────────────────────────────┐        │
   │ L7  Session orchestration + human gates    │        │
   │     EV-07 latency   EV-08 completion,      │        │
   │           trainer_override_rate            │        │
   └───────┬───────────────────────────────────┘        │
           │ full sessions run end-to-end and are       │
           │ replayable → a paired A/B over sessions    │
           ▼                                            ▼
   ┌───────────────────────────────────────────────────────────────────┐
   │ L8  Multi-agent with information isolation                         │
   │     clinician ⟂ patient ⟂ coach ⟂ grader                           │
   │     EV-05 leakage_delta  (needs L4's scorer to measure difficulty  │
   │                           AND L7's sessions to generate the arms)  │
   └───────────────────────────┬───────────────────────────────────────┘
                               │ the grader prompt is stable, the metric
                               │ is trustworthy, and the ceiling is known
                               ▼
   ┌───────────────────────────────────────────────────────────────────┐
   │ L10 (rung 1)  Automated prompt optimisation of the grader          │
   │     EV-01 re-run under the §6 protocol of docs/08-evals.md         │
   │     Reported on the SEALED TEST split, once                        │
   └───────────────────────────────────────────────────────────────────┘
```

Two structural facts this diagram is drawn to make unmissable:

1. **L8 has two parents.** The leakage A/B needs L7 to produce paired sessions *and* L4 to produce the difficulty measure that the two arms are compared on. Attempting L8 with a scorer whose κ is unknown produces an effect size in units nobody can interpret.
2. **L10 is last for a reason that is not sequencing convenience.** An optimiser maximises whatever metric you hand it. Handing it a metric whose agreement with humans has not been established, and whose human ceiling is unknown, produces a prompt that is excellent at a proxy for nothing. L10 is gated on `kappa_intra` existing (`SETUP.md` §6.5 step 6), not merely on the grader running.

---

## 3. L4 — Application / one structured call: the neuro-symbolic fidelity scorer

### What it is, concretely

Given a triple (`source_utterance`, `trainee_rendering`, `direction`), produce a typed verdict: a list of findings, each with a taxonomy category, a character span into the rendering (or the source, for omissions), a severity, and a note. The source utterance is known by construction — the system generated it — which turns the task from *judge quality* into *compare a known sentence to its rendering*. That reframing is the entire reason this rung is tractable (principle 2).

The scorer is **neuro-symbolic** (principle 3). Two passes, then a deterministic merge:

| Pass | Handles | Mechanism | Can it be wrong "interestingly"? |
|---|---|---|---|
| Symbolic | numbers, dosages, units, frequencies, negation, laterality, allergies, temporal markers | Hand-written extractors + normalisation tables, per-language | No — a mismatch is a bug with a failing fixture |
| Semantic | register shift, idiom, pragmatic force, editorialization, role exchange, false fluency, first-person discipline | **One** structured call to the 12B grader, typed output | Yes — hence κ, hence the ceiling |
| Merge | precedence, deduplication, severity assignment | Deterministic table-driven rules in `VerdictMerger` | No — table-driven tests |

The critical error class — the one the clinical literature identifies as consequence-bearing — is handled entirely by the symbolic pass. **The model is never the last line of defence on a dosage.**

### What it rests on

The calibration set (`SETUP.md` §6). Nothing else. L4 needs no agents, no audio, no session — it can be exercised entirely from JSONL fixtures. This is why it is first: it is the only rung whose prerequisite is human labour rather than another rung.

### Exactly what gets built

```
src/rehearsal/scoring/
├── taxonomy.py          # ErrorKind, Severity, Finding, Verdict  (the frozen contract)
├── extractors/
│   ├── __init__.py      # EXTRACTORS: tuple[Extractor, ...]; run_all()
│   ├── numbers.py       # cardinals, ordinals, es/en numeral words, decimals
│   ├── dosage.py        # amount + unit + form; mg/mcg/mL/g, tablet/pill/comprimido
│   ├── frequency.py     # q4h, "twice a day", "cada ocho horas", PRN
│   ├── negation.py      # scope-aware polarity; the negation-flip detector
│   ├── laterality.py    # left/right/bilateral, izquierdo/derecho/ambos
│   ├── allergy.py       # allergen mentions + polarity, drug-class aware
│   └── temporal.py      # onset, duration, since-when; relative → normalised
├── grader.py            # one structured call; SEMANTIC categories only
├── merge.py             # VerdictMerger — deterministic precedence
└── queue.py             # ScoreQueue — off-critical-path dispatch (used from L7)

prompts/grader/v1.md     # versioned, never edited in place
data/fixtures/extractors/*.jsonl
data/calibration/{dev,test,relabel}.jsonl
src/rehearsal/evals/suites/{ev00_extractors,ev01_calibration,ev02_critical_recall,ev03_human_ceiling}.py
```

Frozen signatures other rungs may depend on:

```python
# src/rehearsal/scoring/taxonomy.py
class ErrorKind(str, Enum):
    OMISSION = "omission"
    ADDITION = "addition"
    SUBSTITUTION = "substitution"
    DISTORTION = "distortion"                 # includes negation flips
    EDITORIALIZATION = "editorialization"
    ROLE_EXCHANGE = "role_exchange"
    REGISTER_SHIFT = "register_shift"
    FALSE_FLUENCY = "false_fluency"
    FIRST_PERSON_VIOLATION = "first_person_violation"

class Severity(str, Enum):
    CRITICAL = "critical"       # could change clinical action
    NON_CRITICAL = "non_critical"

@dataclass(frozen=True, slots=True)
class Finding:
    kind: ErrorKind
    severity: Severity
    span: tuple[int, int]
    surface: str
    note: str
    origin: Literal["symbolic", "semantic"]   # provenance is never lost

@dataclass(frozen=True, slots=True)
class Verdict:
    turn_id: str
    findings: tuple[Finding, ...]
    grader_available: bool        # False → extractor-only, reported as `partial`
    prompt_version: str
    model_id: str
    seed: int
```

```python
# src/rehearsal/scoring/grader.py
def grade_semantic(
    source: str, rendering: str, direction: Direction, *,
    prompt_version: str, seed: int,
) -> tuple[Finding, ...]: ...

# src/rehearsal/scoring/merge.py
def merge(symbolic: Sequence[Finding], semantic: Sequence[Finding]) -> Verdict: ...
```

`origin` on every `Finding` is load-bearing, not bookkeeping: the report UI must be able to tell a trainee *this dosage error was checked, this register note was judged* (`docs/09-ui-ux.md`), and per-category reliability disclosure depends on it.

### The eval that proves the rung was earned

| Eval | Metric | How computed | Gate |
|---|---|---|---|
| EV-00 | `extractor_conformance` | Exact-match over the fixture grid, all **seven implemented** extractors, both languages (`temporal` is registered but not yet implemented and is excluded — `docs/06-scoring-engine.md` §4.10) | **= 1.00**, no exceptions |
| EV-01 | `kappa_macro` | Cohen's κ per taxonomy category on turn-level presence/absence, macro-averaged over categories that occur; DEV for promotion, TEST reported | ≥ 0.60 on DEV *(proposed — see below)* |
| EV-02 | `critical_recall` | TP_critical / (TP_critical + FN_critical) over human-labelled critical findings | ≥ 0.90 on DEV; **outranks EV-01 when they conflict** |
| EV-03 | `kappa_intra` (and `kappa_inter` if available) | Labeller vs self on the delayed re-label sample | Report-only, but **must exist** before any κ is published |

Computation details, span-matching rules and interval conventions: `docs/08-evals.md` §3 and §4.1–4.4. The κ gate of 0.60 is marked **proposed** there and should be re-derived as a fraction of the measured ceiling once `kappa_intra` exists; an absolute constant is a convention, not a domain-derived threshold.

### What would falsify this rung

- `kappa_macro` on TEST is at or near the level obtained by a trivial baseline (always-predict-omission, or a length-difference heuristic). The baseline is run in EV-01 for exactly this reason: a κ that is not distinguishable from a bag-of-words heuristic means the semantic pass is decorative.
- `critical_recall` cannot be pushed to 0.90 by extractor work. That would mean the critical class is not, in fact, symbolically decidable in real renderings — which invalidates principle 3, not just this rung. The response is to narrow the critical class to the sub-categories that *are* decidable and re-label, not to hand the residue to the model.
- `fp_rate_clean` stays high while κ is acceptable. A scorer that finds errors in clean turns is unusable in training regardless of its agreement statistics: it teaches trainees to distrust the instrument.
- Per-category recall for `omission` is weak. Omission is 52% of real-world interpreter errors (`docs/01-research.md`); a scorer that misses the dominant class is not a fidelity scorer.

### The "why didn't you do X" this rung pre-answers

**"Why not just ask a big model 'was this a good interpretation?'"**
Because there is no ground truth in that question, so there is nothing to measure agreement against, so the answer's error rate is unknowable. EV-01 answers it with a number *because* the question was reframed to a comparison against a known source. The comparison is EV-01 (structured comparison against known source) vs the free-judgement baseline recorded in the same suite; the honest report is the κ of both.

**"Why hand-write extractors instead of letting the model extract dosages?"**
EV-00 answers this and is the only eval in the project with a gate of exactly 1.00. Dosage, negation and laterality are decidable string problems. A model that gets them right 97% of the time is, on the class of errors that could change clinical action, wrong once every thirty-three turns — and unpredictably. `extractor_conformance = 1.00` is not aspiration; it is what "decidable" means.

---

## 4. L5 — Bare-hands agent: the counterpart driven by a clinical state machine

### What it is, concretely

The clinician and patient are **not** free-running chatbots. Each turn, a deterministic `ClinicalStateGraph` selects the current node; the node carries the encounter phase, the facts the agent is permitted to know, the persona invariants, and a scripted fallback line. The model's job is to render that node's intent as natural speech in its language and register. The graph decides *what happens*; the model decides *how it is said*.

"Bare hands" means: a raw, typed asyncio loop. No agent framework. Build the loop, own the loop, be able to point at the exact line where a failure occurred. The rationale in full is `docs/03-system-architecture.md` §15; the operational consequence is that every agent turn is a pure function of (node, context, seed, prompt version), which is precisely what makes EV-04 deterministic.

### What it rests on

L4's measured scorer. Not for its output — the counterpart agent never sees a verdict — but because "the agent behaved" and "the agent was easy to interpret" are different claims, and only the second is measurable, and it is measurable only via a scorer whose own error rate is known. Building the agent before L4 would leave persona quality as an aesthetic argument.

### Exactly what gets built

```
src/rehearsal/content/
├── graph.py             # ClinicalStateGraph, NodeId, advance(), validate_at_ingest()
├── bank.py              # ScenarioBank — serves scenario + graph + term manifest
└── terms.py             # TermManifest — the scenario's clinical vocabulary
src/rehearsal/runtime/agents/
├── clinician.py         # ClinicianAgent  (en-US, E4B, native audio in)
├── patient.py           # PatientAgent    (es-MX, E4B, native audio in)
└── context.py           # ContextAssembler — allowlist, the isolation chokepoint
prompts/{clinician,patient}/v1.md
src/rehearsal/evals/suites/ev04_persona.py
```

```python
# src/rehearsal/content/graph.py
@dataclass(frozen=True, slots=True)
class Node:
    id: NodeId
    phase: EncounterPhase          # intake | history | exam | plan | teach_back | close
    speaker: Literal["clinician", "patient"]
    intent: str                    # what must be conveyed at this node
    facts: frozenset[FactId]       # the ONLY facts this agent may state here
    must_contain: tuple[Check, ...]   # deterministic post-conditions
    must_not_contain: tuple[Check, ...]
    fallback_line: str             # used verbatim on a second schema failure
    next: tuple[NodeId, ...]

def advance(graph: ClinicalStateGraph, current: NodeId, signal: TurnSignal) -> NodeId: ...
```

Each generated turn is checked against the node before it is spoken. Failure → one re-prompt at temperature 0 → still failing → the node's `fallback_line` is spoken and the event log records `agent.fallback_used`. The trainee's session never stalls on a model that will not comply.

### The eval that proves the rung was earned

| Metric | How computed | Gate |
|---|---|---|
| `persona_consistency` | Fraction of counterpart turns satisfying **every** deterministic check for their node: correct language, correct speaker role, no facts outside `facts`, all `must_contain` satisfied, no `must_not_contain` hit, register band within the node's declared range | ≥ 0.95 turn-level *(proposed)* |
| rubric-vocabulary canary | Zero occurrences of taxonomy terms, rubric vocabulary or scoring language in any counterpart utterance | **= 1.00** *(decided — binary)* |
| `fact_invention_rate` | Clinical facts asserted that are not in the node's `facts` set nor in the scenario record | Must be 0 by construction; any non-zero value is a defect, not a score |

Full definition: `docs/08-evals.md` §4.5. Critically, **none of these are model-judged.** Every check is a string, set-membership or classifier-free predicate over the node contract. The eval for a model-driven rung is deterministic, which is the point of putting the state graph underneath it.

### What would falsify this rung

- `persona_consistency` cannot reach 0.95 without shrinking node intents to the point that the agent is effectively reading a script. If the only way to pass is to remove the model's contribution, the state-graph design is over-constraining and the encounter will not feel real enough to train against — a realism failure that no number in this suite would otherwise catch.
- Fallback usage is high (say, >5% of turns). The agent is then not a bare-hands agent; it is a branching script with a model attached, and the rung should be re-described honestly as such.
- The E4B-class model cannot hold a persona across a full encounter under quantisation. Then the rung is earned only at a larger live model, which collides with the resident-memory budget in `SETUP.md` §4 — a real trade, to be reported, not hidden.

### The "why didn't you do X" this rung pre-answers

**"Why not use LangChain / CrewAI / an agent framework?"**
Because reproducibility, seed control and inspectable failure points are the product's credibility, and a framework hides exactly the layer that must stay visible. The measured form of this argument: EV-04 is only computable because every turn is a pure function of (node, context, seed, prompt version) and every context is assembled by one allowlist function. A framework that assembles context on your behalf makes both `persona_consistency` and the L8 leakage A/B unmeasurable — not harder, unmeasurable.

**"Why a state graph instead of just prompting the model to stay in character?"**
`fact_invention_rate` answers it. "Stay in character" has no post-condition; a node's `facts` set does. Instructing a model not to invent clinical facts is a request; a set-membership check is a guarantee.

---

## 5. L6 — Packaged skill: the session protocol as a portable, versioned definition

### What it is, concretely

The session protocol, the error taxonomy and the rubric are extracted out of prompt strings and into one versioned, portable skill definition — a directory with a manifest, the taxonomy, the rubric, worked examples, and the turn protocol. It is loaded by the grader and the coach; it is **never** loaded by the clinician or the patient (that exclusion is the whole of L8, enforced here at the packaging boundary).

Why package it at all: the taxonomy and rubric appear in the grader prompt, in the optimiser's metric, in the review UI's labels, and in the calibration protocol. Four copies of a definition means four copies that drift. A packaged skill makes the definition a single versioned artifact with a checksum that the eval registry records alongside every run.

### What it rests on

L5. Before a skill can be A/B'd, there must be a task whose correctness is checkable without human judgement. L5 supplied exactly that (node post-conditions), and L4 supplied the verdict schema the protocol produces. Packaging first would be packaging a protocol nobody had run.

### Exactly what gets built

```
skills/interpreting-session/
├── SKILL.md             # the turn protocol: who speaks, what the trainee does,
│                        # what is captured, what the review gate asks
├── taxonomy.md          # the nine categories, definitions, severity rules
├── rubric.md            # what counts as critical; worked boundary cases
├── examples/*.md        # few-shot items — drawn ONLY from DEV, never TEST
├── manifest.toml        # name, version, checksum, consumers, non-consumers
└── CHANGELOG.md
src/rehearsal/skills/loader.py     # load(), checksum(), assert_not_for_role()
src/rehearsal/evals/suites/ev06_skill_ab.py
```

```toml
# skills/interpreting-session/manifest.toml
name = "interpreting-session"
version = "1.0.0"
consumers      = ["grader", "coach", "review_ui", "calibration_protocol"]
non_consumers  = ["clinician", "patient"]   # enforced by loader.assert_not_for_role()
sha256 = "…"                                # recorded in every eval registry row
```

`assert_not_for_role()` raises `IsolationViolation` at load time. The isolation claim is enforced twice: at packaging (here) and at context assembly (`ContextAssembler`, L5/L8). Two independent chokepoints, because a single one is a single bug away from invalidating the project's central claim.

### The eval that proves the rung was earned

| Metric | How computed | Gate |
|---|---|---|
| `skill_delta` | Difference in session-protocol checklist pass rate, with vs without the packaged skill loaded, **paired by scenario and seed** | Skill must not be worse: lower CI bound ≥ −0.02 |

The checklist is deterministic: did the turn protocol run in order, was every trainee turn captured and scored, did the verdict conform to the schema, did the review gate present the required fields, were severities assigned per the rubric's stated rules. Paired design with identical seeds; permutation interval. Detail in `docs/08-evals.md` §4.7.

**This eval is allowed to return null, and the honest outcome is reported as such.** A CI containing zero means the skill delivers no measurable task-correctness benefit. In that case the skill still ships — because single-source-of-truth for the taxonomy is a maintenance argument, and drift between four copies is a real defect class — but it is described as a maintenance artifact, never as a performance improvement. Principle 7 applies to our own architecture decisions, not only to trainee scores.

### What would falsify this rung

- `skill_delta` is materially negative. Packaging cost information the inline prompts were carrying; the packaging boundary is drawn in the wrong place.
- The skill cannot be loaded by an independent consumer (the review UI, the calibration protocol) without pulling in runtime code. Then it is not portable, it is a refactor, and the rung's description is wrong.
- Checksum churn: if `manifest.toml`'s version changes on most commits, the artifact is not a stable definition and the eval registry's provenance is noise.

### The "why didn't you do X" this rung pre-answers

**"Why not just keep the rubric in the grader prompt?"**
Because the rubric has four consumers and the calibration protocol is one of them. If the labeller's rubric and the grader's rubric can drift, κ measures drift as disagreement and the headline number quietly becomes uninterpretable. The measurement that makes this concrete is not `skill_delta` — it is that every registry row records the skill checksum, so any κ change can be attributed to prompt, model, or rubric, rather than guessed at.

---

## 6. L7 — Pipeline with human gates: full session orchestration

### What it is, concretely

The complete loop: scenario bound → seeds drawn → clinician speaks (en) → trainee interprets (es) → patient responds (es) → trainee interprets (en) → repeat through the encounter arc → session closes → fidelity report written → **human review gate** → optional trainer override. Audio in is native to the live model; scoring runs off the critical path (principle 5); every state transition is an append to a hash-chained event log; any session is replayable.

The two human gates are not UI decoration, they are principle 1's third clause:

| Gate | Who | What they can change | What it blocks |
|---|---|---|---|
| In-session control | Trainee | Pause, redo a turn, abort, decline coach feedback | Nothing is scored that the trainee did not choose to attempt |
| Post-session review | Trainee, then optionally trainer | Add, remove or re-severity any finding | An unreviewed session is reported as `unreviewed`, never as `agreed` |

The override is recorded as a first-class event, not a mutation. `trainer_override_rate` is derived from those events and is the project's only direct measurement of whether humans actually trust the grader in practice.

### What it rests on

L6 (a versioned protocol the orchestration executes) and, transitively, L5 and L4. Orchestration before a stable protocol produces a state machine that is rewritten every time the protocol changes.

### Exactly what gets built

```
src/rehearsal/orchestrator/{loop,states,scheduler,budget,seeds,resume}.py
src/rehearsal/runtime/{audio_in,tts,hosts}.py
src/rehearsal/store/{db,events,blobs,projections,migrations/}
src/rehearsal/api/{app,ws,routes_sessions,routes_reports,routes_review}.py
frontend/                       # vanilla-JS SPA; session view + report + review gate
src/rehearsal/evals/suites/{ev07_latency,ev08_session}.py
data/fixtures/sessions/*.json   # replayable transcripts
```

Component responsibilities, the state machine, crash-resume rules, the event schema and the SQLite DDL are in `docs/03-system-architecture.md` §6–§10; the latency budget, barge-in and degradation ladder are in `docs/05-voice-pipeline.md`; the review interface is in `docs/09-ui-ux.md`. They are not repeated here.

The rung-defining property is the scheduler's overlap policy: grading of turn *n* is dispatched to `ScoreQueue` at the moment the trainee begins turn *n+1*. The human's own speaking time is the grader's latency budget. This is the single decision that makes a 12B grader and two live E4B agents coexist on one machine in real time, and `grader_backlog_rate` is the number that says whether it held.

### The eval that proves the rung was earned

| Eval | Metric | How computed | Gate |
|---|---|---|---|
| EV-07 | `p95_first_audio_ms` | 95th percentile, end-of-trainee-speech → first counterpart TTS frame | Within the budget constant in `src/rehearsal/runtime/budget.py` |
| EV-07 | `p99_barge_in_stop_ms` | 99th percentile, trainee speech onset → TTS silence | Within the budget constant |
| EV-07 | `grader_backlog_rate` | Turns where grading of *n* is incomplete when turn *n+1* opens | ≤ 0.05 |
| EV-08 | `session_completion_rate` | Sessions reaching a written report / sessions started | ≥ 0.90 *(proposed)* |
| EV-08 | `turn_capture_loss_rate` | Turns with missing/unusable trainee audio | ≤ 0.02 |
| EV-08 | `trainer_override_rate` | Findings changed at the review gate / findings presented | Investigation band 0.02–0.25 |

`trainer_override_rate` is the most interesting number in the project and the one most easily mis-read, so its interpretation is fixed here and in `docs/08-evals.md` §4.9: **both tails are bad news.** Above the band, the grader is not trusted. Below 0.02, either the grader is genuinely excellent or the reviewer is rubber-stamping, and those two are indistinguishable from the rate alone — which is why a low rate triggers a review of the review, not a celebration.

### What would falsify this rung

- Latency budgets cannot be met with the specified resident memory (~20–24 GB on a 48 GB machine). The degradation ladder in `docs/05-voice-pipeline.md` then becomes the product's normal mode rather than its fallback, and that must be stated as such.
- `grader_backlog_rate` exceeds 0.05 consistently. Principle 5's central claim — that the human's speaking time is a sufficient latency budget — is then false at this model size, and either the grader shrinks or in-session feedback is dropped.
- `turn_capture_loss_rate` above 0.02. A lost turn is unrecoverable trainee effort; this is a data-loss class failure and is never traded for anything.
- `session_completion_rate` is high but sessions are completing by degrading. Completion is measured *at DegradeLevel 0* separately for exactly this reason.

### The "why didn't you do X" this rung pre-answers

**"Why not score after the session instead of during it?"**
Because between-turn coaching is the training mechanism, and it requires a verdict before the next turn. `grader_backlog_rate` is the measurement that says whether that is achievable; if it fails, post-session scoring is the documented fallback, not the design.

**"Why a separate speech-recognition stage — or why not one?"**
There is none in the critical path: the trainee's speech goes directly into the live model's native audio input. The measurement is the latency budget itself. A cascaded ASR stage adds a serial hop to every turn, and EV-07's p95 is where that cost would appear. Transcripts are still produced for the report and the event log — off the critical path, where their latency is free.

**"Why a human gate at all if the scorer is accurate?"**
`trainer_override_rate`. Until that number exists and sits inside its band, "the scorer is accurate" is an untested belief. And even after it exists, the gate stays: the score is a formative training signal, never employment evidence (`docs/12-security-privacy.md`).

---

## 7. L8 — Multi-agent with information isolation

### What it is, concretely

Four session-time agents (the off-session `ScenarioComposer` is excluded — see `docs/04-ai-engineering.md` §2), four disjoint context allowlists:

| Agent | Sees | Never sees |
|---|---|---|
| Clinician (en-US, E4B) | Its node's facts, encounter phase, its own dialogue history, the trainee's rendered speech | The rubric, the taxonomy, any verdict, the learner model, the patient's private facts |
| Patient (es-MX, E4B) | Its node's facts, symptom state, its own history, the trainee's rendered speech | The rubric, the taxonomy, any verdict, the learner model, the clinician's private facts |
| Grader (12B, off-path) | Source utterance, trainee rendering, direction, the packaged skill | Which trainee, prior verdicts, the learner model, agent internals |
| Coach (grader host, low priority) | The merged verdict, the learner model | Anything that would let it re-judge — it phrases, it does not score |

Enforcement is one function. `ContextAssembler` builds every model context from a per-role field allowlist and raises `IsolationViolation` on any field not on the list. Allowlist, never blocklist: a blocklist is wrong the moment a new field is added, silently.

**Why this is the load-bearing justification for multi-agent architecture:** if the clinician or patient could see the scoring rubric, they would unconsciously speak in easy-to-interpret ways — shorter sentences, fewer embedded clauses, cleaner numerals, no idiom — and the training realism would quietly collapse while every other metric in this document continued to look fine. That is the failure mode isolation exists to prevent, and it is invisible to every other eval.

### What it rests on

L7 (to generate paired sessions) **and** L4 (to supply the difficulty measure the arms are compared on). This is the only rung in the vertical with two hard parents.

### Exactly what gets built

```
src/rehearsal/runtime/agents/context.py   # ContextAssembler + ROLE_ALLOWLISTS + IsolationViolation
src/rehearsal/learner/{model,coach}.py    # LearnerModel (per-category EWMA), CoachAgent
src/rehearsal/evals/suites/ev05_leakage.py
```

```python
# src/rehearsal/runtime/agents/context.py
ROLE_ALLOWLISTS: Mapping[Role, frozenset[str]] = {...}   # explicit, per role

class IsolationViolation(RuntimeError): ...

def assemble(role: Role, state: SessionState, *, leak_rubric: bool = False) -> Context:
    """`leak_rubric` is settable ONLY by ev05_leakage.py; asserts on non-eval callers."""
```

The leak flag lives in production code on purpose. An isolation claim that cannot be deliberately violated cannot be tested, and an untestable claim is exactly the kind of architecture assertion this project refuses to make.

### The eval that proves the rung was earned

`leakage_delta` — a **pre-registered** A/B:

| Element | Specification |
|---|---|
| Arms | A: isolated (production). B: identical, plus the rubric and taxonomy injected into clinician and patient contexts. |
| Pairing | Same scenario, same seed, same node sequence, same turn indices. Everything except the injected fields is held identical. |
| Primary outcome | Mean **utterance difficulty index** of counterpart turns — a deterministic composite (sentence length, subordinate-clause depth, numeral and unit density, idiom-list hits, negation-scope count, register band). Deterministic, so it cannot be gamed by the thing being measured. |
| Secondary outcome | Induced trainee error rate, scored by the L4 scorer, on the trainee-facing arm of a matched replay set. |
| Statistics | Paired permutation test, effect size with 95% CI, pre-registered direction, reported with n. |
| Gate | **None.** This eval gates no merge. It determines what the project is permitted to *claim*. |

Detail: `docs/08-evals.md` §4.6.

The honest-reporting protocol here is fixed in advance, before the number exists:

- **Effect in the predicted direction, CI excluding zero** → isolation is load-bearing; the multi-agent architecture is justified by measurement.
- **CI containing zero** → *"we could not detect an effect at this sample size"*, stated plainly. Isolation stays — it costs nearly nothing and the mechanism is sound — but it is reported as a defensible precaution, **not** as a measured benefit. The word "proven" leaves the documentation set.
- **Effect in the opposite direction** → a finding worth writing up. Investigate before believing it.

Writing all three outcomes down before running the test is what makes the result mean anything.

### What would falsify this rung

- The difficulty index does not move under deliberate maximal leakage. Either the metric is insensitive (check it against hand-constructed easy/hard pairs first — this is a precondition of the eval, not a response to its failure) or the effect is genuinely small at this model scale.
- The two arms diverge in node sequence. Then they are not paired and the comparison is invalid; the eval aborts rather than reporting a contaminated number.
- Isolation cannot be maintained without cutting context the agents genuinely need for coherence, and `persona_consistency` (L5) drops as a result. That is a real trade between realism and isolation, and it gets reported as one.

### The "why didn't you do X" this rung pre-answers

**"Why four session-time agents instead of one model playing all the roles?"**
Because one model playing all roles has, by construction, seen everything — the rubric, the other speaker's private facts, the verdict history. `leakage_delta` is the measurement of what that costs. A single-agent design cannot even run this eval, since its arms would be identical. This is the sharpest example in the project of a design argument settled by measurement rather than by philosophy (principle 6).

**"Isn't the rubric harmless for the patient agent to see?"**
That is the hypothesis. EV-05 tests it. Note that the failure mode being tested for is *unconscious* accommodation — the agent is not instructed to speak simply; it just does. Which is why the outcome measure is a deterministic difficulty index rather than any model's opinion of difficulty.

---

## 8. L10 (rung 1) — Automated prompt optimisation of the grader

### What it is, concretely

A DSPy/GEPA-style optimiser improves the **grader's prompt** against the human calibration set as the metric. Prompt-level only: no weights are touched, no adapters, no RL (§10). The optimiser proposes prompt variants; each variant is scored on the **DEV split**; the best variant by the composite metric is promoted; the promoted variant is then evaluated **once** on the sealed TEST split, and that single number is what gets reported.

The metric handed to the optimiser is not κ alone. Optimising κ alone will trade away critical-error recall, because critical errors are a minority class and κ does not care which errors you get right:

The objective function is defined **once**, in `docs/08-evals.md` §5 (`optimisation_metric()` in `src/rehearsal/optimise/metric.py`), because `docs/08-evals.md` is the measurement authority. It is not restated here: two copies of an optimiser objective drift, and a drifted objective silently promotes a different prompt than the one the measurement document says it promotes.

Its shape, for orientation only — read the authority for the actual weights: a **hard floor** on `critical_recall` (a breach returns the worst possible score, not a penalty), and above that floor a weighted combination dominated by `critical_recall`, with `kappa_macro` and `(1 - fp_rate_clean)` contributing less.

A hard constraint rather than a weighted penalty, because a weighted penalty is a price the optimiser is permitted to pay, and this is not for sale.

### What it rests on

Everything below it, and specifically on `kappa_intra` existing. An optimiser maximises the metric it is given; if that metric's relationship to human judgement is unmeasured and its ceiling unknown, the optimiser produces a prompt excellent at a proxy for nothing. The stopping rule needs the ceiling too: at κ approaching the intra-rater bound there is nothing left to win, and further optimisation is fitting the labeller's noise.

### Exactly what gets built

```
src/rehearsal/optimise/
├── metric.py        # objective(); the hard critical-recall constraint
├── search.py        # candidate generation, trial budget, seed control
├── promote.py       # writes prompts/grader/vN.md; refuses in-place edits
└── report.py        # before/after table with intervals, DEV and TEST clearly labelled
prompts/grader/v1.md … vN.md
data/evals/runs/<run_id>.json
data/calibration/TEST_ACCESS.log
```

Discipline, enforced in code and not by intention:

| Rule | Enforcement |
|---|---|
| Optimisation touches DEV only | `seal.py` refuses to load `test.jsonl` outside `rehearsal-evals unseal` |
| TEST is opened once per reported result | Every unseal appends to `TEST_ACCESS.log` with the stated reason; the log is published with the number |
| Few-shot examples come from DEV only | Skill manifest declares example provenance; asserted at load |
| Prompts are versioned, never edited in place | `promote.py` writes a new `vN.md`; the registry records the version with every run |
| Trial count and optimiser are reported | Part of the result artifact; an improvement without its trial count is not interpretable |

The nightmare this discipline exists to prevent: N optimisation trials against TEST, reporting the max. That is not an evaluation, it is a search over the test set with the result quoted as accuracy. `TEST_ACCESS.log` makes it structurally visible.

### The eval that proves the rung was earned

EV-01, re-run under the protocol in `docs/08-evals.md` §6:

| Reported quantity | Split | Note |
|---|---|---|
| `kappa_macro` before / after | TEST | Point estimate + bootstrap CI for each; the CI of the delta is the honest statement |
| `critical_recall` before / after | TEST | Must not decrease. If it does, the change is rejected regardless of κ |
| `fp_rate_clean` before / after | TEST | Reported whether or not it moved |
| Human ceiling (`kappa_intra`, `kappa_inter`) | — | Printed on the same table, always |
| Optimiser, trial count, DEV objective trajectory | DEV | Reported so the reader can see how much search bought how much gain |

**Pass gate:** the lower CI bound of the κ delta on TEST is > 0 **and** `critical_recall` does not decrease. With n = 15 on the sealed split, that is a demanding bar — deliberately. A delta whose CI straddles zero is reported as *"no improvement detectable at this sample size"*, which is an honest and completely acceptable outcome for this rung.

### What would falsify this rung

- The delta on TEST is null or negative while DEV improved substantially. That is overfitting to 25 items, it is the expected failure mode at this sample size, and reporting it is the rung doing its job.
- Optimisation improves κ by trading away critical recall. The hard constraint catches this mechanically; if the optimiser can *only* find gains this way, the metric is telling us the categories are in tension and that fact goes in the report.
- The optimised prompt is unreadable or unmaintainable. A prompt is code (per the project's own standard); a promoted variant that no human can review is a liability regardless of its κ.
- TEST is touched more than once per reported result. Then the number is void. The log makes this checkable by anyone reading the repository.

### The "why didn't you do X" this rung pre-answers

**"Why not fine-tune the grader?"** — §10.

**"Why not just hand-tune the prompt until κ looks good?"**
Because hand-tuning against a metric you can see, without split discipline, *is* overfitting — just slower and less honest about it. The optimiser is not here because it is cleverer than a human; it is here because it is auditable: trial count, objective trajectory, split boundary and prompt versions are all recorded artifacts.

---

## 9. The rung table

| Rung | Artifact | Eval metric | Pass gate | Falsifier |
|---|---|---|---|---|
| **L4** Application / one structured call | Neuro-symbolic fidelity scorer: 8 deterministic extractors + one structured 12B call + deterministic merge (`src/rehearsal/scoring/`) | `extractor_conformance` (EV-00); `kappa_macro` (EV-01); `critical_recall` (EV-02); `kappa_intra` (EV-03) | Conformance **= 1.00**; κ ≥ 0.60 DEV *(proposed)*; critical recall ≥ 0.90 DEV; ceiling must exist before κ is published | κ indistinguishable from a trivial baseline; critical recall unreachable symbolically; omission recall weak |
| **L5** Bare-hands agent | Clinician + patient agents driven by `ClinicalStateGraph`, raw typed loop, no framework (`src/rehearsal/content/`, `runtime/agents/`) | `persona_consistency` (EV-04); rubric-vocabulary canary; `fact_invention_rate` | ≥ 0.95 turn-level *(proposed)*; canary **= 1.00** *(decided)*; invention rate 0 | Passing only by scripting the agent; fallback usage > 5%; persona not holdable at E4B under quantisation |
| **L6** Packaged skill | `skills/interpreting-session/` — protocol, taxonomy, rubric, examples, checksummed manifest | `skill_delta` (EV-06), paired by scenario and seed | Lower CI bound ≥ −0.02 (must not be worse) | Materially negative delta; not loadable without runtime code; version churn making provenance noise |
| **L7** Pipeline with human gates | Full session orchestration, event log, voice pipeline, review gate, SPA (`orchestrator/`, `runtime/`, `store/`, `api/`, `frontend/`) | `p95_first_audio_ms`, `p99_barge_in_stop_ms`, `grader_backlog_rate` (EV-07); `session_completion_rate`, `turn_capture_loss_rate`, `trainer_override_rate` (EV-08) | Latency within `runtime/budget.py`; backlog ≤ 0.05; completion ≥ 0.90 *(proposed)*; capture loss ≤ 0.02; override band 0.02–0.25 | Budgets unmeetable at 20–24 GB resident; completion achieved only by degrading; capture loss > 0.02 |
| **L8** Multi-agent with isolation | `ContextAssembler` + per-role allowlists + `IsolationViolation`; coach and learner model (`runtime/agents/context.py`, `learner/`) | `leakage_delta` (EV-05) — pre-registered paired A/B on a deterministic difficulty index | **No gate.** Pre-registered effect size + CI + permutation p; the result governs the claim, not the merge | Difficulty index insensitive under maximal leakage; arms diverge (invalid pairing); isolation degrades `persona_consistency` |
| **L10 r1** Automated prompt optimisation | Optimiser over grader prompt with a hard critical-recall constraint (`src/rehearsal/optimise/`), versioned `prompts/grader/vN.md` | EV-01 re-run: before/after `kappa_macro`, `critical_recall`, `fp_rate_clean` on the **sealed TEST split** | Lower CI bound of the κ delta > 0 **and** critical recall not decreased | Null/negative TEST delta after large DEV gain (overfit); gains only by trading critical recall; TEST opened more than once |

---

## 10. Deliberately not climbed

Three capabilities are excluded by decision, not by omission. Each is stated with its reason and the specific evidence that would reverse it. The full decision records are in `docs/17-decisions.md`.

### 10.1 Our own inference server

**Not built.** Rehearsal uses MLX on Apple Silicon with llama.cpp as the portable fallback, wrapped by a thin `ModelHostClient` over a UNIX socket.

**Why.** An inference server is a serious, ongoing engineering commitment — batching, KV-cache management, quantisation kernels, memory pressure, Metal correctness — in a domain where two well-maintained projects already do it and where none of the project's differentiating claims live. Nothing in the layer vertical becomes measurable by owning the runtime. Every hour spent on it is an hour not spent on the calibration set, which is the actual bottleneck for every number in this document.

**What the thin client already buys us.** Process isolation between the live host and the grader host — the grader can be killed under memory pressure and the session degrades to extractor-only rather than dying (`docs/03-system-architecture.md` §14). That is the only runtime property the architecture genuinely needs, and it is a process boundary, not a server.

**What would change the decision.** A measured, reproducible failure in EV-07 that is attributable to the runtime rather than to model size — for example, if scheduling contention between the live and grader hosts pushes `p95_first_audio_ms` over budget and the existing runtimes expose no priority or admission control to fix it. That is a specific, falsifiable trigger. Dissatisfaction with the runtime is not one.

### 10.2 Horizontal fleet scale (the L9-shaped rung)

**Not built.** No multi-tenant service, no orchestration across machines, no shared model pool, no per-tenant isolation layer.

**Why.** The product's privacy position is that nothing leaves the machine (`docs/12-security-privacy.md`), and the deployment target is one practitioner or one training program on local hardware. Multi-tenancy would invert that position, add an auth and isolation surface with real consequences for trainee performance data, and it would not improve a single eval number in §9. It is the classic horizontal move: more users of an unproven capability rather than a proven one.

There is also a sequencing argument that is not merely tactical. Scaling a system whose grader accuracy is unestablished distributes an unmeasured instrument to more people. The order — measure, then distribute — is the same order the rest of this document enforces.

**What would change the decision.** Evidence of demand that local deployment provably cannot serve: a training program that needs cohort-level review across trainees, with a stated retention and consent model, *after* `kappa_macro` and `critical_recall` exist on the sealed split. Even then, the first move is a shared-review-server for reports (which contain no audio), not shared inference.

### 10.3 Weight training, fine-tuning, LoRA, RL

**Not built.** Prompt-level optimisation only (L10 rung 1). No weights are modified, no adapters are trained, no reward model exists.

**Why — three independent reasons, any one of which is sufficient.**

1. **The data does not exist.** The whole labelled corpus is 40 items, 25 of which are usable for optimisation. That is a calibration anchor, not a training set. Fine-tuning on 25 items produces a model that has memorised 25 items, and — worse — destroys the anchor's independence: the set can no longer measure the thing it was used to build.
2. **It would break the evaluation story.** Every number in §9 is interpretable because the models are fixed, versioned, publicly identifiable artifacts and only the prompt changes. Once weights are project-specific, "the grader agrees with humans at κ = X" becomes a claim about an artifact nobody else can inspect, and reproducibility — which is this project's stated credibility (`docs/03-system-architecture.md` §15) — is gone.
3. **The failure modes are wrong for the domain.** RL against an automated fidelity metric optimises for the metric's blind spots, and this metric's blind spots are, by construction, the semantic residue: register, idiom, pragmatic force. The predictable outcome is a grader that is superb at the categories already handled deterministically and quietly worse at the ones only it can handle.

**What would change the decision.** All three of the following, together, not any one alone: (a) a labelled corpus at least an order of magnitude larger, with inter-rater agreement established across multiple raters; (b) a demonstrated, reproducible plateau — prompt optimisation exhausted, κ still materially below the human ceiling on a sealed split, across more than one base model; (c) a held-out split that was never touched by any optimisation, prompt-level or weight-level, reserved specifically to evaluate the tuned artifact. Absent all three, tuning would be an unmeasurable change to the one component whose measurability is the product.

---

## 11. Rung sign-off checklist

A rung moves to `signed off` when every box is checked. Anything less is `built / unmeasured`, and the rung above it is blocked.

- [ ] The rung's artifacts exist at the paths named in this document.
- [ ] The owning eval suite module exists in `src/rehearsal/evals/suites/` and returns an `EvalResult`.
- [ ] The eval has been run with an explicit seed and recorded in `data/evals/registry.db`, with a denominator and an interval.
- [ ] The gate is met, or the deviation is written down with its reason and its consequence for downstream claims.
- [ ] `plans/metrics-snapshot.md` is updated in the same working session as the run.
- [ ] Anything downstream that the new number invalidates has been corrected — including this document.
- [ ] Report-only metrics are reported, not silently dropped, and null results are stated as null.

---

## Related documents

| Document | What it carries that this one deliberately does not |
|---|---|
| `SETUP.md` §6 | The calibration protocol — the anchor every rung's number depends on |
| `docs/00-dossier.md` | The product framing and the summary version of this vertical |
| `docs/01-research.md` | The clinical evidence base and the named gaps |
| `docs/03-system-architecture.md` | Component catalogue, state machine, event schema, trust boundaries |
| `docs/06-scoring-engine.md` | The L4 scorer in full — extractors, merge precedence, worked examples |
| `docs/08-evals.md` | Every metric's exact computation, split discipline, registry, statistical conventions |
| `docs/16-roadmap.md` | The same dependency order expressed as stages of work |
| `docs/17-decisions.md` | The full decision records behind §10 |

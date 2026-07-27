# 17 — Decision Record

This is the architecture decision log for Rehearsal. It records *why* the system is shaped the way it is, what was rejected, and what each choice cost. Every decision here is load-bearing: if you are joining the project and something in the code looks strange, the explanation is almost certainly in this file.

Sibling documents describe *what* the system does. This one describes *why it is not something else*. Where a decision has an implementation, the implementing document is named — go there for the mechanism, not here.

## 1. How to read this record

Each entry uses a fixed shape:

| Field | Meaning |
|---|---|
| **Decision** | The choice, stated as a single sentence in the imperative. |
| **Status** | `decided` — implemented or committed, changing it is a migration. `proposed` — the intended answer, not yet built, still cheap to change. `open` — genuinely undecided; the entry states what evidence would close it. |
| **Context** | The forcing constraint. What made a choice necessary. |
| **Options considered** | Real alternatives with their real merits. An option list where every rejected option is obviously bad is a dishonest one. |
| **Choice** | What we do, concretely, with names. |
| **Consequences and price paid** | What this costs. Every entry names a price. If an entry claims a decision is free, the entry is wrong. |
| **What would reverse it** | The falsifier. A named observation or measurement that would make us change our minds. "Nothing" is not an acceptable answer. |

Decisions are numbered `ADR-001` upward and are never renumbered. A superseded decision keeps its number and gains a status line pointing at its replacement.

**Ordering.** ADRs are ordered by dependency, not by when they were made. ADR-001 through ADR-004 are the foundational bets — everything downstream assumes them. ADR-005 onward are consequences and implementation-level commitments.

## 2. Index

| # | Decision | Status | Primary document |
|---|---|---|---|
| ADR-001 | Local-only inference; no cloud model in the core loop | decided | `docs/03-system-architecture.md` |
| ADR-002 | Ground truth by construction — the system generates the source utterance | decided | `docs/06-scoring-engine.md` |
| ADR-003 | Neuro-symbolic scoring; deterministic code owns the critical error classes | decided | `docs/06-scoring-engine.md` |
| ADR-004 | Interpreter fidelity is the beachhead capability, not general communication training | decided | `docs/00-dossier.md` |
| ADR-005 | Native audio input to the conversational agents; no separate ASR stage in the critical path | decided | `docs/05-voice-pipeline.md` |
| ADR-006 | The grader runs off the conversational critical path | decided | `docs/03-system-architecture.md` |
| ADR-007 | Information isolation between agents; the counterpart agents never see the rubric | decided | `docs/08-evals.md` |
| ADR-008 | Hand-rolled typed orchestration; no agent framework | decided | `docs/04-ai-engineering.md` |
| ADR-009 | Prompt-level optimisation only; no weight training, fine-tuning, LoRA or RL | decided | `docs/04-ai-engineering.md` |
| ADR-010 | SQLite with content-addressed audio blobs; no server database | decided | `docs/07-data-and-scenarios.md` |
| ADR-011 | No telemetry; local-only observability, and the debugging price that costs | decided | `docs/12-security-privacy.md` |
| ADR-012 | The calibration test split is sealed | decided | `docs/08-evals.md` |
| ADR-013 | Report rates, distributions and uncertainty; never a single headline score | decided | `docs/08-evals.md` |
| ADR-014 | Bilingual UI as a first-class requirement, not a translation layer | decided | `docs/09-ui-ux.md` |
| ADR-015 | Scenario realism grounded in public corpora; truth still comes from construction | decided | `docs/07-data-and-scenarios.md` |
| ADR-016 | Single-machine deployment; no multi-tenant fleet | decided | `docs/13-deployment-ops.md` |
| ADR-017 | Use an existing inference server (MLX / llama.cpp); do not build one | decided | `docs/13-deployment-ops.md` |
| ADR-018 | The human review loop always wins; trainer override is data, not failure | decided | `docs/03-system-architecture.md` |
| ADR-019 | Consecutive interpreting is the default mode; simultaneous is out of the initial scope | decided | `docs/07-data-and-scenarios.md` |
| ADR-020 | Indigenous-language support (Mixteco, Triqui) is a named gap, not a roadmap promise | decided | `docs/01-research.md` |
| ADR-021 | Severity is assigned by deterministic rule from category and span type, not by the model | decided | `docs/06-scoring-engine.md` |
| ADR-022 | Audio is retained by default under an explicit local-only contract | open | `docs/12-security-privacy.md` |

---

## ADR-001 — Local-only inference; no cloud model in the core loop

**Status:** decided

**Context.** Rehearsal listens to a human speaking, continuously, inside a simulated *clinical* encounter. Two things collide. First, trainees rehearse with material that sounds exactly like protected health information — medication lists, symptoms, family circumstances — and a promotora practising at a safety-net clinic cannot be asked to reason about whether a given vendor's data-retention policy makes that acceptable. Second, the interaction is real-time conversational: a counterpart agent that takes 1.5 s to begin speaking is not a conversation, and network variance sits directly on top of that budget.

There is a third, quieter constraint: the product's credibility rests on reproducibility. A cloud endpoint can change its model behind a stable name. Any eval number we publish would then be a number about a moving target.

**Options considered.**

| Option | For | Against |
|---|---|---|
| Cloud frontier models throughout | Strongest reasoning; no memory ceiling; no local runtime work | Clinical-sounding audio leaves the machine; per-session cost scales with practice volume, which is the thing we want unlimited; latency variance; non-reproducible eval baseline |
| Hybrid — local conversation, cloud grader | Grader quality is where a big model helps most; grader is off the critical path anyway (ADR-006) | Still exports transcripts of clinical content; splits the trust story into "mostly private", which is not a story a clinic can act on; adds an availability dependency to a tool meant to work offline |
| Local-only, open weights | No egress; zero marginal cost per session, so unlimited practice is actually unlimited; frozen weights mean reproducible evals; works offline | Bounded by what fits in memory; we own the runtime, quantisation and memory budget; capability ceiling is genuinely lower |
| Local-only with an opt-in cloud escape hatch | Best of both for power users | The escape hatch becomes the default the moment local quality disappoints, and then the privacy claim is conditional on a setting — a claim nobody can verify from outside |

**Choice.** Local-only, open-weight Gemma models. Live conversational agents are a Gemma 4 E4B-class model, quantised, one instance per agent role. The fidelity grader is a 12B-class Gemma, quantised. TTS is local neural or system voices. Target resident memory is ~20–24 GB on a 48 GB machine. There is no cloud inference path in the core loop and no configuration flag that introduces one — the absence of the code path *is* the guarantee.

**Consequences and price paid.**

- **We accept a real capability ceiling.** A 12B quantised grader is not a frontier model. Its semantic judgements on subtle register and pragmatic-force questions will be worse. ADR-003 is partly a mitigation for this: we route the hard-but-decidable work away from the model precisely because the model we can afford to run is small.
- **We own the memory budget.** Four resident components (clinician, patient, grader, TTS) on one machine is a scheduling and eviction problem we have to solve ourselves. See `docs/13-deployment-ops.md` for the residency plan.
- **We own quantisation quality.** Quantisation is a silent accuracy tax. Every eval number must be produced at the quantisation level that actually ships, never at full precision.
- **Hardware becomes a requirement, and that is an access cost.** The 48 GB machine assumption excludes users on modest laptops — in a product aimed at safety-net clinics, that is not a trivial exclusion. It is the strongest argument against this decision and we accept it knowingly.
- **We give up the easy answer to "why not just use a bigger model?"** Every quality shortfall has to be fixed by architecture, data or prompt work.

**What would reverse it.** A measured finding that the local grader's Cohen's kappa against the human calibration labels sits below the usable floor (see `docs/08-evals.md` for the floor and the ceiling) *and* that no prompt-level work (ADR-009) closes the gap. Even then, the first response is a larger local model, not a cloud one; cloud inference returns only if a deployment partner both requires quality we cannot reach locally and supplies a written no-retention agreement. Local-only for the *conversational* path would survive that reversal regardless — the latency argument stands on its own.

---

## ADR-002 — Ground truth by construction

**Status:** decided

**Context.** "AI grades human performance" usually fails the same way: there is no ground truth, so the model's opinion is both the method and the result, and disagreement cannot be adjudicated. Any assessment product built that way is unfalsifiable, which means it is unimprovable.

Interpreting has an unusual property that inverts this. The utterance being interpreted is a *known artefact*. If the system generated it, the system holds it exactly — token for token, with its numbers, its negations and its laterality intact.

**Options considered.**

- **Judge the rendering on its own merits** (LLM-as-judge over the trainee's Spanish or English). Simple, works with human-to-human recordings. But it is exactly the unfalsifiable design above, and it has no principled way to detect *omission* — the single largest error category in the clinical literature — because you cannot notice the absence of something you never knew was there.
- **Transcribe both sides and align post hoc.** Works on real recordings. But it inherits ASR error on both sides, and ASR error concentrates in numbers and proper nouns, which are the clinically critical tokens. You would be measuring the transcriber.
- **Generate the source, then compare the rendering to it.** The system knows the source exactly. Scoring becomes a comparison problem against a known reference rather than a quality judgement.

**Choice.** The system generates every source utterance and persists it verbatim before the trainee hears it. The scoring question is fixed as: *does this rendering carry the propositional content of this known source utterance?* Every scoring component — symbolic and model-based — receives the source text as a first-class input. The source utterance is stored in `turns.source_text` alongside a structured `turns.source_facts` extraction produced at generation time, before any trainee audio exists.

This is the decision that makes ADR-003 possible. If you do not know the source, you cannot hard-check a dosage against it.

**Consequences and price paid.**

- **The product only works on system-generated encounters.** We cannot score a recording of a real clinic visit, and we cannot score a trainee's practice with a human partner. That is a genuine scope wall, and it closes off an otherwise attractive market (QA on real encounters).
- **Scenario authoring becomes load-bearing.** Because the source utterance is our artefact, its realism is our responsibility. Weak scenario writing produces a system that measures fidelity to unrealistic speech. ADR-015 exists to bound this risk.
- **Ground truth is only as good as the generation-time extraction.** If the source-fact extractor mis-parses "half a tablet twice daily", the scorer's reference is wrong and the trainee is graded against a fiction. Generation-time extraction therefore gets its own eval, separate from the scorer's — see `docs/08-evals.md`.
- **Scoring is scoped to fidelity.** We cannot score things that have no source-side referent: overall professionalism, voice quality, sight translation of a document we did not author.

**What would reverse it.** Nothing short of abandoning the product thesis. This is the foundational bet. If it fails, it fails in the form of ADR-015's risk — that constructed encounters are too unlike real ones to train on — and the response is better scenario grounding, not a different scoring paradigm.

---

## ADR-003 — Neuro-symbolic scoring

**Status:** decided

**Context.** The clinical literature is specific about which interpreting errors carry consequence: dosage, frequency, allergy, negation, laterality, symptom onset. Read that list again — every item is a *decidable* comparison once you have the source (ADR-002). "10 mg" either survived into the rendering or it did not. A negation either flipped or it did not. These are not judgement calls.

Meanwhile the categories that genuinely require a language model — register shift, idiom handling, pragmatic force, first-person discipline, false fluency — are exactly the categories where a wrong call is *less* dangerous.

Handing the whole taxonomy to a model means accepting probabilistic behaviour on the class where probabilistic behaviour is least acceptable. A quantised 12B model will, some fraction of the time, hallucinate agreement on a dosage that changed.

**Options considered.**

| Option | For | Against |
|---|---|---|
| Pure LLM judging over the full taxonomy | One prompt, one call, fastest to build; handles everything uniformly | Non-deterministic on the critical class; unauditable ("why did it say that?"); regressions are invisible without a full eval run; a wrong dosage verdict is a clinical-safety-shaped failure in a training tool |
| Pure symbolic | Fully deterministic and auditable | Cannot handle register, idiom or pragmatics at all — roughly half the taxonomy would go unscored |
| Neuro-symbolic: symbolic owns critical, model owns residue | Critical class is deterministic, reproducible and explainable; model scope is bounded and separately measurable; each half gets its own eval | Two systems to build and maintain; a merge layer with its own conflict semantics; symbolic extractors must work cross-lingually, which is real work |

**Choice.** Deterministic extractors decide the critical categories. A single structured model call handles the semantic residue. A deterministic merge layer combines them, and the symbolic verdict wins any conflict inside its own jurisdiction.

Jurisdiction is explicit, not implied:

| Concern | Owner | Rationale |
|---|---|---|
| Numbers, dosages, units | symbolic | Decidable after cross-lingual normalisation |
| Frequency (`bid`, `dos veces al día`, "every 8 hours") | symbolic | Decidable; normalises to a canonical frequency form |
| Negation and negation flips | symbolic | Decidable; the highest-consequence distortion class |
| Laterality (left/right/bilateral) | symbolic | Decidable |
| Allergies (substance + reaction) | symbolic | Decidable |
| Temporal markers / symptom onset | symbolic | Decidable after normalisation |
| Omission of a non-critical proposition | model | Requires semantic equivalence judgement |
| Addition, editorialization | model | Requires intent-level reading |
| Register shift, false fluency | model | Inherently sociolinguistic |
| Role exchange, first-person violation | model, with a symbolic pronoun pre-filter | Pronoun evidence is cheap and decidable; the call is not |
| **Severity assignment** | symbolic | See ADR-021 |

**Consequences and price paid.**

- **Two eval tracks, permanently.** The symbolic extractors need unit-level accuracy numbers (precision/recall per extractor, per language). The model call needs agreement numbers. Neither substitutes for the other, and a headline "scorer accuracy" that blends them would hide which half regressed.
- **Cross-lingual normalisation is harder than it sounds and is never finished.** `dos veces al día`, `cada 12 horas`, `bid`, `twice a day`, `2x/día` must all collapse to the same canonical frequency. Spanish spelled-out numbers, decimal commas versus decimal points, `mcg`/`μg`/`microgramos`. Regional variation compounds it. This normalisation layer is the highest-maintenance component in the system and we should expect a long tail of misses for the life of the product.
- **The merge layer has real conflict semantics** and needs its own tests. When the model reports "omission — dosage dropped" and the symbolic extractor found the dosage intact, symbolic wins and the model finding is discarded with a recorded reason. That discard is logged, and a rising discard rate is a signal that the model prompt has drifted.
- **We inherit an asymmetric failure mode.** A symbolic extractor that fails to *fire* (misses a dosage in the source entirely) silently downgrades a critical check to nothing at all. Extractor recall on the source side therefore matters more than precision, and is measured separately.

**What would reverse it.** Measured evidence that the symbolic extractors underperform the model on their own jurisdiction — specifically, if extractor recall on critical spans falls below the model's recall on the same spans across the calibration dev split. That would be surprising, and the honest response would be to publish the finding, not quietly delete the extractors. Determinism and auditability have value beyond raw accuracy, so the model would need to win clearly, not marginally.

---

## ADR-004 — Interpreter fidelity as the beachhead capability

**Status:** decided

**Context.** The obvious larger product is "AI-powered communication skills training for healthcare" — motivational interviewing, difficult conversations, cultural humility, patient education. Bigger market, more buyer types, more revenue surface.

It is also, technically, a completely different product: none of it has ground truth. "Did the trainee show empathy?" has no known-correct answer, which returns us to the unfalsifiable design ADR-002 exists to escape.

**Options considered.**

- **Broad communication-skills platform.** Larger market, easier to explain to a buyer. But scoring is opinion, evals are soft, and the product's defensibility collapses to prompt quality — which any competitor can replicate in an afternoon.
- **Interpreter fidelity only.** Narrower market. But the scoring problem is tractable and defensible, the error taxonomy is an operationalisation of the research literature aligned to published professional standards, rather than something we invented, the clinical-consequence evidence is peer-reviewed, and the users are identifiable and geographically concentrated (Watsonville and the Pajaro Valley).
- **Fidelity first, breadth as a later layer.** Same starting point; keeps the option open.

**Choice.** Interpreter fidelity is the beachhead and the only scored capability. Everything scored has a source utterance behind it (ADR-002). Adjacent skills — note-taking, intervention protocol, transparency statements — appear only as *unscored* or rule-checkable session behaviours, never as model-judged competencies.

Concretely, the boundary: a rendering is scored against its source. Everything else in the session is either deterministic (did the trainee use a first-person pronoun? did they announce the intervention?) or unscored.

**Consequences and price paid.**

- **A smaller addressable market, deliberately.** Medical interpreters in training are a small population. We are trading market size for the ability to prove the product works.
- **We will be asked for the broader features constantly,** by exactly the buyers with budget. Training programmes want a cohort-wide communication curriculum. Saying no to that is a recurring commercial cost, not a one-time one.
- **Depth becomes the only differentiator.** Because the scope is narrow, mediocre execution has nowhere to hide. The kappa number is the product.
- **Some genuine interpreter competencies fall outside the scored set** — managing turn-taking under pressure, handling a clinician who talks over the interpreter, cultural brokering judgement. These matter professionally and we do not measure them. Say so in the product, do not imply coverage.

**What would reverse it.** Evidence from deployed use that fidelity scoring is accurate but *insufficient* — trainees improving on measured fidelity while trainers report no improvement in real encounters. That would indicate the scored construct is too narrow, and the response would be to add adjacent capabilities *with their own ground-truth story*, not to bolt on opinion-based scoring.

---

## ADR-005 — Native audio input; no separate speech-recognition stage in the critical path

**Status:** decided

**Context.** The trainee speaks; a counterpart agent must respond in conversational time. The conventional pipeline is ASR → LLM → TTS. Each stage adds latency, and the ASR stage adds something worse: it is a lossy bottleneck placed exactly where the clinically critical tokens live. ASR errors concentrate on numbers, drug names and proper nouns. Code-switching and Spanish regional variety make it worse.

A pipeline that mis-transcribes "fifteen" as "fifty" produces a system that grades the trainee on the transcriber's mistake — which is the single most credibility-destroying failure this product could have.

**Options considered.**

| Option | Critical-path stages | Notes |
|---|---|---|
| ASR → LLM → TTS | 3 | Conventional; mature tooling; but transcript error lands on numbers, and the agent only ever sees text — prosody, hesitation and self-correction are gone |
| Native audio input to the agent | 2 | Trainee audio goes directly into the Gemma 4 E4B-class model; agent hears delivery, not just words; one fewer stage of latency and one fewer stage of error |
| Native audio for the agent, plus offline ASR for the record | 2 on the path, ASR off it | Keeps a searchable transcript without putting ASR in the critical path |

**Choice.** The trainee's speech goes directly into the conversational agents as audio. There is no speech-recognition stage in the critical path.

A transcript is still produced — trainees need to read what they said, and the grader needs text — but it is generated *off* the critical path, concurrently with the next turn, on the same schedule as the grader (ADR-006). A transcription error therefore delays or degrades the *review artefact*, never the conversation.

Critically, the grader's *source* side never depends on transcription at all: the source utterance is known by construction (ADR-002). Only the trainee's rendering is transcribed. This bounds the blast radius of ASR error to one side of the comparison, and it is a bound worth stating explicitly in any accuracy disclosure.

**Consequences and price paid.**

- **We are tied to models with native audio input.** That is a much smaller set than text-only models, and it constrains our model-swap options for the conversational role. If the audio-capable Gemma line stalls, we are stuck.
- **Audio input costs more context than text.** Audio tokens are expensive relative to their information density, which tightens the conversational context window and forces earlier, more aggressive history summarisation.
- **Debugging is harder.** With ASR in the path you can read exactly what the model saw. With native audio you cannot. When an agent responds oddly, the input is a waveform, and reproducing the failure means replaying the audio. This is a real, ongoing tax — see `docs/14-testing-strategy.md` for the fixture-audio approach that partially offsets it.
- **The rendering side still carries transcription error.** We removed ASR from the critical path, not from the system. The grader's view of what the trainee said is still a transcript, and its error rate must be reported as part of the scorer's error budget rather than being quietly folded into "scorer disagreement".

**What would reverse it.** Measured audio-in latency or quality on the target hardware that is worse than a tuned ASR → LLM pipeline. This is a straightforward A/B on the same scenarios and should be re-run whenever either component changes materially. The transcript-side decision does not reverse with it — off-path transcription is correct regardless.

---

## ADR-006 — The grader runs off the conversational critical path

**Status:** decided

**Context.** Four model-shaped components in the live loop must share one machine: clinician agent, patient agent, grader, TTS. Run the 12B grader synchronously between turns and the trainee waits several seconds after every utterance. That destroys the interaction — and interpreting practice specifically depends on sustained conversational pressure, because handling that pressure is part of the skill being trained.

But there is a structural gift here. In consecutive interpreting, the trainee speaks for several seconds after each source utterance. During that window, the previous turn is complete and nothing on the critical path needs the grader.

**Options considered.**

- **Synchronous grading between turns.** Simple; immediate feedback. But it inserts a multi-second stall into every turn and forces the grader to compete for memory and compute with the live agents at the worst moment.
- **Batch grading at session end.** Zero conversational impact; simplest scheduling. But the trainee waits for the whole report, and we lose the ability to surface a critical error mid-session when the trainer wants an interrupt.
- **Concurrent grading, one turn behind.** The grader scores turn *n* while the trainee renders turn *n+1*. The human's own speaking time is the latency budget.

**Choice.** Concurrent grading, one turn behind. `SessionOrchestrator` enqueues a `GradeTask` the moment a turn's rendering audio is finalised, and returns immediately to the conversational loop. A single-worker grading queue drains it. The grader is never awaited on the conversational path.

The scheduling contract:

| Property | Value | Reason |
|---|---|---|
| Queue depth | bounded, 8 | If grading falls this far behind, something is wrong; fail loudly rather than accumulate |
| Overflow behaviour | drop-oldest, record a `grade_deferred` marker on the turn | The conversation must never stall; the report must never silently lie about coverage |
| Worker concurrency | 1 | Serialises grader memory pressure; more workers would contend with the live agents |
| Priority | below conversational inference | The live agents win every scheduling conflict |
| Completion guarantee | all outstanding tasks drain before the session report renders | The report is complete or it is explicitly marked incomplete |

**Consequences and price paid.**

- **Feedback is not instant.** Findings for turn *n* appear during or after turn *n+1*. For a trainee who wants to know immediately, that is a real UX compromise, and the UI must handle a turn that is visibly "not yet scored" without looking broken.
- **Concurrency bugs are now possible, and they are the nasty kind.** Two model families resident and active simultaneously means memory pressure spikes, and a grader that runs long can collide with a TTS burst. `docs/14-testing-strategy.md` covers the soak test that exists for exactly this.
- **Partial reports are a real state we must handle honestly.** A session ended early, or a grader crash, leaves turns ungraded. The report must say "3 of 14 turns not scored" rather than reporting a rate over 11 turns as if it were the whole session. This is ADR-013 applied to an edge case.
- **A mid-session critical-error interrupt is delayed by one turn.** If a trainee drops a dosage, the earliest we can flag it is during the next rendering. We accept this; interrupting *within* a turn would require synchronous grading and would break the conversation anyway.

**What would reverse it.** Nothing likely. If a future grader were fast enough to run inside the inter-turn gap without memory contention, synchronous grading would become viable and would simplify the state machine — but the queue would still be the right structure for robustness.

---

## ADR-007 — Information isolation between agents

**Status:** decided

**Context.** The naive implementation is one model instance holding the whole session: clinician lines, patient lines, the rubric, the learner's weak categories. It is simpler, uses less memory, and is wrong.

If the clinician agent can see that the rubric weights dosage omissions heavily, it will — without being told to — produce dosage-bearing sentences that are unusually easy to interpret: shorter, more clearly enunciated, better segmented. If it can see the learner model, it will accommodate the learner's weaknesses. Both effects make the practice easier than reality, and neither is visible in any output. The system would get quietly, invisibly worse at the one thing it exists to do.

This is the load-bearing justification for the multi-agent architecture. Without it, multi-agent is over-engineering.

**Options considered.**

- **Single context holding everything.** Simplest, cheapest in memory. But it silently destroys training realism and the failure is undetectable from the outside.
- **Prompt-level instruction** ("do not use your knowledge of the rubric"). Cheap. But it relies on a small quantised model reliably suppressing information it can see, which is not a property any model has. It is a hope, not a mechanism.
- **Hard context isolation.** Separate model contexts per role, with an explicit typed message-passing boundary. Rubric and learner state are structurally absent from the counterpart agents' contexts.

**Choice.** Hard isolation, enforced by construction. Each agent role gets its own context object. The rubric, the error taxonomy, prior findings and the learner model are never assembled into the clinician or patient contexts. The boundary is typed — `ClinicianContext` and `PatientContext` have no field capable of carrying rubric or learner data, so leakage is a type error, not a review catch.

And, because "we designed it not to leak" is philosophy and this project settles arguments with measurements (principle 6), the isolation is *proven*: the leakage A/B is the L8 eval. Run matched scenarios with the counterpart agent able to see the rubric versus not, and measure the induced error rate on the trainee side. If isolation matters, the rubric-aware condition produces measurably fewer induced errors — easier speech. Protocol and results live in `docs/08-evals.md`.

**Consequences and price paid.**

- **More resident memory and more moving parts.** Separate contexts mean separate KV caches. On a fixed memory budget (ADR-001) that is a direct cost paid against model size or quantisation level.
- **Cross-agent coherence becomes our problem.** The clinician and patient must stay consistent about the shared clinical situation without sharing a context. A shared, explicitly-scoped `EncounterState` carries the facts both need (chief complaint, medication list, timeline) and nothing else. Getting that scope right is ongoing work, and every field added to it is a potential leakage vector that must be justified.
- **The isolation must be re-proven when things change.** A model swap, a prompt refactor, or a new field on `EncounterState` invalidates the previous A/B result. This is a permanent recurring eval cost.
- **A new class of bug: coherence drift.** Isolated agents can contradict each other about the encounter. This did not exist in the single-context design. It is caught by the L5 persona-consistency eval against the clinical state graph.

**What would reverse it.** A leakage A/B showing no measurable difference in induced error rate between conditions, replicated across scenario types and at adequate sample size. That would mean isolation buys nothing at current model scale, and the honest response is to publish the null result and simplify the architecture. This is the decision most likely in this document to be overturned by its own eval, and that is by design.

---

## ADR-008 — Hand-rolled typed orchestration; no agent framework

**Status:** decided

**Context.** LangChain, CrewAI and their peers exist to remove exactly the work this project needs to do by hand: multi-agent coordination, message passing, tool loops, state management.

But this product's credibility rests on reproducibility, seed control and inspectable failure points. The eval numbers (principle 6) are the product. A framework that inserts its own prompt scaffolding between our prompt and the model means the thing we optimised (ADR-009) and the thing that ran are not the same string. That is not a small inconvenience — it invalidates the optimisation result.

**Options considered.**

| Option | For | Against |
|---|---|---|
| LangChain / LangGraph | Prebuilt graph orchestration, wide ecosystem | Hidden prompt assembly; version churn; failures surface deep in framework internals; abstraction overhead on a latency-critical local loop |
| CrewAI | Multi-agent primitives close to our shape | Opinionated agent-communication model that fights ADR-007's hard isolation; less control over exact context assembly |
| Hand-rolled typed orchestration | Every byte sent to the model is code we wrote and can print; failures are in our stack traces; no dependency churn | We build the retry, timeout, queue and state-machine logic ourselves; more code to own |

**Choice.** Hand-rolled, typed orchestration. The core surface is small and deliberately boring:

```python
# rehearsal/orchestration/types.py
@dataclass(frozen=True)
class ModelCall:
    role: AgentRole                  # CLINICIAN | PATIENT | GRADER | COACH
    context: AgentContext            # role-specific; see ADR-007
    seed: int | None                 # None only where nondeterminism is intended
    max_tokens: int
    schema: type[BaseModel] | None   # structured output contract, None for free text

@dataclass(frozen=True)
class ModelResult:
    text: str
    parsed: BaseModel | None
    prompt_sha256: str               # hash of the exact assembled prompt
    latency_ms: int
    tokens_in: int
    tokens_out: int
```

`prompt_sha256` is the point. The exact assembled prompt is hashed and recorded on every call. Any run can be traced to the literal bytes that produced it, and a prompt change that was not supposed to happen shows up as a hash change in the eval log.

The rejected work is genuinely done, not avoided: retry-with-backoff, timeout, the bounded grading queue (ADR-006), and the session state machine are ours. Total orchestration surface is on the order of a few hundred lines — smaller than the config needed to make a framework behave.

**Consequences and price paid.**

- **We maintain orchestration code forever,** including the unglamorous parts: partial-output handling on timeout, backpressure, clean shutdown mid-generation.
- **No ecosystem.** Framework integrations — tracing UIs, prebuilt evaluators, connectors — do not apply. We build or do without.
- **Onboarding is against our conventions, not a documented framework.** A new engineer cannot lean on framework docs. This document and `docs/04-ai-engineering.md` are the substitute, which raises the bar on documentation quality.
- **It is easy to accidentally reinvent a framework badly.** The guard is a hard rule: orchestration code that is not used by a shipping path gets deleted. No speculative abstraction, no interface with one implementation.

**What would reverse it.** A specific, named pain that a framework demonstrably removes and that costs more to build than to adopt. Per the project's framework rule, adoption requires naming that pain concretely — not "it would be more standard". Distributed multi-node orchestration would qualify, and ADR-016 says we are not doing that.

---

## ADR-009 — Prompt-level optimisation only

**Status:** decided

**Context.** The grader's semantic half (ADR-003) will not be right on the first prompt. There is a human-labelled calibration set to optimise against. The question is what to optimise.

**Options considered.**

- **Fine-tune the grader on the calibration labels.** Potentially the largest quality gain. But 25 dev items is nowhere near enough data — it would memorise, not generalise. It also destroys reproducibility against a published base model, adds a training pipeline to maintain, and each new base model means retraining from scratch.
- **LoRA adapters.** Cheaper than full fine-tuning, same fundamental problem: 25 items is not a training set, it is a test set with delusions of grandeur.
- **RL from human feedback on trainer overrides.** Attractive in principle — overrides are a real preference signal. But the volume is tiny, the signal is noisy and rater-specific, and it introduces a feedback loop that can drift the grader toward whichever trainer clicks most.
- **Automated prompt optimisation (DSPy/GEPA-style)** against the calibration set as the metric. Works with small data because it is searching a prompt space, not fitting parameters. Every artefact is a human-readable string that can be diffed and reviewed.

**Choice.** Prompt-level optimisation only. No weight training, no fine-tuning, no LoRA, no RL. This is the L10 rung of the layer vertical: an optimiser improves the grader's prompt with agreement against the human calibration set as the metric.

Non-negotiable conditions:

1. The optimiser sees **only the DEV split (25 items)**. Never the sealed test split (ADR-012).
2. Before/after agreement is reported on the **sealed TEST split (15 items)**, one time.
3. Optimised prompts are committed to the repository as versioned files under `rehearsal/prompts/`, diffed and reviewed like code — never stored in a database or a UI textbox.
4. Every optimised prompt is tagged with the optimiser version, the base model, the quantisation level and the dev-split hash. A prompt optimised against a different model is not valid for this one.

**Consequences and price paid.**

- **We leave capability on the table.** A fine-tuned grader could plausibly beat a prompted one. We are choosing reproducibility, auditability and a shorter maintenance chain over that headroom, and it is a real trade.
- **Optimising on 25 items risks overfitting the prompt to those 25 items.** The sealed test split is the only defence, and with 15 items its statistical power is limited (ADR-013). We will be able to detect a large overfit, not a subtle one. Say so when reporting.
- **The optimiser is a dependency with its own failure modes** — it can produce prompts that score well and read as nonsense. Every optimised prompt gets human review before it ships. An unreadable prompt that scores well is rejected, because we cannot maintain what we cannot read.
- **Optimised prompts do not transfer across model versions.** Every model or quantisation change invalidates them and requires a re-run.

**What would reverse it.** Nothing in the current scope — weight training is an explicit project-level exclusion. If it were ever revisited, the precondition is a calibration set an order of magnitude larger with measured inter-rater agreement, which is a different project.

---

## ADR-010 — SQLite with content-addressed audio blobs

**Status:** decided

**Context.** A session produces per-turn audio for the source utterances, the trainee's renderings and the TTS output, plus transcripts, findings and scores. Single-user, single-machine (ADR-016), local-only (ADR-001), with clinical-sounding content that must not leave the machine.

**Options considered.**

| Option | For | Against |
|---|---|---|
| Postgres + object storage | Scales; familiar; good concurrency | A server to run, back up and secure, for one user on one machine; contradicts "install and run offline"; the operational cost is entirely wasted at this scale |
| Files on disk, no database | Trivially simple | Querying competency over time means walking the filesystem; no transactions, so a crash mid-session leaves torn state |
| SQLite + content-addressed blobs on disk | Zero-administration, transactional, ships with Python, one file to back up or delete; blob dedup is free and integrity is checkable | Single-writer; not a network database; large blobs need care |

**Choice.** SQLite for all structured data, audio stored as content-addressed files on disk with the hash referenced from the database.

```
~/Library/Application Support/Rehearsal/     # macOS; XDG data dir on Linux
├── rehearsal.db                             # SQLite, WAL mode
├── blobs/
│   └── sha256/
│       ├── 3f/3f9a1c...e2.opus              # two-char fan-out to bound directory size
│       └── a1/a1b7de...04.opus
└── prompts/                                 # active prompt versions, mirrored from the repo
```

Audio never goes *in* the database. Blobs are named by the SHA-256 of their bytes.

```sql
CREATE TABLE blobs (
    sha256      TEXT PRIMARY KEY,
    byte_len    INTEGER NOT NULL,
    media_type  TEXT NOT NULL,              -- 'audio/opus'
    created_at  TEXT NOT NULL               -- ISO-8601 UTC
);

CREATE TABLE turns (
    id                  INTEGER PRIMARY KEY,
    session_id          INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    turn_index          INTEGER NOT NULL,
    direction           TEXT NOT NULL CHECK (direction IN ('en_to_es','es_to_en')),
    speaker_role        TEXT NOT NULL CHECK (speaker_role IN ('clinician','patient')),
    source_text         TEXT NOT NULL,       -- ADR-002: known by construction
    source_facts_json   TEXT NOT NULL,       -- generation-time structured extraction
    source_audio_sha    TEXT REFERENCES blobs(sha256),
    rendering_audio_sha TEXT REFERENCES blobs(sha256),
    rendering_text      TEXT,                -- off-path transcript, ADR-005; NULL until produced
    grade_status        TEXT NOT NULL DEFAULT 'pending'
                        CHECK (grade_status IN ('pending','graded','deferred','failed')),
    UNIQUE (session_id, turn_index)
);
```

Content addressing buys three things concretely: identical TTS output across sessions is stored once; corruption is detectable by rehashing; and deletion is a safe refcount check rather than a guess. `rehearsal-gc` sweeps blobs with no referencing row.

**Consequences and price paid.**

- **Single-writer.** Concurrent writes serialise. WAL mode makes readers non-blocking, but a genuine multi-user deployment would need a different database. That is precisely the scenario ADR-016 excludes, so the cost is only paid if that decision reverses.
- **No cross-device sync, at all.** A trainee who practises on a lab machine and a home machine has two disconnected histories. For interpreter training programmes this will be a real complaint, and there is no cheap fix consistent with ADR-001.
- **Backup is the user's problem.** We ship `rehearsal-export --session <id>` and `rehearsal-export --all` producing a portable archive, but there is no automatic backup, and a disk failure loses everything. This is documented prominently rather than solved.
- **Blob GC is a correctness hazard we own.** A refcount bug either leaks disk (annoying) or deletes referenced audio (data loss). The GC path is transactional and gets its own tests; per project standards, error handling that prevents data loss is never simplified away.
- **SQLite migrations need discipline.** No migration framework — plain numbered SQL under `rehearsal/db/migrations/` applied in order, recorded in a `schema_version` table.

**What would reverse it.** A deployment requiring genuine concurrent multi-user access on shared hardware — a training programme running a lab of trainees against one server. That is ADR-016 reversing, and this decision follows it.

---

## ADR-011 — No telemetry, and the debugging price

**Status:** decided

**Context.** Nothing about a Rehearsal session leaves the machine (ADR-001). The natural next question is whether *anonymous* telemetry — crash reports, latency histograms, feature usage — should be exempt.

It should not, and the reason is not purity. It is that the privacy claim has to be verifiable by someone who does not trust us. "No data leaves your machine, except anonymised diagnostics" is a claim that requires the listener to trust our definition of anonymised. "No data leaves your machine" can be verified with a firewall. In a product handling clinical-sounding speech for safety-net clinics, the verifiable claim is worth more than the diagnostic data.

There is also a specific risk: crash reports containing prompt content or transcript fragments would export exactly the thing we promised not to export. Scrubbing that reliably is hard, and the failure is silent.

**Options considered.**

- **Standard anonymous telemetry.** Best debugging; industry normal. But it breaks the verifiable claim and risks content leakage in stack traces and payloads.
- **Opt-in telemetry, default off.** Preserves the default claim. But it forks the deployed population into observed and unobserved, and the users least likely to opt in are exactly the clinic users whose environments we most need to understand.
- **No telemetry; rich local diagnostics plus a user-initiated export.** Nothing automatic. The user can generate and inspect a diagnostic bundle and send it if they choose.

**Choice.** No telemetry of any kind. No crash reporting, no usage analytics, no update pings, no remote error aggregation. The application makes no outbound network requests during normal operation. This is testable, and it *is* tested: `tests/test_no_egress.py` asserts that a full scripted session performs zero outbound connections, with the socket layer patched to fail on any attempt.

In exchange, local observability is unusually thorough:

| Artefact | Location | Content |
|---|---|---|
| Structured session log | `logs/session-<id>.jsonl` | One JSON object per orchestration event: model calls with `prompt_sha256`, latencies, token counts, queue depth, extractor firings, merge-layer decisions and discards |
| Model call trace | same file, `event: model_call` | Role, seed, quantisation, model id, prompt hash, timing. Prompt *text* is written only when `REHEARSAL_TRACE_PROMPTS=1` is set explicitly |
| Diagnostic bundle | `rehearsal-diagnose --out bundle.zip` | Logs, schema version, model manifest, hardware profile, timing histograms. **Excludes audio blobs and transcripts by default**; `--include-content` is a separate, warned flag |
| Eval run records | `evals/runs/<timestamp>/` | Full inputs, outputs and metrics for every eval — the substitute for production telemetry |

**Consequences and price paid.** This is the entry where the price is largest and most concrete.

- **We are blind to field failures.** If Rehearsal crashes on a machine we do not own, we learn about it only if the user tells us. There is no crash rate, no regression alert, no "this happens to 4% of sessions" signal. Bug reports arrive as prose, and we debug from a user's description plus whatever bundle they choose to send.
- **We cannot see aggregate quality drift.** A prompt or model change that degrades scoring for a subset of accents or scenario types is invisible unless it shows up in the calibration set — which is 40 items, and cannot represent the field. Our eval suite has to substitute for production monitoring, and it is a weaker substitute than it sounds.
- **We have no usage data to prioritise with.** Which scenarios get run, where trainees abandon, which findings get disputed — unknown. Roadmap decisions are made from user conversations and trainer overrides (ADR-018), which are lower-volume and more biased than telemetry.
- **The hardware matrix is unverified.** We cannot confirm the memory budget holds across real machines. We test what we own.

We accept all of this. The verifiable claim is the thing that lets a clinic say yes, and a training tool that clinics will not install has no crash rate worth measuring. But the cost is real and is not to be minimised in any external material.

**What would reverse it.** Nothing, for content-bearing telemetry. A narrowly-scoped, opt-in, human-readable-before-send crash report — where the user sees the exact bytes and presses send — remains a legitimate open option. It would need to preserve the property that the default install makes zero outbound requests.

---

## ADR-012 — The calibration test split is sealed

**Status:** decided

**Context.** The calibration set is 40 interpreting turns hand-labelled against the error taxonomy — the external anchor for the entire project. It is small and expensive to produce, and it is the only thing standing between "the scorer agrees with expert judgement" and "the scorer agrees with itself".

The failure mode is well known and easy to fall into by accident: iterate on prompts, check agreement, iterate again. After enough rounds the number reflects the prompt fitting the evaluation items, not the scorer working. With 40 items, a handful of iterations is enough to do real damage.

**Options considered.**

- **One pool, iterate against all 40.** Maximum signal per iteration on a small set. But the final number is uninterpretable, and the more careful the iteration the more overfit the result.
- **Cross-validation over all 40.** Statistically better use of small data. But it still touches every item during development, so the final number is still not a held-out number.
- **Dev/test split with the test split sealed.** DEV 25 for all iteration; TEST 15 untouched until a single final evaluation.

**Choice.** DEV 25 / TEST 15, with the test split sealed. Enforced procedurally *and* mechanically:

- Test-split items live in `evals/calibration/test/` and are gated behind `REHEARSAL_UNSEAL_TEST=1`. The eval harness refuses to load them otherwise and exits non-zero.
- Every test-split evaluation appends to `evals/calibration/test_unseal_log.md`: what was run, which prompt hash, which model, why. The log is committed. If it grows, the sealing has failed and the number's credibility degrades accordingly — and that degradation is public in the repository.
- Automated prompt optimisation (ADR-009) is wired to the dev loader only. It has no code path to the test items.
- Test-split results are reported once per release candidate, not per iteration.

The set's composition matters as much as the split, and is fixed: clean items (to measure false alarms), critical-error items, non-critical items, multi-error items, and deliberately ambiguous items that establish the honest human ceiling. Labelling was blind. Intra-rater and, where available, inter-rater agreement are reported alongside the grader's score as the ceiling — a grader at kappa 0.72 against a human who agrees with herself at 0.78 is a different result from the same grader against a ceiling of 0.95. Full protocol: `SETUP.md` section 6.

**Consequences and price paid.**

- **We iterate against 25 items.** That is a small dev set, and it will produce noisy iteration signal. Some prompt changes that look like improvements on dev are noise, and we will not always be able to tell.
- **15 test items is a weak final measurement.** The confidence interval on kappa from 15 items is wide. ADR-013 requires reporting it, which means publishing honest error bars that will sometimes be embarrassingly large. That is the correct outcome, not a presentation problem to solve.
- **The set can be exhausted.** Each unsealing costs a little credibility. If we unseal several times across releases the test split is effectively burned, and the only remedy is labelling new items — which is expensive human expert time.
- **Discipline is required at the exact moment it is hardest.** The temptation to peek is strongest right before a release when dev results are ambiguous. The unseal log exists because willpower is not an engineering control.

**What would reverse it.** Only growth. If the calibration set expands substantially — say to 150+ items with multiple raters — a three-way dev/validation/test split becomes appropriate and the current test split can be retired into the dev pool with that transition documented.

---

## ADR-013 — Report rates and uncertainty; never a single headline score

**Status:** decided

**Context.** Every stakeholder wants one number. "How accurate is it?" is a reasonable question and "0.74" is a satisfying answer. It is also, here, close to a lie — because the target being measured is a stochastic human performing a stochastic task, evaluated by a stochastic grader against a small labelled set with a human ceiling below 1.0.

A single number implies precision that the measurement does not have, and it invites comparison against numbers computed differently.

**Options considered.**

- **Single headline accuracy.** Communicates instantly. But it hides the confidence interval, the human ceiling, per-category variation and the split it came from.
- **Full statistical reporting only.** Honest and complete. But nobody reads it, and the practical effect is that people quote a number they found somewhere else.
- **A small set of headline numbers, each always accompanied by its interval, its n, its split and the human ceiling.**

**Choice.** The third. The reporting contract is fixed and applies to every eval number in every document, UI surface and external description:

| Requirement | Rule |
|---|---|
| Interval | Every rate carries an interval. Proportions use Wilson score at 95%; kappa uses bootstrap over items, 2000 resamples |
| Sample size | `n` is stated adjacent to the number, always |
| Split | `dev` or `test (sealed)` is stated, always |
| Ceiling | Agreement figures are reported next to the human intra-rater ceiling on the same items |
| Precision | Two significant figures. `0.74`, never `0.7413` |
| Category breakdown | Aggregate agreement is never reported without per-category agreement, because performance varies sharply by error category and the aggregate hides it |
| Failure disclosure | Known weaknesses are named in the same place as the score, not in a footnote elsewhere |

Correct form:

> Grader–human agreement on the sealed test split: **kappa 0.74** (95% bootstrap CI 0.58–0.86, n=15). Human intra-rater agreement on the same items: **0.81** (n=15). Critical-category agreement: **0.91** (CI 0.74–0.98). Non-critical: **0.63** (CI 0.44–0.79). Register-shift findings remain the weakest category and are surfaced to trainees as advisory rather than scored.

Banned form: "74% accurate."

This extends into the product itself. The trainee-facing report carries a permanent, non-dismissible disclosure of the scorer's measured accuracy and its known weak categories. The system tells the user where it is unreliable, in the same view as its findings.

**Consequences and price paid.**

- **We look less impressive than competitors who quote one number.** Wide intervals from a 15-item test split read as weakness next to a confident round figure, even when ours is the more trustworthy claim. This is a genuine commercial cost and it will not go away.
- **More work in every reporting surface.** Bootstrap machinery, interval propagation, per-category breakdowns in the UI. The report page is meaningfully more complex than a score card.
- **Users must be taught to read it.** A trainee seeing "kappa 0.74, CI 0.58–0.86" needs context. The UI has to translate without flattening — which is a hard design problem, addressed in `docs/09-ui-ux.md`.
- **Some numbers will be too uncertain to report at all.** Per-category agreement on a category with 2 test items is not a number. We say "insufficient data" rather than computing something. Saying that repeatedly is uncomfortable and correct.

**What would reverse it.** Nothing. This is the honest-reporting principle, and abandoning it would remove the reason to believe any other number in the project.

---

## ADR-014 — Bilingual UI as a first-class requirement

**Status:** decided

**Context.** The users are bilingual by definition. Many promotoras and community health workers are Spanish-dominant. A tool that trains Spanish–English interpreting through an English-only interface with a translation bolted on later is telling its users something about who it was built for.

The usual approach — build in English, extract strings, translate — produces a predictable set of failures: layouts that break when Spanish runs 15–30% longer, fonts missing diacritic coverage, mixed-language screens where the chrome is Spanish and the content is untranslated English, and error messages that fall back to English at the worst moment.

**Options considered.**

- **English-first, translate later.** Fastest to a working product. But retrofitting bilingual support means re-doing layout, and interim releases are visibly English-first to a Spanish-dominant user.
- **Two separate builds.** Clean per-language. But it doubles maintenance and cannot handle genuinely mixed sessions, which are the normal case here.
- **Bilingual from the first component,** with language a first-class piece of state and both locales exercised in every layout test.

**Choice.** Bilingual from the first component. Specifics:

- **No hard-coded user-facing string, ever.** All copy resolves through `t(key, locale)`. `en-US` and `es-MX` catalogues are maintained together; a key present in one and missing in the other fails the build. There is no English fallback at runtime — a missing translation is a build error, not a degraded screen.
- **Layout is tested at Spanish string lengths.** Component tests render with the `es-MX` catalogue and assert no overflow or clipping. Spanish's greater average length is a layout constraint, not an afterthought.
- **Noto Sans for body text is chosen for coverage,** not aesthetics. Spanish diacritics and extended-Latin glyphs must render correctly at every weight used, including in mixed-script contexts. Figtree is used for headings; its coverage is verified for the heading strings actually shipped.
- **The interface language and the practice languages are independent.** A trainee can run the UI in Spanish while practising English→Spanish. Conflating them is a bug.
- **Bilingual content coexists on one screen by design.** The turn review shows an English source and a Spanish rendering simultaneously. Each is marked with its language for screen readers via `lang` attributes, so assistive technology switches pronunciation correctly. This is an accessibility requirement, not a nicety.
- **Errors, empty states and permission prompts are translated too.** These are the surfaces that get skipped, and they are the surfaces a user hits when something has already gone wrong.

**Consequences and price paid.**

- **Every copy change is two changes,** and shipping is blocked on translation. There is no "ship English now, translate next release" path — that is the point, and it is also a real velocity cost on every single UI change.
- **Layout budgets are tighter.** Components must accommodate the longer language, which constrains dense layouts and costs horizontal space everywhere.
- **Translation quality is a real dependency.** Machine-translated UI copy in a *professional language-services* product is self-discrediting. Copy needs review by a fluent speaker familiar with the interpreting domain — `es-MX` register specifically, since the patient agent targets that variety.
- **Testing surface doubles** for anything user-facing: two locales times light and dark mode times the accessibility checks.

**What would reverse it.** Nothing. Reversing this would contradict the product's reason for existing.

---

## ADR-015 — Scenario realism grounded in public corpora; truth from construction

**Status:** decided

**Context.** ADR-002 makes the system the author of every source utterance, which makes realism our responsibility. Model-generated clinical dialogue has a characteristic failure: it is too clean. Real patients interrupt, trail off, use folk terms, give timelines out of order, and answer a different question than the one asked. An interpreter trained only on tidy speech is trained on the easy case.

There is a related trap: assuming that because we need realism, we need real recordings — and therefore real patient data.

**Options considered.**

- **Purely model-generated scenarios from a short brief.** Cheapest and most scalable. But it produces the tidy-speech failure and imports the model's stylistic priors into training material.
- **Real clinical recordings.** Maximum realism. But it requires protected health information, consent infrastructure and IRB-shaped process, and it directly contradicts ADR-001. Not viable and not desirable.
- **Grounding in public corpora and published materials,** with the actual utterances still constructed by us.

**Choice.** Scenario *characteristics* are grounded in public, non-PHI sources; scenario *content* is constructed. The two are not in tension because grounding constrains the shape of speech, not its literal text.

| Grounding source | What it constrains | What it does not supply |
|---|---|---|
| Published medical-interpreting training materials and certification practice sets | Encounter structure, turn length distribution, the standard difficulty devices (embedded numbers, negation, rapid clinician monologue) | Any literal utterance we ship |
| Published clinical guidelines and formularies | Medication names, plausible dosing, realistic frequency patterns, plausible symptom timelines | Any patient |
| Public health-communication corpora and plain-language guidance | Health-literacy register, folk terminology, common patient misconceptions | Any transcript we reproduce |
| Regional demographic and language-access reporting for Santa Cruz County | Which conditions and encounter types matter locally; Spanish variety; realistic barriers | Any individual's data |

Every scenario in the bank records its grounding in `scenarios/<id>/grounding.md` — what informed the clinical content and the speech characteristics. A scenario without recorded grounding does not ship.

Ground truth remains construction-derived and is unaffected. Grounding shapes *what kind of sentence* the clinician agent produces; the sentence itself is still generated by us and stored verbatim (ADR-002). We never need a real recording to know what was said.

Realism is measured, not asserted. Interpreter trainers review scenarios against a rubric covering clinical plausibility, speech naturalness, difficulty calibration and cultural appropriateness. That review score is the scenario bank's own eval number — see `docs/08-evals.md`.

**Consequences and price paid.**

- **Scenario authoring is slow and expert-dependent.** Each scenario needs clinical grounding, speech design, difficulty calibration and trainer review. This is the project's main content bottleneck and it does not parallelise well.
- **Coverage will be uneven.** We will have good scenarios for common primary-care encounters in this region and thin coverage of specialist encounters and rare presentations. Say so, rather than implying breadth.
- **We cannot claim ecological validity.** Constructed encounters resemble real ones; they are not sampled from them. Any claim about transfer to real-world performance is a hypothesis, not a result, and must be labelled as such.
- **Grounding needs periodic refresh.** Formularies and guidelines change; dosing in an old scenario can become wrong. `docs/07-data-and-scenarios.md` defines the review cadence by dependency (on guideline revision), not by calendar.

**What would reverse it.** Trainer review consistently finding constructed scenarios unrealistic in ways that grounding cannot fix. The response would be a licensed, consented, de-identified corpus of *interpreted encounters* used as authoring reference — still not as scored input, because ADR-002 requires a known source.

---

## ADR-016 — Single-machine deployment; no multi-tenant fleet

**Status:** decided

**Context.** Given local-only inference (ADR-001) and a ~20–24 GB resident model footprint, the natural scaling question is whether to build a shared deployment: one powerful machine, several trainees connecting from thin clients.

**Options considered.**

| Option | For | Against |
|---|---|---|
| Multi-tenant server | Amortises hardware across a cohort; central management for a training programme | Concurrent sessions multiply resident memory or force model sharing with queueing, which reintroduces latency; needs auth, tenant isolation, per-tenant data separation, session scheduling and capacity planning — a horizontal infrastructure product bolted onto a vertical training product |
| Single machine, single user | Whole memory budget for one session; no auth surface; no tenant-isolation bugs; data locality is trivially true | One machine per concurrent user; hardware cost falls on the deployer; no central cohort management |
| Single machine, sequential multi-user (shared lab machine, one at a time) | Programmes can share hardware; still no concurrency | Needs local user separation and per-user data partitioning; modest but real work |

**Choice.** Single-machine deployment, one active session at a time. Multi-user *fleet* scaling is an explicit, reasoned exclusion — it is horizontal infrastructure, and this is a vertical product. Building it would consume the effort that should go into scoring accuracy, which is the thing users actually buy.

Sequential multi-user on shared hardware is accommodated at the thinnest possible level: local OS user accounts, each with their own data directory (ADR-010) and their own SQLite file. No application-level auth, no user table, no session management. The operating system already solves this problem.

**Consequences and price paid.**

- **Hardware cost per concurrent trainee is high.** A programme wanting ten trainees practising simultaneously needs ten capable machines. For a safety-net clinic, that is a serious barrier — and it is the same barrier ADR-001 already created, compounded. This is the strongest commercial argument against the current architecture.
- **No central administration.** A programme director cannot see cohort progress from one place; each machine holds its own data. `rehearsal-export` produces portable session archives that can be aggregated manually, which is a workaround, not a feature.
- **No remote access.** A trainee cannot practise from a personal device against a programme's server. Practice happens where the machine is.
- **Scaling later is a rewrite of specific layers,** not a config change: auth, tenant isolation, request scheduling and a real database (ADR-010) would all be new. We accept that cost rather than pay for it speculatively now.

**What would reverse it.** A training-programme deployment where per-seat hardware cost is the binding blocker on adoption, evidenced by an actual programme declining for that reason. The first response would be sequential scheduling on shared hardware — a booking layer, not a multi-tenant rewrite — because it captures most of the amortisation for a fraction of the complexity.

---

## ADR-017 — Use an existing inference server; do not build one

**Status:** decided

**Context.** Running four model-shaped components in ~20–24 GB with tight latency requirements creates obvious temptation: write a custom runtime that knows about our specific residency and scheduling needs.

**Options considered.**

- **Build a custom inference server.** Perfect fit for our residency and scheduling model; no dependency. But it is a large, specialised, permanent engineering commitment in an area where the open-source state of the art moves fast, and every hour spent on it is an hour not spent on scoring accuracy.
- **MLX only.** Excellent on Apple Silicon, which is the primary target. But it strands any non-Apple deployment entirely.
- **llama.cpp only.** Highly portable, broad quantisation support. But it leaves Apple-specific performance on the table on the primary platform.
- **MLX primary, llama.cpp fallback, behind one internal interface.**

**Choice.** MLX as the primary runtime on Apple Silicon, llama.cpp as the portable fallback, both behind a single narrow internal interface:

```python
# rehearsal/runtime/base.py
class InferenceBackend(Protocol):
    def load(self, model_id: str, quantisation: str) -> LoadedModel: ...
    def generate(self, model: LoadedModel, call: ModelCall) -> ModelResult: ...
    def generate_stream(self, model: LoadedModel, call: ModelCall) -> Iterator[str]: ...
    def unload(self, model: LoadedModel) -> None: ...
    def resident_bytes(self) -> int: ...
```

Two implementations, `MLXBackend` and `LlamaCppBackend`. This is one of the few places the project accepts an interface with more than one implementation, and it is justified: both implementations ship, and the portable one is the reason the product is not permanently Apple-only.

Building an inference server is an explicit project-level exclusion, in the same category as weight training (ADR-009): a capability we deliberately do not develop.

**Consequences and price paid.**

- **We inherit two dependencies' release cadences and bugs.** Both move fast. A breaking change in either is our problem, and pinning versions means periodically absorbing a large upgrade.
- **Behaviour differs between backends.** Same weights, same quantisation, different backend can produce different output. Consequently every eval number is tagged with the backend that produced it, and a headline number produced on MLX is not automatically a claim about llama.cpp.
- **The abstraction constrains us to the intersection of both APIs.** A backend-specific optimisation that has no counterpart cannot be used through the common interface without special-casing, which we avoid.
- **We do not control scheduling.** Residency and eviction across four components must be managed at our layer, on top of runtimes that were not designed for our specific contention pattern. This is where the memory-budget work in `docs/13-deployment-ops.md` actually lives.

**What would reverse it.** Only a demonstrated, measured performance requirement that neither runtime can meet and that no upstream contribution can fix. Contributing upstream is strictly preferred to forking, and forking is strictly preferred to writing one.

---

## ADR-018 — The human review loop always wins

**Status:** decided

**Context.** The scorer is measured and imperfect (ADR-013). A trainer who disagrees with a finding must be able to override it, and that override must be the record of what happened. This follows directly from principle 1: the model generates and extracts, deterministic code decides, and the human decides ultimately.

The design question is what an override *means* — an exception, or data.

**Options considered.**

- **No override; the score is the score.** Simple; consistent. But it means telling a professional interpreter trainer that the machine is right and she is wrong, which is both false and commercially fatal.
- **Override as a silent correction.** The trainee sees the corrected finding, nothing else changes. Preserves the trainee experience but throws away the most valuable signal the system can produce.
- **Override as first-class recorded data.** The override becomes the record of truth, the original finding is retained, and the disagreement is measurable.

**Choice.** Overrides are first-class and recorded with reasons.

```sql
CREATE TABLE finding_overrides (
    id                  INTEGER PRIMARY KEY,
    finding_id          INTEGER NOT NULL REFERENCES findings(id) ON DELETE CASCADE,
    reviewer_label      TEXT NOT NULL,     -- local reviewer identifier, not an account
    action              TEXT NOT NULL CHECK (action IN ('reject','reclassify','reseverity','add')),
    original_category   TEXT,
    new_category        TEXT,
    original_severity   TEXT,
    new_severity        TEXT,
    reason              TEXT NOT NULL,     -- required; free text, never optional
    created_at          TEXT NOT NULL
);
```

The overridden state is what the trainee sees and what competency tracking uses. The original finding is retained and visible in the trainer view, never deleted.

Trainer-override rate is the L7 eval number. It is a quality signal about the *scorer*, read alongside the calibration results: a rising override rate in one category is direct evidence of a scorer weakness in the field, and given ADR-011 it is close to the only such evidence we have. This is why the `reason` field is mandatory — an override without a reason is a number without a diagnosis.

Overrides are never fed back as training data (ADR-009 forbids weight training in any case). They inform prompt work and extractor work through human analysis, with a human deciding what the pattern means.

**Consequences and price paid.**

- **Override review is unpaid human labour** and it will not happen at volume. Most sessions in most deployments will have no trainer review at all, which makes the override signal sparse and biased toward the trainers who bother.
- **Two versions of the truth exist,** and every downstream consumer — competency tracking, session reports, exports — must consistently use the overridden view. Getting this wrong in one place produces contradictory numbers in the same product.
- **Overrides are rater-specific.** Two trainers may disagree with each other. Treating override rate as ground truth about scorer error would be a mistake; it is evidence, weighted by how many raters produced it.
- **The trainee can see that the machine was wrong.** This is correct and healthy for a tool that publishes its own accuracy, but it does place a burden on the UI to present disagreement without undermining confidence in the whole report.

**What would reverse it.** Nothing. Removing the human gate would contradict the product's core architectural principle.

---

## ADR-019 — Consecutive interpreting is the default mode

**Status:** decided

**Context.** Medical interpreters work in two modes. *Consecutive* — the speaker pauses, the interpreter renders — is overwhelmingly the norm in clinical encounters and the mode certification assesses. *Simultaneous* — rendering while the speaker continues — appears in specific contexts such as long clinician monologues and psychiatric encounters.

Simultaneous is technically much harder for us: it requires the agent to keep speaking while the trainee speaks, real-time overlapping audio handling, and turn segmentation without a clean boundary. It also breaks the assumption ADR-006 depends on — that the trainee's rendering time is dead time for the grader.

**Options considered.**

- **Both modes from the start.** Complete professional coverage. But simultaneous invalidates the grading-window assumption and demands full-duplex audio, which is a substantially harder pipeline.
- **Consecutive only, permanently.** Simplest. But it leaves a real professional competency permanently unaddressed.
- **Consecutive first; simultaneous as a later capability with its own architecture work.**

**Choice.** Consecutive only in the initial scope, with clean turn boundaries. Simultaneous is deferred, not rejected, and the deferral is stated in the product rather than left implicit.

Turn boundaries are detected by end-of-speech with a configurable silence threshold plus an explicit trainee-controlled "done" affordance, because silence thresholds are unreliable for a trainee who pauses to think. Both paths converge on the same `turn_finalised` event that drives ADR-006's queue.

**Consequences and price paid.**

- **A real professional competency is unaddressed.** Interpreters need simultaneous skill; we do not train it. Say so plainly rather than letting "medical interpreting practice" imply coverage.
- **Adding it later is architectural, not incremental.** Full-duplex audio, overlapping-turn segmentation and a different grading schedule. ADR-006's core assumption does not survive it, and the grading window would have to be rethought.
- **The silence threshold is a tuning knob that will annoy people.** Too short cuts off a thinking trainee; too long makes the system feel dead. It is exposed in settings with a sensible default because no single value is right for every speaker — this is a physical-world calibration problem, not something a better algorithm removes.

**What would reverse it.** Trainer feedback identifying simultaneous practice as the binding gap in trainee readiness. It would be scheduled as its own capability with its own eval, after the consecutive scoring path has a defensible kappa — adding a harder mode before the easier one is measured would be building on sand.

---

## ADR-020 — Indigenous-language support is a named gap, not a promise

**Status:** decided

**Context.** The geographic grounding is deliberate: Watsonville and the Pajaro Valley have a large farmworker population speaking Mixteco and Triqui, not only Spanish. The research is specific — Salud Para La Gente reports access to three Mixteco interpreters; Watsonville Community Hospital employs none. The unmet need for indigenous-language interpreting is larger, proportionally, than the Spanish need.

It is also the need we are least equipped to meet. Mixteco is a group of related variants with limited mutual intelligibility, not one language. Available models have effectively no coverage. TTS does not exist for most variants. And we have no basis for constructing a ground-truth error taxonomy in a language we cannot verify.

There is a strong temptation to gesture at it anyway — it is the most compelling part of the need story.

**Options considered.**

- **Attempt Mixteco support.** Maximum impact if it worked. But with no model coverage, no TTS and no verification path, we would ship something that appears to assess and does not. In a language-access context that is worse than nothing.
- **Do not mention indigenous languages.** Avoids overpromising. But it misrepresents the problem the product sits inside.
- **State it explicitly as a named gap** the system does not address, with the reasons.

**Choice.** Spanish–English only. Indigenous-language interpreting is named as a real and larger gap that Rehearsal does not address, with the reasons stated: no adequate model coverage, no TTS, no verification path for ground truth, and no basis for a defensible error taxonomy without deep community and linguistic partnership that we do not have.

This appears in `docs/00-dossier.md` and `docs/01-research.md` as a limitation, never as a roadmap item, because a roadmap item implies a plan and we do not have one.

**Consequences and price paid.**

- **The product does not serve the population with the greatest unmet need.** That is an uncomfortable thing to write and it should stay uncomfortable rather than being softened.
- **We forgo the most compelling version of the impact story,** which has a real cost in how the product is received by exactly the organisations most motivated to adopt it.
- **Some may read the gap as lack of ambition.** The alternative — claiming capability we cannot verify — is worse, particularly in a domain where an unverified assessment tool could give a community health worker false confidence in an interpreting encounter that matters.

**What would reverse it.** Three things together, none sufficient alone: adequate model coverage for a specific variant, a viable TTS path, and a partnership with speakers and linguists who can construct and verify ground truth. Absent all three, the answer stays no.

---

## ADR-021 — Severity is assigned deterministically

**Status:** decided

**Context.** Every finding carries a severity: `critical` (could change clinical action) or `non_critical`. This is the field that drives what the trainee sees first, what a trainer reviews, and what competency tracking weights most heavily. It is the most consequential single field the scorer produces.

The obvious implementation is to have the model assign it — it already has the context. But severity is precisely the "anything consequential" that principle 1 reserves for deterministic code.

**Options considered.**

- **Model assigns severity per finding.** Contextually sensitive; handles cases a rule misses. But it is non-deterministic on the most consequential field, it varies between runs on identical input, and there is no way to explain a severity to a trainer beyond "the model said so".
- **Model proposes, code confirms.** Keeps model nuance with a deterministic check. But it is genuinely unclear what "confirms" means when the two disagree, and the merge semantics get muddy.
- **Deterministic rule from category plus span type,** with the model contributing only the span content it identified.

**Choice.** Deterministic assignment. Severity is a pure function of the error category and the *type* of the affected span, computed by code from the source-facts extraction (ADR-002), never by the model.

```python
# rehearsal/scoring/severity.py
CRITICAL_SPAN_TYPES: frozenset[str] = frozenset({
    "dosage", "frequency", "allergy", "negation",
    "laterality", "symptom_onset", "route", "medication_name",
})

def assign_severity(category: ErrorCategory, span_types: frozenset[str]) -> Severity:
    """Severity is decided by rule, never by the model (ADR-021).

    A finding is critical iff it touches a span type that can change clinical
    action. Category alone never makes a finding critical: an omission of a
    pleasantry and an omission of a dosage are the same category.
    """
    if span_types & CRITICAL_SPAN_TYPES:
        return Severity.CRITICAL
    return Severity.NON_CRITICAL
```

The model may identify *what* was omitted or distorted. It never decides *how much that matters*. Consequently the same finding always carries the same severity, and any severity can be explained to a trainer in one sentence: it touched a dosage.

**Consequences and price paid.**

- **The rule is coarse and will misjudge edge cases.** A distorted symptom description that is clinically significant but touches no listed span type is scored non-critical. That is a real false negative on the most important axis, and the rule is deliberately biased toward the reproducible answer over the contextually clever one.
- **`CRITICAL_SPAN_TYPES` is a policy decision embedded in code.** Changing it changes every historical score's meaning. It is versioned with the scoring engine, and reports record the scoring-engine version so old and new results are never compared naively.
- **Severity accuracy depends entirely on span-type extraction.** If the extractor fails to type a span as `dosage`, the severity is silently wrong. This makes span-type recall a critical-path measurement in its own right, tracked separately in `docs/08-evals.md`.
- **Trainers will disagree with specific severities,** and the override path (ADR-018) is the intended pressure valve. A pattern of severity overrides in one category is the signal to revisit the rule — through a reviewed code change, not a model prompt tweak.

**What would reverse it.** Measured evidence that model-assigned severity agrees with human severity judgements substantially better than the rule does, on the calibration dev split, across categories. Even then the likely response is to *improve the rule* using what the model got right, because a severity a trainer cannot have explained to them is not usable in a training context.

---

## ADR-022 — Audio retention defaults

**Status:** **open**

**Context.** A session produces the trainee's rendering audio for every turn. It is genuinely valuable: hearing your own hesitation and self-correction is a large part of what makes review useful, and re-grading an old session after a scorer improvement requires the audio.

It is also the most sensitive artefact the system holds. It is a voice recording of an identifiable person speaking clinical content. Even though the content is simulated and no real patient exists, the recording is of a real person and may be discoverable, subpoena-able, or simply embarrassing.

Nothing leaves the machine (ADR-001, ADR-011), so this is entirely a question about local storage: what the default should be, how long, and how deletion works.

**Options considered.**

| Option | For | Against |
|---|---|---|
| Retain indefinitely by default | Best review experience; enables re-grading with improved scorers; simplest | Accumulates a growing corpus of voice recordings the user may not realise exists; unbounded disk growth |
| Retain for the session, discard on report generation | Minimal footprint; smallest possible exposure | No later review, no re-grading; the trainee loses the most useful review artefact |
| Retain by default with a visible, adjustable retention window and one-click purge | Balances both; puts the user in control | More UI; a retention setting is a thing users must understand to use correctly |
| Discard by default, opt in to retention | Most conservative | Most users never opt in and lose the feature; a privacy default that removes the product's value is a bad default |

**Current position (not final).** Retain by default, with three commitments that are already decided regardless of how the retention question resolves:

1. Retention is **visible**. The UI states plainly what is stored, where it is on disk, and how much space it occupies. No hidden corpus.
2. Deletion is **complete and easy**. `rehearsal-purge --session <id>` and `rehearsal-purge --all` remove blobs and rows transactionally, with the blob GC guaranteeing no orphans. A UI equivalent exists.
3. Retention is **configurable before the first session**, not buried after the fact.

**What is genuinely open.** The default retention window. Indefinite is the best product experience and the worst privacy posture. A bounded default (some number of sessions, or some amount of disk) is more defensible but arbitrary, and an arbitrary number in a privacy control is its own kind of dishonesty.

**Consequences and price paid, either way.** Indefinite retention accumulates voice recordings a user may forget about, and disk grows without bound. A bounded window silently destroys review material a trainee may have wanted, and "silently" is the problem — any bounded default needs a warning before deletion, which is more UI and more ways to annoy.

**What would close this.** Input from interpreter trainers and from at least one prospective clinic deployment on what their own policies require. This is a decision that should be made with the people whose recordings they are, not inferred from first principles. Until then the implementation carries the three commitments above and the default is set to indefinite, with the open status recorded here so it is not mistaken for a settled answer.

---

## 3. Decisions explicitly not made here

For completeness, the following are recorded elsewhere and are not ADRs because they are project-level exclusions rather than choices between options. They are stated so that nobody re-litigates them as if they were open:

| Exclusion | Where stated |
|---|---|
| No model weight training, fine-tuning, RL or LoRA adapters | ADR-009; project scope |
| No building of an inference server | ADR-017; project scope |
| No horizontal multi-tenant fleet scaling | ADR-016; project scope |
| No cloud inference in the core loop | ADR-001 |
| No scoring of encounters the system did not generate | ADR-002 |

## 4. Adding a decision

New ADRs take the next unused number and the format in section 1. A decision belongs here if reversing it would require changing more than one document or migrating data. Decisions smaller than that belong in the relevant document, not in this record — a decision log that records everything records nothing.

Superseding an ADR: leave the original in place, change its status line to `superseded by ADR-0NN`, and write the new one. Never edit a decided ADR's Choice field in place; the record's value is that it shows what we used to think.

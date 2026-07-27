# 16 — Roadmap

## 0. How to read this document

This roadmap contains no dates, no durations and no schedule. It is ordered by **dependency** and gated by **evidence**.

A stage is not a period of time. A stage is a **statement that becomes true about the system**, plus the measurement that proves it became true. Stages are strictly ordered because each one consumes a number produced by the one below it: you cannot honestly measure whether isolating the counterpart agent changes utterance difficulty until you have a difficulty measure, and you cannot have a difficulty measure until the scorer exists and is calibrated.

Every stage has four fixed parts:

| Part | Meaning | Enforcement |
|---|---|---|
| **Entry criteria** | Numbers that must already exist, recorded in `plans/metrics-snapshot.md`, before work in this stage begins | A stage entered without its entry numbers is building on an unmeasured assumption; this is the single most common way projects like this fail |
| **What gets built** | Concrete modules, files and commands. No stage lists a capability without naming where it lives | Reviewed against `docs/03-system-architecture.md` §4 |
| **Exit criteria** | Named evals from `docs/08-evals.md` at stated gate values, recorded in the eval registry with a clean git tree | `make evals` prints the gate table; a stage is not exited by assertion |
| **Abandon / re-plan trigger** | The specific observation that would mean this stage is the wrong stage | Written *before* the stage starts, so it cannot be rationalised away afterwards |

Two rules apply across every stage and are not negotiable at any point in the climb:

1. **No performance claim exists before the calibration anchor exists.** Until `SETUP.md` §6 has produced a labelled 40-item set with a sealed TEST split, the correct statement about grader accuracy is "unmeasured", not an estimate. This is why Stage 0 is Stage 0.
2. **The sealed TEST split is touched once per stage at most, through `uv run rehearsal-evals unseal --reason "<text>"`, and the reason is written into `TEST_ACCESS.log`.** Every stage below states explicitly whether it is permitted to unseal. Most are not.

Stage numbering here is independent of the layer-vertical rung numbers (L4–L10). The mapping is given in §2. A stage may complete a rung, or it may complete part of one; the rungs describe *capability class*, the stages describe *build order*.

---

## 1. Stage map

| Stage | What becomes true | Rungs advanced | Headline exit number | May unseal TEST? |
|---|---|---|---|---|
| **0** | The system can score a known source against a known rendering, and we know how often that score is right | L4 | `kappa_macro` on DEV with `kappa_intra` beside it; `critical_recall` ≥ 0.90 DEV | **Once**, at stage close only |
| **1** | A single human can complete one scored spoken encounter end to end, alone, on one machine | L5, L7 (partial) | `session_completion_rate` ≥ 0.90; `p95_first_audio_ms` within budget | No |
| **2** | Two isolated counterpart agents hold a clinically coherent triadic encounter, and isolation is shown to matter or shown not to | L5, L6, L8 | `persona_consistency` ≥ 0.95 with canary = 1.00; `leakage_delta` reported with CI | No |
| **3** | The grader's prompt is improved by a measured optimisation loop rather than by taste | L10 (rung 1) | Before/after `kappa_macro` on the sealed TEST split, single unseal | **Once**, mandatory |
| **4** | The system remembers a trainee across sessions and its recommendations are explainable | — (deepens L7) | Difficulty-oscillation rate; recommendation-rationale coverage = 1.00 | No |
| **5** | A trainer can review, override and see a cohort, and overrides feed back into measurement | L7 complete | `trainer_override_rate` inside the 0.02–0.25 investigation band, with n printed | No |
| **6** | The system covers more than one clinical domain, and the cost of a new language pair is known rather than assumed | — (breadth) | Per-domain `critical_recall` no worse than the seed domain − 0.05 | Per-domain, once |

**Dependency edges, stated as facts rather than arrows:**

- Stage 1 needs Stage 0 because a session that produces an unvalidated score is a demo, not a training tool.
- Stage 2 needs Stage 1 because the leakage A/B measures *utterance difficulty in a real encounter*, which requires real encounters to exist.
- Stage 3 needs Stage 0 and Stage 2 because the optimiser's metric is calibration-set agreement, and the prompt being optimised must be the prompt that runs in the real multi-agent loop, not a lab variant.
- Stage 4 needs Stage 2 because a learner model built on single-scenario data models the scenario, not the learner.
- Stage 5 needs Stage 4 because trainer override is only interesting when there is a track record to override against.
- Stage 6 needs Stage 5 because the trainer-review path is how a new domain's labels get produced at all.

---

## 2. Stage 0 — The scorer and the anchor

### What becomes true

Given a source utterance and a trainee rendering **as text**, the system produces a typed verdict: a list of findings with span, category from the nine-item taxonomy, severity, and note — with the critical categories decided by deterministic code and only the semantic residue decided by a model. And we know, with a stated interval and a human ceiling beside it, how often that verdict agrees with a human expert.

This stage has no audio, no agents, no session and no UI. That is deliberate. Everything above it is worthless if this is wrong, and everything above it makes this harder to debug.

### Entry criteria

| Requirement | Evidence |
|---|---|
| Repository, toolchain and model hosts run | `rehearsal doctor` exits clean; `make check` passes on a trivial commit |
| The 12B grader model loads and returns structured output | A fixture round-trip through `src/rehearsal/scoring/grader.py` at temperature 0 |
| The taxonomy is frozen | `src/rehearsal/scoring/taxonomy.py` defines exactly the nine `ErrorKind` members and the `Severity` rule; changing it after labelling begins invalidates the labels |

The third row is the one that gets skipped and should not be. The calibration set is labelled *against* the taxonomy; a taxonomy edit after labelling means either re-labelling or a silently invalid anchor.

### What gets built

```
src/rehearsal/scoring/
├── taxonomy.py                 # ErrorKind, Severity, Finding, Verdict  — frozen first
├── extractors/
│   ├── numbers.py              # cardinals, decimals, ranges, cross-lingual normalisation
│   ├── dosage.py               # value + unit + form; mg/ml/mcg/tablet/pill equivalence
│   ├── frequency.py            # q.d./b.i.d./"dos veces al día"/"cada 8 horas"
│   ├── negation.py             # scope-aware polarity, incl. Spanish double negation
│   ├── laterality.py           # left/right/bilateral, izquierdo/derecho/ambos
│   ├── allergy.py              # allergen mention + polarity + reaction
│   └── temporal.py             # onset, duration, "since", "hace tres días"
├── grader.py                   # ONE structured call; semantic residue only
├── merge.py                    # VerdictMerger — deterministic precedence
└── queue.py                    # ScoreQueue (built here, exercised in Stage 1)

data/calibration/
├── items.jsonl                 # 40 labelled turns  (SETUP.md §6)
├── split.json                  # DEV 25 / TEST 15, seeded, committed
└── relabel_sample.jsonl        # delayed re-label subset for kappa_intra

src/rehearsal/evals/suites/
├── ev00_extractors.py
├── ev01_calibration.py
├── ev02_critical_recall.py
└── ev03_human_ceiling.py
```

The calibration set is built **in parallel with** the extractors, not after them, and the labelling is done blind — the labeller must not have seen extractor output for the items they are labelling. If labelling follows the extractors, the labeller learns what the extractors catch and the anchor stops being external. Protocol in `SETUP.md` §6; do not re-derive it here.

### Exit criteria

| Eval | Gate | Split | Notes |
|---|---|---|---|
| `EV-00` extractor conformance | `extractor_conformance = 1.00` | fixture grid | Not a score. A failure is a bug. |
| `EV-03` human ceiling | `kappa_intra` **exists and is recorded** | re-label sample | Blocks publishing any headline number at all |
| `EV-01` grader calibration | `kappa_macro ≥ 0.60` | **DEV** | Promotion gate for a grader prompt version |
| `EV-02` critical-error recall | `critical_recall ≥ 0.90` | **DEV**, Wilson interval printed with denominator | The safety gate. Outranks κ on conflict. |
| `EV-01`/`EV-02` confirmation | Reported, not gated | **TEST**, single permitted unseal | Recorded with `unseal_reason`; this is the stage's one look |
| Per-category | Any category with `recall < 0.50` labelled "not reliably detected" | DEV | The label is a product requirement, not a note to ourselves |

Also required to exit: `fp_rate_clean ≤ 0.15` on DEV. A scorer that invents errors on clean renderings will teach trainees to distrust it, and distrust is unrecoverable.

### Open risk

**The anchor is one rater.** With 40 items labelled by one person, `kappa_inter` may not exist, and if it does not, the honest statement is "the grader agrees with *this rater's* application of the standard", not "the grader agrees with the professional standard". This is a named gap and is stated in `MODEL_CARD.md` and in the product, per `docs/08-evals.md` §9.

**Small denominators.** 15 sealed TEST items with a handful of critical errors among them means the interval on `critical_recall` is wide. Two decimals of κ on 15 items is close to false precision; the interval is the number, and the point estimate alone is never quoted.

**Cross-lingual normalisation is where extractors actually break.** `dos y medio` → 2.5, `cada ocho horas` → q8h, `medio comprimido` → 0.5 tablet. Conformance = 1.00 on a fixture grid we wrote ourselves proves the code matches our own idea of the language, not the language. The fixture grid must be extended from real rendering text as sessions accumulate — a Stage 1 and Stage 6 obligation, tracked as such.

### Abandon / re-plan trigger

| Observation | Response |
|---|---|
| `kappa_macro` on DEV cannot be pushed above ~0.40 with reasonable prompt work | The semantic categories are not decidable at the granularity we defined. **Re-plan**: narrow the model's scope further (fewer categories, wider spans), or ship deterministic-only scoring with the semantic categories explicitly disabled and labelled as such |
| `critical_recall` on DEV stalls below 0.90 and the misses are *extractor* misses, not grader misses | Fixable and expected; extend extractors, re-run. Not an abandon signal |
| `critical_recall` stalls below 0.90 and the misses are cases where the *source utterance itself* was ambiguous | **Re-plan the content**, not the scorer. The scenario generator is producing utterances whose critical content is not unambiguously present. Fix at `docs/07-data-and-scenarios.md`, not here |
| `kappa_intra` comes back low (the human does not agree with themselves) | **Stop.** The anchor is not usable. Re-label with a tightened protocol before anything downstream is measured. A grader cannot be more consistent than the ceiling it is measured against |

---

## 3. Stage 1 — One complete scored session, one scenario, one human

### What becomes true

A trainee starts the system, is given one scenario, hears an English clinician utterance, speaks a Spanish interpretation aloud, hears the Spanish patient reply, speaks an English interpretation, and at the end reads a report showing what survived each rendering. Scoring for turn *n* completes while the trainee is speaking turn *n+1*. Nothing leaves the machine, and a crash mid-session does not lose the session.

### Entry criteria

| Requirement | Number |
|---|---|
| Stage 0 exited | `critical_recall` ≥ 0.90 DEV, `kappa_macro` ≥ 0.60 DEV, `extractor_conformance` = 1.00 |
| Measured per-machine latency envelope | `rehearsal doctor` has written real values for live-model first-token, TTS first-frame, and grader wall-clock into the budget config |
| Resident memory measured, not assumed | Live host + grader host + TTS loaded simultaneously, RSS recorded against the ~20–24 GB target on a 48 GB machine |

The second and third rows exist because the whole feasibility argument is "the grader runs off the critical path inside the human's speaking time". If the grader's wall-clock exceeds a typical trainee utterance, the argument is false on this hardware and the stage must be re-planned before it is built, not after.

### What gets built

```
src/rehearsal/
├── orchestrator/               # loop.py states.py scheduler.py budget.py seeds.py resume.py
├── runtime/
│   ├── audio_in.py             # capture, VAD, endpointing, barge-in detection
│   ├── tts.py                  # TTSRouter — en-US / es-MX, streamed, interruptible
│   ├── hosts.py                # ModelHostClient over UNIX socket, health probe, one restart
│   └── agents/clinician.py     # single agent this stage; patient is scripted from the graph
├── store/                      # db.py events.py blobs.py projections.py migrations/0001_init.sql
├── api/                        # app.py ws.py routes_sessions.py routes_reports.py
└── cli.py                      # rehearsal up | session | replay | doctor

frontend/                       # vanilla-JS SPA: session view + report view only
content/scenarios/              # ONE scenario, hand-authored, with its ClinicalStateGraph
```

**Deliberate scope cuts in this stage, each with a reason:**

| Cut | Reason | Re-added in |
|---|---|---|
| Patient agent is scripted node text, not a model | Two live agents doubles the failure surface while the audio loop is still unstable. The audio loop is the risk here, not agent quality | Stage 2 |
| One scenario only | Scenario breadth tests content tooling; this stage tests the loop | Stage 2 (bank), Stage 6 (domains) |
| No learner model, no difficulty adaptation | Adaptation on a single scenario adapts to the scenario | Stage 4 |
| No coach agent | A third model on a machine whose memory envelope is still being measured | Stage 2 |
| Report is per-session only; no history | History without a learner model is a list, and a list is not a feature | Stage 4 |

### Exit criteria

| Eval | Gate | Notes |
|---|---|---|
| `EV-07` latency conformance | `p95_first_audio_ms` and `p99_barge_in_stop_ms` within the constants in `src/rehearsal/runtime/budget.py` | Measured on the target host class, ≥ 3 seeds |
| `EV-07` grader overlap | `grader_backlog_rate ≤ 0.05` | This is the number that proves principle 5 on real hardware |
| `EV-08` completion | `session_completion_rate ≥ 0.90` over real runs, denominator printed | Placeholder gate per `docs/08-evals.md` §1.1; re-derived from the first real failure distribution |
| Capture integrity | `turn_capture_loss_rate ≤ 0.02` | A lost turn is unrecoverable trainee effort |
| Crash resume | `rehearsal replay <id> --rebuild --verify` clean after a `SIGKILL` mid-turn | Deterministic; a test, not a score |
| `EV-09` regression | All Stage 0 gates still hold, re-run | Audio-derived renderings are not the same distribution as calibration text; if κ moves, that is a finding |

That last row is the substantive one. Stage 0 measured the scorer on **hand-authored text**. Stage 1 feeds it **renderings derived from real speech**, which contain disfluency, self-correction, restarts and false starts. The scorer's DEV numbers do not automatically transfer. Whichever way this comes out, the number is recorded and the difference is stated.

### Open risk

**The rendering-provenance question is unresolved and it is load-bearing.** The live model takes native audio input; the canonical trainee rendering is currently `heard_verbatim` from that model, with an off-path re-transcription fallback behind a config flag (`docs/03-system-architecture.md` §16, question 1). If `heard_verbatim` is a paraphrase rather than a transcript, the scorer is grading the model's summary of the trainee, and omissions will be systematically over-reported. This must be measured in this stage: word-error-rate of `heard_verbatim` against hand transcripts of calibration audio, plus grader agreement under both settings on DEV.

**Echo without headphones.** If the trainee is on speakers, the TTS voice is captured and scored as the trainee's rendering. The energy-correlation guard exists; whether it is sensitive enough is unmeasured.

**Barge-in against consecutive interpreting practice.** Real consecutive interpreting has the interpreter waiting for a complete utterance. If a trainee starts early, the partial source becomes the scoring source and spurious omissions appear. The current position (`docs/03-system-architecture.md` §16, question 2) is proposed, not decided; this stage produces the recorded cases that settle it.

### Abandon / re-plan trigger

| Observation | Response |
|---|---|
| `grader_backlog_rate` cannot be brought under 0.05 on target hardware | Principle 5 does not hold on this machine class. **Re-plan**: smaller grader quantisation, or grading deferred entirely to end-of-session with no in-session feedback — which changes the product, so it is a documented decision in `docs/17-decisions.md`, not a silent one |
| Resident memory with both hosts exceeds the 48 GB envelope | **Re-plan the model layout** before adding agents. Options in dependency order: harder grader quantisation, single-host time-slicing with explicit unload, dropping the coach permanently |
| `heard_verbatim` WER is high enough that omission findings are dominated by transcription loss | **Switch the default** to off-path re-transcription and re-measure. This costs latency off the critical path only, so it is affordable; the decision gets recorded |
| Trainees cannot complete a session because turn-taking is confusing rather than because of a fault | Interface problem, not architecture. Re-plan against `docs/09-ui-ux.md`; do not add features to compensate |

---

## 4. Stage 2 — The isolated multi-agent encounter

### What becomes true

Both counterparts are live models with isolated contexts. The clinician sees clinician-visible facts; the patient sees patient-visible facts; **neither ever sees the rubric, the taxonomy, the learner model, or any scoring output**. The encounter follows a clinical state graph, and persona consistency is checkable deterministically against that graph rather than judged. The claim that isolation matters is settled by a pre-registered A/B, in whichever direction the data goes.

### Entry criteria

| Requirement | Number |
|---|---|
| Stage 1 exited | `session_completion_rate` ≥ 0.90, latency gates met, `grader_backlog_rate` ≤ 0.05 |
| Memory headroom for a second live agent measured | Recorded RSS from Stage 1 with the second agent's context budget added, still inside envelope |
| An utterance-difficulty index defined and **pre-registered before the A/B is run** | Written into `docs/08-evals.md` §4.6 with its components fixed; a difficulty metric chosen after seeing the arms is not evidence |

### What gets built

```
src/rehearsal/runtime/agents/
├── patient.py                  # PatientAgent — Spanish, symptom state, health-literacy level
├── clinician.py                # extended: full state-graph drive
└── context.py                  # ContextAssembler — per-role field ALLOWLIST, the chokepoint

src/rehearsal/content/
├── bank.py                     # ScenarioBank
├── graph.py                    # ClinicalStateGraph, NodeId, advance(), ingest-time validation
└── terms.py                    # TermManifest per scenario

skills/rehearsal-session/       # L6: the packaged, versioned session skill
├── SKILL.md                    # protocol + rubric + taxonomy as a portable definition
└── version.json

src/rehearsal/evals/suites/
├── ev04_persona.py
├── ev05_leakage.py
└── ev06_skill_ab.py
```

**`ContextAssembler` is the whole stage.** Isolation is not a convention agents are asked to respect; it is a construction where a role's context is assembled from an explicit field allowlist and any attempt to include a non-allowlisted field raises `IsolationViolation` at runtime. There is no code path where an agent prompt is assembled by string concatenation outside this module, and a test asserts that.

The **rubric-vocabulary canary** is the cheap enforcement: a fixed list of rubric-specific terms (the nine category names, "severity", "critical", "fidelity score") that must appear zero times in any counterpart-agent context or output. It is binary and gated at 1.00. It cannot detect subtle leakage; the A/B is what addresses that.

### The leakage A/B, stated precisely

Two arms, paired by scenario and turn index, identical seeds:

| Arm | Counterpart context |
|---|---|
| **Isolated** (shipping configuration) | Role fields only, via allowlist |
| **Leaked** (experimental arm, never shipped) | Same, plus the full scoring rubric and error taxonomy |

Measured: mean utterance difficulty index per arm — a pre-registered composite over utterance length, embedded-clause depth, count of extractor-relevant items (numbers, dosages, negations, laterality markers), idiom density and register level. Reported as an effect size with a permutation-test p-value (10 000 permutations, two-sided) and a 95% CI.

**There is no pass/fail gate on `leakage_delta`, and this is intentional.** A null result does not remove the isolation architecture — isolation is also the correct default for privacy of the learner model and for reproducibility. What a null result removes is the *claim* that isolation demonstrably preserves training realism. That claim is then reported as unsupported at this sample size. Pre-registration is what makes this an honest test rather than a search for a confirming statistic.

### Exit criteria

| Eval | Gate |
|---|---|
| `EV-04` persona consistency | `persona_consistency ≥ 0.95` turn-level against the state graph, **and rubric-vocabulary canary = 1.00** |
| Fact containment | Zero instances of the patient agent stating a clinician-only fact, across the scenario bank at ≥ 3 seeds |
| `EV-05` leakage A/B | Effect size, permutation p-value and CI recorded — in **either** direction; pre-registration hash matches |
| `EV-06` skill A/B | `skill_delta` lower CI bound ≥ −0.02. A CI containing zero ships as "no measurable benefit", not as an improvement |
| `EV-09` regression | Every Stage 0 and Stage 1 gate re-run and holding |
| Isolation unit test | Attempting to assemble a counterpart context containing any scoring field raises `IsolationViolation` |

### Open risk

**Two live agents on one host is the memory cliff.** If the E4B class agents cannot both stay resident with the 12B grader, the degradation is either shared-weights-with-swapped-context (cheap, risks persona bleed across roles) or sequential loading (expensive, breaks the latency budget). Neither is chosen in advance; the measurement decides.

**Persona consistency at 0.95 is a proposed gate, not a derived one.** It was chosen to tolerate rare benign state-graph edges while catching drift. Once a real failure distribution exists, it is re-derived; until then it is marked proposed wherever it is quoted.

**The difficulty index may not be sensitive enough.** A composite that moves only for gross changes will produce a null result that means "our instrument is blunt", not "isolation does not matter". The pre-registration must therefore include an estimate of the smallest effect the index can detect at this sample size — stated honestly as a limitation of the test.

### Abandon / re-plan trigger

| Observation | Response |
|---|---|
| `persona_consistency` cannot exceed ~0.85 | The state graph is under-constraining the agents. **Re-plan the content layer** — richer node invariants, scripted fallback lines at high-risk nodes — before touching prompts |
| The leakage A/B returns a null with a wide CI | Report it as unsupported, keep isolation on the other two justifications, and **do not re-run the test with a new metric to get a better answer**. A second bite requires a new pre-registration and both results reported |
| Memory forces sequential agent loading and latency gates break | **Re-plan to a single counterpart agent** that plays both roles with hard context separation between turns, and measure whether cross-role bleed appears. This weakens the multi-agent claim and must be stated, not hidden |
| The packaged skill (L6) shows no benefit and adds a failure mode | Ship it as versioned documentation, drop it from the runtime path. A skill that does not measurably help is documentation with extra steps |

---

## 5. Stage 3 — The measured prompt-optimisation loop

### What becomes true

The grader's prompt is improved by an automated optimiser (DSPy/GEPA-style) whose metric is agreement with the human calibration labels on the **DEV** split, and the improvement is confirmed once on the **sealed TEST** split under a written protocol. Prompt-level only: **no weight training, no fine-tuning, no LoRA, no RL** — out of scope by decision, not by omission (`docs/17-decisions.md`).

### Entry criteria

| Requirement | Number |
|---|---|
| Stage 0 exited and its numbers still current | `kappa_macro` DEV, `critical_recall` DEV, `kappa_intra` all recorded from the *current* commit |
| The grader prompt is versioned and hashed | `prompt_version` + `prompt_sha256` present on every registry row for EV-01 |
| Stage 2 exited | The prompt being optimised must be the one that runs in the shipping multi-agent loop |
| A frozen baseline exists | `uv run rehearsal-evals baseline --freeze EV-01` and `--freeze EV-02` on a clean tree |

### What gets built

```
src/rehearsal/optim/
├── objective.py                # metric = macro kappa on DEV, with critical_recall as a hard constraint
├── search.py                   # candidate generation + selection loop
├── candidates/                 # every prompt candidate, hashed and retained
└── report.py                   # before/after table, DEV and TEST, with intervals

prompts/grader/
├── v1.md … vN.md               # every version committed; prompts are code
└── CURRENT -> vN.md
```

**The objective is constrained, not scalar.** The optimiser maximises `kappa_macro` on DEV **subject to** `critical_recall` not falling below its gate. A candidate that improves κ by shifting errors out of the critical class is rejected by the objective function itself, not caught in review. This is principle 1 applied to optimisation: deterministic code decides what "better" means.

### The honest reporting protocol

Non-negotiable, and the reason this stage exists as its own stage rather than as a tweak inside Stage 0:

1. All search, all candidate evaluation, all selection happens on **DEV only**. `seal.py` refuses TEST access to the optimiser process entirely.
2. Exactly **one** candidate is promoted.
3. The sealed TEST split is unsealed **once**, with a written reason, and both the pre-optimisation and post-optimisation prompts are evaluated on it in the same run.
4. Both numbers are reported, with intervals, next to the human ceiling.
5. **The number of DEV iterations is reported.** An optimiser that ran 400 candidates against 25 DEV items has fitted DEV, and the TEST number is the only one that means anything. Hiding the iteration count is how prompt optimisation results become dishonest.
6. If the TEST improvement is smaller than the DEV improvement — the expected outcome — that gap is reported as the overfitting estimate, not smoothed away.

### Exit criteria

| Requirement | Gate |
|---|---|
| Before/after `kappa_macro` on sealed TEST | **Reported with bootstrap CI**, not gated on improvement |
| `critical_recall` post-optimisation | ≥ 0.90 DEV **and** ≥ baseline − 0.05; a κ gain that costs critical recall is rejected |
| `fp_rate_clean` post-optimisation | ≤ 0.15 DEV, ≤ baseline + 0.05 |
| DEV iteration count | Recorded in the registry `notes` and printed in the report |
| `TEST_ACCESS.log` | Exactly one new entry for this stage, with reason text |
| `EV-09` regression | All prior gates hold under the promoted prompt |

**A stage exit does not require the optimiser to have won.** "The optimiser produced no improvement on the sealed split" is a complete and valid exit, recorded as such, and it is a genuinely useful finding about a 25-item DEV set.

### Open risk

**25 DEV items is a small optimisation surface.** The risk is not subtle: an optimiser can memorise 25 items. The mitigations are the iteration-count disclosure, the sealed split, and the constrained objective — none of which *prevent* overfitting, they only make it visible. This limitation is stated wherever the optimised number appears.

**The optimiser is a dependency with a cost.** It is the only place a framework enters the project, and it enters **off the runtime path** — it produces a text file, and the runtime loads a text file. If it required the runtime to adopt its abstractions, it would be rejected under the no-framework decision in `docs/03-system-architecture.md` §15.

### Abandon / re-plan trigger

| Observation | Response |
|---|---|
| DEV κ improves substantially and TEST κ does not move at all | Textbook overfitting to 25 items. **Report it as the finding**, keep the pre-optimisation prompt, and state that automated optimisation is not supported at this calibration-set size. Growing the calibration set is the prerequisite, not a better optimiser |
| The optimiser cannot be constrained to respect `critical_recall` within its own objective | Do not run it. A post-hoc filter is weaker than a constrained objective, and the safety metric is not something to check after the fact |
| The optimiser requires the runtime to adopt its execution model | Out of scope. Use it offline to emit prompt text or not at all |

---

## 6. Stage 4 — The learner model and progress over time

### What becomes true

The system remembers a trainee across sessions: per-category performance, tracked with an exponentially weighted moving average, driving scenario difficulty and a next-practice recommendation. **Every recommendation shows its reason**, and the trainee can see and export their entire record.

### Entry criteria

| Requirement | Number |
|---|---|
| Stage 2 exited | Multi-scenario encounters exist; a learner model over one scenario models the scenario |
| Enough session volume to see variance | Multi-session traces from at least two distinct users across at least four scenarios, so oscillation can be observed at all |
| Scorer accuracy stable across scenarios | Per-scenario `critical_recall` spread recorded; if the scorer is uneven across scenarios, the learner model will track scenario difficulty and call it trainee skill |

That third row is the trap of this stage. A learner model is a low-pass filter over the scorer's output. Systematic scorer bias becomes an authoritative-looking trend line about a person.

### What gets built

```
src/rehearsal/learner/
├── model.py                    # LearnerModel — per-category EWMA + counts + interval
├── coach.py                    # CoachAgent, suppression rules (turn-boundary only)
└── recommend.py                # next-scenario selection, ALWAYS with a rationale string

src/rehearsal/store/projections.py   # extended: per-trainee competency projection
frontend/                            # progress view, competency-by-category, export
```

**Deterministic rules that are not the model's to decide:**

- A competency estimate with fewer than *n* observations in a category displays as "insufficient data", never as a low score. The threshold is config, defaulted conservatively.
- A category the scorer labelled "not reliably detected" (recall < 0.50 in Stage 0) **cannot** drive a recommendation. It is displayed with its unreliability marked and excluded from the selector.
- Difficulty moves at most one step per session. Whipsaw is a worse experience than slow adaptation.
- Every recommendation carries a rationale naming the specific turns it derives from; coverage of that rationale field is gated at 1.00.

### Exit criteria

| Requirement | Gate |
|---|---|
| Difficulty-oscillation rate | Below the threshold set from observed multi-session traces; the α that produces it is recorded in `docs/17-decisions.md` |
| Recommendation-rationale coverage | `= 1.00`. A recommendation without a traceable reason is not shipped |
| Unreliable-category exclusion | Test asserts no category with recall < 0.50 can be selected as a practice target |
| Export completeness | A trainee export round-trips: every session, verdict, override and audio reference, re-importable |
| `EV-08` | `session_completion_rate` holds with the coach agent enabled; coach suppression under `DegradeLevel ≥ 1` verified |

### Open risk

**A tracked score changes what the tool is.** The moment performance is longitudinal, it becomes usable as employment evidence regardless of intent. The countermeasures are architectural and stated in `docs/12-security-privacy.md`: the record is local, the trainee owns and exports it, and there is no path that transmits it. Repurposing it without consent is out of bounds and the product says so.

**EWMA α is unresolved** (`docs/03-system-architecture.md` §16, question 6). It is a real tuning knob against real human variance and it cannot be derived from first principles; it is set from observed oscillation and left configurable.

**Coach hint timing is unresolved** (question 4). Current position — turn boundaries only, suppressed under load — is proposed. Mid-encounter hints may destroy the realism the isolation architecture was built to protect: a trainee who expects a hint is not interpreting under real conditions.

### Abandon / re-plan trigger

| Observation | Response |
|---|---|
| Competency estimates are dominated by scenario variance rather than trainee variance | **Stop shipping the trend line.** Report per-scenario results only, and treat cross-scenario normalisation as an open research problem rather than a feature |
| Trainees report the score feels like surveillance | Re-plan the presentation, not the maths: default to session-local view, make longitudinal view opt-in. Consistent with `docs/12-security-privacy.md` |
| Coach hints measurably reduce completion or trainee-reported realism | Move hints to debrief only. Cheap reversal; the position was proposed for exactly this reason |

---

## 7. Stage 5 — Program-level features: trainer review, cohorts, curriculum

### What becomes true

A trainer can review a trainee's session, override any finding, and have the override recorded permanently and fed back into measurement. Cohort-level patterns are visible. Overrides become a growing second source of labels.

### Entry criteria

| Requirement | Number |
|---|---|
| Stage 4 exited | A learner record exists to review |
| Grader accuracy currently reported and current | The trainer must see the scorer's measured accuracy **before** reviewing, so review is calibrated rather than deferential |
| Consent path defined | Cohort visibility requires trainee consent recorded as an event; this is a data-model requirement, not a UI one |

### What gets built

```
src/rehearsal/api/routes_review.py   # review queue, override capture
src/rehearsal/store/events.py        # verdict.overridden event kind — permanent, never edits the original
frontend/                            # trainer review view, cohort view, curriculum assembly
src/rehearsal/evals/suites/ev08_session.py   # extended: override-rate reporting
```

**An override never mutates a verdict.** It appends a `verdict.overridden` event carrying the original verdict, the trainer's replacement, and the trainer's note. The projection shows the current state; the event log shows both. This makes the override stream usable as label data later, which is the entire strategic reason to build review properly rather than as a UI affordance.

### Exit criteria

| Requirement | Gate |
|---|---|
| `trainer_override_rate` | Inside the 0.02–0.25 investigation band, **with denominator printed**. Outside the band triggers mandatory review, not an automatic block |
| Override immutability | Test asserts the original verdict is recoverable after any number of overrides |
| Consent enforcement | Test asserts cohort views exclude any trainee without a recorded consent event |
| `EV-08` | `session_completion_rate` holds with review enabled |

**Both tails of the override band are informative and neither is good.** Near zero means the trainer is rubber-stamping — the review gate exists on paper only. Above 0.25 means the scorer is not trusted in practice, and the Stage 0 numbers do not transfer to real sessions. Either finding is more valuable than the feature.

### Open risk

**Override data is not blind and cannot be used as calibration labels without care.** A trainer overriding a displayed verdict has been anchored by that verdict. Overrides are a *signal* about scorer disagreement, not a substitute for the blind-labelled calibration set. Any future use of override data as training or optimisation input requires a blind re-labelling protocol; this is stated so it is not quietly assumed later.

**Cohort views create the strongest pull toward employment use in the whole product.** A trainer seeing a ranked cohort is one export away from a performance review. Mitigations are in `docs/12-security-privacy.md`; the roadmap's contribution is to name the pressure rather than pretend it is not there.

### Abandon / re-plan trigger

| Observation | Response |
|---|---|
| `trainer_override_rate` sits near zero across trainers | The review gate is not real. **Re-plan the review UX** to require an explicit agree/disagree per finding rather than passive acceptance |
| Override rate exceeds 0.25 with consistent disagreement in specific categories | The scorer is wrong in a way the calibration set did not capture. **Return to Stage 0** with those cases as new calibration candidates — blind-labelled by someone who has not seen the grader output |
| Cohort features are requested primarily for evaluation of staff rather than training | Do not build them. Restate the product boundary from `docs/00-dossier.md` §6 |

---

## 8. Stage 6 — Breadth: more domains, and the honest cost of a language pair

### What becomes true

The system covers more than one clinical domain, and the actual requirements for a new language pair are documented from measurement rather than assumed from the Spanish case.

### Entry criteria

| Requirement | Number |
|---|---|
| Stage 5 exited | The trainer-review path is how new-domain labels get produced |
| Seed-domain baseline frozen | Per-category `precision`/`recall` and `critical_recall` for the existing domain, frozen in `data/evals/baselines/` |
| Extractor fixture grid extended from real data | The cross-lingual normalisation risk named in Stage 0 is closed for the seed domain before it is duplicated into a new one |

### 8a. New clinical domains

Domain expansion is the cheap axis: the taxonomy, the scoring engine, the agents and the loop are unchanged. What changes is content and extractor coverage.

| Work | Where |
|---|---|
| Scenario set with clinical state graphs | `content/scenarios/<domain>/` |
| Term manifest — domain vocabulary, units, dosing forms | `src/rehearsal/content/terms.py` |
| Extractor fixture extension for domain-specific units and frequencies | `src/rehearsal/scoring/extractors/*` fixture grids |
| Domain calibration slice — **new hand-labelled items in the new domain** | `data/calibration/` |

**Exit gate:** per-domain `critical_recall` no worse than the seed domain − 0.05, measured on that domain's own calibration slice, plus `extractor_conformance = 1.00` on the extended fixture grid.

The non-obvious requirement is the last row. A domain whose numbers are only ever measured against the seed domain's calibration set is unmeasured. Adding a domain adds a labelling obligation; if the labelling capacity does not exist, the domain does not ship — it can exist as unscored practice content, explicitly marked as such.

### 8b. A new language pair — what it actually costs

A second language pair is **not** a translation task. Every layer is affected:

| Layer | What a new pair requires | Transferable from Spanish? |
|---|---|---|
| Live agent | The E4B-class model must be genuinely fluent in the language, in the clinical register, with native audio input quality in that language | **No.** Must be measured per language |
| TTS | A neural or system voice in the target locale, streamed and interruptible at the same latency | **No.** Voice availability is the binding constraint for most languages |
| Rendering provenance | `heard_verbatim` fidelity in the target language | **No.** WER must be re-measured; this is where low-resource languages fail first |
| Extractors | Number words, dosage units, frequency idioms, negation scope, laterality terms, temporal expressions — per language, each a separate implementation | **No.** This is real linguistic work, not a lookup table |
| Taxonomy | The nine error categories | **Yes.** They are properties of interpreting, not of a language |
| Scoring architecture | Neuro-symbolic split, merge logic, off-path grading | **Yes** |
| Calibration set | 40 hand-labelled turns **in the new pair**, by a labeller competent in both languages, blind, with a sealed split | **No.** This is the gating cost and it is a human cost |
| Cultural and register norms | What constitutes register shift, appropriate formality, first-person discipline conventions | **No.** Requires domain expertise in that community |

**The honest statement about indigenous languages, which is the reason this section exists.**

The population this product is grounded in — Watsonville and the Pajaro Valley — includes a substantial Mixteco- and Triqui-speaking farmworker community, and the interpreting gap there is more severe than the Spanish gap, not less. Salud Para La Gente reports access to three Mixteco interpreters across 182,186 annual visits; Watsonville Community Hospital employs none (`docs/01-research.md`).

**This architecture cannot currently serve those languages, and the reason is not effort.** The pipeline assumes, at minimum:

- A speech-capable model with genuine competence in the language. Mixteco is not one language but a group of varieties with limited mutual intelligibility; Triqui likewise. Both are tonal, and tone is lexically and grammatically contrastive — a speech pipeline that flattens tone loses meaning that carries clinical content.
- A TTS voice in the variety the patient actually speaks. These do not exist at production quality.
- Enough text and audio for the model to have learned the clinical register at all. It has not.
- A bilingual labeller who can produce a blind calibration set. The pool of people who could do this is small and is exactly the pool already overloaded with interpreting work.

**What we will not do:** ship a Mixteco mode by routing through Spanish, or by using a model with no demonstrated competence and reporting its scores as if they meant something. A confident wrong fidelity score in a language the system does not understand is worse than no product — it would tell a Mixteco-speaking health worker that their interpreting was accurate when the system has no basis for that claim, in exactly the population that has the least recourse.

**What might be honest instead** — proposed, not decided, and requiring community partnership rather than an engineering decision:

| Option | What it would require | Status |
|---|---|---|
| Terminology and concept practice without full-encounter scoring | A community-authored term set; deterministic term-presence checks only; no semantic scoring | **Proposed** |
| Human-in-the-loop recording and review, with the system as a capture and structuring tool rather than a scorer | The review path from Stage 5, with the AI scoring path disabled and labelled disabled | **Proposed** |
| Spanish↔Mixteco relay-interpreting practice, which is the actual working pattern in these clinics | Everything above, plus modelling a three-language relay | **Open** |

Each of these would be built *with* the relevant community and language experts, or not at all. None is a roadmap commitment; they are recorded so the gap is documented rather than silently omitted.

### Abandon / re-plan trigger

| Observation | Response |
|---|---|
| A new domain's `critical_recall` falls well below the seed domain and extractor work does not close it | That domain's critical content is not decidable with the current extractor set. Ship it as **unscored practice content**, marked, or not at all |
| Labelling capacity for new-domain calibration does not exist | Do not ship the domain as scored. This is a hard stop, not a trade-off |
| A candidate language pair lacks production TTS or a competent speech model | Do not ship the pair. Document the blocker with the specific missing resource named |

---

## 9. What does not change across any stage

These are invariant. A stage that would violate one is mis-planned, and the violation is the finding.

| Invariant | Where it is enforced |
|---|---|
| Deterministic code decides anything consequential; the model generates and extracts | `merge.py`, `orchestrator/`, the constrained optimisation objective |
| Counterpart agents never see the rubric or the learner model | `ContextAssembler` allowlist + `IsolationViolation` + rubric canary |
| The grader is off the critical path | `TurnScheduler`; `grader_backlog_rate ≤ 0.05` |
| No cloud inference in the core loop; nothing is transmitted | No HTTP client may be imported under `runtime/`, `scoring/` or `orchestrator/` |
| Every gated number is recorded with commit, seed, model hash, dataset hash and denominator | `evals/registry.py`, append-only, enforced by SQL triggers |
| The TEST split is sealed; access is logged with a written reason | `evals/seal.py`, `TEST_ACCESS.log` |
| No weight training, fine-tuning, LoRA or RL | Scope decision in `docs/17-decisions.md` |
| A category the scorer cannot detect reliably is labelled as such in the product | Stage 0 exit requirement, carried forward permanently |

---

## 10. Deferred with reasons

Deferral here means "not now, for a stated reason, with a named trigger that would reverse it". It does not mean "rejected" — rejections with their prices live in `docs/17-decisions.md`.

| Deferred | Reason | What would trigger reconsideration |
|---|---|---|
| **Multi-user / multi-tenant deployment** | The product is a local application. Fleet scaling is a different product with a different threat model and would compromise the local-by-architecture guarantee | A training programme with a concrete requirement for shared infrastructure **and** a privacy design that survives `docs/12-security-privacy.md` review |
| **Building our own inference server** | MLX and llama.cpp exist and are maintained. Writing one consumes the effort that should go into the scoring engine | Neither runtime can hold the required model set inside the memory envelope, measured |
| **Cloud inference, even as an option** | It would silently become the default, and the privacy guarantee would become conditional | Nothing currently identified. This is close to a rejection |
| **Fine-tuning the grader** | Out of scope by decision; also, 40 calibration items is nowhere near a training set, and fine-tuning on it destroys the anchor | Out of scope regardless of data volume — this is a project-identity decision, not a resource one |
| **Automated speech scoring of the trainee's accent, fluency or delivery** | Fidelity is the scope precisely because fidelity is checkable. Delivery scoring has no ground truth and would import exactly the failure mode this project avoids | A defensible ground-truth construction for delivery. None is known |
| **A retrieval layer / vector database in the live loop** | The scenario and term manifest are bound at session start and are small. Retrieval adds latency and non-determinism to the critical path for no measured benefit | Scenario content grows past what fits in a bound context, measured |
| **A heavyweight frontend framework** | The SPA is two views and a WebSocket. A framework would add a build surface and a dependency tree with no named pain removed | A concrete interaction requirement that vanilla JS makes genuinely worse — named, not anticipated |
| **Real-time in-encounter coaching** | It may destroy the training realism the isolation architecture protects. Turn-boundary only, suppressed under load, until measured | Trainee outcome data showing in-encounter hints help more than they distort |
| **Mobile or tablet clients** | The memory envelope is a 48 GB machine. A mobile client implies remote inference, which contradicts the local guarantee | Local models in this class running inside a mobile memory envelope |
| **Efficacy claims — that trainees improve in real interpreting** | The evals measure the *scorer*, not learning outcomes. That claim requires a study design this project has not run (`docs/08-evals.md` §9.2) | A pre-registered study with a control condition and real-encounter outcome measures. Until then, no efficacy language appears anywhere in the product |
| **Certification or credentialing positioning** | Certification is human-rated to a standard this does not claim to meet | Nothing. Stated permanently in `MODEL_CARD.md` |

---

## 11. Open research questions

Questions the roadmap does **not** answer and does not pretend to. Each is stated with what would settle it. Where a question is already tracked elsewhere with a status, it is cross-referenced rather than restated.

| # | Question | Status | What would settle it |
|---|---|---|---|
| R1 | Is `heard_verbatim` from a native-audio model a faithful transcript or a paraphrase — and does the answer differ between the trainee's L1 and L2? | **Open** (`docs/03-system-architecture.md` §16 q1) | WER against hand transcripts of calibration audio, computed separately per direction, plus grader agreement under both provenance settings on DEV |
| R2 | Does an agreement number measured on hand-authored calibration text transfer to speech-derived renderings containing disfluency, restarts and self-correction? | **Open** | Re-run EV-01 on speech-derived items labelled under the same protocol; report the delta. This is arguably the most important unanswered question in the project |
| R3 | Is the utterance-difficulty index sensitive enough to detect the leakage effect if it exists, at this sample size? | **Open** | A power analysis on the pre-registered index before Stage 2's A/B; the minimum detectable effect must be published with the result |
| R4 | Can a κ gate be derived from the human ceiling rather than borrowed from convention? | **Proposed** (`docs/08-evals.md` §1.1) | Once `kappa_intra` and ideally `kappa_inter` exist, re-derive the gate as a fixed fraction of the ceiling |
| R5 | Does one rater's application of the taxonomy generalise to the professional standard? | **Open — named gap** | A second independent blind labeller on a shared subset; `kappa_inter`. Absence is stated explicitly wherever the headline appears |
| R6 | Where is the boundary between deterministic and semantic? Are there categories currently given to the model that are actually decidable — or extractor categories that are not? | **Open** | Per-category precision/recall over the calibration set, plus error analysis on disagreements. A category the model handles better than the extractor is a finding either way |
| R7 | Does the grader benefit from seeing the term manifest slice, or does it bias it toward extractor territory and inflate agreement for the wrong reason? | **Open** (`docs/03-system-architecture.md` §16 q3) | A/B on DEV: semantic-category precision/recall with and without the manifest slice |
| R8 | Does automated prompt optimisation produce real generalisation at a 25-item DEV split, or only DEV memorisation? | **Open** | The Stage 3 protocol answers this directly; the DEV-to-TEST improvement gap *is* the answer |
| R9 | What EWMA α produces stable adaptation against real human session-to-session variance? | **Proposed** (`docs/03-system-architecture.md` §16 q6) | Difficulty-oscillation rate across real multi-session traces from multiple users |
| R10 | Do measured fidelity improvements in practice sessions correspond to any improvement in real encounters? | **Open — the efficacy question** | A study design outside this project's current scope (`docs/08-evals.md` §9.2). Until then the product claims measured practice, never improved outcomes |
| R11 | When a trainee starts interpreting before the source utterance completes, is the partial source a valid scoring source or must the turn be marked unscoreable? | **Proposed** (`docs/03-system-architecture.md` §16 q2) | Trainer judgement on recorded Stage 1 cases; spurious-omission rate on partial-source turns |
| R12 | Is trainer-override data usable as a second label source, given that the trainer was anchored by the displayed verdict? | **Open** | A blind re-labelling of a sample of overridden turns by a labeller who has not seen the grader output; agreement between blind and anchored labels |
| R13 | Are there fidelity-relevant phenomena the nine-category taxonomy does not capture — prosodic meaning, code-switching, culturally-loaded terms with no clean equivalent? | **Open** | Error analysis of turns where trainer and grader both find nothing but a trainer notes a problem in free text. Requires the Stage 5 review corpus |
| R14 | What would an honest, non-harmful product look like for a language the speech pipeline cannot serve? | **Open — requires community partnership, not engineering** | §8b options, developed with Mixteco- and Triqui-speaking community organisations and interpreters. Not a decision this project makes alone |

---

## Related documents

| Document | Relationship to this roadmap |
|---|---|
| `docs/02-layer-vertical.md` | The capability rungs; §1 maps stages to rungs |
| `docs/03-system-architecture.md` | Every module named in a stage's "what gets built" |
| `docs/06-scoring-engine.md` | The Stage 0 deliverable in full |
| `docs/07-data-and-scenarios.md` | Scenario and state-graph work in Stages 1, 2 and 6 |
| `docs/08-evals.md` | Every eval and gate cited as an exit criterion |
| `docs/12-security-privacy.md` | The constraints Stages 4–5 must not violate |
| `docs/13-deployment-ops.md` | Release gates, which are stricter than stage-exit gates |
| `docs/15-workstreams.md` | How stage work is split across parallel streams and which interfaces are frozen |
| `docs/17-decisions.md` | Rejections and their prices; §10 here covers deferrals, not rejections |
| `SETUP.md` §6 | The calibration protocol that Stage 0 executes |
| `SETUP.md` §9 | The rule that a changed number is updated in the same working session |

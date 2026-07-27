# Model Card — Rehearsal

This card describes **Rehearsal** as a *system* assembled from openly available model weights.
No model in this system is trained, fine-tuned, distilled or adapted by this project. What is
engineered here is the orchestration, the prompting, the deterministic scoring code, and the
evaluation apparatus. This card therefore documents *configuration, composition and measured
behaviour* rather than a training run.

Card scope: the whole runtime system (conversational agents, deterministic extractors, grader,
TTS, orchestration). Component-level detail lives in the documents cross-referenced throughout;
this card does not duplicate them.

| Field | Value |
|---|---|
| System name | Rehearsal |
| System type | Real-time voice training and formative assessment for medical interpreters |
| Card version | `MODEL_CARD.md` v1, tracks the `system.version` string emitted in every score record |
| Owner | Rehearsal engineering (see **How to report a problem**) |
| Weights trained by this project | None |
| Inference location | Entirely local (Apple Silicon via MLX; llama.cpp portable fallback) |
| Primary language pair | English (en-US) ↔ Spanish (es-MX) |
| Status | Active development; every claim below is either **measured**, **decided**, or **open** and is labelled |

---

## 1. System overview

A trainee stands in the middle of a simulated clinical encounter. An AI clinician speaks English;
an AI patient speaks Spanish; the trainee interprets aloud in both directions. Because the system
*generated* the source utterance, it knows exactly what was said — scoring is a comparison of a
known source against the trainee's rendering, not an open-ended quality judgement. This is the
**ground truth by construction** property and it is what makes the assessment defensible.

Scoring is **neuro-symbolic**. Deterministic Python extractors hard-check the provably decidable,
clinically consequential facts — numbers, dosages, frequencies, negation, laterality, allergies,
temporal markers. A language model handles only the semantic residue: register, idiom, pragmatic
force, first-person discipline. The model generates and extracts; deterministic code decides
anything consequential; the human — trainee and reviewing trainer — decides ultimately.

The clinician and patient agents **never see the scoring rubric or the learner model**. Leaking
either would cause them to speak in easy-to-interpret ways and destroy training realism. This
information isolation is the load-bearing reason the architecture is multi-agent, and it is
verified by a leakage A/B test rather than asserted (see `docs/08-evals.md`).

The grader runs **off the conversational critical path**: it scores turn *n* while the trainee is
still speaking turn *n+1*. The human's own speaking time is the latency budget.

Architecture detail: `docs/03-system-architecture.md`. Capability layering: `docs/02-layer-vertical.md`.

---

## 2. Models used and their roles

> **No model weights are trained, fine-tuned, quantisation-aware-trained, LoRA-adapted, RLHF'd,
> or otherwise modified by this project.** Weights are used as published. The only things this
> project authors are configuration (sampling parameters, seeds, context assembly), prompts
> (version-controlled as code), deterministic scoring code, and — at L10 — *prompt-level*
> optimisation that changes prompt text only. Model training, fine-tuning, RL and adapters are
> explicit, deliberate out-of-scope exclusions; the project's credibility rests on being
> reproducible from open weights plus inspectable text, not on private weights nobody can audit.

| Role | Model class | Precision | Sees | Never sees | On critical path |
|---|---|---|---|---|---|
| Clinician agent | Gemma 4 E4B class, native audio input | Quantised (4-bit class) | Case brief, clinical state node, dialogue history | Rubric, error taxonomy, learner model, grader output | Yes |
| Patient agent | Gemma 4 E4B class, native audio input | Quantised (4-bit class) | Persona sheet, symptom script, dialogue history | Rubric, error taxonomy, learner model, grader output | Yes |
| Fidelity grader | Gemma 12B class | Quantised (4-bit class) | Known source utterance, trainee rendering transcript, extractor findings, rubric | Learner identity, prior scores (per-turn scoring is stateless by design) | **No** |
| Coach | Gemma 12B class (shared weights with grader, separate context) | Quantised | Completed score records for the session | Live dialogue in progress | No |
| TTS (en-US, es-MX) | Local neural voices, system voices as fallback | n/a | Agent utterance text | Everything else | Yes (streamed, interruptible) |
| Deterministic extractors | **Not a model.** Python 3.12 | n/a | Source + rendering text | n/a | No |

Notes that matter operationally:

- **Native audio input, no ASR stage in the critical path.** The trainee's speech goes directly
  into the conversational model. There is no separate speech-recognition component to blame or
  tune; its failure modes are folded into the model's and are discussed under **Bias**.
- **The grader is a larger model precisely because it is off the critical path.** Latency there is
  paid out of human speaking time, so the quality/latency trade runs the opposite way from the
  agents.
- **Two model sizes only.** Adding a third tier is not justified by any measurement to date.
- Target resident memory: **~20–24 GB** on a 48 GB machine, all models co-resident. Exceeding this
  causes swap and destroys the latency budget; it is a hard configuration constraint, not a goal.
- **No cloud inference in the core loop**, ever. This is a privacy guarantee, not a preference.
- **No agent framework.** Hand-rolled typed orchestration. Reproducibility, seed control and
  inspectable failure points are the product's credibility; a framework hides exactly what must
  stay visible.

### Determinism and reproducibility

| Knob | Default | Why |
|---|---|---|
| Grader temperature | `0.0` | Scores must be as reproducible as the runtime allows |
| Grader seed | Fixed per release, recorded in the score record | Enables replay of any score |
| Agent temperature | Non-zero (persona liveness) | Realism requires variation; agents are not scored artefacts |
| Extractor behaviour | Fully deterministic | Same input → byte-identical output, always |

Even at temperature 0, quantised local inference is not bit-reproducible across runtimes,
hardware and batch shapes. Run-to-run score variation is therefore **measured and reported**, not
assumed away — see **Limitations**.

---

## 3. Intended use

Rehearsal is built for **practice and formative assessment**.

**Intended users**

- Medical interpreters in training, and working interpreters maintaining skill.
- Bilingual community health workers / promotoras who interpret as part of their role.
- Interpreter training programs, for structured practice and for trainer-reviewed feedback.
- Safety-net clinics that employ or contract these staff, for internal skill development.

Geographic grounding: Santa Cruz County, California — Watsonville and the Pajaro Valley, whose
Spanish-speaking and indigenous-language farmworker population is served by safety-net clinics.
The system is designed against that context first.

**Intended uses**

| Use | Supported |
|---|---|
| Unlimited private practice against a documented error taxonomy | Yes |
| Per-turn feedback showing what meaning survived, was omitted, added or distorted | Yes |
| Trainer review of a completed session, with override authority over every score | Yes |
| Cohort-level formative signal for a training program (where is the class weak?) | Yes, with the human ceiling reported alongside |
| Self-assessment before pursuing a real credential | Yes, as preparation only |

The design intent is that **the AI drafts; the human decides.** Every score is a draft finding
presented to a human who can and should override it. Trainer-override rate is itself a tracked
eval number, not an embarrassment.

---

## 4. Out-of-scope and prohibited uses

These are firm. They constrain the product's design, not just its terms of use.

| Use | Status | Why |
|---|---|---|
| **Certification or credentialing instrument on its own** | **Prohibited** | Professional interpreter certification requires validated psychometrics, secure proctoring and a defensible standard-setting process. Rehearsal has none of these and makes no claim to them. There is no evidence that Rehearsal scores predict certification outcomes. |
| **Employment decisions** — hiring, firing, promotion, pay, scheduling — or **disciplinary action**, without the interpreter's informed, specific, revocable consent | **Prohibited** | Scores carry measurement error that is largest exactly where employment stakes are highest (register, pragmatics, accented or regionally-varied speech). Using them as an unconsented adverse-action input converts a practice tool into a surveillance instrument. |
| **Substitute for a qualified interpreter in real patient care** | **Prohibited** | Rehearsal does not interpret. It simulates and scores. It has no role at the bedside, on a call, or in any live encounter with a real patient. |
| **Any use with real patient data** — real PHI, real recordings of real encounters, real chart content | **Prohibited** | All cases are synthetic by construction. The system has no PHI handling, no HIPAA-covered posture, no BAA, and no audit trail designed for regulated data. Introducing real patient data breaks every privacy assumption in `docs/03-system-architecture.md`. |
| Assessment in a language pair the system does not support | Out of scope | Only en-US ↔ es-MX is built and evaluated. See **Limitations**. |
| Assessment of indigenous-language interpreting (Mixteco, Triqui, and others) | Out of scope, named gap | The population most in need is currently unserved. See **Bias and fairness**. |
| General-purpose translation, chat, medical advice, or clinical decision support | Out of scope | Not built for it, not evaluated for it, and the agents are personas, not clinicians. |
| Multi-tenant fleet deployment / horizontal scaling as a service | Deliberately out of scope | The system is single-machine, local-first by design. |

If a program intends to use Rehearsal output in *any* consequential decision about a person, the
requirement is: **explicit consent, human review of every score used, disclosure of the human
ceiling and the measured agreement figure, and a documented appeal path.** Anything less
misrepresents what the number is.

---

## 5. Inputs and outputs

### Inputs

| Input | Source | Form | Retention |
|---|---|---|---|
| Trainee speech | Microphone | Streamed audio directly into the conversational model | Content-addressed blob in local SQLite; deletable per session |
| Session/case selection | Trainee | Case id + difficulty parameters | Local SQLite |
| Case brief, persona sheet, clinical state graph | Repository, versioned | Structured YAML/JSON authored content, fully synthetic | In-repo |
| Trainer overrides and comments | Reviewing trainer | Structured edits attached to score records | Local SQLite |

**Never an input:** real patient records, real clinical audio, identifiable third-party data, or
anything transmitted off the machine.

### Outputs

Per interpreted turn, the system emits one score record. Shape (authoritative definition lives with
the scorer — see `docs/06-scoring-engine.md`; reproduced here only so this card is actionable):

```jsonc
{
  "turn_id": "s_01H…:t_014",
  "session_id": "s_01H…",
  "direction": "en_to_es",              // or "es_to_en"
  "source_utterance": "Take one tablet twice a day for ten days.",
  "rendering_transcript": "Tome una pastilla al día por diez días.",
  "findings": [
    {
      "type": "omission",               // taxonomy value, see table below
      "span": { "start": 18, "end": 29, "text": "twice a day" },
      "severity": "critical",           // "critical" | "non_critical"
      "decided_by": "extractor",        // "extractor" | "model"
      "extractor": "frequency_v3",      // present iff decided_by == "extractor"
      "confidence": null,               // null for deterministic findings
      "note": "Dosing frequency dropped; rendering implies once daily."
    }
  ],
  "critical_error_count": 1,
  "human_review": {
    "status": "pending",                // "pending" | "confirmed" | "overridden"
    "reviewer_id": null,
    "overrides": []
  },
  "provenance": {
    "system_version": "…",
    "grader_model": "…",
    "grader_prompt_version": "…",
    "grader_seed": 20260101,
    "extractor_versions": { "frequency": "v3", "negation": "v2", "…": "…" }
  }
}
```

**Error taxonomy** — an operationalisation drawn from the interpreting research literature
(Flores et al.; Vasquez & Javier, 1991) and aligned to NCIHC Standards of Practice 1, 2, 5–6, 12
and 16–18. It is **not** a single codified professional standard: no authoritative publication
defines this category set as one unit, no public inter-rater-calibrated severity rubric exists, and
NCIHC contains no explicit first-person requirement, so `first_person_violation` encodes
professional convention rather than a written standard (see `docs/01-research.md` §8.1).
Every finding carries exactly one type, one span, one severity, one note:

| Type | Decided primarily by | Typical severity driver |
|---|---|---|
| `omission` | Extractor when the dropped item is numeric/negation/laterality/allergy/temporal; model otherwise | Critical if the dropped item could change clinical action |
| `addition` | Model, extractor for spurious numerics | Critical if it introduces a clinical fact |
| `substitution` | Extractor for numerics and named entities; model otherwise | Critical for dosage/drug/allergy substitution |
| `distortion` (incl. negation flips) | Extractor for negation and laterality; model otherwise | Negation flips are always critical |
| `editorialization` | Model | Usually non-critical |
| `role_exchange` | Model | Usually non-critical, escalates if advice is given |
| `register_shift` | Model | Non-critical |
| `false_fluency` | Model | Non-critical unless it fabricates a fact |
| `first_person_violation` | Model | Non-critical |

**Severity rule is deterministic, not modelled.** `critical` means *could change clinical action*:
dosage, frequency, allergy, negation, laterality, symptom onset. The model may propose a finding;
deterministic code assigns its severity from the class of the affected content. A model is never
permitted to downgrade a critical finding.

Session-level outputs: a per-turn timeline, aggregate rates by taxonomy type, a critical-error
count, and a coach summary — all presented as **draft, pending human confirmation**.

---

## 6. Performance — how quality is measured

Full protocol, splits and reported figures live in `docs/08-evals.md`. This section states what is
measured, what is reported, and the reporting rules.

### The external anchor

**The calibration set**: 40 interpreting turns, hand-labelled by a human against the professional
error taxonomy, split **DEV 25 / TEST 15 with the test split SEALED** — never used for prompt
optimisation, prompt selection, extractor tuning or any other fitting. Labelled blind. It
deliberately includes clean items (to measure false alarms), critical-error items, non-critical
items, multi-error items, and ambiguous items that establish the honest human ceiling. Intra-rater
and, where available, inter-rater agreement are computed on the same items. The full protocol is
**SETUP.md section 6**; it is not duplicated here.

### Per-layer eval numbers

Every architectural layer ships its own number. Design arguments are settled with measurements,
never with philosophy.

| Layer | What it is | Eval number |
|---|---|---|
| L4 | Neuro-symbolic fidelity scorer | Cohen's kappa vs human labels |
| L5 | Counterpart agent on a clinical state machine | Persona-consistency rate, deterministically checkable against the state graph |
| L6 | Session protocol / rubric / taxonomy as a portable versioned skill | A/B task-correctness delta, with vs without the skill |
| L7 | Full session orchestration with human gates | End-to-end completion rate + trainer-override rate |
| L8 | Multi-agent with information isolation | Leakage A/B: induced error rate when the counterpart can vs cannot see the rubric |
| L10 | Prompt-level optimiser against the calibration set | Before/after agreement, reported on the **sealed** test split |

### Reporting rules (binding)

1. **The human ceiling is reported alongside every grader agreement figure, always.** A kappa
   presented without the intra-/inter-rater agreement on the same items is an incomplete and
   misleading number. No exception.
2. **Rates and distributions, with stated uncertainty** — never a single decimal implying
   precision the sample size cannot support. n=15 on a sealed split is a small sample and is
   described as one.
3. **Critical-error recall and false-alarm rate on clean items are reported separately** from
   overall agreement. An overall figure can hide the only failure mode that matters clinically.
4. **Deterministic extractor performance is reported separately from model performance.**
   Blending them flatters the model.
5. **Sealed means sealed.** A TEST-split number is reported once per release candidate. If it is
   used to choose between configurations, it is no longer a test split and must be re-sealed with
   fresh items.
6. **Named gaps are stated, never papered over.** Every limitation in section 7 appears in any
   external report of performance.

---

## 7. Limitations

Stated as **measured**, **expected but unmeasured**, or **open**.

**Language coverage — decided constraint.** English ↔ Spanish only, targeting en-US and es-MX.
No other pair is built, prompted, or evaluated. Using the system on another pair produces output
that looks identical in structure and is entirely unvalidated.

**Dialect and regional variation — expected, partially measured.** The patient persona and TTS
target Mexican Spanish. Caribbean, Central American, Andean and Peninsular varieties, and the
Spanish of the Pajaro Valley specifically (which is not textbook es-MX), are under-represented in
both the agent voice and the grader's notion of "correct". A legitimate regional rendering can be
scored as a substitution or register shift. Detection approach in **Bias**.

**Register and pragmatics scoring is materially weaker than numeric and negation fidelity —
measured, and structural.** This is not a defect to be prompted away; it is the honest shape of
the problem. Numbers, dosages, frequencies, negation, laterality, allergies and temporal markers
are provably decidable and handled by deterministic code with near-ceiling reliability. Register
shift, idiom, pragmatic force and first-person discipline are judgement calls where human
annotators themselves disagree — the ceiling is lower and the grader is further below it. Agreement
is therefore reported **per taxonomy type**, and consumers should weight the semantic-residue
categories accordingly.

**Stochastic variation between runs — measured, reported as a distribution.** The trainee is human
and the agents are sampled, so no two sessions are comparable turn-for-turn. Even the grader at
temperature 0 is not bit-reproducible across runtimes and hardware. Repeat-run variance on the DEV
split is measured and reported; a single session's score is a noisy observation, not a
measurement of a person.

**No evidence that scores predict real-world performance — open, and the most important
limitation on this card.** There is no validity study linking Rehearsal scores to on-the-job
interpreting quality, patient outcomes, or certification results. The underlying evidence base is
that untrained and ad-hoc interpreters produce materially more consequence-bearing errors than
trained professionals, and that practice against a real standard is scarce — that motivates the
product; it does not validate its scores. Anyone treating a Rehearsal score as a predictor of
professional competence is making a claim this project does not support.

**Audio-condition sensitivity — expected, unmeasured.** Microphone quality, room noise, overlapping
speech and clipping degrade the conversational models' understanding of the trainee. Because
audio goes natively into the model, this degradation surfaces as scoring error rather than as an
obvious transcription failure. Open: a signal-quality gate that refuses to score turns below a
threshold rather than scoring them badly.

**Simulation is not a clinic.** No interruptions from a third party, no phone handoffs, no
distressed family member, no equipment failure, no ambient chaos. Skill demonstrated here is
necessary, not sufficient.

**Coverage of the taxonomy is uneven.** Rare types (`role_exchange`, `false_fluency`) have few
calibration items and correspondingly wide uncertainty on their agreement figures.

---

## 8. Bias and fairness considerations

The fairness risks here are concrete and mostly concern **who gets understood**.

| Risk | Mechanism | What is done |
|---|---|---|
| **Accent bias in speech understanding** | The conversational models take trainee audio natively. Speech models generally understand some accents better than others; heritage speakers, indigenous-language-first Spanish speakers, and strongly accented English speakers are the likely losers. A misunderstood rendering becomes a false omission or substitution finding. | Error rates are stratified by self-reported speaker background on any evaluation where that data is voluntarily provided; stratified figures are reported, never only the pooled figure. A refusal-to-score path for low-confidence audio is **open**. |
| **Penalising legitimate regional variation** | The grader's implicit "correct Spanish" skews es-MX and formal register. Regionally valid lexical choices (*chamarra*/*chaqueta*, *pastilla*/*comprimido*, voseo, local idiom) can be scored as substitution or register shift. | Calibration items deliberately include regional-variant renderings labelled as **correct**; false-alarm rate on those items is tracked as a first-class metric. Extractors are variant-tolerant by construction (they match on the *value*, not the word form). |
| **Indigenous-language speakers unserved** | Mixteco and Triqui speakers in the Pajaro Valley are a large share of the population with the greatest interpreting need, and the pipeline serves none of them. Relay interpreting (Mixteco→Spanish→English) is the real-world pattern and is not modelled at all. | Stated as a **named gap**, not a roadmap promise. No claim of coverage is made anywhere in the product. Open: whether relay-interpreting simulation is tractable with available open weights at all — currently unknown, and the honest answer is that it may not be. |
| **Register scoring encoding class assumptions** | "Appropriate register" carries class and education assumptions that can systematically disadvantage promotoras who interpret effectively in a community voice. | Register findings are always non-critical, are never allowed to drive a critical-error count, and are the category where trainer override is most expected. Override rates on register findings are tracked precisely because a high rate is evidence the rubric is wrong, not the trainee. |
| **Small calibration set from a single labeller** | 40 items labelled by one human encodes that human's judgement, including their dialect assumptions. | The single-labeller dependency is disclosed with every reported figure. Inter-rater agreement with a second labeller is the highest-value improvement available and is stated as such. |

Fairness posture in one line: **the failure mode we most fear is the system telling a competent
bilingual community health worker that her Spanish is wrong.** Every design choice above — critical
severity restricted to decidable facts, deterministic severity assignment, register capped at
non-critical, human override always winning — exists to make that failure recoverable.

---

## 9. Safety and refusal behaviour

| Situation | Behaviour |
|---|---|
| Trainee asks the clinician or patient agent for real medical advice | Agents stay in persona and do not step out to advise. Personas are simulation artefacts; they hold no clinical authority and the UI labels them as simulated at all times. |
| A session touches distressing clinical content (abuse disclosure, terminal diagnosis, pregnancy loss) | Cases containing such content are flagged in the case brief and surfaced before the session starts, so the trainee consents to the scenario. An always-available end-session control stops audio immediately. |
| Trainee attempts to use the system to interpret a real encounter in progress | Not detectable by the system. Mitigation is documentation and product framing only. Stated honestly as a limitation of the control, not a control. |
| Grader produces a finding it cannot ground in a span | The finding is dropped by deterministic post-processing. Every finding must carry a span that exists in the rendering; ungrounded findings are a known model failure mode and are filtered structurally rather than begged away in the prompt. |
| Grader output fails schema validation | Rejected, one bounded retry, then the turn is marked `unscored` with a reason. **A malformed score is never coerced into a valid-looking one.** |
| Model attempts to assign or alter severity | Ignored. Severity is computed by deterministic code from the affected content class. |
| Audio quality below usable threshold | **Open** — currently the turn is scored anyway, which is the wrong behaviour. Refusing to score is the intended fix. |

There is no content-moderation layer beyond the above, because the content is authored synthetic
clinical dialogue and the trainee's own speech, held locally. Adding one is not justified by any
observed failure.

---

## 10. Privacy

Privacy is a property of the architecture, not a policy statement.

- **All inference is local.** No cloud calls in the core loop. Trainee audio never leaves the
  machine.
- **Storage** is a local SQLite database with content-addressed audio blobs. Nothing is
  synchronised, uploaded, or telemetered by default.
- **Trainee audio is deletable per session**, and deleting a session removes its blobs. Because
  blobs are content-addressed, a blob referenced by no remaining session is garbage-collected.
- **No real patient data, ever.** All cases are synthetic. The system has no PHI handling, no BAA,
  no HIPAA-covered posture. This is stated as a prohibition in section 4 because the architecture
  is not built to protect data it was never designed to receive.
- **Trainer access is explicit.** A trainer sees a session because the trainee shared it. There is
  no ambient supervisory view.
- **Learner model isolation.** The conversational agents never receive the learner model — for
  training-realism reasons (section 1), but the effect is also that trainee performance history
  never enters an agent context.
- **Evaluation data.** Calibration items are authored synthetic turns. If any real trainee session
  is ever used in evaluation, it requires that trainee's explicit, specific, revocable consent, and
  the consent record travels with the item.

---

## 11. Maintenance and version policy

Anything that can change a score is versioned and recorded in every score record's `provenance`
block. A score without provenance is not a valid score.

| Artefact | Versioning | Change triggers |
|---|---|---|
| Grader prompt | Semantic version, in-repo, diffed and reviewed like code — never edited in a dashboard | Any text change, including whitespace |
| Deterministic extractors | Per-extractor version (`negation_v2`, `frequency_v3`) | Any behaviour change |
| Error taxonomy / rubric | Versioned as the L6 packaged skill definition | Any category, severity-rule or definition change |
| Model identity + quantisation | Recorded exactly (weights id, quantisation, runtime) | Any weights or runtime swap |
| Sampling config + seed | Recorded per record | Any change |
| Calibration set | Versioned; items append-only, labels amend-only with a logged reason | Any item or label change |

**Release gate.** No release that changes the grader prompt, an extractor, the taxonomy, or the
model set ships without: DEV-split agreement re-measured, per-taxonomy-type breakdown,
false-alarm rate on clean items, and the human ceiling reported alongside. The sealed TEST split is
read **once** for the release candidate.

**Re-baselining.** Changing models or quantisation invalidates prior agreement figures. They are
re-measured, not carried forward, and the card's reported numbers are updated in the same change.

**Breaking-change policy.** A taxonomy or severity-rule change makes historical scores
non-comparable. Such a change bumps a major version and historical records keep their original
version — old scores are never silently re-interpreted under new rules.

**Deprecation.** A retired extractor or prompt version stays resolvable in the repo so any archived
score record can be explained after the fact.

---

## 12. How to report a problem

Report anything that looks like a wrong score, an unfair score, a privacy concern, or a claim in
this card that the system does not honour.

**What to include** — this is the difference between a report we can act on and one we cannot:

1. `session_id` and `turn_id` from the score record (visible in the turn detail view).
2. The full `provenance` block (copyable from the same view) — model, prompt version, extractor
   versions, seed.
3. The `source_utterance` and the `rendering_transcript` as recorded.
4. What the score said, and what you believe the correct finding is — including "no finding".
5. For dialect or accent issues: the variety involved, and whether the rendering is correct in
   that variety. These reports are the highest-value input the project receives and are treated as
   candidate calibration items.
6. Whether audio may have been a factor (noise, mic, overlapping speech).

**Where to send it** — file an issue in the project repository. Reports that include a session
record should attach the exported score record, **not** raw audio; audio is only requested if
needed and only with explicit consent.

**Severity handling**

| Report class | Handling |
|---|---|
| A critical-severity finding was wrong in either direction (missed or fabricated) | Highest priority. Triaged against the extractor responsible; a reproducing case is added to the DEV split. |
| Legitimate regional variation penalised | High priority. Becomes a labelled correct-variant calibration item. |
| Register/pragmatics disagreement | Expected and useful. Aggregated; clusters indicate the rubric needs revision. |
| Privacy concern — anything suggesting data left the machine | Treated as a defect against a core architectural guarantee and investigated before feature work. |
| Claim in this card not honoured by the system | The card is wrong or the system is; either way it is a defect. |

Trainers: a **high override rate is a signal about the system, not about your trainees.** Report
it. Override rate is a tracked eval number (`docs/08-evals.md`, L7) and a rising one is how we
learn the rubric or the grader has drifted.

---

### Cross-references

`SETUP.md` (section 6: calibration-set protocol) · `docs/02-layer-vertical.md` ·
`docs/03-system-architecture.md` · `docs/06-scoring-engine.md` · `docs/08-evals.md` ·
`docs/09-ui-ux.md` · `docs/18-glossary.md`

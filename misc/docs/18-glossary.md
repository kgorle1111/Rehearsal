# 18 — Glossary

Rehearsal spans three vocabularies that do not normally share a room: professional **interpreting**, **clinical** communication, and **AI/software engineering**. The same word can mean three different things depending on who is reading. `register` is a linguistic property to an interpreter trainer, a CPU concept to an engineer, and a verb to a clinic administrator. `finding` is a clinical observation to a nurse and a typed dataclass to us.

This document is the single authority on how each term is used **in this project's documentation and code**. Where our usage is narrower, stricter, or simply different from the term's ordinary meaning, the entry says so under **In Rehearsal**.

**How to read the entries**

| Marker | Meaning |
| --- | --- |
| **In Rehearsal:** | This system's specific, binding meaning. When it conflicts with common usage, this wins inside this repository. |
| `code identifier` | The term has a literal representation in code — a field, a type, a table column, a CLI flag. The identifier given is the real one. |
| [decided] / [proposed] / [open] | Status of a definition that encodes a design choice, matching the convention in `docs/17-decisions.md`. |

**Scope note.** This is a vocabulary reference, not a specification. Where an entry names a mechanism, the mechanism itself is specified elsewhere and cross-referenced — see `docs/03-system-architecture.md` for the component map, `docs/06-scoring-engine.md` for scoring internals, `docs/07-data-and-scenarios.md` for the scenario and calibration data, `docs/08-evals.md` for every eval number, and `SETUP.md` section 6 for the calibration-set labelling protocol. Definitions here never restate those documents; they tell you what the words mean so those documents are readable.

---

## Section A — Interpreting and language-access terms

Terms from the professional practice this system trains and measures. Where a term is defined by published standards of practice, the entry reflects that professional meaning first, then any narrowing this system applies.

### ad hoc interpreter

An untrained bilingual person pressed into interpreting — a family member, a bilingual staff member pulled from another job, a bystander, or a child. The peer-reviewed evidence base summarised in `docs/01-research.md` is that ad hoc interpreters produce materially more errors of potential clinical consequence than trained professionals, which is the empirical premise of this entire product.

**In Rehearsal:** never a role the system simulates. Rehearsal trains the trainee *out of* ad hoc practice; the counterpart agents are always clinician and patient, never a third bilingual party.

### addition

An error category: the trainee's rendering introduces content the source utterance did not contain. Severity turns on what was added — an added dosage, an added reassurance, or an added clinical instruction is `critical`; an added discourse particle is not.

**In Rehearsal:** `kind = "addition"` in `ErrorKind`. Distinguished from **editorialization** by intent: an addition inserts *content*, editorialization inserts the interpreter's *opinion or gloss*. Distinguished from **false fluency** by fabrication: an addition may be plausible filler; false fluency invents a rendering for something the interpreter did not understand.

### certification

Formal credentialing of a medical interpreter by a national certifying body, following training hours, a written examination and an oral performance examination.

**In Rehearsal:** explicitly **not** conferred, simulated, or predicted. Rehearsal produces formative practice scores. No score, badge, streak or report in this product is a credential or a proxy for one, and the product surfaces say so — see `docs/00-dossier.md` for the non-goals table and `docs/12-security-privacy.md` for the prohibition on repurposing scores as employment evidence.

### consecutive interpreting

The interpreter waits for the speaker to finish a segment, then renders it. Segments in healthcare are typically one to several sentences; the interpreter may take notes and may ask the speaker to pause.

**In Rehearsal:** the **default and only fully supported mode** [decided]. Consecutive turn boundaries are what make ground truth by construction clean: one source utterance in, one rendering out, one scored unit. The turn taking is enforced by the orchestrator, not by politeness — see `docs/03-system-architecture.md`.

### distortion

An error category: content is present but its meaning is altered. The clinically dangerous subtype is the **negation flip** — "you should *not* take this with alcohol" rendered without the negative, or an affirmative rendered as a negative.

**In Rehearsal:** `kind = "distortion"`. Negation flips, laterality swaps (left/right) and dosage-magnitude changes are detected by deterministic extractors, not by the language model, because they are provably decidable from the known source. See **neuro-symbolic** in Section C.

### editorialization

The interpreter adds their own commentary, opinion, softening, or explanation that neither party said — "he's just saying that because he's nervous", or smoothing a blunt prognosis into something kinder.

**In Rehearsal:** `kind = "editorialization"`. Judged by the model side of the scorer, not by an extractor, because recognising it requires reading pragmatic intent rather than checking a token. Frequently co-occurs with **register shift** and **role exchange**; the scorer may emit all three as separate findings on overlapping spans, and does not collapse them.

### false fluency

The interpreter renders something confidently that they did not actually understand, producing smooth, plausible target-language speech that does not correspond to the source. The professional hazard is that it is invisible to both parties: everyone hears fluent speech and assumes accuracy.

**In Rehearsal:** `kind = "false_fluency"`. This is the category with the closest analogue in our own machinery — it is the human version of model hallucination, and it is the category the system is best positioned to catch, because it holds the source text and the rendering side by side.

### fidelity

The degree to which an interpretation preserves the meaning, content, register and force of the source utterance. Professional standards frame fidelity as completeness and accuracy, not word-for-word literalness.

**In Rehearsal:** the single quantity the product measures, and the reason "compare known source to rendering" replaces "judge quality" as the problem statement. Fidelity here is **operationalised as the set of findings against a known source**, not as a holistic impression score. A session's fidelity summary is derived from findings by deterministic code — the model never emits an overall score.

### first-person interpreting

Standard professional practice: the interpreter speaks in the first person of whoever they are rendering. The clinician says "How long have you had the pain?" and the interpreter says "¿Cuánto tiempo hace que tiene el dolor?" — not "The doctor asks how long you have had the pain."

**In Rehearsal:** violations are `kind = "first_person_violation"`. Detection is hybrid: third-person reporting frames ("el doctor dice que", "she says that", "he wants to know") are matched by a deterministic pattern extractor; ambiguous cases go to the model. Habitual first-person discipline is one of the skills the coach agent tracks across sessions.

### language access

The body of law, policy and practice governing meaningful access to services for people who do not speak the dominant language — in US healthcare, the obligation on federally funded providers to provide competent language assistance at no cost to the patient.

**In Rehearsal:** context, not a feature. Rehearsal is a training tool, not a compliance or reporting system; it makes no claim about a clinic's language-access obligations and produces no compliance artefacts.

### LEP (limited English proficiency)

The standard US administrative term for a person who does not speak English as a primary language and has a limited ability to read, speak, write or understand English.

**In Rehearsal:** used only when quoting or citing sources in `docs/01-research.md`. Product-facing copy in `docs/09-ui-ux.md` and `docs/10-frontend-spec.md` prefers concrete phrasing ("Spanish-speaking patients") over the administrative label. Note that the term is about the *encounter*, not the person's competence, and it does not cover the indigenous-language speakers (Mixteco, Triqui) present in the Pajaro Valley population — for whom Spanish is itself a second language and a Spanish interpreter is not full access.

### omission

An error category: content present in the source is absent from the rendering. The most common error category in the literature and often the most consequential, because nothing in the encounter signals that something went missing.

**In Rehearsal:** `kind = "omission"`. The one category where `span` refers to the **source**, not the rendering — there is no rendering text to point at. In the `Finding` record this appears as `span = None` with `source_span` set; consumers must handle that shape. See the schema in `docs/06-scoring-engine.md`.

### promotora / community health worker

A trusted frontline health worker from the community they serve, usually bilingual and bicultural, who does outreach, education, navigation and informal interpreting. *Promotora* is the term used in Spanish-speaking communities, including the farmworker communities of Watsonville and the Pajaro Valley.

**In Rehearsal:** a first-class user, not an edge case. Promotoras typically interpret regularly without formal interpreter training, which places them exactly at the risk profile the research identifies. Product language never implies they are unqualified — the framing is measured practice, not remediation.

### register

The level of formality, technicality and social positioning of language. A clinician's "hypertension" and a patient's "la presión alta" are the same referent at different registers, and choosing between them is a professional judgement, not an error by default.

**In Rehearsal:** `kind = "register_shift"` fires when the rendering moves register in a way that changes what the listener can do with the utterance — rendering plain-language patient speech into clinical jargon the patient could not have produced, or flattening a clinician's careful hedging into blunt certainty. **Not** a synonym for "wrong word choice", and never `critical` on its own. This is model-judged territory; extractors do not attempt it.

### role exchange

The interpreter steps out of the interpreting role and becomes a participant — answering the clinician's question on the patient's behalf, asking their own follow-up questions, or explaining medical content directly.

**In Rehearsal:** `kind = "role_exchange"`. Deliberately provoked by some scenarios: a patient agent who answers vaguely, or a clinician agent who addresses the interpreter directly ("does she understand?"), creates the pressure that produces the error. Provocations are properties of the clinical state graph and are recorded as scenario difficulty features — see `docs/07-data-and-scenarios.md`.

### sight translation

Reading a document written in one language aloud in another — a discharge instruction, a consent form, a medication label.

**In Rehearsal:** **out of scope for the live loop** [decided]. It requires a document surface and a different turn model. Noted here because it appears in the professional standards this taxonomy is drawn from, and because omitting it is a deliberate scope decision rather than an oversight. Listed as a candidate extension in `docs/16-roadmap.md`.

### simultaneous interpreting

The interpreter renders while the speaker is still speaking, lagging by a few seconds. Standard in conference settings; used in healthcare mainly for one-way stretches such as a clinician's extended explanation.

**In Rehearsal:** **not supported in the core loop** [decided], and the reason is architectural rather than aspirational. Simultaneous interpreting destroys the clean turn boundary that ground truth by construction depends on, and it removes the trainee's speaking time that the grader's latency budget is built from (see **off-critical-path**). Supporting it would require a different scoring unit, not a bigger model.

### standards of practice

The published professional codes defining what a medical interpreter must and must not do — accuracy, confidentiality, impartiality, role boundaries, cultural mediation, professional development.

**In Rehearsal:** the error taxonomy is derived from these standards rather than invented, which is what makes a finding arguable against an external reference instead of against our opinion. Specific standards, editions and the mapping from each standard to each `ErrorKind` are documented in `docs/06-scoring-engine.md`; they are not restated here.

### substitution

An error category: source content is replaced by different content — a wrong drug name, a wrong body part, a wrong time reference, a wrong relative.

**In Rehearsal:** `kind = "substitution"`. Overlaps conceptually with distortion; the operational rule the labelling protocol uses is that substitution swaps a **discrete item** (this drug for that drug), while distortion alters the **meaning of the utterance** (the negation, the certainty, the direction). Borderline cases are exactly the material the deliberately ambiguous calibration items are made of.

### triadic encounter

The three-party clinical conversation — clinician, patient, interpreter — with its own dynamics: the interpreter is in the middle of the information flow, and both parties direct speech, gaze and social pressure at them.

**In Rehearsal:** the structure the whole simulation reproduces, and the direct justification for two separate counterpart agents rather than one agent playing both parts. One agent playing both roles would have both sides' knowledge in one context, which would collapse the encounter's information structure — see **information isolation**.

---

## Section B — Clinical terms this system handles

These are the clinical concepts that appear inside scenario content and that the deterministic extractors must handle correctly. This section is not a clinical reference; it defines each term to the depth needed to read the scoring rules and the scenario schema.

### adherence

Whether and how closely a patient follows an agreed treatment plan — taking medication as prescribed, keeping follow-up appointments, following activity or diet instructions. The older term is *compliance*, now generally avoided for its one-sided framing.

**In Rehearsal:** an encounter *topic*, not an extracted field. Adherence discussion is where **register shift** and **editorialization** cluster most heavily, because trainees soften a patient's admission ("I stopped taking it") or a clinician's concern. Several scenarios in the bank are built around it for exactly that reason.

### chief complaint

The patient's reason for the visit, in the patient's own words — the presenting problem that opens the encounter.

**In Rehearsal:** a required field on every scenario and normally the first patient utterance the trainee interprets. Distorting or clinically rewriting the chief complaint (patient's "my chest feels tight" → "chest pain") is a canonical `register_shift` plus `substitution` pair and appears deliberately in the calibration set.

### contraindication

A condition or factor that makes a treatment inadvisable or unsafe — an allergy, an interacting medication, a pregnancy, a comorbidity.

**In Rehearsal:** treated as a **critical fact class**. An omitted or flipped contraindication is `critical` severity by rule, without model judgement, because it can directly change clinical action. Allergy statements are handled by a dedicated extractor; see `docs/06-scoring-engine.md`.

### dosage

The amount of a medication per administration — "500 milligrams", "two tablets", "10 units", "half a teaspoon". Distinct from frequency and from total daily dose.

**In Rehearsal:** extracted deterministically by `src/rehearsal/scoring/extractors/numbers.py`. Any mismatch in the number, the unit, or the unit's scale between source and rendering is a `critical` finding, no model involved. Handles Spanish and English numerals, spelled-out numbers, decimal and comma decimal separators, and unit synonyms (mg / miligramos / milligrams). Locale decimal handling — Spanish `0,5` versus English `0.5` — is a named correctness obligation with its own test set, not an assumption.

### frequency

How often a medication is taken or an action performed — "twice a day", "every eight hours", "cada ocho horas", "once a week", "as needed / por razón necesaria".

**In Rehearsal:** extracted deterministically alongside dosage; mismatches are `critical`. Frequency is separately extracted from dosage because the classic dangerous error preserves one and mutates the other ("500 mg every 8 hours" → "500 mg twice a day"), which a naive whole-string comparison scores as *mostly correct*. Every-N-hours and N-times-daily forms are normalised to a common representation before comparison, so "every 12 hours" and "twice a day" do not fire a false alarm.

### health literacy

A person's capacity to obtain, process and understand basic health information well enough to make decisions. Low health literacy is common, is independent of intelligence and education, and is aggravated when the encounter is not in the person's first language.

**In Rehearsal:** the reason `register_shift` toward jargon is scored as an error rather than as sophistication. An interpretation that is technically accurate but pitched above the patient's register has failed to transfer meaning, which is the fidelity criterion — not a stylistic preference.

### informed consent

The process by which a patient is given the information needed to agree to or refuse a procedure — the nature of it, its risks, its benefits, its alternatives — and agrees voluntarily.

**In Rehearsal:** the highest-stakes scenario class in the bank. Consent scenarios are scored with the same taxonomy but tend to concentrate `critical` findings, because omitting a risk or editorialising a reassurance directly undermines the validity of the consent. The system never produces or handles a real consent document; encounters are synthetic by construction (`docs/12-security-privacy.md`).

### laterality

Which side of the body — left, right, bilateral. "Left knee", "rodilla derecha".

**In Rehearsal:** extracted deterministically by `src/rehearsal/scoring/extractors/laterality.py`; any left/right swap is `critical` by rule. A short list of tokens in two languages, provably decidable, and a wrong-site consequence — the clearest illustration in the system of why the model is not asked to judge things code can decide.

### symptom onset

When a symptom began and how it has progressed — "three days ago", "desde el martes", "it started suddenly last night", "it's been getting worse for a month".

**In Rehearsal:** handled by the temporal extractor (`src/rehearsal/scoring/extractors/temporal.py`). Onset changes triage: three days versus three weeks of chest pain are different encounters, so temporal mismatches are `critical`. Relative expressions are resolved against the scenario's declared reference time — the scenario, not the wall clock, defines "today", so replay is deterministic.

### teach-back

The technique of asking a patient to restate instructions in their own words to confirm understanding — "just so I know I explained it clearly, tell me how you'll take this at home."

**In Rehearsal:** a scenario feature and a hard interpreting test. Teach-back turns are where trainees most often slip into **role exchange** — correcting the patient's restatement themselves instead of rendering it faithfully and letting the clinician correct it. Scenarios that include a teach-back turn are flagged with a difficulty feature so the eval can report performance on them separately.

---

## Section C — System and AI-engineering terms as used here

Several of these terms have broad or contested meanings in the wider field. The definitions below are the ones binding inside this repository. Where our usage is narrower than the industry's, the entry says so.

### calibration set

The 40 hand-labelled interpreting turns that anchor the entire project: labelled blind by a human against the error taxonomy, split DEV 25 / TEST 15 with the test split sealed. Composition includes clean items (to measure false alarms), critical-error items, non-critical items, multi-error items and deliberately ambiguous items that establish the honest human ceiling.

**In Rehearsal:** the **only external truth in the system**. Every claim about scorer quality resolves to agreement against it. It is small on purpose — hand-labelled by one human against a published taxonomy beats a large set labelled by a model against itself — and its size is reported as a limitation, not hidden. Full labelling protocol lives in `SETUP.md` section 6; the eval consuming it is specified in `docs/08-evals.md`.

### clinical state graph

The explicit, deterministic graph that drives the encounter: nodes carry a speaker, an intent, persona invariants, required clinical facts, an optional scripted fallback line, and difficulty features. Edges define legal transitions. `ClinicalStateGraph` exposes `entry(seed)`, `successors(node_id)` and `advance(node_id, seed)`.

**In Rehearsal:** the counterpart agent's **plan is the graph, not the model's improvisation**. The model supplies wording; the graph decides what happens next. This is the concrete form of principle 1 in this project, and it is what makes persona consistency deterministically checkable — you can compare what the agent said against what the node it was standing on permitted. Graph validity (no dead ends, no unreachable nodes) is checked at ingest, not at runtime.

### coach agent

The agent that turns a scored session into feedback a human can act on — patterns across turns, the two or three categories a trainee should work on next, suggested scenarios.

**In Rehearsal:** runs **after** the session, never during it, and never scores anything itself. It reads findings that already exist; it cannot create, delete or reclassify one. Isolated from the counterpart agents' contexts in both directions.

### Cohen's kappa

Chance-corrected agreement between two raters on categorical labels. Ranges from below 0 (worse than chance) to 1 (perfect). Preferred over raw percentage agreement because a taxonomy with a dominant "no error" class makes raw agreement look impressive for free.

**In Rehearsal:** the headline L4 eval metric — grader versus human labels on the calibration set. Reported per-category as well as overall (a good aggregate kappa can hide a category the scorer never gets right), always with a confidence interval, and always next to the human ceiling. A kappa without its ceiling and its interval is an incomplete result in this project. Exact computation, matching rules for spans and CI method are specified in `docs/08-evals.md`.

### counterpart agent

Either of the two live conversational agents the trainee interprets between: `ClinicianAgent` (English) and `PatientAgent` (Spanish). Gemma 4 E4B class, quantised, native audio input.

**In Rehearsal:** a deliberately chosen term. Not "the AI", not "the bot", not "the NPC" — *counterpart* names the relationship: these agents are the trainee's conversational partners and adversaries, and they are the thing the trainee's fidelity is measured against. Counterpart agents never see the rubric, the taxonomy, prior findings, or the learner model. See **information isolation**.

### critical error

A finding whose severity is `critical`: one that could change clinical action. The class is defined by fact type — dosage, frequency, allergy, negation, laterality, symptom onset — not by the model's sense of importance.

**In Rehearsal:** `severity = "critical"` in the `Finding` record, and severity is assigned by **deterministic rule wherever the fact type is one of the above**. The grader may not create a `critical` severity in an extractor-owned category, and may not downgrade an extractor's `critical`. This is the single most load-bearing sentence in the scoring design: the dangerous class is decided by code, so it cannot be talked out of by a fluent model.

### dev / test split

The DEV 25 / TEST 15 partition of the calibration set. DEV is the working set — prompt iteration, extractor tuning, threshold selection, optimiser metric. TEST exists to produce one honest number.

**In Rehearsal:** the split is fixed at creation and stratified so both halves contain clean, critical, non-critical, multi-error and ambiguous items. A change to the split is a decision-log entry in `docs/17-decisions.md`, not a routine edit.

### finding

One scored observation about one interpreting turn: `kind` (an `ErrorKind`), `severity`, `span`, `source_span`, `note`, `origin` (`"extractor"` or `"grader"`), `extractor_name`, `confidence`.

**In Rehearsal:** **not the clinical sense of the word** — nothing about the simulated patient's condition. A finding is an interpreting-error record. A turn produces zero or more findings; a session's summary is computed from them by deterministic code. Findings are append-only within a session record: an overruled grader finding is retained with its overruled status, never deleted, because the extractor-versus-grader disagreement rate is itself a reported number. Schema in `docs/03-system-architecture.md`, semantics in `docs/06-scoring-engine.md`.

### grader

The scoring model: a larger Gemma (12B class), quantised, making one structured call per turn over the known source utterance and the trainee's rendering.

**In Rehearsal:** the grader handles **only the semantic residue** — register, idiom, pragmatic force, first-person discipline, editorialization, role exchange. Everything decidable by code has already been decided before the grader's output is merged. "Grader" therefore names a *component of* the scoring engine, not the scorer as a whole; the scorer is extractors plus grader plus deterministic merge. Runs off the critical path.

### ground truth by construction

The property that the system generated the source utterance and therefore knows exactly what was said, with no transcription or annotation step in between.

**In Rehearsal:** the founding architectural asset, and the reason the scoring problem is tractable. It converts an open-ended "how good was this interpretation?" into a bounded "what survived from this known string into that string?". It is a property of the *counterpart's* utterance only — the trainee's rendering is human speech and is not ground truth. The rendering text arrives as the `heard_verbatim` field of the live agent's structured turn output, produced in the same forward pass as its in-character reply, and is content-addressed as `rendering_sha`; the measurement obligation attached to that mechanism is named in `docs/03-system-architecture.md` and evaluated in `docs/05-voice-pipeline.md`.

### human ceiling

The agreement level a competent human reaches with themselves or another human on the same labelling task — the realistic upper bound for any automatic scorer on that task.

**In Rehearsal:** established from intra-rater (and ideally inter-rater) agreement on the calibration set, and **reported alongside every grader agreement number**. A grader at kappa 0.68 against a 0.72 human ceiling is near-saturated; the same 0.68 against a 0.95 ceiling is mediocre. Reporting the first number without the second is the specific dishonesty principle 7 exists to prevent.

### information isolation

The architectural guarantee that the counterpart agents' contexts contain **no** scoring rubric, no error taxonomy, no prior findings, and no learner model — only their persona, their state-graph node, and the conversation so far.

**In Rehearsal:** the load-bearing justification for a multi-agent architecture rather than one big prompt. A counterpart that knows the rubric drifts, unconsciously, toward speaking in easy-to-interpret ways — short sentences, no idiom, no overlapping clauses — which destroys the realism that makes the training worth anything. Isolation is enforced by construction (separate context assembly, no shared conversation object) and **verified empirically** by the leakage test, not asserted. Context-assembly boundaries in `docs/03-system-architecture.md`.

### inter-rater agreement

Agreement between two different human labellers on the same items.

**In Rehearsal:** the stronger form of the human ceiling and the one preferred where a second qualified labeller is available. Marked **[open]**: securing a second labeller with the relevant professional background is a dependency, not a certainty, and if only intra-rater agreement is available the ceiling is reported as intra-rater and explicitly labelled as the weaker estimate. Not silently substituted.

### intra-rater agreement

Agreement of a single labeller with themselves, measured by re-labelling the same items blind after enough separation to defeat recall.

**In Rehearsal:** the minimum viable human ceiling, always collected. It bounds how much of the grader's disagreement is genuine error versus irreducible task ambiguity. Protocol — the re-label pass, the separation, the blinding — is in `SETUP.md` section 6.

### leakage test

The A/B experiment that proves information isolation is doing work: run matched sessions where the counterpart agent's context *can* see the rubric versus *cannot*, and measure the trainee-induced error rate.

**In Rehearsal:** the L8 eval. The prediction is that rubric-aware counterparts produce measurably *easier* speech and therefore a lower induced error rate — the training gets easier and the realism drops. Reported as rates with uncertainty across matched scenario seeds, per principle 7. If the effect does not appear, that result is reported as-is and the multi-agent justification is weakened accordingly; the experiment is a real test, not a demonstration. Design in `docs/08-evals.md`.

### neuro-symbolic

The scoring architecture: deterministic symbolic extractors hard-check the provably decidable facts, and the language model handles only what is left over.

**In Rehearsal:** a specific and narrow claim, not a branding word. It means exactly this division of labour: numbers, dosages, frequencies, negation, laterality, allergies and temporal markers are decided by code with no model in the path; register, idiom, pragmatic force and first-person discipline go to the model; a deterministic merge policy resolves conflicts with the extractors holding precedence in the critical categories. Nothing else in this system is described as neuro-symbolic.

### off-critical-path

The property that a computation does not sit between the trainee's action and the system's audible response.

**In Rehearsal:** specifically means the grader scores **turn N while the trainee is still speaking turn N+1**. The human's own speaking time is the latency budget — that is the entire trick that makes a 12B grader affordable in a real-time loop on one machine. It is a scheduling property enforced by `TurnScheduler`, not an aspiration: if the grader has not finished, the session continues and the finding lands late, because the conversation never waits for scoring. Scheduling and back-pressure behaviour in `docs/03-system-architecture.md`.

### persona consistency

Whether a counterpart agent stayed in role: correct language, correct character, correct knowledge boundaries, no rubric awareness, no answering for the other party.

**In Rehearsal:** the L5 eval metric, and it is **deterministically checkable against the state graph** rather than model-judged — the node the agent was standing on declares its persona invariants and required facts, so violations are detected by comparing output against declared constraints. Reported as a rate over turns with the failure modes broken out (language slip, role slip, fact violation), never as a single quality adjective.

### prompt optimisation

Automated search over prompt formulations — a DSPy/GEPA-style optimiser — scored against a metric.

**In Rehearsal:** the L10 rung, applied to the **grader's prompt only**, with agreement against the DEV calibration split as the metric. Strictly prompt-level: **no weight training, no fine-tuning, no reinforcement learning, no LoRA adapters** — a deliberate scope exclusion, not a limitation of ambition. Before/after agreement is reported on the sealed TEST split, once. An improvement measured on DEV and reported as a headline result would be the exact failure the sealed split exists to prevent.

### scenario bank

The versioned collection of encounters: each carries a chief complaint, a clinical state graph, personas for both agents, the required clinical facts, difficulty features, and provenance. `ScenarioBank` exposes `get(scenario_id)` and `sample(difficulty, seed)`; built by `make scenarios`.

**In Rehearsal:** content, not configuration — scenarios are versioned artefacts with sources and licences, and a scenario change is a data change with a provenance record. Sources, licensing and the authoring process are in `docs/07-data-and-scenarios.md`. Distinct from the **calibration set**, which is labelled *turns* used for measurement; the two never mix.

### sealed split

The TEST 15 half of the calibration set, quarantined from all development activity: never inspected during prompt iteration, never used as an optimiser metric, never used to select thresholds.

**In Rehearsal:** enforced by tooling, not by discipline. `src/rehearsal/evals/seal.py` gates access, and a run against the sealed split is recorded — the number of times it has been opened is itself reported, because a "held-out" split evaluated fifty times is a dev split wearing a costume. Unsealing is a decision-log event in `docs/17-decisions.md`.

### span

A character-offset pair `(start, end)` locating a finding in text. `Finding` carries two: `span` into the trainee's rendering and `source_span` into the source utterance.

**In Rehearsal:** `span` is `None` for omissions (there is nothing in the rendering to point at) and `source_span` may be `None` for additions (there is nothing in the source). Consumers must handle both. Offsets are into the canonical text form of the utterance, and span-matching tolerance for eval agreement is defined in `docs/08-evals.md` — two labellers marking the same error with slightly different boundaries count as agreeing, and the tolerance rule is stated rather than assumed.

---

## Cross-vocabulary collisions

Terms that mean different things to different readers of these documents. Each row states the binding meaning and what it is *not*, to head off the misreading.

| Term | Reads as (outside) | Binding meaning here |
| --- | --- | --- |
| finding | A clinical observation about a patient | An interpreting-error record. Never about the simulated patient's condition. |
| register | CPU register; to sign up | Linguistic level of formality. `register_shift` is an error category. |
| critical | Severe patient condition; a critical bug | `severity = "critical"` — a finding that could change clinical action. |
| session | An HTTP session; a therapy session | One practice encounter, from scenario selection to scored report. |
| turn | A patient's turn in a queue | One source utterance plus the trainee's rendering — the unit of scoring. |
| distortion | Audio distortion | An error category: meaning altered, including negation flips. |
| grader | A person who grades; the whole scorer | Only the model component of the scoring engine. Extractors are not the grader. |
| ground truth | Human-annotated labels | The system-generated source utterance, known exactly and without annotation. |
| span | A time span; a `<span>` element | Character offsets into a rendering or source utterance. |
| coach | A human trainer | The post-session feedback agent. The human trainer is called the **trainer** or **reviewer**. |
| addition | Adding a feature | An error category: content the source did not contain. |
| onset | Any beginning | Symptom onset specifically — an extracted, `critical` temporal fact. |

---

## Related documents

| Document | What it holds that this glossary points at |
| --- | --- |
| `docs/00-dossier.md` | Product framing, non-goals, what this is not |
| `docs/01-research.md` | The evidence base for interpreter error and its clinical consequences |
| `docs/03-system-architecture.md` | Component map, `Finding` schema, orchestration, context boundaries |
| `docs/05-voice-pipeline.md` | Audio path, TTS, interruption, the `heard_verbatim` measurement obligation |
| `docs/06-scoring-engine.md` | Extractors, grader prompt, merge policy, taxonomy-to-standard mapping |
| `docs/07-data-and-scenarios.md` | Scenario bank, state graphs, provenance and licensing |
| `docs/08-evals.md` | Every eval, metric definition, span-matching rules, CI method |
| `docs/09-ui-ux.md`, `docs/10-frontend-spec.md` | Product-facing terminology and copy rules |
| `docs/12-security-privacy.md` | Synthetic-only enforcement, score-use restrictions |
| `docs/17-decisions.md` | Decision log for every [decided] item referenced here |
| `SETUP.md` section 6 | The calibration-set labelling protocol in full |

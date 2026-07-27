# 00 — Product Dossier

## 1. In one paragraph

Rehearsal is a local, voice-based training and assessment system for medical interpreters and bilingual community health workers. A trainee interprets aloud between an AI clinician speaking English and an AI patient speaking Spanish, inside a clinically grounded scenario. The system then scores the *fidelity* of each interpretation — what meaning survived and what did not — using the source utterance it generated as ground truth. Clinically dangerous errors (dosage, frequency, negation, laterality, allergy) are checked by deterministic code; only genuinely semantic questions (register, idiom, pragmatic force) go to a model. The scorer's agreement with human expert judgement is measured on a sealed split and reported alongside the human ceiling. Everything runs on local open models; nothing leaves the machine.

## 2. The problem

**Interpreting errors are frequent, and a large minority are clinically consequential.** Audio-taped paediatric encounters showed a mean of 31 interpreter errors per encounter, 63% carrying potential clinical consequence. Omission alone accounts for 52% of errors — meaning is not mangled so much as it silently disappears.

**Training, specifically, is what fixes it.** In the 2012 replication, professional interpreters produced errors of potential clinical consequence at 12%, versus 22% for ad hoc interpreters. And within the professional group, *hours of training — not years of experience* — predicted error rates: ≥100 hours of training produced a median of 12 errors and 2% clinically consequential, against 33 errors and 12% below that threshold.

**Training volume is exactly what is scarce.** The profession assesses fidelity rigorously and expensively: certification oral exams are scored by two or more trained human raters per response. That rigour is appropriate for credentialing and structurally impossible for daily practice. There is no way for a working bilingual health worker to get twenty measured repetitions this week.

**Locally, the gap is quantified.** Salud Para La Gente serves 27,480 patients across 182,186 annual visits in Watsonville; 71% are best served in a language other than English; the organisation reports access to three Mixteco interpreters. Watsonville Community Hospital employs none. Twelve Mixtec doulas who completed training remain blocked from working inside the hospital on administrative grounds. The binding constraint is trained, available interpreting capacity.

Sources and confidence levels for all of the above: `docs/01-research.md`.

## 3. Who it is for

| User | Need | What they get |
|---|---|---|
| **Interpreter in training** | Repetition against a real standard, without a human rater's time | Unlimited scenarios, per-turn fidelity findings, competency tracking |
| **Bilingual community health worker / promotora** | Interpreting is a de facto part of the job, often without formal training — the population the evidence identifies as highest-risk | Structured practice targeting the error classes that carry clinical consequence |
| **Interpreter training programme** | Scale practice beyond available instructor hours; see where a cohort is weak | Trainer review queue, override capture, cohort patterns |
| **Safety-net clinic** | Raise the floor of ad hoc interpreting capacity | A tool staff can practise on locally, with no patient data involved |

Primary design target is the first two. The product is built for the individual practising alone, with programme features layered on top — not the reverse.

## 4. What it does

1. **Selects a scenario** — a clinically grounded encounter (condition, medication list with real dosing, symptom timeline, emotional state, health-literacy level, language variety) drawn from the scenario bank.
2. **Runs a triadic encounter** — clinician agent (English) and patient agent (Spanish) converse; the trainee interprets aloud in both directions. Turn-taking, repetition requests and note-taking mirror real consecutive interpreting practice.
3. **Scores each turn** — comparing the known source utterance against the trainee's rendering: symbolic extractors decide the critical categories, a single structured model call handles the semantic residue, and the findings merge into one evidence-bearing result.
4. **Produces a report** — per-turn findings with source-vs-rendering comparison, severity, the clinical reason each finding matters, session patterns, competency by skill dimension, and a permanent disclosure of the scorer's own measured accuracy and known weaknesses.
5. **Tracks competency over time** and recommends what to practise next, with the reason always visible.

## 5. The thesis — why this can work when "AI judges performance" usually cannot

Most attempts to score human performance with a language model fail for the same reason: there is no ground truth, so the model's opinion is the output, and nobody can say whether it is right.

Interpreting inverts that problem, and this is the entire technical bet:

**The system generates the source utterance, so it knows exactly what was said.** The question is not "was this good?" but "does this rendering carry the propositional content of this known sentence?" — and for the categories that matter clinically, that question has a *decidable* answer. A dosage either survived or it did not. A negation either flipped or it did not. Those are string-and-number comparisons after cross-lingual normalisation, not judgements.

This yields three properties that ordinarily conflict:

- **The dangerous errors are checked deterministically** — the class the clinical literature identifies as consequential is exactly the class that is provably decidable.
- **The model's scope is bounded** to genuinely semantic residue, where its errors are less consequential and its accuracy is separately measured.
- **The whole thing is falsifiable**, because a human-labelled calibration set anchors it to expert judgement rather than to itself.

## 6. What it deliberately is not

| Not | Why |
|---|---|
| A certification or credentialing instrument | Certification is human-rated to a standard this does not claim to meet. Stated in `MODEL_CARD.md` and shown in the product |
| A performance-management or employment tool | Scores are formative. Repurposing them as disciplinary evidence without consent is out of bounds — see `docs/12-security-privacy.md` |
| A substitute for a qualified interpreter | It trains people; it does not interpret for patients |
| A system that touches real patient data | Encounters are synthetic by construction. Real patient audio is prohibited, with enforcement described in `docs/12-security-privacy.md` |
| A general conversation-skills coach | Fidelity is the scope precisely because fidelity is checkable |
| A cloud service | Local by architecture |

## 7. How it is built — the capability vertical

The project is a deliberate climb, where each layer rests on a measured layer beneath it. No rung is built before the one below it has an eval number.

| Layer | What is built | Eval that proves it |
|---|---|---|
| **L4** Application / one structured call | The neuro-symbolic fidelity scorer | Cohen's κ vs human labels; critical-error recall |
| **L5** Bare-hands agent loop | Counterpart agent driven by a clinical state machine | Persona-consistency rate, checked against the state graph |
| **L6** Packaged skill | Session protocol, rubric and taxonomy as a portable skill | A/B task-correctness with vs without the skill |
| **L7** Pipeline with human gates | Full session orchestration; trainee and trainer are the gates | End-to-end completion rate; trainer-override rate |
| **L8** Multi-agent with isolation | Clinician + patient + coach + grader, isolated contexts | Leakage A/B — induced error rate with vs without rubric exposure |
| **L10 (rung 1)** Automated prompt optimisation | Optimiser improves the grader's prompt against the calibration metric | Before/after agreement, reported on a **sealed** test split |

Explicitly out of scope: model weight training, fine-tuning, reinforcement learning, building an inference server, multi-tenant fleet scaling. Reasons and reversal conditions in `docs/17-decisions.md`.

## 8. The anchor

Everything the system claims about its own accuracy rests on **40 interpreting turns hand-labelled by a human** against the error taxonomy — split 25 development / 15 sealed test, labelled blind, including clean items to measure false alarms and deliberately ambiguous items to establish the honest ceiling.

This is the one task that cannot be delegated to a model. If a model generates the labels, the evaluation is circular and every downstream number is worthless. The full protocol — why it exists, how to compose it, how to label it correctly, and how it is split — is `SETUP.md` §6.

## 9. What success looks like

| Question | Answered by |
|---|---|
| Does the scorer agree with human experts? | Cohen's κ on the sealed split, reported beside intra-/inter-rater agreement |
| Does it catch the errors that could hurt someone? | Critical-error recall — the safety metric, optimised above all others |
| Does it cry wolf? | False-positive rate on clean turns |
| Is the simulation realistic enough to train against? | Persona consistency; leakage A/B showing isolation matters |
| Can a person actually practise with it? | End-to-end session completion; conversational latency within budget |
| Does practice improve real interpreting performance? | **Not established.** See §10 |

## 10. Open risks, stated plainly

1. **No efficacy evidence.** That measured practice with *this* system improves real-world interpreting performance is unproven. The literature establishes that training hours reduce error rates; it does not establish that this tool delivers that benefit. Claiming otherwise would be unsupported. What a real efficacy claim would require is described in `docs/08-evals.md`.
2. **The taxonomy is an operationalisation, not a codified standard.** Research established that no single authoritative publication defines the six-category taxonomy as one unit, and that NCIHC's standards contain no explicit first-person requirement. The product must describe its taxonomy as drawn from the research literature and aligned to NCIHC standards — never as "the professional standard." See `docs/01-research.md` §8.1.
3. **Semantic scoring is materially weaker than symbolic scoring.** Register, idiom and pragmatic force will be scored less reliably than dosages and negations. This must be disclosed in the report interface, not buried.
4. **Speech understanding carries dialect and accent bias.** Regional Spanish variation risks being penalised as error. Detection and mitigation are a first-class concern in `MODEL_CARD.md`.
5. **Indigenous-language communities are not served.** The most acute local gap — Mixteco and Triqui — is precisely the one this pipeline cannot currently address, because the speech resources do not exist. Naming this is more honest than implying coverage.
6. **Latency may not hold.** A real-time multi-model voice loop on a single machine is the hardest engineering surface. The degradation ladder, including a fully text-based mode, is specified in `docs/05-voice-pipeline.md`.

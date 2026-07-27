# SETUP — Rehearsal

Everything required to take this project from an empty machine to a running system with trustworthy numbers. Read top to bottom the first time.

---

## 0. What you are setting up

Rehearsal is a real-time, voice-based training and assessment system for medical interpreters and bilingual community health workers. A trainee stands in the middle of a simulated clinical encounter: an AI clinician speaks English, an AI patient speaks Spanish, and the trainee interprets between them out loud. The system then scores the *fidelity* of each interpretation — what meaning survived, what was omitted, added, or distorted — against professional interpreting standards.

Everything runs locally on open Gemma models. There is no cloud inference in the core loop.

---

## 1. Prerequisites

| Requirement | Why | Check |
|---|---|---|
| macOS on Apple Silicon (M-series), 32 GB RAM minimum, 48 GB recommended | Three models resident simultaneously (see §4) | `sysctl -n hw.memsize \| awk '{print $1/1073741824" GB"}'` |
| Python 3.12 | Backend, scoring engine, eval harness | `python3 --version` |
| `uv` | Dependency + venv management | `uv --version` |
| Node 20+ | Frontend build | `node --version` |
| ~40 GB free disk | Model weights + caches | `df -h /` |
| Working microphone + headphones | Voice loop; headphones prevent the AI's own speech being captured as trainee input | — |

Headphones are not optional during development. Without them the TTS output bleeds into the microphone and the system scores the AI's own voice as the trainee's interpretation.

---

## 2. Repository setup

```bash
git clone <your-repo-url> rehearsal && cd rehearsal
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
cd frontend && npm install && cd ..
cp .env.example .env      # then edit — see §3
```

---

## 3. Environment variables

The core product needs **no secrets**. Everything in `.env` is optional configuration or applies only to the offline evaluation tooling.

| Variable | Required? | Purpose |
|---|---|---|
| `REHEARSAL_MODEL_DIR` | No (defaults to HF cache) | Where model weights live |
| `REHEARSAL_LIVE_MODEL` | No | Model id for the live conversational agents |
| `REHEARSAL_GRADER_MODEL` | No | Model id for the off-path scoring agent (larger) |
| `REHEARSAL_TTS_BACKEND` | No | `system` (macOS `say`) or a local neural TTS |
| `REHEARSAL_LOG_LEVEL` | No | `INFO` default |
| `HF_TOKEN` | Only for first model download | Hugging Face model pull |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | **Optional, eval tooling only** | If you run a frontier model as a *second opinion* during grader calibration analysis. Never used in the product runtime. |

If you never set an API key, everything in the product still works. That is the design.

---

## 4. Models & memory layout

Three models are resident during a live session. Target layout for a 48 GB machine:

| Role | Model class | Approx. resident | Latency budget |
|---|---|---|---|
| Speech understanding + live agents (clinician, patient) | Gemma 4 E4B, quantised, native audio input | ~6–8 GB | must be fast — in the conversational critical path |
| Fidelity grader | Gemma 12B, quantised | ~8–10 GB | **off** the critical path — runs while the trainee is speaking |
| Text-to-speech (two voices: en-US, es-MX) | Local neural TTS or system voices | ~1–2 GB | streamed, interruptible |

Total ≈ 20–24 GB resident, leaving headroom for the OS, browser and audio buffers.

Pull models:

```bash
make models          # downloads + verifies the model set
make smoke-models    # one inference per model, prints latency
```

`make smoke-models` must pass before you build anything else. If the live model cannot round-trip an audio turn within the latency budget in `docs/05-voice-pipeline.md`, stop and read that document's fallback section before continuing.

---

## 5. Data

Rehearsal needs three kinds of data. Only one of them requires you personally.

**(a) Scenario seed data — public datasets.** Clinical encounter realism (conditions, medication lists, symptom timelines) is seeded from public medical dialogue and transcription datasets. See `docs/07-data-and-scenarios.md` for the exact list, licences, and the ingestion command:

```bash
make scenarios       # builds the scenario bank from configured sources
```

**(b) Session data — generated at runtime.** Every practice session produces a transcript and per-turn scores, stored locally. Never leaves the machine. Git-ignored.

**(c) Calibration labels — you, by hand.** This is §6, and it is the most important thing in this document.

---

## 6. The calibration set — what it is, why it exists, and how to do it correctly

> **This is the single task that cannot be delegated to an AI agent, a teammate who hasn't read the standards, or a script. Budget it first, not last. Everything the system claims about its own accuracy rests on it.**

### 6.1 Why this exists (read this part properly)

Rehearsal's central output is a **score of a human's interpreting performance**. A model produces that score. So the obvious, fatal question is:

> *"How do you know the score is right?"*

If the answer is "the model is good at this," you have nothing. You have an opinion generator wearing the costume of an assessment instrument. Worse — if you were to validate the grader by asking *another model* whether it agrees, the evaluation is **circular**: two systems with correlated blind spots agreeing with each other proves nothing about reality.

The only way out is an **external anchor**: a set of interpreting turns that a *human being* has judged, carefully, against the taxonomy and the NCIHC Standards of Practice it aligns to. That anchor is the calibration set. Once it exists:

- You can measure grader accuracy as **agreement with human expert judgement** — a real, defensible number.
- You can *improve* the grader (via prompt optimisation) with something honest to optimise **against**.
- You can answer "why didn't you do X?" with a measurement instead of an argument.

Without it, every other number in this project is decoration. With it, the project has a spine.

### 6.2 What a "calibration turn" actually is

One calibration item is a triple:

```
source_utterance   — what the AI speaker said (English or Spanish). Known exactly, because the system generated it.
trainee_rendering  — what the interpreter said back in the other language.
human_label        — your judgement of what, if anything, went wrong.
```

The crucial structural advantage of this domain: **the source is known ground truth by construction.** You are not asking "was this empathetic?" (unanswerable). You are asking "does this rendering carry the same propositional content as this known sentence?" — a question with a defensible answer.

### 6.3 The label schema

Each item is labelled with **zero or more errors**, using the error taxonomy this system implements — an operationalisation drawn from the interpreting research literature and aligned to the NCIHC Standards of Practice, *not* a single codified standard (see `docs/01-research.md` §8.1; implemented in `docs/06-scoring-engine.md`):

| Error | Meaning | Example |
|---|---|---|
| `omission` | Content in the source is missing from the rendering | Source mentions "twice a day"; rendering doesn't |
| `addition` | Rendering contains content not in the source | Interpreter adds "the doctor says it's nothing to worry about" |
| `substitution` | Content replaced with different content | "50 mg" rendered as "15 mg" |
| `distortion` | Meaning materially altered, including negation flips | "do not take with food" → "take with food" |
| `editorialization` | Interpreter's own opinion/explanation inserted | Adding advice the clinician never gave |
| `role_exchange` | Interpreter converses on their own behalf instead of interpreting | Answering the patient directly |
| `register_shift` | Register/formality/tone materially changed | Clinical explanation rendered as slang, or vice versa |
| `false_fluency` | Term invented or "Spanglish-ised" rather than interpreted | "la aplicación" for an appointment |
| `first_person_violation` | Switching to reported speech instead of first person | "He says that you should…" |

Each error carries:
- **the exact span** of the rendering (or the missing source span) it applies to,
- a **severity**: `critical` (could change clinical action — dosage, frequency, allergy, negation, laterality, symptom onset) or `non-critical`,
- an optional note.

Items with no errors are labelled `clean` — and you need plenty of those. A calibration set of only broken examples teaches you nothing about false alarms.

### 6.4 Where the 40 items come from

Aim for **40 items minimum**, composed deliberately — not randomly:

| Bucket | Count | Purpose |
|---|---|---|
| Clean, correct renderings | 12 | Measures false-positive rate. If the grader flags these, it is unusable. |
| Single critical error (dosage, negation, frequency, laterality, allergy) | 10 | The errors that matter most clinically. Recall here is the headline safety metric. |
| Single non-critical error (register, first-person, mild omission) | 10 | Tests discrimination, not just "did something break". |
| Multiple simultaneous errors | 4 | Real interpreting fails in clusters. |
| Genuinely ambiguous / borderline | 4 | Establishes the honest ceiling: where *humans* disagree, the grader cannot be expected to do better. |

Generate the renderings by interpreting the source yourself (or having a bilingual colleague do it) and deliberately seeding the error types above. Record which error you *intended* to seed — but **do not** let that intention be the label. Label what is actually there. Sometimes you'll seed one error and produce two.

### 6.5 How to label it perfectly — the protocol

Follow this exactly. The value of the set is destroyed by shortcuts.

> **If you are monolingual (English only): read this first.** Calibration items split into two directions. `es_to_en` items (patient speaks Spanish, rendering is in English) you can label alone — you're comparing an English rendering against an independent English fact, no Spanish required. `en_to_es` items (rendering is in Spanish) you **cannot** label alone, and there is no honest interface shortcut around it: any English gloss you'd check the Spanish against would just be confirming content someone already wrote, not an independent judgement — exactly the circularity rule 2 below exists to prevent. **Recruit a bilingual person for the `en_to_es` half before you start** — this also satisfies step 7's inter-rater-reliability recommendation, so it isn't extra work on top of the protocol, it's the same requirement arriving early. Use `tools/label_quiz.py` to run this interactively: it quizzes you on `es_to_en` items one at a time and automatically queues `en_to_es` items for your bilingual reviewer without ever showing you their content. See `tools/README.md`.

1. **Read the standard first.** Sit with the NCIHC / CHIA standards of practice and the error taxonomy in `docs/01-research.md` before labelling item one. You are applying an operationalisation drawn from the research literature and aligned to the NCIHC Standards of Practice (see `docs/01-research.md` §8.1) — not personal taste.
2. **Label blind.** Never look at the model's output for an item before you have committed your own label. Seeing the model's answer first contaminates your judgement irreversibly — you will rationalise its choice. This single rule is the difference between a real calibration set and a rubber stamp.
3. **Label the rendering, not the interpreter.** No holistic impressions. For each item, work through the taxonomy in order and ask a yes/no question per category.
4. **Mark severity by clinical consequence, not by how wrong it feels.** A politeness slip is non-critical. A dropped "not" is critical. Ask: *could a clinician act differently because of this?*
5. **Record your uncertainty.** Add a `confidence` field: `sure` / `unsure`. Items you were unsure about get analysed separately — they are the honest ceiling of the metric, not failures of the model.
6. **Rest, then re-label a sample.** After finishing, do the re-label pass in a separate working session, far enough removed that you cannot recall your original labels, then re-label 10 items *without looking at your first pass*. Compare. This is your **intra-rater agreement** — your own consistency with yourself. If you disagree with yourself on 3 of 10, the grader cannot be expected to beat that, and you must say so publicly.
7. **Get a second human if at all possible.** A bilingual colleague or a certified interpreter labelling even 15 of the items gives you **inter-rater agreement** — by far the most credible number in the whole project. It converts "one person's opinion" into "a measurable standard."
8. **Freeze it.** Once labelled, the set is immutable. If you later decide a label was wrong, do not silently edit it — record the change with a reason in `data/calibration/CHANGELOG.md`. Silently re-labelling to make a metric look better is the single easiest way to make the entire project dishonest.

### 6.6 The split — do not skip this

Divide the 40 items **before** you look at any results:

- **DEV set — 25 items.** Used to develop and *optimise* the grader (including automated prompt optimisation).
- **TEST set — 15 items.** Sealed. Never used for tuning. Touched only to produce the final reported number.

Why: if you optimise a prompt against all 40 and then report agreement on those same 40, the number is contaminated — you have measured memorisation, not accuracy. Every credible before/after claim comes from the sealed TEST set. Store them separately:

```
data/calibration/
├── dev.jsonl          # 25 items — used for optimisation
├── test.jsonl         # 15 items — SEALED. Do not open during development.
├── CHANGELOG.md       # any label correction, with reason
└── raw/               # git-ignored; original recordings/renderings
```

### 6.7 What gets computed from it

```bash
make calibrate      # scores the grader against dev + test, writes the report
```

Produces:

| Metric | What it tells you |
|---|---|
| **Cohen's κ** (grader vs human, per error category) | Agreement corrected for chance. The headline. |
| **Critical-error recall** | Of the clinically dangerous errors, what fraction did the grader catch? This is the safety number. Optimise for this above all others. |
| **False-positive rate on clean items** | Does it invent errors? A grader that cries wolf destroys trainee trust immediately. |
| **Per-category precision / recall** | Where it is strong and weak — e.g. excellent on numbers, poor on register. |
| **Human ceiling** (intra-/inter-rater agreement) | The honest upper bound. Report it next to the grader's score, always. |

### 6.8 How it is used downstream

- It is the **metric for automated prompt optimisation** of the grader (see `docs/08-evals.md`). Optimisation runs against DEV; the improvement is reported on TEST.
- It gates releases: a grader that regresses on critical-error recall does not ship.
- It is the answer to the hardest question anyone will ask about this project.

### 6.9 Effort

This is a substantial task — plan for it to occupy a full working session, with a shorter second session for the delayed re-label pass. Do it early. Every engineering decision downstream is measured against it, so producing it late means building blind.

---

## 7. Running the system

```bash
make dev            # backend + frontend, hot reload
make session        # CLI: run one practice session end-to-end
make report         # render the last session's fidelity report
make evals          # full eval suite (see docs/08-evals.md)
make calibrate      # grader vs human calibration report
make check          # lint + types + tests + evals — the pre-commit gate
```

---

## 8. Accounts & external services

| Service | Needed for | Required? |
|---|---|---|
| Hugging Face account | Model weights download | Yes (free) |
| GitHub | Repository, CI | Yes |
| Public dataset host account | Public dataset download for the scenario bank | Yes (free) |
| Frontier LLM API key | Optional second-opinion analysis during calibration only | No |
| Cloud hosting | — | **No.** The system runs locally by design. |

---

## 9. Living documents — the update rule

Two documents in `plans/` consume live numbers from the eval suite:

- `plans/writeup-plan.md`
- `plans/video-plan.md`

Both read from `plans/metrics-snapshot.md`, which is the single place current numbers live.

**The rule: whenever an eval run produces a number that differs materially from the one recorded in `plans/metrics-snapshot.md`, update the snapshot in the same working session, then re-read both plans and correct any claim that the new number invalidates.**

A number that changes in the eval output but not in the plans is how a project ends up publicly claiming something its own tests contradict. `make evals` prints a reminder and diffs against the snapshot.

`plans/` is git-ignored — it is internal working material, not part of the published product.

---

## 10. First-run checklist

- [ ] `make smoke-models` passes within the latency budget
- [ ] Headphones connected; microphone captures trainee audio only
- [ ] `make scenarios` produced a non-empty scenario bank
- [ ] One end-to-end `make session` completes and writes a report
- [ ] Calibration set labelled, split into sealed dev/test, `make calibrate` produces a report
- [ ] `make check` green
- [ ] `plans/metrics-snapshot.md` reflects the numbers you just produced

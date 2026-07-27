# Data Card — Rehearsal

Every dataset Rehearsal creates, consumes or ships. One section per asset, each covering purpose, schema
reference, provenance, collection method, known biases and gaps, sensitivity, storage, retention, access,
and licence / redistribution status.

Scope note: this document is the **register** of data assets. It does not restate the labelling protocol
(`SETUP.md` §6), the scoring schema (`docs/06-scoring-engine.md`), the ingestion pipeline and licence
matrix for seed corpora (`docs/07-data-and-scenarios.md`), the eval definitions (`docs/08-evals.md`), or
the storage design (`docs/03-system-architecture.md` §10). It references them.

Status labels used throughout: **[decided]**, **[proposed]**, **[open]**.

---

## 0. The five assets, and the rule that separates them

| # | Asset | One-line role | Machine-generated? | Human-labelled? |
|---|---|---|---|---|
| 1 | Scenario bank | The encounters a trainee practises against; owns the ground-truth clinical facts | Yes, reviewed by a human | No |
| 2 | Public seed corpora | Realism input to scenario generation — vocabulary, shape, cadence | No (third-party) | No |
| 3 | Calibration set | The external anchor; the only place human judgement enters as data | No | **Yes — exclusively** |
| 4 | Session data | What a trainee actually did, and what the system said about it | Yes (runtime) | Partially (trainer reviews) |
| 5 | Evaluation run records | The audit trail of every number the project reports | Yes | No |

**The load-bearing rule across all five: the calibration set is the only asset whose labels are ground truth
about *quality*.** Assets 1 and 2 ground *realism*, not truth. Asset 4 contains model output that is
explicitly provisional until a human passes it. Asset 5 records measurements, not judgements. Confusing any
of these with the calibration set — in particular, letting model output flow back into it — collapses the
project's epistemics (principle 2, principle 7).

---

## 1. Scenario bank

### 1.1 Purpose

Supplies the clinical encounters. A scenario carries: a clinical state graph (who speaks, in what order,
with what intent and persona invariants), the required clinical facts at each node, and a **term manifest** —
the numbers, dosages, frequencies, allergies, laterality markers and temporal markers of that encounter, in
both languages. The term manifest is what makes principle 2 operational: the deterministic extractors in
`docs/06-scoring-engine.md` compare a rendering against *known* facts rather than inferring them.

The bank is also the difficulty ladder. Each node declares the difficulty features it exercises
(numeric density, negation, idiom, register distance, speech rate, overlap), which is how `LearnerModel`'s
`difficulty()` integer selects an appropriate scenario without the runtime ever seeing the learner model
itself (principle 4).

### 1.2 Schema reference

Authoritative definition: `docs/07-data-and-scenarios.md` (authoring format, node vocabulary, validation
rules). Runtime contract: `docs/03-system-architecture.md` §9 (`ScenarioBank`, `ClinicalStateGraph`,
`TermManifest`). Reproduced here only far enough to make the provenance and review discussion concrete:

```
data/scenarios/
├── bank.jsonl                      # built artefact — one scenario per line
├── bank.sha256                     # hash of bank.jsonl; recorded in every eval run
├── sources/                        # normalised seed extracts (see §2)
├── authored/                       # hand-written scenarios and hand-edited overrides
│   └── sc-wat-diabetes-001.yaml
└── REVIEW.md                       # per-scenario review sign-off log
```

```jsonc
// one line of data/scenarios/bank.jsonl
{
  "scenario_id": "sc-wat-diabetes-001",
  "schema_version": "1.0.0",
  "title": "Type 2 diabetes medication adjustment",
  "setting": "safety-net primary care, follow-up visit",
  "difficulty": 3,                        // 1..5
  "difficulty_features": ["numeric_density", "frequency", "negation"],
  "languages": { "clinician": "en-US", "patient": "es-MX" },
  "provenance": {
    "generator": "gemma-12b-it-q4_k_m",
    "generator_prompt_version": "scenario/v3",
    "seed": 90210,
    "seed_corpora": ["mtsamples:endocrinology", "medical-dialogue-en:diabetes"],
    "authored_by": null,                  // set when hand-written
    "reviewed_by": "kn",                  // required — see §1.4
    "review_sha256": "…"                  // hash of the exact reviewed content
  },
  "term_manifest": {
    "medications": [
      { "id": "m1", "en": "metformin", "es": "metformina",
        "dose": { "value": 500, "unit": "mg" },
        "frequency": { "times": 2, "per": "day", "en": "twice a day", "es": "dos veces al día" } }
    ],
    "allergies":  [ { "id": "a1", "en": "penicillin", "es": "penicilina" } ],
    "laterality": [ { "id": "l1", "en": "left foot", "es": "pie izquierdo" } ],
    "temporal":   [ { "id": "t1", "en": "for about three weeks", "es": "desde hace unas tres semanas" } ],
    "negations":  [ { "id": "n1", "en": "do not take it on an empty stomach",
                      "es": "no lo tome con el estómago vacío" } ]
  },
  "graph": {
    "entry": ["n_open"],
    "nodes": {
      "n_open": { "speaker": "clinician", "intent": "greet_and_orient",
                  "facts": [], "persona_invariants": ["uses_plain_language"],
                  "fallback_line": "Good morning. How have you been since we last met?",
                  "successors": ["n_symptom_probe"] }
    }
  }
}
```

Every `facts` entry is a term-manifest `id`. A node may not reference a fact that does not exist in the
manifest; `make scenarios` fails the build if it does. This is what prevents the classic failure mode where
an agent improvises a dosage the extractors have never heard of and the grader then scores a hallucination.

### 1.3 Provenance and collection method

Built, never hand-collected in bulk:

```bash
make scenarios                  # ingest → generate → validate → review-gate → bank.jsonl
```

| Stage | What happens | Deterministic? |
|---|---|---|
| Ingest | Seed corpora (§2) are downloaded, licence-checked, normalised into `data/scenarios/sources/` | Yes |
| Sample | A seeded sampler draws condition/medication/timeline motifs from the normalised sources | Yes, given `seed` |
| Generate | One structured local-model call per scenario emits the graph and term manifest as JSON | No (model), but seeded and recorded |
| Validate | Deterministic checks: schema, fact-id integrity, both-language coverage, dose/unit plausibility ranges, no free-floating PHI-shaped strings | Yes |
| Review | A human reads the scenario and signs it off in `data/scenarios/REVIEW.md` | Human |
| Freeze | `bank.jsonl` written; `bank.sha256` recomputed | Yes |

Hand-authored scenarios in `data/scenarios/authored/` bypass generation but **not** validation or review.

### 1.4 Who reviews, and what they are checking

Review is a required gate, not a courtesy. Reviewer roles [decided]:

| Reviewer | Reviews | Blocking authority |
|---|---|---|
| Project engineer (`kn`) | Every scenario: schema sanity, fact integrity, difficulty labelling, Spanish register plausibility | Yes |
| Bilingual reviewer / certified interpreter (**[open]** — not yet engaged) | Spanish naturalness, regional register, idiom plausibility for es-MX and Pajaro Valley usage | Yes, when engaged |
| Clinical reviewer (**[proposed]**) | Whether the clinical content is *safe to practise against* — plausible dosing, no dangerous instruction presented as normal care | Yes, when engaged |

Until the bilingual and clinical reviewers exist, the bank ships with a stated limitation (§8) and every
scenario carries `reviewed_by: "kn"` — a single non-clinician, non-native reviewer. That is recorded in the
data, not hidden in a footnote, so a downstream reader can weight it.

A scenario whose content changes after review has its `review_sha256` invalidated by `make scenarios`, which
returns it to unreviewed state. Review does not survive an edit.

### 1.5 Known biases and gaps

| Bias / gap | Effect | Mitigation status |
|---|---|---|
| Generated by a model trained largely on English clinical text | Spanish turns may read as translated English rather than natively Spanish; register may skew formal | Partly mitigated by generating the Spanish side under an explicit es-MX register instruction; **unmitigated** until a bilingual reviewer signs off |
| Seed corpora skew to US specialty dictation, not safety-net primary care | Over-representation of specialist vocabulary, under-representation of the actual Watsonville visit mix (diabetes, hypertension, occupational injury, prenatal, pediatric asthma) | Partly mitigated by weighted sampling toward primary-care categories; residual skew is real |
| **Indigenous-language reality is absent.** Mixteco and Triqui speakers are a large part of the served population; the bank is Spanish/English only | The product does not represent, and must not claim to represent, relay interpreting or indigenous-language encounters | **Named gap, not mitigated.** Out of scope for the current system |
| No dialectal variety within Spanish | A trainee practises against a narrow register band and may be over-confident with real speakers | **Open.** Dialect axis is a proposed future difficulty feature |
| Model-generated scenarios cluster | Generated encounters converge on a few narrative shapes; diversity is bounded by the generator, not by the seeds | Measured, not assumed: `make scenarios` reports a lexical-diversity and motif-collision report; see §7 |
| Difficulty labels are declared, not measured | A scenario labelled difficulty 4 may be easier than one labelled 3 | **Open.** Calibrating declared difficulty against observed trainee error rates requires session volume we do not yet have |

### 1.6 Sensitivity, storage, retention, access, licence

| Property | Value |
|---|---|
| Sensitivity | **Low.** Fully synthetic. Contains no real patient, no real clinician, no real encounter |
| PHI | None by construction — the generator is never given real records (§2) |
| Storage | `data/scenarios/` in the repository; `bank.jsonl` committed [decided] so a session is reproducible from a clean checkout |
| Retention | Indefinite; versioned by `schema_version` and by git history |
| Access | Anyone with the repository. No access control; nothing here is confidential |
| Licence | Project licence (`LICENSE`) applies to authored content and generated output. Redistributable **only after** the derivation check in §2.4 passes |

---

## 2. Public seed corpora

### 2.1 Purpose, and the rule that governs their use

Public corpora exist to make generated scenarios *sound like medicine* — the vocabulary, the turn shapes, the
way a clinician actually opens a follow-up visit, the way symptom timelines get described. Nothing more.

> **Public data grounds realism, not truth.** No fact in a seed corpus is ever treated as clinically correct,
> as a scoring reference, or as ground truth for anything. The term manifest is the only source of truth for
> scoring, and it is produced *with* the scenario, not extracted *from* a corpus.

The distinction is not stylistic. If a corpus sentence were allowed to become a scored fact, the system would
inherit that corpus's transcription errors, its de-identification artefacts and its clinical mistakes into a
number it reports as an interpreter's fidelity score. The one-directional flow — corpus → realism → generated
scenario → term manifest → scoring — is enforced by the pipeline: the extractors read the term manifest and
have no code path to `data/scenarios/sources/`.

### 2.2 Categories used

The authoritative source list, per-source licence text, and ingestion commands live in
`docs/07-data-and-scenarios.md`. This card records the **categories** and the discipline, which is what a
data reviewer needs:

| Category | What it contributes | Example class of source | Licence posture |
|---|---|---|---|
| Clinical dictation / transcription samples | Encounter structure, clinical vocabulary, section shapes | Public medical transcription sample collections | Permissive or public-domain only |
| Doctor–patient dialogue corpora (English) | Turn-taking rhythm, question forms, patient phrasing | Openly licensed research dialogue sets | Permissive research licences, attribution retained |
| Bilingual / Spanish health education material | es-MX health register, patient-facing phrasing, diacritic-realistic text | Public-health agency patient materials | Public-domain or explicitly reusable government material |
| Medical terminology and drug-name lists | Dose/unit/frequency surface forms in both languages | Open terminology and drug reference lists | Permissive; used as vocabulary, never as clinical guidance |
| Interpreting standards of practice | The error taxonomy and its definitions — **normative text, not training data** | NCIHC / CHIA published standards | Cited and quoted minimally under fair use; never redistributed in bulk |

### 2.3 Licence discipline

Rules, enforced at ingest [decided]:

1. **Allowlist, not blocklist.** A source is ingested only if its licence appears in the allowlist in
   `docs/07-data-and-scenarios.md`. An unknown or ambiguous licence is a hard ingest failure, not a warning.
2. **Licence travels with the data.** Every file in `data/scenarios/sources/` has a sibling
   `<name>.license.json` recording source URL, licence identifier, retrieval method and a content hash.
   Missing sidecar → `make scenarios` fails.
3. **No scraping behind a login, no terms-of-service circumvention, no bulk copying of a source whose licence
   permits reading but not redistribution.**
4. **Share-alike sources are excluded**, not accommodated. The project does not want a copyleft obligation
   propagating into generated scenarios it intends to redistribute; excluding those sources is cheaper than
   reasoning about derivation.
5. **Raw sources are git-ignored.** `data/scenarios/sources/` is not committed. A clean checkout rebuilds it
   with `make scenarios`, or consumes the committed `bank.jsonl` and never needs it at all.

### 2.4 PHI and de-identification posture

| Rule | Detail |
|---|---|
| **No real patient data enters this project. Ever.** | There is no ingestion path for clinical records, no BAA, no covered-entity relationship, and no intent to create one. The project is a training simulator, not a clinical system |
| Only already-de-identified public material is ingested | De-identification is a property the source must already have; the project does not perform de-identification and does not claim competence to do so |
| Second-pass scrub anyway | Ingest runs a deterministic scrub for identifier-shaped strings (names against a common-name list, dates, MRN-shaped tokens, phone/SSN patterns, addresses). Hits are **rejected with the file named**, not silently redacted — a scrub hit means the source's own de-identification is suspect, which is a licence-and-trust question, not a regex question |
| Generated output re-checked | The scenario validator re-runs the same scrub on generated text. A generated scenario containing an identifier-shaped string fails the build |
| Residual risk, stated | Public de-identified corpora are known to retain occasional residual identifiers. Our scrub reduces but does not eliminate this. The mitigation that actually matters is that we never publish `sources/` and never treat corpus content as fact |
| Scenario text is untrusted input | Even though we generated the bank, scenario text crosses a trust boundary into the agents' context (`docs/03-system-architecture.md` §12, boundary B3). Prompt-injection-shaped content in a seed corpus cannot become an instruction |

### 2.5 Known biases and gaps

- English-dominant, US-clinical-system-shaped. Encounter norms encoded in these corpora are US norms.
- Specialty-dictation heavy; safety-net primary care under-represented (inherited by §1.5).
- Spanish material is largely *translated* patient education, not transcribed natural Spanish speech —
  it teaches written register better than spoken register. This is the most consequential single bias in the
  seed layer for a system that trains *spoken* interpreting.
- Indigenous languages absent entirely.
- De-identified corpora have flattened demographic and temporal detail, which removes some of the exact
  cues (ages, dates, durations) that a fidelity trainer most wants to exercise. The term manifest supplies
  those synthetically instead.

### 2.6 Sensitivity, storage, retention, access, licence

| Property | Value |
|---|---|
| Sensitivity | **Low–medium.** Public and de-identified, but treated as untrusted and unpublished |
| Storage | `data/scenarios/sources/` — **git-ignored**, local only, rebuildable |
| Retention | Kept while the bank is being developed; `make clean-sources` removes them. No requirement to retain |
| Access | Local machine only |
| Licence / redistribution | Per-source, recorded in the sidecar. **We redistribute none of it.** Derived scenarios are redistributable only where the source licence permits derived works without share-alike — which the allowlist guarantees by construction (rule 4) |

---

## 3. The calibration set

### 3.1 Purpose

The external anchor. 40 interpreting turns hand-labelled by a human against the error taxonomy.
It is the only reason any accuracy claim in this project means anything: grader agreement is measured against
*human expert judgement*, not against another model's opinion. `SETUP.md` §6.1 makes the argument in full;
it is not repeated here.

Everything downstream depends on it: L4's Cohen's kappa, L10's before/after prompt-optimisation numbers, and
the honest ceiling that both are reported against.

### 3.2 Composition by bucket

Per `SETUP.md` §6.4:

| Bucket | Count | What it measures |
|---|---|---|
| Clean, correct renderings | 12 | False-positive rate. A grader that flags these is unusable regardless of its recall |
| Single critical error (dosage, negation, frequency, laterality, allergy) | 10 | Critical recall — the headline safety metric |
| Single non-critical error (register, first-person, mild omission) | 10 | Discrimination, not merely "something broke" |
| Multiple simultaneous errors | 4 | Real interpreting fails in clusters; tests that the grader does not stop at the first finding |
| Genuinely ambiguous / borderline | 4 | The honest ceiling. Where humans disagree, the grader is not expected to do better |
| **Total** | **40** | |

The 12 clean items are the bucket most often omitted from home-made eval sets and the one that most often
kills a scorer in practice. They are non-negotiable.

### 3.3 Labelling protocol

**Defined in `SETUP.md` §6.5. Follow it there; it is not duplicated here.** The four rules that this card
exists to enforce as *data properties*:

- Labelled **blind** — the human's label is committed before the model's output for that item is seen.
- Labelled against the **published standard** (NCIHC / CHIA, taxonomy in `docs/01-research.md`), not taste.
- Severity assigned by **clinical consequence**, not by how wrong it feels.
- A `confidence` field (`sure` / `unsure`) is recorded per item, and `unsure` items are analysed separately
  as the ceiling rather than counted as model failures.

### 3.4 Schema

Label schema: `SETUP.md` §6.3. On-disk form:

```jsonc
// one line of data/calibration/dev.jsonl
{
  "item_id": "cal-017",
  "schema_version": "calibration/v2",
  "bucket": "single_critical",
  "direction": "en->es",
  "source_utterance": "Take one 500 milligram tablet twice a day, and do not take it on an empty stomach.",
  "trainee_rendering": "Tome una pastilla de 500 miligramos al día, y tómela con el estómago vacío.",
  "labels": [
    { "kind": "substitution", "severity": "critical",
      "src_span": [37, 49], "span": [30, 36],
      "note": "frequency twice a day rendered as al día" },
    { "kind": "distortion", "severity": "critical",
      "src_span": [55, 89], "span": [42, 74],
      "note": "negation dropped; instruction inverted" }
  ],
  "confidence": "sure",
  "seeded_intent": ["frequency_substitution"],   // what was intended; NEVER the label
  "labeller": "kn",
  "labelled_at": "…",
  "relabel_pass": 1
}
```

`seeded_intent` is recorded and deliberately *not* used as the label — per `SETUP.md` §6.4, seeding one error
often produces two, and the label is what is actually there. Any evaluation code that reads `seeded_intent`
as a target is a bug; CI checks for it (§7).

### 3.5 Split and sealed status

```
data/calibration/
├── dev.jsonl          # 25 items — optimisation, development, iteration
├── test.jsonl         # 15 items — SEALED
├── CHANGELOG.md       # every label correction, with reason
├── SEAL.md            # unseal log: who, why, which run cited it
└── raw/               # git-ignored; original recordings and renderings
```

| Property | dev.jsonl | test.jsonl |
|---|---|---|
| Items | 25 | 15 |
| Used for prompt optimisation (L10) | Yes | **Never** |
| Used for iteration and error analysis | Yes | No |
| Read during `make evals` | Yes | **No — the harness refuses** |
| Read when | Any time | Only to produce a final reported number |
| Unseal record required | No | **Yes** — `eval_runs.unseal_reason` is NOT NULL for `split='test'` (`docs/08-evals.md`) |

Sealing is enforced in three independent places, because a rule enforced only by discipline is not enforced:

1. `make evals` refuses to touch `test.jsonl` at all.
2. The eval harness requires an explicit `--unseal-reason` to read it, recorded in `eval_runs`.
3. `dataset_sha256` is recorded on every run, so a silent edit to the test split invalidates every prior
   citation of it rather than passing unnoticed.

### 3.6 The prohibition

> **The calibration set must never be model-labelled. Not partially, not "to bootstrap", not "and then a
> human checks it".**

Human-checking a model's labels is not the same operation as labelling blind. It is anchoring: the reviewer
rationalises the model's choice, agreement rises, and the measured agreement becomes a measurement of the
model's influence on the human rather than of the model's accuracy. `SETUP.md` §6.5 rule 2 exists for this
and is the single rule whose violation cannot be detected after the fact from the data — which is precisely
why it is stated as a prohibition rather than a check.

Corollaries, all [decided]:

- No LLM-assisted pre-filling of labels, spans, or severities.
- No expansion of the set with synthetically labelled items to "get to 100".
- If the set is ever expanded, the new items are labelled by the same blind human protocol and the split is
  re-declared before any result is looked at. Expansion is a new dataset version, not an edit.
- An LLM-as-judge, if ever introduced elsewhere in the project, is calibrated *against* this set. It never
  contributes to it.

### 3.7 Provenance and change-log discipline

| Property | Value |
|---|---|
| Source utterances | Generated by the system from the scenario bank — ground truth by construction |
| Renderings | Produced by a human interpreting the source, with error types deliberately seeded (`SETUP.md` §6.4) |
| Labels | Human, blind, against the published standard |
| Labellers | `kn` (all 40). Second labeller on ≥15 items for inter-rater agreement: **[open], not yet done** |
| Immutability | Frozen once labelled. A label is never silently edited |
| Change log | Every correction appends to `data/calibration/CHANGELOG.md`: item id, old label, new label, reason, date, who. A metric computed before a change and one computed after are different numbers over different datasets, and are reported as such |
| Integrity | `dataset_sha256` in every `eval_runs` row detects any edit, logged or not |

### 3.8 Known biases and gaps — stated plainly

This is the project's most important dataset and its most limited one. Honest reporting (principle 7) means
the limitations are part of the asset, not a caveat appended to it.

| Limitation | Consequence for every number derived from it |
|---|---|
| **n = 40; test split n = 15** | Confidence intervals on test-split agreement are wide. A test-split kappa must always be reported with its interval, never as a point estimate. A 15-item split cannot distinguish small improvements from noise, and no claim to that effect will be made |
| **Single labeller** | The set encodes one person's application of the standard. Intra-rater agreement (`SETUP.md` §6.5 rule 6) bounds it; inter-rater agreement, which would bound it far better, does not yet exist |
| **The labeller is the project author** | Not blind to the system's design. The blind-labelling protocol mitigates per-item contamination; it does not mitigate the labeller's overall theory of what errors matter, which is the same theory the scorer implements |
| **Renderings are seeded, not naturally occurring** | Error distribution reflects what was deliberately constructed, not the empirical distribution of trainee errors. Recall measured here is recall on constructed errors |
| **Spanish register is one speaker's** | Regional and dialectal variation is not represented |
| **No indigenous-language items** | See §1.5 |
| **Ambiguous bucket is 4 items** | The honest ceiling is itself estimated from 4 items and is correspondingly imprecise |

### 3.9 Sensitivity, storage, retention, access, licence

| Property | Value |
|---|---|
| Sensitivity | **Medium.** No PHI (sources are synthetic), but the labels are the project's credibility and the raw audio contains an identifiable human voice |
| Storage | `dev.jsonl`, `test.jsonl`, `CHANGELOG.md`, `SEAL.md` committed to the repository. `data/calibration/raw/` git-ignored, local only |
| Retention | Indefinite for labels — they are the audit trail for every published number. `raw/` may be deleted once renderings are transcribed and hashed |
| Access | Repository read access for labels. `raw/` audio: labeller only |
| Licence / redistribution | Labels are project-licensed and redistributable [decided] — publishing the calibration set is the strongest possible support for the project's claims. `raw/` audio is **not** redistributable: consent for redistribution of a recorded voice has not been obtained. **[open]**: publishing `test.jsonl` publicly would end its usefulness as a sealed split for future work; the current position is that it is published only alongside the final reported number, not before |

---

## 4. Session data

### 4.1 Purpose

The record of what a trainee did. It drives the debrief, the trainer review, the learner model, and the L7
completion / override evals. It is also the most sensitive data the system holds and the only data that
concerns a real, identifiable person.

### 4.2 What is captured

| Captured | Where | Why it must exist |
|---|---|---|
| Event log — every state transition, seed draw, degradation, turn boundary, verdict | `events` table | The event log is the truth; every other table is a rebuildable projection (`docs/03-system-architecture.md` §10.1) |
| Session record | `sessions` | Which scenario, which seeds, which models, which prompt version |
| Per-turn record | `turns` | Direction, node, seed, and content hashes for source / rendering / audio |
| Verdicts and findings | `verdicts`, `findings` | The score, keyed idempotently so re-scoring cannot silently rewrite history |
| Trainer / trainee reviews | `reviews` | Overrides are appended as new facts, never mutations — which is what makes trainer-override rate measurable |
| Learner model state | `learner_state` | Per-category EWMA; deterministic arithmetic, not a model |
| Trainee rendering audio | `blobs/` (opus, 16 kHz mono) | Debrief playback and any later re-transcription |
| Canonical source text, canonical rendering text, assembled grader input | `blobs/` | A verdict provably refers to *the same strings* it was computed over |
| Synthesised TTS audio | **Not stored** [decided] | Regenerable from source text + voice id; it is the bulk of the bytes |

Full DDL: `docs/03-system-architecture.md` §10.4. Blob layout and verification: §10.5.

### 4.3 Provenance and collection method

Generated at runtime by the trainee's own use. There is no background collection, no telemetry, no analytics
beacon, and no network egress in the core loop — the models are local (`SETUP.md` §4), so a session that
produces this data never contacts a server.

### 4.4 Where it lives

```
~/.rehearsal/
├── rehearsal.db              # SQLite, WAL
├── blobs/sha256/ab/cd/…      # content-addressed, write-once
├── logs/                     # operator JSONL logs — droppable, NOT the event log
└── exports/                  # human-initiated, redacted
```

Outside the repository, git-ignored by construction, never synced.

### 4.5 Ownership, retention, deletion

| Question | Answer [decided] |
|---|---|
| Who owns it? | The trainee. It is their performance record, on their machine |
| Default retention | Indefinite locally, because the trainee owns the machine and deletion is their call, not ours |
| How is it deleted? | `rehearsal gc --dry-run` lists unreferenced blobs; deletion requires a second explicit invocation. A whole session is deleted with `rehearsal session delete <session_id> --confirm`, which removes the events, the projections and the blobs no other session references |
| Is deletion complete? | Yes for the session's own data. It is a genuine delete, not a tombstone. The one honest caveat: SQLite WAL and free-page reuse mean bytes may persist on disk until vacuumed; `rehearsal session delete` runs `VACUUM` for this reason |
| Can a trainer delete a trainee's data? | No. There is no multi-tenant model and no administrative delete. Horizontal multi-tenant fleet operation is explicitly out of scope |
| Institutional retention policy | **[open].** A training program deploying this will have its own retention requirements. The current design assumes single-machine, trainee-owned data and does not implement policy-driven expiry |
| Export | Human-initiated only, to `~/.rehearsal/exports/`, through a redaction pass (`docs/03-system-architecture.md` §12, boundary B7) |

### 4.6 Sensitivity, biases, access, licence

| Property | Value |
|---|---|
| Sensitivity | **High.** Contains an identifiable human voice and an assessment of a named person's professional competence. Treat it as employment-adjacent personal data even though it contains no PHI |
| PHI | None. Every clinical fact in a session originates from a synthetic scenario. This is a deliberate architectural property: no real encounter is ever recorded |
| Access | The local user. The API binds `127.0.0.1` only; `GET /api/blobs/{sha256}` is loopback-only and hash-verified |
| Known biases | Session data reflects who used the system, which is currently a very small and non-representative set of trainees. Any aggregate computed from it (difficulty calibration, error base rates) is anecdote until the n justifies otherwise, and will be reported as rates with intervals, never as findings |
| Second bias worth naming | Verdicts in session data are **model output that a human has not necessarily reviewed**. Unreviewed verdicts are not evidence of trainee performance and must never be aggregated as if they were. The `reviews` table is what distinguishes the two |
| Licence / redistribution | **Not redistributable.** No consent framework exists for sharing a trainee's recorded voice or performance record. Sharing requires explicit per-session human action through the redacted export path |

---

## 5. Evaluation run records

### 5.1 Purpose

Principle 6 says every layer ships its own eval number; principle 7 says those numbers are reported honestly.
This asset is what makes both auditable. An eval run record captures the full environment a number was
produced in, so that "the grader scores 0.81 kappa" is a citable claim with a commit, a model hash, a prompt
hash, a dataset hash and a seed behind it — rather than a remembered result.

### 5.2 Schema reference

Authoritative: `docs/08-evals.md` (the `eval_runs` DDL, the gate semantics, the per-eval definitions). The
properties that matter to this card:

| Property | Mechanism |
|---|---|
| Append-only | Enforced by SQLite triggers `eval_runs_no_update` / `eval_runs_no_delete`, not by discipline |
| Reproducible | `git_commit`, `seed`, `temperature`, `top_p`, `max_tokens`, `model_sha256`, `runtime`, `host_class` all recorded |
| Un-citable when dirty | `git_dirty = 1` marks a run that may never be cited |
| Dataset-pinned | `dataset_path` + `dataset_sha256` — a silent label edit invalidates the citation rather than passing unnoticed |
| Seal-aware | `split = 'test'` requires `unseal_reason` |
| Uncertainty carried | `intervals_json` alongside `metrics_json`; a metric without its interval is an incomplete record |
| Survives the database | JSON mirror per run at `data/evals/runs/<run_id>.json`, readable in review diffs |

```
data/evals/
├── registry.db               # append-only eval_runs
└── runs/<run_id>.json        # per-run mirror, ULID-named, lexicographically ordered
```

### 5.3 Provenance, biases, sensitivity, retention

| Property | Value |
|---|---|
| Provenance | Machine-generated by `make evals` and `uv run rehearsal-evals run …` |
| Collection | Automatic on every eval invocation. There is no way to run an eval without producing a record |
| Known biases | Records are only as representative as the datasets they ran over — inheriting every limitation in §3.8. A record is evidence about a measurement, never evidence about the world |
| Second bias | Runs are produced on one host class (`apple-silicon-48gb`). Latency and throughput numbers do not generalise to other hardware and are labelled with `host_class` for exactly that reason |
| Sensitivity | **Low**, with one caveat: a run over live session data could embed trainee-derived content in `artifact_path`. Live-split artefacts stay under `~/.rehearsal/`, not in the repository |
| Storage | `data/evals/` in the repository (fixture / dev / test splits). Live and replay splits write artefacts under `~/.rehearsal/` |
| Retention | Indefinite. Deleting an eval record deletes the basis of a published claim; the append-only triggers make it impossible without dropping the table |
| Access | Repository read access |
| Licence / redistribution | Project-licensed, fully redistributable. Publishing these records is the point |

---

## 6. Summary table

| Asset | Provenance | Sensitivity | Retention | Redistributable |
|---|---|---|---|---|
| Scenario bank (`data/scenarios/bank.jsonl`) | Model-generated from public seeds, human-reviewed; plus hand-authored scenarios | Low — fully synthetic, no PHI | Indefinite, git-versioned | **Yes**, under the project licence (allowlist guarantees no share-alike upstream) |
| Public seed corpora (`data/scenarios/sources/`) | Third-party public, de-identified; ingested under an allowlist | Low–medium — public but untrusted | While building the bank; `make clean-sources` removes | **No** — we redistribute no source material; derived scenarios only |
| Calibration labels (`dev.jsonl`, `test.jsonl`) | Human, blind, against NCIHC/CHIA; never model-labelled | Medium — the project's credibility | Indefinite — audit trail for every number | **Yes** for labels; `test.jsonl` publication timing **[open]** |
| Calibration raw audio (`data/calibration/raw/`) | Human-recorded renderings | Medium-high — identifiable voice | Deletable after transcription + hashing | **No** — no redistribution consent |
| Session data (`~/.rehearsal/rehearsal.db`, `blobs/`) | Trainee runtime, local only, no telemetry | **High** — identifiable voice + competence assessment | Trainee-controlled; indefinite by default; `rehearsal session delete` | **No** — export is human-initiated and redacted |
| Eval run records (`data/evals/`) | Machine-generated by the eval harness | Low (live-split artefacts stay local) | Indefinite, append-only | **Yes** — publishing them is the point |

---

## 7. Data-quality checks that run in CI

All are deterministic. All fail the build rather than warn — a warning in a data pipeline is a defect that
ships.

| Check | Command | Applies to | Fails when |
|---|---|---|---|
| Scenario schema validation | `make scenarios` | Bank | Any scenario violates `scenario/v3` |
| Fact-id integrity | `make scenarios` | Bank | A graph node references a term-manifest id that does not exist |
| Bilingual coverage | `make scenarios` | Bank | A term-manifest entry is missing its `en` or `es` surface form |
| Dose/unit plausibility | `make scenarios` | Bank | A dose falls outside a configured plausibility range for its unit, or a unit is unrecognised |
| Identifier scrub | `make scenarios` | Sources + generated scenarios | Any identifier-shaped string survives into ingested or generated text |
| Licence sidecar presence | `make scenarios` | Sources | A source file has no `<name>.license.json`, or its licence is not on the allowlist |
| Bank hash freshness | `make check-data` | Bank | `bank.sha256` does not match `bank.jsonl` |
| Review-gate integrity | `make check-data` | Bank | A scenario's content hash differs from its `review_sha256`, i.e. it was edited after review |
| Diversity report | `make scenarios` | Bank | Report-only: lexical diversity and motif-collision rates are printed and diffed; a collapse is visible rather than silent |
| Calibration schema validation | `make check-data` | dev + test | Any item violates `calibration/v2` |
| Bucket-count assertion | `make check-data` | dev + test | Bucket counts drift from 12 / 10 / 10 / 4 / 4, or the split is not 25 / 15 |
| Span integrity | `make check-data` | dev + test | A label span falls outside its utterance, or `src_span` is absent on an `omission` |
| Severity vocabulary | `make check-data` | dev + test | A severity is not `critical` \| `non-critical`, or a kind is outside the taxonomy |
| Split disjointness | `make check-data` | dev + test | Any `item_id` or `source_utterance` appears in both splits |
| `seeded_intent` leakage | `make check-data` | Repository | Any code outside the label-authoring tool reads `seeded_intent` |
| Seal guard | `make evals` | test split | The harness attempts to read `test.jsonl` without an explicit unseal reason |
| Dataset-hash pinning | `make evals` | Eval records | A run's `dataset_sha256` does not match the file it names |
| Changelog discipline | `make check-data` | Calibration | A label differs from its last committed value with no corresponding `CHANGELOG.md` entry |
| Dirty-run guard | `make evals` | Eval records | A gated run is attempted with uncommitted changes (`git_dirty = 1`) |
| Session-data absence | CI | Repository | Anything under `~/.rehearsal/`-shaped paths, or any `.opus`, is staged for commit |

`make check-data` is a distinct target from `make evals` deliberately: data integrity is checkable without
loading a model, so it runs on every commit while the eval suite does not.

---

## 8. Honest statement of the gaps

Ordered by how much they should change a reader's confidence.

1. **The calibration set is n = 40, single-labeller, and the labeller is the project author.** Every accuracy
   claim inherits this. Inter-rater agreement — the number that would most improve the project's credibility —
   does not exist yet. Engaging a certified interpreter to label 15 items is the single highest-value
   outstanding data task. Until then, agreement is reported against intra-rater consistency as the ceiling,
   with intervals, and described as one person's application of the standard.
2. **The sealed test split is 15 items.** It can distinguish a large improvement from nothing. It cannot
   distinguish a small improvement from noise, and no claim will be made that it can.
3. **No bilingual or clinical reviewer has signed off the scenario bank.** The Spanish is model-generated and
   reviewed by a non-native speaker; the clinical content is reviewed by a non-clinician. A trainee could
   currently practise against Spanish that is subtly unnatural or clinical content that is subtly wrong, and
   the system would not know.
4. **Indigenous languages are absent.** Mixteco and Triqui speakers are a substantial part of the population
   the served clinics actually see. The system does not address them, does not simulate relay interpreting,
   and must not be described as covering the region's interpreting need. This is a scope boundary, not an
   oversight — but it is the gap most likely to be mistaken for coverage.
5. **Seeded errors are not observed errors.** The calibration set's error distribution was constructed. Recall
   on it is recall on constructed errors. Whether it predicts recall on the errors real trainees actually make
   is untested and requires session volume we do not have.
6. **Declared difficulty is uncalibrated.** Difficulty labels are authorial judgement, not measurement.
7. **Spoken-Spanish register is under-sourced.** The Spanish seed material is predominantly translated written
   patient education. For a system that trains *spoken* interpreting, this is a real mismatch between the
   realism source and the target task.
8. **Session data is n≈0 and non-representative.** Nothing aggregate should be computed from it yet, and the
   L7 completion and override rates will be reported as raw counts with intervals until the denominator
   justifies a rate.
9. **No institutional retention or multi-user data policy.** The design assumes one trainee, one machine, one
   owner. A training program with record-keeping obligations would need a policy layer that does not exist,
   and building one is out of scope for the current system.

None of these are blockers for the system doing what it claims. All of them are reasons a specific number
should be read with a specific amount of caution, which is the only reason to write them down.

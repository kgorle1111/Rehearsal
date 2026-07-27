# 07 — Data & Scenario Bank

**How clinical realism is produced without inventing medicine.**

---

## 1. The thesis of this document

Rehearsal has to sound like a real clinic and must never assert a clinical fact it cannot vouch for. Those two requirements pull in opposite directions, and the whole data design is the resolution:

> **Public data grounds REALISM. Construction grounds TRUTH.**
> Corpora teach us how a rushed family-medicine clinician phrases a follow-up question, how a patient describes chest tightness in Pajaro Valley Spanish, and which drugs actually appear in a diabetes visit. They never become the content of a scenario. Every clinical fact a trainee is scored against — every dose, every frequency, every allergy, every negation, every laterality marker, every onset date — is **authored into the scenario record and then verbalised**, never generated free-hand at runtime and never lifted from a source document.

That is architectural principle 2 (ground truth by construction) applied to the content plane. The scoring engine (`docs/06-scoring-engine.md`) can say "the source contained *500 mg cada ocho horas* and the rendering contains no frequency" with certainty rather than opinion **only because** the frequency was a field in a record before it was ever a sentence.

Two consequences that run through everything below:

1. The patient agent is a **verbaliser of state**, not a clinical author. Section 5 gives the enforcement and the tests.
2. Ingested corpus text is **untrusted data**, even though we chose the corpus — it enters prompts through delimited data slots only, never as instructions (`docs/03-system-architecture.md` §12, boundary B3).

**What this document does not cover:** how findings are produced from a source/rendering pair (`docs/06-scoring-engine.md`), how the calibration set is labelled (`SETUP.md` §6 — the protocol lives there and is not duplicated here), the eval numbers computed over this data (`docs/08-evals.md`), or storage encryption and threat model (`docs/12-security-privacy.md`).

---

## 2. The three data classes

Every byte in the system belongs to exactly one class. The classes differ in **provenance** (who authored it), **trust** (may it influence control flow), **mutability**, and **exit rules** (may it leave the machine).

| | **A — Public seed corpora** | **B — Generated scenarios** | **C — Session & calibration data** |
|---|---|---|---|
| **Provenance** | Third parties, downloaded | Composer agent + human reviewer | The trainee, the running system, the human labeller |
| **What it is** | Clinical dialogue transcripts, drug labels, terminology, lay-language corpora | Scenario records, clinical state graphs, term manifests | Audio blobs, transcripts, findings, learner model, 40 calibration labels |
| **Lives at** | `data/corpora/` (git-ignored) | `data/scenarios/` (**committed**) | `~/.rehearsal/` (git-ignored, never committed) |
| **Trust level** | **Untrusted data.** Delimited slots only | **Reviewed data.** Facts are authoritative; free text is still data | **Untrusted data** (trainee speech is user input) |
| **Grounds** | Realism: phrasing, register, frequency-of-occurrence, terminology | **Truth**: the ground-truth facts scoring compares against | The measurement itself |
| **Mutability** | Immutable once pinned (hash + licence lock) | Immutable once merged; changes are a new `scenario_version` | Append-only event log; projections rebuildable |
| **Enters a model prompt?** | Only at compose time, in a `<corpus_excerpt>` slot, and only for the composer | Yes — the agents see their **partition** of it (`docs/03-system-architecture.md` §12) | Trainee rendering goes to the grader only, off the critical path |
| **PHI risk** | Screened at ingestion; anything not verifiably de-identified or synthetic is rejected | None by construction — synthetic people | **Trainee voice is personal data**; §11 |
| **May leave the machine** | It already came from outside | Yes (scenarios are shareable content) | **No.** No network egress path exists in the runtime |
| **Deletion** | `make corpora-clean` | Git history | `rehearsal forget` (§11) — hard delete, audited |

The clean separation is what lets us make the two claims that matter simultaneously: *"a real interpreter would recognise this encounter"* (class A did that) and *"we know exactly what was said"* (class B did that). Class C is what we measure, and it is the class with the only real privacy surface.

---

## 3. The clinical state schema

A scenario carries a **clinical state**: the complete, closed world of one synthetic patient. The patient agent may verbalise anything in it that the current graph node permits, and may say nothing clinical that is not in it.

### 3.1 Design rules

| Rule | Why |
|---|---|
| Every clinically-decidable value is a **structured field**, never prose | Extractors need a machine-readable ground truth; a sentence is not a ground truth |
| Every fact carries `surface_forms.en` and `surface_forms.es` | The term manifest is built from these; cross-lingual normalisation is not inferred at runtime |
| Every fact carries a `gate` (which graph node must be reached before it may be spoken) | `no_premature_disclosure` in `docs/08-evals.md` EV-04 is checkable only against an explicit gate |
| Dosing is `{value, unit, route, frequency_per_day, prn}` — never a free string | "500 mg every 8 hours" has four independently droppable components; four fields, four checks |
| Nothing is optional-by-omission | A missing `allergies` list and an empty one mean different things; `allergies: []` with `allergies_asked: true` is explicit |
| Free-text fields exist but are **non-authoritative** | `note` fields help the reviewer; no extractor and no score ever reads them |

### 3.2 Schema

```jsonc
// data/scenarios/<scenario_id>.json  →  "clinical_state"
// JSON Schema: data/schema/clinical_state.schema.json  (draft 2020-12)
{
  "schema_version": "1.0.0",

  "patient": {
    "given_name": "Rosa",              // synthetic; §9.4 name-source rule
    "family_name": "Delgado",
    "age_years": 54,                   // integer 0..110
    "sex_at_birth": "female",          // female | male | intersex
    "gender": "woman",                 // free label, non-authoritative
    "occupation": "strawberry harvest crew, Pajaro Valley",
    "insurance_status": "medi_cal",    // uninsured | medi_cal | medicare | commercial | unknown
    "accompanied_by": "adult_daughter" // none | adult_child | minor_child | spouse | other
  },

  "language": {
    "primary": "es",                             // BCP-47 primary subtag
    "variety": "es-MX-rural-central",            // controlled vocab, §3.4
    "english_proficiency": "minimal",            // none | minimal | conversational
    "literacy_level": "low",                     // low | moderate | high  (print literacy)
    "health_literacy": "low",                    // low | moderate | high  (§3.5)
    "code_switching": {
      "enabled": true,
      "max_english_token_ratio": 0.08,           // hard bound; EV-04 language_discipline uses this
      "allowed_borrowings": ["troca", "yarda", "la app", "el chequeo"]
    },
    "indigenous_language_context": {             // §3.6 — realism only, never simulated
      "present": false,
      "language": null,                          // mixteco_alto | mixteco_bajo | triqui | null
      "note": null
    }
  },

  "presenting_problem": {
    "chief_complaint": {
      "surface_forms": {
        "es": ["me duele el pecho cuando camino rápido"],
        "en": ["chest pain when walking fast"]
      },
      "concept_code": { "system": "ICD-10-CM", "code": "R07.9" }   // §9.3 coding rule
    },
    "onset": {
      "value": 3, "unit": "weeks",               // temporal marker → critical error class
      "qualifier": "gradual",                    // sudden | gradual | intermittent | unknown
      "surface_forms": { "es": ["hace tres semanas"], "en": ["three weeks ago"] }
    },
    "laterality": "not_applicable",              // left | right | bilateral | not_applicable
    "severity_0_10": 6,
    "aggravating": ["exertion", "cold_air"],
    "relieving": ["rest"]
  },

  "conditions": [
    {
      "id": "cond_dm2",
      "label": { "en": "type 2 diabetes", "es": "diabetes tipo 2" },
      "concept_code": { "system": "ICD-10-CM", "code": "E11.9" },
      "status": "active",                        // active | resolved | suspected
      "diagnosed": { "value": 6, "unit": "years" },
      "control": "poor",                          // good | fair | poor | unknown
      "gate": "hx_conditions",                    // node id that must be reached first
      "patient_knows_diagnosis": true,
      "patient_words": {                          // how THIS patient says it, low health literacy
        "es": ["el azúcar", "azúcar alta"],
        "en": ["sugar", "high sugar"]
      }
    }
  ],

  "medications": [
    {
      "id": "med_metformin",
      "ingredient": "metformin",
      "brand": null,
      "rxnorm_cui": "6809",                       // §9.3 — identifier only, not a dosing source
      "dose": { "value": 500, "unit": "mg" },
      "route": "oral",
      "frequency_per_day": 2,
      "frequency_phrase": {
        "en": ["twice a day", "two times a day"],
        "es": ["dos veces al día", "cada doce horas"]
      },
      "prn": false,
      "duration": { "value": 4, "unit": "years" },
      "adherence": "partial",                     // full | partial | none | unknown
      "adherence_reason": "runs out before payday",
      "gate": "hx_meds",
      "critical": true                            // participates in the critical error class
    }
  ],

  "allergies": [
    {
      "id": "alg_pcn",
      "substance": "penicillin",
      "rxnorm_cui": "7980",
      "reaction": { "en": "rash and swelling", "es": "ronchas e hinchazón" },
      "severity": "moderate",                     // mild | moderate | severe | anaphylaxis
      "gate": "hx_allergies",
      "critical": true
    }
  ],
  "allergies_asked": true,                        // distinguishes "none" from "not established"

  "vitals": {                                     // clinician-side facts; the clinician agent may state these
    "bp_systolic": 148, "bp_diastolic": 92,
    "hr_bpm": 88, "temp_c": 36.8,
    "spo2_pct": 97, "weight_kg": 78.0,
    "measured_at_node": "vitals_review"
  },

  "symptom_timeline": [                           // ordered; the patient may only reveal reached entries
    {
      "id": "tl_1",
      "offset": { "value": 3, "unit": "weeks", "direction": "before_visit" },
      "event": { "en": "chest tightness on hills", "es": "opresión en el pecho en las subidas" },
      "gate": "hpi_onset"
    },
    {
      "id": "tl_2",
      "offset": { "value": 4, "unit": "days", "direction": "before_visit" },
      "event": { "en": "woke at night short of breath, twice", "es": "despertó dos noches sin aire" },
      "gate": "hpi_progression",
      "critical": true                            // numeric + temporal → hard-checked
    }
  ],

  "emotional_state": {
    "baseline": "worried",                        // §3.3 controlled vocabulary
    "arc": [
      { "at_node": "hpi_onset",     "state": "worried",  "intensity": 2 },
      { "at_node": "plan_referral", "state": "fearful",  "intensity": 4,
        "trigger": "cost and missing work" }
    ],
    "expression": {
      "verbal": ["shorter sentences", "repeats the cost question"],
      "prosodic": ["slower rate", "trailing off"],   // consumed by TTS, docs/05-voice-pipeline.md
      "never": ["shouting", "crying that blocks the turn"]  // realism floor, not a content rule
    }
  },

  "social_context": {
    "transport": "relies on a ride from a coworker",
    "work_flexibility": "loses the day's pay if absent",
    "childcare": "none needed",
    "immigration_disclosure": "not_discussed",     // never a scenario topic unless authored + reviewed
    "note": "Grounds realistic barrier talk. No fact here is scored."
  },

  "knowledge_boundary": {
    "knows": ["med_metformin", "cond_dm2", "alg_pcn"],
    "does_not_know": ["ejection fraction", "what a stress test is", "her HbA1c number"],
    "will_misname": [
      { "concept": "electrocardiogram", "patient_says_es": "la máquina del corazón" }
    ]
  },

  "forbidden_moves": [
    "state a lab value not present in this record",
    "name a medication not in medications[]",
    "self-diagnose with a condition not in conditions[]",
    "volunteer any fact whose gate node has not been reached",
    "speak English beyond language.code_switching bounds",
    "reference the interpreter's performance or any rubric vocabulary"
  ]
}
```

### 3.3 Controlled vocabularies

| Field | Values | Notes |
|---|---|---|
| `emotional_state.baseline` / `arc[].state` | `calm` `worried` `fearful` `frustrated` `embarrassed` `resigned` `hopeful` `distracted` `in_pain` | 9 values, closed set; the composer may not invent one |
| `arc[].intensity` | `1`–`5` | Drives the `emotional_load` difficulty axis (§8) and TTS prosody |
| `health_literacy` | `low` `moderate` `high` | Determines lexical register, not intelligence — see §3.5 |
| `conditions[].status` | `active` `resolved` `suspected` | `suspected` facts may never be verbalised as certain |

### 3.4 Language variety

`language.variety` is a closed vocabulary because it selects lexicon files, TTS voice parameters and idiom sets — a free string would silently fall back to defaults.

| Value | Population it represents | Lexicon file |
|---|---|---|
| `es-MX-rural-central` | Michoacán/Guanajuato-origin farmworker Spanish, the dominant Pajaro Valley variety | `data/lexicons/idiom.es-MX-rural-central.json` |
| `es-MX-urban` | Urban Mexican Spanish, higher formal register | `data/lexicons/idiom.es-MX-urban.json` |
| `es-US-heritage` | US-born heritage speaker; heavier code-switching, English medical terms retained | `data/lexicons/idiom.es-US-heritage.json` |
| `es-neutral` | Broadcast-neutral; the low-difficulty baseline | `data/lexicons/idiom.es-neutral.json` |

Each lexicon is a flat list of `{term_es, gloss_en, register, false_friend_of?}` entries, hand-curated and reviewed like a scenario. They serve two consumers: the composer (as vocabulary the patient may use) and the difficulty index (as the `idiom` feature's fixed lexicon, `docs/08-evals.md` §EV-05). **The same file must serve both**, otherwise difficulty is measured against a lexicon the content was not written from.

### 3.5 Health literacy is a register control, not a capability slur

`health_literacy: low` means the patient says *"el azúcar"* not *"glucosa en ayunas"* — it constrains **which surface form** of a known fact gets spoken. It never means the patient is confused, passive or incapable, and the composer prompt states this explicitly. Practically it is the main generator of `register_distance` difficulty (§8): the clinician says "we'll check your A1c", the patient says "la prueba de los tres meses", and the trainee has to bridge in both directions without editorialising.

### 3.6 Indigenous-language context — a deliberate limitation

Santa Cruz County's Mixteco- and Triqui-speaking farmworker communities are a real and under-served part of the population this product is aimed at (`docs/00-dossier.md` §2). **Rehearsal does not simulate Mixteco or Triqui speech.** We have neither the linguistic competence to author it nor a defensible way to score fidelity in a language we cannot verify, and a bad simulation of an under-served language is worse than its absence.

What the schema *does* support is the **realistic frame**: `indigenous_language_context.present: true` marks scenarios where the patient's Spanish is a second language — shorter clauses, narrower register, occasional non-target-like agreement — which is a genuine and common interpreting condition. This is authored as Spanish, reviewed by a human, and labelled honestly in the scenario's `provenance.limitations`. Stated as a named gap, not papered over. Any future relay-interpreting support is out of scope until a qualified speaker can review it.

---

## 4. The clinical state graph

The clinical state says *what is true*. The **state graph** says *what may be said, when, and by whom*. It is the object that makes the counterpart agents checkable (`docs/03-system-architecture.md` §9; EV-04 in `docs/08-evals.md`).

### 4.1 Node schema

```jsonc
// scenario.state_graph
{
  "entry": "greeting",
  "nodes": [
    {
      "id": "hx_meds",
      "speaker": "clinician",                 // clinician | patient
      "intent": "elicit_medication_list",     // closed vocab, §4.2
      "purpose_en": "Establish what she is actually taking and how consistently.",

      "must_convey": ["med_metformin.dose", "med_metformin.frequency_per_day"],
      "may_convey":  ["med_metformin.adherence_reason"],
      "must_not_convey": ["alg_pcn", "tl_2"],   // gated behind later nodes

      "persona_invariants": [
        "speaks English only",
        "addresses the patient in second person, never the interpreter",
        "does not simplify for the interpreter's benefit"
      ],

      "scripted_fallback": {
        "en": "What medicines are you taking right now, and how often do you take them?"
      },

      "difficulty_features": ["numeric_density", "register_distance"],
      "max_utterance_tokens": 55,
      "successors": [
        { "to": "hx_meds_probe", "when": "adherence_mentioned" },
        { "to": "hx_allergies",  "when": "default" }
      ],
      "terminal": false
    }
  ]
}
```

### 4.2 Intent vocabulary

Closed set; `docs/08-evals.md` EV-04 `state_edge_legal` is only meaningful against a closed set.

| Group | Intents |
|---|---|
| Opening | `greeting` `identify_participants` `interpreter_preamble` |
| History | `elicit_chief_complaint` `elicit_onset` `elicit_progression` `elicit_medication_list` `elicit_allergies` `elicit_social_context` |
| Examination | `announce_exam` `direct_physical_action` `report_vitals` |
| Explanation | `explain_finding` `explain_diagnosis` `explain_procedure` `deliver_serious_news` |
| Plan | `prescribe` `change_dose` `order_test` `refer` `schedule_followup` `safety_net_advice` |
| Patient-initiated | `ask_question` `express_concern` `raise_barrier` `decline` `request_repetition` |
| Closing | `teach_back` `confirm_understanding` `farewell` |

`prescribe`, `change_dose` and `safety_net_advice` nodes are automatically `critical: true` for scoring weight — they are where a dropped number changes clinical action.

### 4.3 Transition guards

`when` is a **deterministic predicate over the turn record**, evaluated in `src/rehearsal/content/graph.py` — never a model judgement. This is principle 1 at the content layer.

| Guard | Predicate |
|---|---|
| `default` | Always true; every node needs exactly one, checked at build time |
| `<fact_id>_mentioned` | The fact's `surface_forms` matched (normalised, accent- and case-insensitive) in the last counterpart utterance |
| `patient_asked_question` | The patient turn ended in an interrogative (punctuation + interrogative-lemma check) |
| `interpreter_requested_repetition` | Trainee turn matched the repetition-request pattern set |
| `turn_index_gte:<n>` | Sequence-position guard, for pacing |
| `emotional_state_at_least:<n>` | Current arc intensity ≥ n |

Guard evaluation order is declaration order; the first match wins; `default` must be last. `make scenarios` fails the build on: unreachable node, missing `default`, a `must_convey` fact whose `gate` is a node not dominating this one, or a cycle without a `turn_index_gte` escape.

---

## 5. Why the patient agent verbalises and never invents

### 5.1 The contract

The patient agent's job is **surface realisation of a fact it was handed**, in this patient's register, in this patient's emotional state, in this language variety. It performs no clinical reasoning and originates no clinical proposition.

| The agent decides | The record decides |
|---|---|
| Word choice, sentence length, hesitation, hedging | Every number, unit, frequency, route, date, duration |
| Which permitted fact to lead with | Which facts are permitted at all |
| Emotional colouring within the arc | The arc |
| Whether to answer directly or ask for clarification | Whether the answer exists |

This is not a stylistic preference — it is what makes the scoring defensible. If the patient invented "I take two of those little white pills, maybe 800 milligrams?", nobody knows the true dose, and every fidelity claim about that turn collapses. The term manifest (`docs/03-system-architecture.md` §9) is generated *with* the utterance request, not parsed *from* the utterance.

### 5.2 How it is enforced — four layers, only one of which is the prompt

| # | Layer | Mechanism | Failure mode it closes |
|---|---|---|---|
| 1 | **Context construction** | `ContextAssembler` passes only the facts whose gate is satisfied at the current node. Un-gated facts are physically absent from the prompt. | The agent cannot leak what it was never shown |
| 2 | **Structured output** | The agent returns `{utterance_es, facts_conveyed: [fact_id], state_transition}` — not free text. `facts_conveyed` is validated against the node's `must_convey ∪ may_convey`. | Silent smuggling of extra content |
| 3 | **Post-generation numeric audit** | `content/audit.py: audit_utterance(utterance, allowed_facts, manifest) -> list[Violation]` — every numeral, unit, dosage phrase, frequency phrase, laterality token and temporal marker in the generated text must resolve to an allowed fact's surface form. **Any unresolved numeric token is a hard violation.** | The classic failure: a fluent, plausible, *invented* dose |
| 4 | **Deterministic fallback** | On violation: one re-prompt with the violation named; on a second violation, the node's `scripted_fallback` is spoken verbatim and `agent.fallback_used` is appended to the event log. | The session degrades to scripted rather than to wrong |

Layer 3 is the load-bearing one, and it is deliberately over-strict: it rejects a *correct* number stated in an unregistered surface form (e.g. "half a gram" for 500 mg) rather than admitting an unregistered one. Registering an additional surface form is a scenario edit a human approves; loosening the audit is not an option. Rejections are counted — a scenario with a high fallback rate is a scenario with an incomplete surface-form list, and `make scenarios --report` surfaces it.

### 5.3 How it is tested

| Test | Location | Asserts | Blocks |
|---|---|---|---|
| `test_audit_rejects_unregistered_numeral` | `tests/content/test_audit.py` | An utterance containing `850 mg` against a 500 mg manifest yields a `Violation` | Every commit |
| `test_audit_accepts_all_registered_forms` | same | Every `surface_forms` entry in every committed scenario passes its own audit — no scenario can ship a fact its own audit rejects | Every commit |
| `test_gate_absent_facts_not_in_context` | `tests/runtime/test_context.py` | The assembled patient context contains no gated fact string before its gate node | Every commit |
| **EV-04 persona consistency** | `docs/08-evals.md` | ≥ 0.95 turn-level over seeded replay; `no_premature_disclosure` and `persona_facts_stable` are the relevant checks | Merging a scenario or an agent prompt |
| **Invention canary** | `evals/suites/ev04_persona.py` | Across the seeded replay set, count of unresolved numeric tokens must be **exactly 0** after fallback. Not a rate — a zero. | L5 rung sign-off |

The canary is a hard zero because the failure it detects is the one that invalidates the product's central claim. A 1% invention rate is not a quality issue; it is a 1% rate of scoring a trainee against a fiction.

### 5.4 The clinician agent

Same contract, mirrored: it verbalises the node's `must_convey` facts in clinical English register, and it is additionally forbidden from **accommodating the interpreter** — no pre-chunking, no simplification, no waiting for a nod. That prohibition is the behavioural half of information isolation (principle 4): an agent that knew it was being interpreted-for would help, and the training value would evaporate. The measurement of whether that leaks anyway is EV-05 in `docs/08-evals.md`.

---

## 6. The scenario schema

### 6.1 Full schema

```jsonc
// data/scenarios/sc_0042_chest_pain_dm2.json
// JSON Schema: data/schema/scenario.schema.json  (draft 2020-12)
{
  "schema_version": "1.0.0",
  "scenario_id": "sc_0042_chest_pain_dm2",      // ^sc_\d{4}_[a-z0-9_]+$ ; immutable
  "scenario_version": 3,                         // bumped on any content change
  "content_hash": "sha256:9f3c…",                // over the canonical JSON minus this field

  "title_en": "Exertional chest pain in a patient with poorly controlled type 2 diabetes",
  "title_es": "Dolor de pecho al esfuerzo en paciente con diabetes tipo 2 mal controlada",

  "setting": {
    "site_type": "fqhc_primary_care",            // fqhc_primary_care | urgent_care | ed | specialty | telephonic
    "region": "santa_cruz_county_ca",
    "encounter_type": "follow_up",               // new_patient | follow_up | acute | results_disclosure | discharge
    "modality": "in_person",                     // in_person | telephonic | video  (affects overlap difficulty)
    "expected_turns": 18                          // counterpart turns; drives session length estimates
  },

  "clinical_state": { /* §3 */ },
  "state_graph":    { /* §4 */ },

  "term_manifest": {                              // §7 — DERIVED, never hand-written
    "generated_by": "content.terms.build_manifest",
    "generator_version": "1.0.0",
    "entries": [
      { "fact_id": "med_metformin.dose",
        "kind": "dosage", "value": 500, "unit": "mg", "critical": true,
        "forms_en": ["500 milligrams", "500 mg", "five hundred milligrams"],
        "forms_es": ["500 miligramos", "500 mg", "quinientos miligramos"] },
      { "fact_id": "med_metformin.frequency_per_day",
        "kind": "frequency", "value": 2, "unit": "per_day", "critical": true,
        "forms_en": ["twice a day", "two times a day", "every twelve hours"],
        "forms_es": ["dos veces al día", "cada doce horas"] },
      { "fact_id": "alg_pcn.substance",
        "kind": "allergy", "value": "penicillin", "critical": true,
        "forms_en": ["penicillin"], "forms_es": ["penicilina"] },
      { "fact_id": "tl_2.offset",
        "kind": "temporal", "value": 4, "unit": "days", "critical": true,
        "forms_en": ["four days ago", "four nights ago"],
        "forms_es": ["hace cuatro días", "hace cuatro noches"] }
    ]
  },

  "difficulty": {                                 // §8 — authored axes 0..4
    "numeric_density": 3,
    "idiom_load": 2,
    "emotional_load": 3,
    "register_distance": 3,
    "overlap_pressure": 1,
    "computed_index": 2.55,                       // deterministic; recomputed at build, never hand-set
    "band": "intermediate"                        // introductory | intermediate | advanced | stress
  },

  "learning_objectives": [                        // shown to the trainee AFTER the session, never before
    "Preserve dose and frequency across a medication reconciliation",
    "Render a low-health-literacy symptom description without upgrading its register",
    "Maintain first person while the patient addresses the interpreter directly"
  ],

  "provenance": {
    "composed_by": "composer@1.2.0",
    "seed": 918273,
    "grounded_in": ["mts_dialog", "primock57", "dailymed_spl", "medlineplus_es"],
    "clinical_facts_source": "authored",          // ALWAYS "authored" — see §9.2
    "review": {
      "status": "approved",                       // draft | in_review | approved | retired
      "reviewer": "kn",
      "reviewer_role": "project_lead",
      "checklist_version": "1.1.0",
      "checklist_results": { /* §6.3 */ },
      "notes": "Softened the daughter's interruption at plan_referral; it made overlap unscoreable."
    },
    "limitations": [
      "Cardiac work-up depth is shallow; this is an interpreting exercise, not a cardiology case."
    ]
  },

  "retired": false,
  "retired_reason": null
}
```

### 6.2 What is deliberately absent

| Absent | Why |
|---|---|
| Pre-written counterpart dialogue | Fixed scripts are memorisable and destroy repeat practice value. The graph fixes *facts and order*; the agents produce wording |
| Any expected trainee rendering | There is no single correct interpretation. Scoring compares against **source meaning**, not a reference translation (`docs/06-scoring-engine.md`) |
| Rubric or taxonomy references | Principle 4. A scenario file is loaded into agent contexts; anything in it can leak |
| Real clinical guidance thresholds | We do not want a trainee learning medicine from us; the clinician agent's plan is realistic, not authoritative |

### 6.3 Review checklist (`checklist_version 1.1.0`)

Recorded as booleans in `provenance.review.checklist_results`, all of which must be `true` for `status: approved`.

| Key | Question |
|---|---|
| `facts_internally_consistent` | Do doses, frequencies, durations and timeline offsets agree with each other and with the vitals? |
| `dosing_plausible` | Is every dose within the labelled range for that ingredient/route? (checked against the DailyMed-derived table, §9.3) |
| `no_medical_advice_emitted` | Does no node instruct the patient to do something we would not want a real person to copy? |
| `graph_reachable` | Machine-checked, but the reviewer confirms the *clinical* order is sensible |
| `surface_forms_complete` | Does every critical fact carry at least two forms per language, including a spelled-out numeral form? |
| `register_authentic` | Would a Pajaro Valley Spanish speaker recognise this as a person, not a textbook? |
| `no_stereotype` | Is the social context specific rather than a demographic cliché? Would the reviewer show this to a promotora? |
| `no_phi_resemblance` | Does no name/DOB/address/MRN pattern resemble a real person or a real record? |
| `difficulty_honest` | Do the authored difficulty axes match what the graph actually contains? |
| `limitations_stated` | Are the scenario's clinical shortcuts written down rather than implied? |

---

## 7. The term manifest

The manifest is the **extractors' ground truth** and is produced *with* the scenario, never parsed *from* generated speech.

```python
# src/rehearsal/content/terms.py
def build_manifest(state: ClinicalState) -> TermManifest:
    """Derive every hard-checkable fact from the clinical state.

    Deterministic and total: every field marked critical=True in the schema
    yields exactly one manifest entry. Raises ManifestGapError if a critical
    field produces no entry — silence here would silently disable an extractor.
    """
```

| Manifest `kind` | Sourced from | Extractor that consumes it |
|---|---|---|
| `entities` | clinical named entities: drug names, substances, anatomical sites | `extractors/entities.py` |
| `number` | any bare integer/decimal in a conveyed fact | `extractors/numbers.py` |
| `dosage` | `medications[].dose` + `unit` + `route` | `extractors/dosage.py` |
| `frequency` | `medications[].frequency_per_day`, `prn` | `extractors/frequency.py` |
| `negation` | node-level `must_convey` polarity flags, e.g. *do not take with alcohol* | `extractors/negation.py` |
| `laterality` | `presenting_problem.laterality`, exam node targets | `extractors/laterality.py` |
| `allergy` | `allergies[].substance` | `extractors/allergy.py` |
| `temporal` | `onset`, `symptom_timeline[].offset`, `medications[].duration` | `extractors/temporal.py` |

Surface-form generation is rule-based, not model-generated: numerals expand to digit and spelled-out forms in both languages, frequencies expand through a fixed equivalence table (`2/day ⇄ "twice a day" ⇄ "cada doce horas"`), units expand through a fixed abbreviation table. **A model never authors a manifest entry**, because the manifest is the yardstick and a stochastic yardstick is not one.

---

## 8. The difficulty model

### 8.1 Five authored axes

Difficulty is authored on five axes, integer `0..4`, chosen because each maps to a distinct interpreting failure mode and each is independently observable in the transcript.

| Axis | What raises it | Failure mode it stresses | Countable proxy |
|---|---|---|---|
| `numeric_density` | Many doses/frequencies/dates per turn; multi-component regimens; unit changes mid-encounter | Dropped or transposed numbers — the critical class | manifest entries with `critical: true` per counterpart turn |
| `idiom_load` | Regionalisms, somatic idioms (*me cae mal la comida*, *tengo el azúcar alta*), false friends (*constipado*, *molestia*, *droga*) | `false_fluency`, `substitution` | lexicon hits per 100 tokens against the variety's idiom file |
| `emotional_load` | High arc intensity, bad news, cost/work barriers, an interrupting family member | `editorialization`, `role_exchange`, `first_person_violation` | max `arc[].intensity` × count of intensity ≥ 3 nodes |
| `register_distance` | Gap between clinician's technical register and patient's lay register | `register_shift`, `omission` of nuance | mean lexical-tier gap between paired clinician/patient nodes |
| `overlap_pressure` | Long unbroken utterances, no natural pause, speakers starting before the interpreter finishes, telephonic modality | Memory overload → wholesale `omission` | mean `max_utterance_tokens`; count of nodes with `allow_overlap: true` |

### 8.2 The computed index

```python
# src/rehearsal/content/difficulty.py
WEIGHTS = {                      # v1.0.0, versioned; changing them bumps the version
    "numeric_density":   0.30,
    "idiom_load":        0.15,
    "emotional_load":    0.20,
    "register_distance": 0.20,
    "overlap_pressure":  0.15,
}

def computed_index(axes: dict[str, int]) -> float:
    """Weighted mean of the five axes on 0..4. Deterministic; recomputed at
    build time and compared to the stored value — a mismatch fails the build."""
```

| Band | `computed_index` | Intended for |
|---|---|---|
| `introductory` | `0.00 – 1.24` | First sessions; establishes the false-alarm baseline for the learner model |
| `intermediate` | `1.25 – 2.49` | Working practice |
| `advanced` | `2.50 – 3.24` | Certification-style pressure |
| `stress` | `3.25 – 4.00` | Deliberate failure induction; the learner model down-weights these when estimating competence |

### 8.3 Two difficulty numbers, and why they are not the same one

| | **Authored difficulty** (this document) | **Measured difficulty index** (`docs/08-evals.md` EV-05) |
|---|---|---|
| Object | The scenario | A single generated utterance |
| Computed | At build time from the axes | At eval time from the produced text |
| Used for | Selection, banding, progression | Detecting rubric leakage |
| Weights | `content/difficulty.py` v1.0.0 | `evals/suites/ev05_leakage.py`, frozen before the run |

They share the *idea* and the idiom lexicon file, not the code path, and deliberately so: if the eval's difficulty measure were the same function the content was authored against, EV-05 would partly be measuring its own definition. Keeping them separate is what makes "the leaked agent made things easier" a finding rather than a tautology. **Open question:** whether the two should be correlated as a sanity check (they should agree loosely on the same scenarios) — proposed, not built.

### 8.4 Selection

`ScenarioBank.sample(difficulty, seed)` selects deterministically from the band, excluding scenarios seen within the trainee's last *N* sessions, seeded from the session's root seed so a session is reproducible (`docs/03-system-architecture.md` §7). Difficulty progression is proposed by the learner model and **the trainee always chooses** — the system never silently escalates. Adaptive difficulty inside a running session is **out of scope**: it would confound competence measurement with difficulty drift and make session-to-session comparison meaningless.

---

## 9. Public dataset ingestion

### 9.1 What corpora are for

Exactly four things, all of them about form rather than content:

1. **Phrasing and turn shape** — how a clinician actually opens, interrupts, and closes; how patients actually answer indirectly.
2. **Register calibration** — what "lay" and "clinical" lexical tiers contain, per language.
3. **Occurrence realism** — which conditions and drugs plausibly co-occur in a primary-care visit, so a scenario is not an implausible collage.
4. **Terminology surface forms** — the Spanish and English forms a term actually takes in the wild, feeding lexicons.

They are **never** copied into a scenario, never quoted verbatim in an agent prompt at runtime, and never a source of a scored fact.

### 9.2 The realism/truth boundary, stated as a rule

> No value in `clinical_state` may originate from a corpus document. `provenance.clinical_facts_source` is the constant string `"authored"`, and `make scenarios` fails the build on any other value.

The composer sees corpus excerpts as **style exemplars in a delimited slot**, and its output is a structured record that a human reviews. If a corpus excerpt contained "metformin 850 mg TID", that fact does not become a scenario fact by having been read; a human decides the regimen and the dosing table validates it. The distinction is the difference between "our patients sound real" and "we are republishing someone's clinical record", and the second is both a licence problem and a privacy problem.

### 9.3 Where clinical facts actually come from

| Fact class | Source of truth | Discipline |
|---|---|---|
| Drug ingredient names & identifiers | RxNorm (public domain, NLM) | Identifier only; `rxnorm_cui` never implies a dose |
| Plausible dose/route/frequency ranges | A **derived table** `data/lexicons/dosing_ranges.json`, built from DailyMed/openFDA structured product labelling, reviewed by a human | Used as a **validator** (`dosing_plausible`), not a generator. It answers "is 500 mg BID oral metformin plausible?" — it never proposes a regimen |
| Condition labels & codes | ICD-10-CM (public domain, CMS/NCHS) | Labelling and grouping only; no clinical logic derived from codes |
| Lay ⇄ clinical term pairs, Spanish | MedlinePlus en español (US Gov, public domain) + curated lexicons | Register tiers |
| Everything else clinical | **A human author, reviewed by a human reviewer** | Recorded in `provenance.review` |

Neither the composer nor any runtime agent has read access to `dosing_ranges.json`. It is a build-time validator only — a generator that can see its own validator will satisfy it rather than be constrained by it.

### 9.4 Dataset table

Licence and PHI columns below are the **project's working position**, not legal advice, and every one of them is re-verified mechanically at ingestion (§9.5). Nothing is used before that check passes.

| Name | Purpose | Licence considerations | PHI status | Used for |
|---|---|---|---|---|
| **MTS-Dialog** (doctor–patient dialogue/summary pairs) | Encounter structure, clinician turn shape | CC BY 4.0 per publisher; attribution recorded in `LICENCES.lock` | Synthetic/derived from de-identified sources; screened again on ingest | Composer style exemplars; node-intent frequency priors |
| **ACI-Bench** (clinical visit dialogue ↔ note) | Realistic visit arcs, plan-segment phrasing | Open research licence (CC-BY family); redistribution not required — we consume locally | De-identified by the publisher; re-screened | Graph arc templates; clinician register tier |
| **PriMock57** (mock primary-care consultations, audio + transcript) | Spoken-language realism: disfluency, overlap, repair | CC BY 4.0; **audio** carries actor voices — we use transcripts only | Simulated consultations with actors — no real patients | Overlap/disfluency modelling for `overlap_pressure`; turn-length priors |
| **MedlinePlus en español** | Lay Spanish health vocabulary, patient-facing register | US Government work, public domain; NLM attribution recorded anyway | None (no patient data) | `health_literacy` register tiers; lay ⇄ clinical term pairs |
| **RxNorm** (NLM) | Drug ingredient normalisation, `rxnorm_cui` | Public domain core; some source vocabularies inside UMLS are restricted — **we use the RxNorm-only release, not the full UMLS** | None | Ingredient identifiers, brand↔generic mapping |
| **DailyMed / openFDA SPL** | Building `dosing_ranges.json` | Public domain (FDA/NLM); openFDA terms recorded | None | Build-time dosing **validator** only |
| **ICD-10-CM** (CMS/NCHS) | Condition codes and labels | Public domain in the US | None | `concept_code` labelling |
| **PharmaCoNER / CodiEsp** (Spanish clinical NER corpora) | Spanish clinical term surface forms and inflections | CC BY 4.0 per publishers; Spanish-language clinical case corpora | Publisher states de-identified/anonymised clinical cases; re-screened, and only *term types* are extracted — never spans of text | Spanish clinical register tier; `false_friend` candidates |
| **Common Voice — Spanish** | Accent/variety reference for TTS and audio-front-end tuning | CC0 | None (consented volunteer speech) | Voice pipeline only (`docs/05-voice-pipeline.md`); no scenario content |
| **MIMIC-III / MIMIC-IV notes** | — | **REJECTED.** PhysioNet credentialed access + DUA restricting redistribution and derived-work sharing | De-identified but DUA-bound | **Not used.** We do not need real patient text, and accepting a DUA to obtain style exemplars we can author ourselves is an unnecessary obligation |
| **n2c2 / i2b2 clinical NLP corpora** | — | **REJECTED.** Restricted DUA, per-user agreements | De-identified, DUA-bound | **Not used**, same reasoning |
| **Any scraped patient forum / social media** | — | **REJECTED.** No licence to redistribute derivative style; consent-absent personal disclosure | Contains real, identifiable personal health disclosure | **Not used** |
| **Any real recorded clinical encounter** | — | **PROHIBITED** by product policy (`docs/00-dossier.md` §6, `docs/12-security-privacy.md`) | PHI | **Never** |

**Honest note on this table:** licence terms change and publisher pages get revised. Every cell above is asserted from the project's reading at the time of writing and is enforced — not trusted — by the lock file in §9.5. If `make corpora-verify` cannot confirm a licence from the recorded URL, the corpus is unusable until a human re-checks it, and the build says so by name.

### 9.5 The ingestion pipeline

```bash
make corpora            # fetch → verify → screen → normalise → index    (network; explicit)
make corpora-verify     # re-check licences and hashes only              (network)
make corpora-clean      # delete data/corpora/ entirely
make scenarios          # build + validate the scenario bank             (NO network)
make scenarios -- --report   # per-scenario difficulty, fallback rate, surface-form coverage
```

`make scenarios` is offline by construction. Scenario building must be reproducible on a machine that has never had network access, which is only true if corpora are a pinned, already-local input.

| Stage | Implementation | Fails the build when |
|---|---|---|
| 1. Fetch | `tools/ingest/fetch.py` — explicit per-corpus URL, no crawling | HTTP error, or the file hash differs from `LICENCES.lock` |
| 2. Licence verify | `tools/ingest/licence.py` — records `{name, url, spdx_or_text_sha256, retrieved_at, human_signed_by}` | The licence text hash changed since the last human sign-off, or `human_signed_by` is empty |
| 3. PHI screen | `tools/ingest/phi_screen.py` — §9.6 | Any HIGH-confidence identifier hit |
| 4. Normalise | Unicode NFC, control characters stripped, one record per line JSONL, provenance stamped per record | Malformed record |
| 5. Index | Frequency tables, lexical tiers, term candidates written to `data/lexicons/*.candidates.json` | — (candidates require human promotion) |

Nothing in stage 5 becomes a lexicon entry automatically. Candidates are promoted by a human editing the real lexicon file, for the same reason scenarios need review: an unreviewed term list is an unreviewed model input.

### 9.6 PHI and de-identification screening

We screen even corpora the publisher calls de-identified. Publishers are usually right; "usually" is not a standard we want to stand on, and the cost is one regex pass.

| Detector | Pattern class | Confidence | Action |
|---|---|---|---|
| `us_ssn` | `\b\d{3}-\d{2}-\d{4}\b` | HIGH | **Reject corpus**, name the file and line |
| `mrn_like` | 6–10 digit token adjacent to MRN/record/chart lemmas | HIGH | Reject |
| `phone_us` | NANP formats | HIGH | Reject |
| `email` | RFC-ish | HIGH | Reject |
| `dob_full` | Full date adjacent to DOB/born lemmas | HIGH | Reject |
| `street_address` | Number + street-type token + city/state | MEDIUM | Quarantine for human review |
| `person_name_dense` | > 3 capitalised person-name candidates per 100 tokens | MEDIUM | Quarantine |
| `date_shift_artifact` | Years outside 1900–2100 (a de-identification tell) | LOW | Log only — informative, not a defect |

A rejection is loud and specific (`phi_screen: mts_dialog/train.jsonl:8812 us_ssn`) rather than a silent skip. The screen's own regressions are covered by `tests/ingest/test_phi_screen.py` with synthetic positives — **there are no real identifiers in the test fixtures**, because a test fixture is a file we commit.

**Synthetic names rule (§3.2 `patient.given_name`):** scenario names are drawn from a curated list in `data/lexicons/names.es-MX.json` chosen for regional plausibility, and the combination given+family is checked at build time against every name appearing anywhere in `data/corpora/` to avoid accidentally reproducing a corpus individual.

---

## 10. The scenario composer and the human review gate

### 10.1 The pipeline

```
corpus excerpts (style only)
        │
        ▼
  ScenarioComposer  ── one structured call per stage, seeded, logged ──▶  draft scenario JSON
        │
        ▼
  Deterministic validators  (schema, graph, dosing, manifest, difficulty, name collision)
        │  fail → back to composer with the named violation, max 2 retries
        ▼
  Human review gate  (checklist §6.3, in the review UI)
        │  reject → draft with reviewer notes ;  approve → commit
        ▼
  data/scenarios/<id>.json   (committed, hashed, indexed by `make scenarios`)
```

### 10.2 The composer

```python
# tools/compose/composer.py
def compose(
    brief: ScenarioBrief,          # setting, target difficulty axes, condition family, objectives
    exemplars: list[CorpusExcerpt],# style only, delimited slots, never facts
    seed: int,
) -> DraftScenario:
    """Four seeded structured calls, in dependency order:
         1. clinical_state       (facts, gates, surface forms)
         2. state_graph          (nodes, intents, transitions)
         3. emotional arc + social context
         4. surface-form expansion pass over every critical fact
       Each stage's output is schema-validated before the next runs.
       Never called at session time. Runs on the grader-class model, offline.
    """
```

Design notes worth stating: the composer is **offline tooling**, not part of the product runtime — it runs on the larger grader-class model with no latency budget, and a session never composes a scenario. It is also the one place a model is allowed to *propose* clinical content, which is precisely why its output cannot reach a trainee without a human approving it. Composition is seeded and every call is logged to `tools/compose/runs/<seed>.jsonl`, so any scenario in the bank can be traced to the exact prompt that produced its draft.

### 10.3 The human gate

**A scenario with `review.status != "approved"` cannot be loaded by the runtime.** `ScenarioBank.get()` raises `ScenarioNotApproved`; there is no override flag, no `--force`, and no environment variable. This is principle 1's "the human decides ultimately" made structural rather than procedural — the honour system does not survive a deadline, and a bypass flag is a bypass that will eventually be used.

| Reviewer sees | Why |
|---|---|
| Side-by-side clinical state and rendered graph walk | Facts and their order are what matters |
| Every generated fact with its gate and surface forms | Missing surface forms are the top cause of fallback |
| Dosing validator output, per medication | The one clinical safety check |
| Difficulty axes vs. the graph's countable proxies | Catches an "advanced" scenario that is actually flat |
| A dry-run session transcript with a scripted trainee | The only way to notice a scenario that reads fine and plays badly |
| Diff against the previous `scenario_version`, if any | Review effort proportional to change |

Reviewer role is recorded (`project_lead` today; `certified_interpreter` and `clinician` are the roles we want and do not yet have — a **named gap**, stated in `docs/08-evals.md` and reflected in `MODEL_CARD.md`). A scenario reviewed only by the project lead carries that fact in its own provenance, permanently.

### 10.4 Retirement, never deletion

A scenario found to be wrong is set `retired: true` with a reason. It stays in the repository and stays loadable for **replay** of sessions that used it — deleting it would break `rehearsal replay --verify` and quietly invalidate historical numbers. `sample()` never returns retired scenarios; `get()` returns them with a flag.

---

## 11. Retention, local-only storage, and deletion

### 11.1 Where session data lives

```
~/.rehearsal/
├── rehearsal.db              # SQLite (WAL): events, blobs index, projections
├── blobs/sha256/ab/cd/…      # content-addressed audio, write-once
├── calibration/              # the 40 labelled items — DEV 25 / TEST 15 (SETUP.md §6)
│   ├── dev/  test/           # test/ is SEALED; see 11.4
└── exports/                  # only ever written by an explicit human action
```

Layout and the event-log/blob mechanics are specified in `docs/03-system-architecture.md` §10–§11; threat model and access control in `docs/12-security-privacy.md`. This section covers only the **data-lifecycle policy**.

### 11.2 Local-only, stated concretely

The product runtime has no outbound network client. Models are local (MLX / llama.cpp over a UNIX socket), the API binds `127.0.0.1`, and the frontend is served from the same process. There is no telemetry, no crash reporting, no analytics, no model provider. The optional frontier-model key in `SETUP.md` §3 is **eval tooling only** and is never reachable from a session code path; `tests/test_no_egress.py` asserts that no module under `src/rehearsal/runtime/` or `src/rehearsal/scoring/` imports an HTTP client.

Audio is the sharpest edge: **the trainee's voice is personal data**, and it is the one thing here that identifies a real person. It is also the raw material of every review and re-score, so it cannot simply be discarded.

### 11.3 Retention policy

| Data | Default retention | Rationale | Configurable |
|---|---|---|---|
| Event log (`events`) | Indefinite | It is the record; deleting it makes past numbers unverifiable | No — only whole-session deletion |
| Trainee audio blobs | **90 days**, then eligible for `rehearsal gc` | Long enough for review, re-score and dispute; short enough that a laptop is not a voice archive | Yes, `retention.audio_days` |
| Counterpart TTS audio | 30 days | Regenerable from the event log + seed | Yes |
| Transcripts, findings, scores | Indefinite | Small, and the substance of progress tracking | No |
| Learner model state | Indefinite | Rebuildable from the event log anyway | No |
| Calibration set | Indefinite | The project's external anchor | No |
| Compose run logs | Indefinite | Scenario traceability | No |

Blob reclamation is two-step and never automatic: `rehearsal gc --dry-run` lists unreferenced blobs past the retention floor; `rehearsal gc --confirm` deletes them and appends `blob.reclaimed` events. A garbage collector that runs on a timer and deletes evidence is not a feature we want on a machine where the evidence is someone's practice history.

### 11.4 The sealed test split

`~/.rehearsal/calibration/test/` is the sealed half of the calibration set (`SETUP.md` §6.6). Handling rules that belong here rather than there:

- The eval harness refuses to load `test/` unless invoked as `rehearsal eval --sealed --i-am-reporting-final-numbers`, and every such invocation appends a `sealed_split.opened` event with the current grader prompt hash.
- The L10 optimiser (`docs/08-evals.md`) has **no filesystem path to `test/`** — the split is passed as a constructor argument that the optimiser's entry point never populates.
- The open count is reported alongside any number computed from the split. A sealed split opened eleven times is not sealed, and the honest thing is to make that visible rather than to rely on discipline.

### 11.5 Deletion

```bash
rehearsal forget --session <session_id>     # one session: events, blobs, projections, learner contribution
rehearsal forget --all                      # everything under ~/.rehearsal except calibration/
rehearsal forget --all --including-calibration
```

| Property | Behaviour |
|---|---|
| Scope | Hard delete: rows removed, blob files unlinked, projections rebuilt from the remaining log |
| Learner model | Recomputed from the surviving event log — a deleted session leaves no residue in the competence estimate |
| Confirmation | Interactive, typed session id or the literal word `everything`; `--yes` exists only for `--session` |
| Audit | A `forget.executed` record is appended to `~/.rehearsal/forget.log` (outside the event log, since the log is what was deleted): timestamp, scope, counts. No content |
| Irreversibility | Stated before execution, with counts: *"this removes 1 session, 214 events, 38 audio blobs (412 MB). There is no undo."* |
| Backups | There are none. The product creates no backup and no sync. If the user has a Time Machine backup, that is theirs to manage, and `rehearsal forget` says so |

Deletion is a **one-way door** and is presented as one. Nothing in the product deletes trainee data without an explicit human instruction — not on error, not on abort, not on uninstall.

---

## 12. Files, commands and schemas

```
data/
├── schema/
│   ├── scenario.schema.json          # §6
│   ├── clinical_state.schema.json    # §3
│   └── state_graph.schema.json       # §4
├── scenarios/                        # committed, reviewed, one file per scenario
│   └── sc_0042_chest_pain_dm2.json
├── lexicons/                         # committed, human-curated
│   ├── idiom.es-MX-rural-central.json  idiom.es-MX-urban.json
│   ├── idiom.es-US-heritage.json       idiom.es-neutral.json
│   ├── register_tiers.en.json          register_tiers.es.json
│   ├── dosing_ranges.json            # build-time validator only
│   ├── frequency_equivalences.json   # 2/day ⇄ "twice a day" ⇄ "cada doce horas"
│   └── names.es-MX.json
└── corpora/                          # git-ignored, fetched
    ├── LICENCES.lock                 # name, url, hash, spdx, retrieved_at, human_signed_by
    └── <corpus>/…

src/rehearsal/content/
├── bank.py          # ScenarioBank.get / sample / list_bands
├── graph.py         # ClinicalStateGraph, guards, entry/successors/advance
├── terms.py         # build_manifest
├── audit.py         # audit_utterance — §5.2 layer 3
└── difficulty.py    # WEIGHTS, computed_index, band

tools/
├── ingest/          # fetch.py licence.py phi_screen.py normalise.py index.py
└── compose/         # composer.py brief.py validators.py runs/
```

| Command | Network | Does |
|---|---|---|
| `make corpora` | yes | Fetch, verify licences, PHI-screen, normalise, index |
| `make corpora-verify` | yes | Re-check licence hashes only |
| `make corpora-clean` | no | Delete `data/corpora/` |
| `make scenarios` | **no** | Validate every scenario, rebuild manifests, recompute difficulty, index into the bank |
| `make scenarios -- --report` | no | Coverage/difficulty/fallback report per scenario |
| `rehearsal compose --brief <file>` | no | Draft a scenario into `in_review` |
| `rehearsal review --scenario <id>` | no | Open the human gate |
| `rehearsal gc --dry-run` / `--confirm` | no | Blob reclamation, two-step |
| `rehearsal forget …` | no | §11.5 |

---

## 13. Decision status

| Item | Status | Note |
|---|---|---|
| Three data classes and their trust boundaries | **Decided** | Drives context assembly and the egress test |
| Clinical state schema v1.0.0 | **Decided** | Additive changes bump minor; a removed field bumps major and retires affected scenarios |
| Facts-in-record / wording-by-agent split | **Decided** | The product's central claim depends on it |
| Four-layer invention enforcement, canary at exactly zero | **Decided** | §5.2, §5.3 |
| Human approval as a structural gate with no bypass flag | **Decided** | §10.3 |
| Five difficulty axes and weights v1.0.0 | **Proposed** | Weights are reasoned, not empirically derived. To be checked against observed trainee error rates once enough sessions exist |
| Difficulty band boundaries | **Proposed** | Placeholder cut-points; expect revision from real score distributions |
| The dataset table's licence cells | **Proposed** | Asserted from the project's reading; enforced by `LICENCES.lock` + human sign-off, not by trust |
| `dosing_ranges.json` as validator-only | **Decided** | Generator/validator separation is deliberate |
| Audio retention default of 90 days | **Proposed** | Chosen for review-and-dispute headroom; no evidence behind the exact number |
| Reviewer roles beyond `project_lead` | **Open — named gap** | Certified-interpreter and clinician review is wanted and unavailable; recorded in every scenario's provenance |
| Correlating authored vs measured difficulty as a sanity check | **Open** | Would be a useful cross-check; not built |
| Indigenous-language relay scenarios | **Open — deliberately excluded** | §3.6. Blocked on qualified human review, not on engineering |
| Scenario sharing/import between installations | **Open** | Scenarios are shareable by class; no signing, provenance-verification or import UI is designed |

---

## 14. Related documents

| Document | Relationship |
|---|---|
| `docs/03-system-architecture.md` | Content plane contracts, context isolation, event log, storage layout |
| `docs/06-scoring-engine.md` | What the term manifest is consumed by; extractor and grader behaviour |
| `docs/08-evals.md` | EV-04 persona consistency and EV-05 leakage, both computed against the scenarios defined here |
| `docs/05-voice-pipeline.md` | Consumes `emotional_state.expression.prosodic` and the language variety |
| `docs/12-security-privacy.md` | Threat model, access control, the prohibition on real patient audio |
| `SETUP.md` §5–§6 | Operator-facing data setup and the calibration labelling protocol (authoritative; not duplicated here) |
| `docs/01-research.md` | Error taxonomy definitions and the evidence base |

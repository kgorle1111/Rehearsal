# Scenario Template

A scenario defines one simulated clinical encounter. It is **data, not code** — adding a scenario should never require an engineering change.

Every scenario is reviewed by a human before entering the bank. See `docs/07-data-and-scenarios.md` for the schema of record and the review gate.

---

## Authoring rules

1. **The patient agent verbalises state; it never invents clinical fact.** Everything the patient can say about their condition, medications or history must exist in the clinical state below. If it is not here, the patient cannot say it.
2. **Dosing must be plausible.** Realistic drugs, realistic doses, realistic frequencies. A scenario with impossible dosing trains the wrong instincts and makes the critical-error checks meaningless.
3. **Design the difficulty deliberately.** Name which skills the scenario is meant to stress, and place the material that stresses them.
4. **No real patient data. Ever.** Scenarios are synthetic by construction. If a scenario was inspired by a real encounter, it is paraphrased beyond re-identification and that is noted in provenance.
5. **Language variety is a design choice.** Specify the Spanish variety and register; a scenario written in neutral clinical Spanish trains something different from one written in the idiom of a farmworker patient describing pain.

---

## Metadata

| Field | Value |
|---|---|
| `id` | *(slug, e.g. `diabetes-followup-01`)* |
| `title` | |
| `setting` | *(primary care / emergency / prenatal / pharmacy / discharge)* |
| `languages` | `en` ⇄ `es` |
| `spanish_variety` | *(e.g. Mexican, Central American, neutral clinical)* |
| `difficulty` | 1–5 |
| `estimated_turns` | |
| `skills_targeted` | *(numeric_density, negation, register_distance, idiom, emotional_load, medical_lexicon)* |
| `provenance` | *(how it was authored; any corpus that seeded it)* |
| `reviewed_by` | *(human reviewer — required before entering the bank)* |

---

## Clinical state

The ground truth the patient agent may draw on. Nothing outside this is sayable.

```yaml
patient:
  age: 
  sex: 
  chief_complaint: 
  health_literacy: low | moderate | high
  emotional_state: calm | anxious | frustrated | frightened | withdrawn
  language_notes: 

conditions:
  - name: 
    since: 
    controlled: true | false

medications:
  - drug: 
    dose: 
    route: 
    frequency: 
    adherence: good | partial | poor
    notes: 

allergies:
  - substance: 
    reaction: 

symptom_timeline:
  - onset: 
    symptom: 
    severity: 
    change: 

social_context:      # only what is clinically relevant
  - 
```

---

## Encounter outline

The clinician agent's intent per phase. Not a script — the agents converse freely within these bounds.

| Phase | Clinician intent | Material that stresses the trainee |
|---|---|---|
| Opening | | |
| History | | |
| Examination / findings | | |
| Plan and instructions | | *(the phase where critical numeric content usually lands)* |
| Teach-back / closing | | |

---

## Designed challenges

List what this scenario is deliberately testing, so the report can attribute performance to intent.

| Challenge | Where it appears | Error class it probes |
|---|---|---|
| e.g. dose + frequency + duration in one utterance | Plan phase | `omission`, `substitution` (critical) |
| e.g. patient uses a colloquial pain idiom | History | `false_fluency`, `register_shift` |
| e.g. a negated instruction ("do **not** take with…") | Plan | `distortion` (critical) |
| e.g. patient addresses the interpreter directly | Any | `role_exchange` |

---

## Review checklist

- [ ] All dosing clinically plausible
- [ ] Nothing sayable by the patient that is absent from the clinical state
- [ ] At least one critical-class challenge present
- [ ] Spanish variety and register specified and consistent
- [ ] No real patient data; provenance recorded
- [ ] Difficulty rating matches the actual material
- [ ] Reviewed and signed off by a human

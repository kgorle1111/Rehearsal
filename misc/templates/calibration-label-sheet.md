# Calibration Label Sheet

The working document for hand-labelling calibration items. Read `SETUP.md` §6 before using it — particularly the rule about labelling **blind**, which is the one that decides whether this data is worth anything.

Copy this file to `data/calibration/worksheet.md` (git-ignored) and work through it.

---

## Before you start

- [ ] I have read the NCIHC Standards of Practice 1, 2, 5–6, 12, 16–18 (`docs/01-research.md` §2)
- [ ] I have read the error taxonomy and severity rules below
- [ ] **I have not looked at any model output for these items, and will not until every label is committed**
- [ ] I know the target composition: 12 clean · 10 single-critical · 10 single-non-critical · 4 multi-error · 4 ambiguous

## The taxonomy (reference while labelling)

| Code | Meaning |
|---|---|
| `omission` | Content in the source is absent from the rendering |
| `addition` | Content in the rendering that was not in the source |
| `substitution` | Content replaced with different content |
| `distortion` | Meaning materially altered, including negation flips |
| `editorialization` | Interpreter's own opinion, advice or explanation inserted |
| `role_exchange` | Interpreter speaks on their own behalf instead of interpreting |
| `register_shift` | Formality, style or tone materially changed |
| `false_fluency` | Invented or borrowed term used instead of interpreting the concept |
| `first_person_violation` | Reported speech ("he says that…") instead of first person |
| *(none)* | `clean` — the rendering carries the source faithfully |

**Severity.** `critical` if the error could change clinical action — dosage, frequency, duration, route, laterality, allergy, negation, symptom onset, or a red-flag instruction. Otherwise `non-critical`. The test is: *could a clinician or patient reasonably do something different because of this?*

**Confidence.** Mark `sure` or `unsure`. Unsure items are analysed separately — they establish the honest ceiling, and pretending to be certain about them corrupts the metric.

---

## Worked example (do not include in the set — this is the format reference)

**Item 00 — reference example**

| Field | Value |
|---|---|
| Direction | EN → ES |
| Source | "Take one tablet twice a day with food." |
| Rendering | "Tome una pastilla al día con comida." |
| **Findings** | `substitution` · **critical** · source span *"twice a day"* → rendering span *"al día"* |
| Note | Frequency halved. Patient would under-dose. |
| Confidence | `sure` |

Note what the label does **not** do: it does not say "the interpreter was careless," does not give a score out of ten, and does not comment on fluency. It names the category, the spans, and the clinical consequence.

---

## Items

> Duplicate the block below for each item. Number sequentially. Fill **Findings** with one row per error, or write `clean`.

### Item 01

| Field | Value |
|---|---|
| Bucket | *(clean / critical / non-critical / multi / ambiguous)* |
| Direction | *(EN → ES / ES → EN)* |
| Source | |
| Rendering | |
| Confidence | *(sure / unsure)* |

**Findings**

| # | Code | Severity | Source span | Rendering span | Why it matters |
|---|---|---|---|---|---|
| 1 | | | | | |

**Note:**

---

### Item 02

| Field | Value |
|---|---|
| Bucket | |
| Direction | |
| Source | |
| Rendering | |
| Confidence | |

**Findings**

| # | Code | Severity | Source span | Rendering span | Why it matters |
|---|---|---|---|---|---|
| 1 | | | | | |

**Note:**

---

*(continue to Item 40)*

---

## After labelling

- [ ] All 40 items labelled, composition matches the target buckets
- [ ] **Waited at least a day**, then re-labelled 10 items without looking at the first pass
- [ ] Intra-rater agreement computed and recorded in `plans/metrics-snapshot.md` §2
- [ ] A second human labelled a subset (ideally ≥15) → inter-rater agreement recorded
- [ ] Split into `dev.jsonl` (25) and `test.jsonl` (15) via `make split-calibration` — **before** looking at any model output
- [ ] `data/calibration/CHANGELOG.md` created for any future label corrections

## The rule that protects all of this

Once split, the **test set is sealed**. It is not opened during development, not used for prompt tuning, and not consulted when a number disappoints. If a label later turns out to be wrong, correct it in the open with a dated entry in `CHANGELOG.md` and a reason — never silently, and never because a metric would look better.

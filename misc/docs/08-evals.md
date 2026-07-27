# 08 — Evaluation & Measurement

The measurement system that gives every claim in this project its warrant.

Rehearsal scores human performance. Any such system has to answer one question before it is allowed to say anything: *how do you know your score is right?* This document is that answer, in full. It defines the metric hierarchy, every eval in the suite, the gates each one enforces, the split discipline that keeps the numbers honest, the append-only registry that makes every number reproducible, and — the section people skip and shouldn't — the things these evals categorically **cannot** tell you.

Governing principle: **everything is measured** (principle 6) and **honest reporting** (principle 7). A design argument in this project is settled with a number and an interval, or it is not settled. A number without its uncertainty is not a number, it is a claim.

The external anchor for all of it is the hand-labelled calibration set. Its construction protocol lives in `SETUP.md` §6 and is not repeated here — this document consumes it.

---

## 1. The metric hierarchy

Metrics are not a flat list. They sit in five tiers, and the tiers determine what a failure blocks.

| Tier | Name | Metrics | What it governs |
|---|---|---|---|
| 0 | **Provable** | deterministic extractor conformance (EV-00) | Must be perfect. These checks are decidable; a failure is a bug, not a score. |
| 1 | **Headline** | grader agreement with human labels — Cohen's κ, macro-averaged over error categories, reported on the sealed TEST split | The single number that answers "is the score right?" |
| 2 | **Safety** | critical-error recall | Whether the system is safe to put in front of a trainee at all. Outranks the headline when they conflict. |
| 3 | **Ceiling** | human intra-rater and inter-rater agreement | The upper bound the headline is read against. Never optional. |
| 4 | **Supporting** | per-category precision/recall, false-positive rate on clean items, persona consistency, leakage effect, skill delta | Architecture claims. Each rung of the layer vertical owns one. |
| 5 | **Operational** | latency conformance, session completion, trainer-override rate | Whether the thing runs and whether humans trust it. |

**Named explicitly, so there is no ambiguity anywhere else in the documentation set:**

- **The headline metric is grader agreement with human labels** — Cohen's κ between the grader's per-turn error labels and the human labels in the calibration set, macro-averaged across the taxonomy categories that occur in the split, computed on the **sealed TEST split**, reported with a bootstrap interval and always printed next to the human ceiling.
- **The safety metric is critical-error recall** — the fraction of human-labelled `critical` errors (dosage, frequency, allergy, negation, laterality, symptom onset) that the grader also flags as errors of critical severity. When optimisation improves κ and degrades critical-error recall, critical-error recall wins and the change is rejected.

Everything else exists to explain, bound, or defend those two.

### 1.1 The master metric table

| Metric | Definition | Gate | Blocks what on failure |
|---|---|---|---|
| `extractor_conformance` | Exact-match accuracy of the deterministic extractors (`entities`, `numbers`, `dosage`, `frequency`, `negation`, `laterality`, `allergy`) on the fixture grid. `temporal` is registered in `EXTRACTOR_ORDER` but **not yet implemented** and is excluded from this grid until it ships (`docs/06-scoring-engine.md` §4.10) | **= 1.00**, no exceptions | Every merge. `make check` fails. Nothing downstream is trusted, because the neuro-symbolic split assumes this layer is provably correct. |
| `kappa_macro` | Cohen's κ, grader vs human, per-category presence/absence per turn, macro-averaged **over categories that occur in the split** — categories with zero occurrences are `undefined` and excluded, never counted as 1.0 (see §5 for the full rule) | ≥ 0.60 on DEV to promote a prompt; TEST value is reported, not gated | Grader prompt promotion; any public claim of grader accuracy. |
| `critical_recall` | TP_critical / (TP_critical + FN_critical) over human-labelled critical errors | ≥ 0.90 on DEV, with the point estimate and Wilson interval reported on TEST | **Release. Everything.** Also blocks the trainee-facing score display and any pilot with real trainees. |
| `fp_rate_clean` | Fraction of `clean` calibration items on which the grader reports ≥ 1 error | ≤ 0.15 on DEV | Showing automatic flags to trainees without a human gate; release. |
| `precision[c]`, `recall[c]` | Per-category precision and recall over matched error spans | No numeric gate; **any category with recall < 0.50 must be labelled "not reliably detected" in the UI and the report** | Silent presentation of that category as if it were reliable. |
| `kappa_intra` | Human labeller vs themselves on the delayed re-label sample (`SETUP.md` §6.5 step 6) | Report-only; must exist before any headline number is published | Publishing `kappa_macro` at all. A headline with no ceiling is uninterpretable. |
| `kappa_inter` | Second human labeller vs first, on the shared subset | Report-only; absence must be stated explicitly as a named gap | Claiming the labels represent "the professional standard" rather than one rater's application of it. |
| `persona_consistency` | Fraction of counterpart-agent turns that satisfy every deterministic check against the scenario's clinical state graph | ≥ 0.95 turn-level, and **= 1.00** on the rubric-vocabulary canary | Merging a scenario or an agent-prompt change; sign-off of the L5 rung. |
| `leakage_delta` | Difference in mean utterance difficulty index between the isolated arm and the rubric-leaked arm, paired by scenario and turn index | No pass/fail threshold — a **pre-registered** effect size with a permutation-test p-value and CI | Nothing mechanically; a null result changes the *claim*, not the architecture (see §4.6). |
| `skill_delta` | Difference in session-protocol checklist pass rate, with vs without the packaged session skill, paired by scenario | Skill must not be worse: lower CI bound ≥ −0.02 | Shipping the skill as a claimed improvement. A CI containing zero means the skill is reported as "no measurable benefit". |
| `grader_backlog_rate` | Fraction of turns where grading of turn *n* has not completed before the trainee begins turn *n+1* | ≤ 0.05 | Enabling in-session coach feedback; release. Forces the fallback path in `docs/05-voice-pipeline.md`. |
| `p95_first_audio_ms` | 95th percentile time from end-of-trainee-speech to first TTS audio frame of the counterpart | Within the budget constant exported by `src/rehearsal/runtime/budget.py` | Release. Below-budget conversational realism is a product failure, not a nice-to-have. |
| `p99_barge_in_stop_ms` | 99th percentile time from detected trainee speech onset to TTS output silence | Within the budget constant | Release. A voice that talks over the trainee makes the session unusable. |
| `session_completion_rate` | Sessions that reach a written fidelity report / sessions started | ≥ 0.90 | Any pilot with real trainees; L7 rung sign-off. |
| `turn_capture_loss_rate` | Turns with missing or unusable trainee audio / total turns | ≤ 0.02 | Release. Lost audio means an unscoreable turn and an unrecoverable trainee effort. |
| `trainer_override_rate` | Fraction of grader-reported errors a reviewing trainer changes (adds, removes, or re-severities) | Investigation band 0.02–0.25; outside the band triggers a mandatory review, not an automatic block | Nothing directly; outside-band values block the *claim* that the grader is trusted in practice. |
| `regression_delta` | Change in each gated metric vs the frozen baseline in `data/evals/baselines/` | `critical_recall` ≥ baseline − 0.05 **and** ≥ its own gate; `fp_rate_clean` ≤ baseline + 0.05; `extractor_conformance` = 1.00; latency p95 ≤ baseline × 1.10 | The merge. `make check` is the enforcement point. |

Gate provenance — which of these are settled and which are still arguable:

| Gate | Status | Rationale |
|---|---|---|
| `extractor_conformance = 1.00` | **Decided** | Provably decidable checks. Anything less is a defect. |
| `critical_recall ≥ 0.90` (DEV) | **Decided** | This is the clinical-consequence class; a system that misses one in five dosage errors teaches trainees that dosage errors are acceptable. |
| `kappa_macro ≥ 0.60` (DEV) | **Proposed** | 0.60 is the conventional "substantial agreement" boundary, not a domain-derived number. It should be re-derived from the human ceiling once `kappa_intra` exists: a defensible gate is a fixed fraction of the ceiling, not an absolute constant. |
| `fp_rate_clean ≤ 0.15` | **Proposed** | With 12 clean items on the full set, 0.15 is a two-item tolerance. The gate is coarse because the denominator is small; it should tighten as the clean bucket grows. |
| `persona_consistency ≥ 0.95` | **Proposed** | Chosen to permit rare benign state-graph edge cases while catching systematic drift. The rubric-vocabulary canary inside it is **decided** at 1.00 — that one is binary. |
| `session_completion_rate ≥ 0.90` | **Proposed** | Placeholder until the first multi-session run produces a real failure distribution. |
| `trainer_override_rate` band | **Proposed** | Both tails are informative (see §4.9); the band edges are judgement, not measurement, and are marked as such wherever the number is reported. |

### 1.2 Which rung of the layer vertical owns which eval

Every rung ships its own eval number. This is the mapping, and it is the checklist for rung sign-off.

| Rung | What it ships | Owning eval(s) | Number that must exist |
|---|---|---|---|
| L4 | Neuro-symbolic fidelity scorer (`docs/06-scoring-engine.md`) | EV-00, EV-01, EV-02, EV-03 | κ vs human labels, with the human ceiling beside it |
| L5 | Bare-hands counterpart agent driven by a clinical state machine | EV-04 | Persona-consistency rate, deterministically checkable |
| L6 | Packaged, versioned session skill (protocol + rubric + taxonomy) | EV-06 | A/B task-correctness delta, with vs without |
| L7 | Full session orchestration with human gates | EV-07, EV-08 | End-to-end completion rate + trainer-override rate |
| L8 | Multi-agent with information isolation | EV-05 | The leakage A/B effect size and interval |
| L10 (rung 1) | Automated prompt optimisation of the grader | EV-01 re-run under §6 protocol | Before/after agreement on the **sealed TEST split** |

---

## 2. Harness layout, contracts and commands

### 2.1 Directory tree

```
src/rehearsal/evals/
├── __init__.py
├── cli.py              # `rehearsal-evals` entry point
├── result.py           # EvalResult, GateOutcome — the contract every eval returns
├── registry.py         # append-only run recording (SQLite + JSONL mirror)
├── matching.py         # span/category alignment between gold and predicted errors
├── metrics.py          # kappa, precision/recall, Wilson + bootstrap intervals, permutation test
├── report.py           # markdown + JSON rendering; snapshot diffing
├── seal.py             # the deterministic guard on the sealed TEST split
└── suites/
    ├── ev00_extractors.py
    ├── ev01_calibration.py
    ├── ev02_critical_recall.py
    ├── ev03_human_ceiling.py
    ├── ev04_persona.py
    ├── ev05_leakage.py
    ├── ev06_skill_ab.py
    ├── ev07_latency.py
    ├── ev08_session.py
    └── ev09_regression.py

data/
├── calibration/
│   ├── dev.jsonl              # 25 items — optimisation is allowed here
│   ├── test.jsonl             # 15 items — SEALED
│   ├── relabel.jsonl          # delayed re-label pass → kappa_intra
│   ├── rater2.jsonl           # second human's labels → kappa_inter (may be absent)
│   ├── CHANGELOG.md           # every label correction, with reason
│   └── TEST_ACCESS.log        # append-only record of every unseal
├── fixtures/
│   ├── extractors/*.jsonl     # EV-00 grid
│   └── sessions/*.json        # replayable session transcripts for EV-08/EV-09
└── evals/
    ├── registry.db            # append-only run registry
    ├── runs/<run_id>.json     # per-run artifact mirror
    └── baselines/<gate>.json  # frozen baselines for EV-09

prompts/
├── grader/v1.md … vN.md       # versioned; never edited in place
├── clinician/vN.md
└── patient/vN.md
```

### 2.2 The contract every eval satisfies

```python
# src/rehearsal/evals/result.py
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Literal

Split = Literal["dev", "test", "fixture", "live", "replay"]


class GateOutcome(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    REPORT_ONLY = "report_only"   # measured, deliberately not gated
    SKIPPED = "skipped"           # prerequisite missing; must state why


@dataclass(frozen=True, slots=True)
class EvalResult:
    eval_id: str                              # "EV-02"
    split: Split
    n: int                                    # denominator — always reported
    metrics: dict[str, float]
    intervals: dict[str, tuple[float, float]] # 95%; empty only if n is too small to bootstrap
    gate: GateOutcome
    gate_detail: str                          # "critical_recall <r> < gate 0.90 (dev)"
    artifacts: list[Path]
    notes: str
```

Every suite module exposes exactly one function:

```python
def run(cfg: EvalConfig) -> EvalResult: ...
```

`EvalConfig` carries the split, the seed, the model roles to load, the prompt versions, and a `dry_run` flag. Nothing else. An eval that needs a network call, a live human, or a wall-clock schedule does not belong in this suite.

### 2.3 Commands

| Command | What it runs |
|---|---|
| `make evals` | The whole suite on DEV + fixtures. Refuses to touch TEST. Prints the gate table and diffs against `plans/metrics-snapshot.md`. |
| `make calibrate` | EV-01 + EV-02 + EV-03 only — the grader-accuracy report. |
| `make check` | lint + types + tests + EV-00 + EV-09. The pre-commit gate. |
| `uv run rehearsal-evals run --eval EV-05 --seed 7 --out data/evals/runs/` | One eval, explicit seed. |
| `uv run rehearsal-evals report --run <run_id>` | Re-render a recorded run without re-executing it. |
| `uv run rehearsal-evals unseal --reason "<text>"` | The only path that permits TEST access. Writes `TEST_ACCESS.log`. |
| `uv run rehearsal-evals baseline --freeze <eval_id>` | Writes the current result into `data/evals/baselines/`. Requires a clean git tree. |

---

## 3. How grader output is compared to human labels

Every agreement number in §4 depends on one alignment decision, so it is specified here once and referenced from there.

A calibration item is a triple (`source_utterance`, `trainee_rendering`, `human_label`); the label is zero or more errors, each with a span, a category from the taxonomy, and a severity. The grader emits the same shape. Comparison happens at two granularities:

**(a) Turn-level category presence — the input to Cohen's κ.**
For each item and each of the nine categories, gold and predicted are reduced to a boolean: did this category occur in this turn at all? This produces nine 2×2 tables. κ is computed per category and macro-averaged. Rationale: κ needs a fixed, shared set of decision opportunities; spans do not provide one, turn×category does. Categories that never occur in a split are reported as `undefined` and excluded from the macro-average — never silently counted as 1.0, which is the classic way to inflate this number.

**(b) Span-level matching — the input to precision, recall and critical recall.**

```python
# src/rehearsal/evals/matching.py
def match_errors(
    gold: Sequence[LabelledError],
    pred: Sequence[LabelledError],
    *,
    iou_threshold: float = 0.5,
    require_category: bool = True,
) -> MatchResult:
    """Greedy maximum-IoU alignment over character spans of the rendering.

    A gold error and a predicted error match when their character spans have
    IoU >= iou_threshold and (if require_category) their categories are equal.
    Omissions carry a span in the SOURCE, not the rendering; those are matched
    in source coordinates. Unmatched gold -> FN. Unmatched pred -> FP.
    """
```

Three matching decisions, stated so nobody has to reverse-engineer them:

1. **IoU ≥ 0.5, greedy, highest-IoU-first.** Greedy rather than Hungarian: with at most a handful of errors per turn the assignments are identical in practice, and greedy is inspectable line by line. *Marked as a simplification; if a turn ever produces more than ~5 overlapping errors, revisit.*
2. **Category-blind recall is reported alongside category-strict recall.** "Found the problem but named it `distortion` instead of `substitution`" is a materially different failure from "missed it entirely", and collapsing the two hides the grader's real behaviour.
3. **Severity is scored separately from category.** A matched pair where gold is `critical` and prediction is `non-critical` counts as a **severity miss** and is a false negative for `critical_recall` even though it is a true positive for category recall. This is deliberate: under-severity is the failure mode that gets someone hurt.

Deterministic extractor findings and language-model findings are tagged with their `source` field (`extractor` | `model`) and can be broken out. This is how the neuro-symbolic split is audited: if the extractors are carrying critical recall and the model is contributing mostly noise, that is visible in the report rather than a matter of belief.

---

## 4. The eval suite

One subsection per eval: what it measures, how it is computed, what the gate is, and what failing it blocks.

### 4.1 EV-00 — Deterministic extractor conformance

**Measures.** Whether the provably-decidable half of the scorer is actually correct. The extractors hard-check numbers, dosages, units, frequencies, negation, laterality, allergies and temporal markers across English and Spanish. Principle 3 says the model handles only the semantic residue — that division is only legitimate if the deterministic half is exact.

**Computed.** A fixture grid in `data/fixtures/extractors/*.jsonl`, one file per extractor. Each row is `{"text": ..., "lang": "en"|"es", "expect": [...]}`. Exact set equality between extracted structures and `expect`. No fuzzy matching, no partial credit. The grid must include, per extractor: the plain case, the Spanish-diacritic case, the decimal-comma vs decimal-point case (`0,5 mg` vs `0.5 mg`), the unit-abbreviation variants (`mcg`/`µg`/`microgramos`), negation scope traps (`no tome` vs `no sólo tome`), laterality traps (`izquierdo`/`derecho` plus `bilateral`), frequency traps (`cada 8 horas` vs `3 veces al día` — semantically near, textually unrelated), and at least three adversarial cases per extractor that previously failed.

**Gate.** `extractor_conformance = 1.00`. Any failure is a bug with a reproducer, not a score to be improved.

**Blocks on failure.** Every merge (`make check`), and by construction every downstream claim: if the extractors are wrong, EV-01 and EV-02 are measuring an unknown mixture and mean nothing.

**Regression rule.** Every extractor bug found anywhere — in a session, in calibration, in review — gets a fixture row before it gets a fix. The grid only grows.

### 4.2 EV-01 — Grader calibration vs human labels

**Measures.** The headline. Agreement between the grader's labels and the human's on the calibration set, plus the shape of the disagreement.

**Computed.** Load the split (DEV by default; TEST only under §5). For each item, run the full scoring pipeline exactly as production runs it — same prompt version, same decode parameters, same seed — and compare with §3. Outputs:

| Output | Definition |
|---|---|
| `kappa_macro` | Macro-average of per-category Cohen's κ over turn×category presence |
| `kappa[c]` | Per-category κ, with the marginal counts printed (κ is unstable when a category is rare, and the counts are how a reader sees that) |
| `precision[c]`, `recall[c]`, `f1[c]` | Span-level, category-strict |
| `recall_blind[c]` | Span-level, category-blind — "found it but misnamed it" |
| `fp_rate_clean` | Fraction of `clean` items with ≥ 1 predicted error |
| `fp_per_clean_item` | Mean predicted-error count on clean items — distinguishes "one over-eager flag" from "a shower of them" |
| `severity_confusion` | 2×2 table of gold vs predicted severity on matched pairs |
| `source_split` | Contribution of `extractor` vs `model` findings to TP/FP/FN |

Intervals: 2000-resample bootstrap over **items** (not over errors — errors within an item are not independent), percentile method, reported to two decimals. With 25 DEV items the intervals are wide; the report prints them anyway, because a wide interval honestly stated is the finding.

**Gate.** `kappa_macro ≥ 0.60` on DEV to promote a grader prompt version. `fp_rate_clean ≤ 0.15`. The TEST value is **reported, never gated** — gating on TEST would turn the sealed split into a tuning signal by the back door (§5).

**Blocks on failure.** Promotion of the prompt version to `prompts/grader/` head; any public statement of grader accuracy; the L4 rung sign-off.

**Reported with.** Always beside EV-03. A κ printed without the human ceiling is a number without a scale.

### 4.3 EV-02 — Critical-error recall (the safety gate)

**Measures.** Of the errors a human judged could change clinical action — wrong dose, wrong frequency, a missed allergy, a flipped negation, swapped laterality, a shifted symptom onset — what fraction did the grader catch *and mark critical*?

**Computed.**

```
TP_crit = matched pairs where gold.severity == critical and pred.severity == critical
FN_crit = gold critical errors that are (a) unmatched, or (b) matched but predicted non-critical
critical_recall = TP_crit / (TP_crit + FN_crit)
```

Reported with a **Wilson score interval**, not a normal approximation — the denominator is ~10–14 items and the normal approximation is simply wrong at that n. Also reported: `critical_precision` (over-flagging criticality erodes the severity signal until it means nothing), and the per-trigger breakdown (dosage / frequency / allergy / negation / laterality / onset) so a systematic blind spot is visible rather than averaged away.

**Gate.** `critical_recall ≥ 0.90` on DEV. Any single miss is enumerated verbatim in the report with the item id, the gold label and the grader's output. There is no threshold at which a missed dosage error becomes a rounding error.

**Blocks on failure.** Release. Trainee-facing score display. Any pilot. A prompt-optimisation candidate that raises κ and drops critical recall is rejected regardless of κ, and the rejection is recorded in the registry — including the tempting ones.

**Why this outranks the headline.** A grader with excellent κ that misses dosage errors teaches trainees that dosage errors are survivable. That is worse than no system, because it is a training signal pointed the wrong way.

### 4.4 EV-03 — The human ceiling

**Measures.** How well a human agrees with a human on this task. This is the scale the headline is read against, and it is not optional.

**Computed.** Two numbers, from the protocol in `SETUP.md` §6.5:

- `kappa_intra` — the labeller vs themselves on the delayed re-label sample (10 items, re-labelled blind after a rest interval). Same turn×category κ machinery as EV-01, so the numbers are directly comparable.
- `kappa_inter` — a second human labeller vs the first on their shared subset (~15 items). If it does not exist, EV-03 returns `GateOutcome.SKIPPED` with `notes` stating plainly that inter-rater agreement is unmeasured, and that note propagates into every report. A missing ceiling is a named gap, never an empty cell.

Also reported: `ambiguous_item_agreement` — agreement restricted to the deliberately ambiguous bucket, and separately to items the labeller marked `confidence: unsure`. These are where the ceiling actually lives.

**Gate.** Report-only, with one hard rule: **`kappa_macro` may not be published without `kappa_intra` printed adjacent to it.** `report.py` enforces this — the renderer raises if the ceiling is absent. Deterministic code decides what may be published; the format cannot be talked into an exception.

**Blocks on failure.** Publication of the headline metric in any form: the report, the UI, `plans/metrics-snapshot.md`.

**Interpretation.** If `kappa_intra` is 0.72 and the grader reaches 0.68, the honest statement is "the grader is approaching the consistency of the human labeller on this set", not "the grader is 68% accurate". If the grader ever *exceeds* the ceiling, the correct conclusion is that the set is too small to distinguish them — not that the machine has surpassed the human. With n=15 sealed items that gap is well inside the interval, and the report says so.

### 4.5 EV-04 — Persona consistency of the counterpart agent

**Measures.** Whether the clinician and patient agents stay inside the scenario's clinical state graph. This is the L5 rung's number, and it is deterministic by design — no model judges another model here.

**Computed.** Replay a fixed set of seeded scenarios (defined in `docs/07-data-and-scenarios.md`) with a scripted trainee side, and check every counterpart turn against the state graph:

| Check | Rule | Violation |
|---|---|---|
| `state_edge_legal` | The turn's declared state transition is an edge in the scenario graph | Agent jumped to a state it cannot reach from here |
| `no_premature_disclosure` | No fact gated behind an unreached state appears in the turn (facts carry surface forms + regex/lemma triggers in the scenario file) | The patient volunteers the allergy before the clinician asks |
| `language_discipline` | Patient turns are ≥ 95% Spanish tokens; clinician turns ≥ 95% English — unless the scenario explicitly enables code-switching, in which case the scenario's own bound applies | Agent drifts into the trainee's output language and quietly removes the need to interpret |
| `role_boundary` | The patient never produces clinician-only speech acts (orders, diagnoses, prescriptions) and vice versa | Role collapse |
| `persona_facts_stable` | Age, medications, symptom onset and named allergies match the scenario record across the whole session | The patient's dose changes mid-session, making the fidelity score meaningless |
| `rubric_vocabulary_canary` | No taxonomy term, rubric phrase, severity word or scoring vocabulary appears in any counterpart turn or its context window | **Information isolation has failed** (principle 4) |

Metric: `persona_consistency` = clean turns / total turns, plus a per-check violation breakdown so a single systematic bug does not read as generalised flakiness.

**Gate.** `persona_consistency ≥ 0.95`; `rubric_vocabulary_canary` violations **= 0**, which is a hard fail on its own regardless of the aggregate.

**Blocks on failure.** Merging a scenario or a counterpart-agent prompt change; L5 rung sign-off. A canary violation additionally invalidates any EV-05 run performed under that build — the isolated arm was not isolated.

**Why deterministic.** The state graph is data the system already owns. Asking a language model whether a persona was consistent would import the exact class of unfalsifiable judgement this project exists to avoid.

### 4.6 EV-05 — The information-isolation leakage A/B

**Measures.** The load-bearing architectural claim (principle 4): that a counterpart agent which can see the scoring rubric will unconsciously speak in easier-to-interpret ways, destroying training realism. This is the L8 rung's number, and it is the justification for the multi-agent design. If the claim is untested, the architecture is a preference.

**Design.** Paired, two-arm, everything held constant except one block of context.

| | Arm A — isolated (production) | Arm B — leaked |
|---|---|---|
| Counterpart context | Scenario, state graph, persona, dialogue history | Identical, **plus** the full rubric and error taxonomy appended |
| Scenario set | Same N scenarios, same order | Same |
| Seeds | Fixed per (scenario, turn) | **Same seeds as Arm A** |
| Trainee side | Fixed scripted renderer, held constant | Identical |
| Model, quantisation, decode params | Held constant | Held constant |

Pairing is by `(scenario_id, turn_index)`, which removes between-scenario variance — the dominant noise source — and is why this design has usable power at a feasible N. Pre-registered size: **24 scenarios × ~12 counterpart turns ≈ 288 paired turns**, recorded in the registry *before* the run.

**Primary outcome — utterance difficulty index.** A deterministic, model-free score over each generated counterpart utterance, computed by `src/rehearsal/evals/suites/ev05_leakage.py` from countable features (weights fixed and versioned before the run):

| Feature | Direction | Why it is a difficulty feature |
|---|---|---|
| numerals + dosage/frequency expressions | ↑ harder | The critical error class; high interpretive load |
| negation particles, and negation scope depth | ↑ harder | Negation flips are the classic critical distortion |
| laterality and temporal-onset markers | ↑ harder | Provably decidable, easily dropped |
| token count, and clauses per utterance | ↑ harder | Working-memory load on the interpreter |
| subordinate-clause depth | ↑ harder | Syntactic restructuring across languages |
| idiom / colloquialism hits against a fixed lexicon | ↑ harder | Requires pragmatic transfer, not word substitution |
| sentence-final chunking pauses inserted by the agent | ↓ easier | Spoon-feeding: the tell that the agent is helping |

**Statistic.** Paired permutation test, 10 000 permutations, on the difference in mean difficulty index (Arm A − Arm B), α = 0.05, two-sided; effect size reported as **Cliff's delta** with a bootstrap CI. The directional hypothesis is registered in advance: **Arm B produces lower difficulty**, i.e. the leaked agent makes life easier. A two-sided test is used anyway so that a surprise in the other direction is visible rather than discarded.

**Secondary outcome — proxy fidelity score.** The fixed scripted trainee renderer is scored by the grader in both arms. If Arm B's fidelity scores are higher with identical rendering logic, the source utterances got easier. This is a *proxy*, stated as such: it is not evidence about human trainees, and it inherits every limitation of the grader itself.

**Tertiary outcome — canary rate.** How often Arm B leaks rubric vocabulary verbatim into speech. This is the crude, unmissable form of the effect; the difficulty index catches the subtle form.

**Gate.** None. This is a pre-registered measurement, not a threshold. Gating it would create an incentive to keep re-running until it passes, which is the failure mode it exists to prevent.

**Blocks on failure.** Nothing mechanically. What it changes is the **claim**.

**What a null result means — stated in advance, so it cannot be retrofitted.** If the interval on `leakage_delta` includes zero, the honest report is: *"at this sample size and with this difficulty index, we did not detect a leakage effect."* That is not "isolation doesn't matter". Three live explanations must be listed alongside any null: (a) the study is underpowered — report the minimum detectable effect at the achieved N; (b) the difficulty index does not capture the channel the effect travels through — the leak may show up as topic selection or turn pacing, which the index does not measure; (c) there genuinely is no effect for this model class at this scale. **Isolation stays either way.** It costs one context-assembly boundary, its failure mode is invisible-but-severe, and removing a cheap safeguard on the strength of a null result is exactly the reasoning that produces incidents. What a null result removes is the *right to claim the architecture is proven load-bearing* — the documentation must then say "isolation is enforced as a precaution; the effect is unmeasured at our power."

### 4.7 EV-06 — Skill A/B (with vs without the packaged session skill)

**Measures.** Whether the L6 packaged skill — the session protocol, rubric and error taxonomy as a portable, versioned definition — actually improves task correctness, or is documentation wearing an artifact's clothes.

**Design.** Same paired structure as EV-05, same scenarios and seeds. Arm A: orchestration runs with the packaged skill loaded. Arm B: the same orchestration with the skill absent and only the minimal inline instructions that predate it.

**Outcome — session-protocol checklist.** A fixed, deterministically-checkable list applied to every completed session:

| # | Check |
|---|---|
| 1 | Every trainee turn is segmented and attributed to exactly one source utterance |
| 2 | Turn roles (clinician / patient / trainee) are correctly labelled throughout |
| 3 | Every scored turn carries all required fields: source, rendering, errors, severities, spans |
| 4 | Error categories are drawn only from the nine-term taxonomy — no invented labels |
| 5 | Severity is present on every error and drawn from `critical` \| `non-critical` |
| 6 | The session report contains all required sections in the required order |
| 7 | The pre-session briefing and the post-session review gate both fired |
| 8 | Every audio blob referenced by the report resolves to a stored blob |

**Statistic.** `skill_delta` = mean checklist pass rate (Arm A) − (Arm B), paired by scenario, bootstrap CI over scenarios. Per-item binary agreement is tested with **McNemar's test** on discordant pairs, which is the correct test for paired binary outcomes and is not interchangeable with a two-proportion z-test here.

**Gate.** The skill must not be worse: lower CI bound ≥ −0.02.

**Blocks on failure.** Shipping the skill as a claimed improvement. If the interval contains zero, the report says "no measurable benefit at this N" — and the follow-on question is asked in the open: *does the skill earn its maintenance cost?* A packaged skill that measurably changes nothing is a candidate for deletion, and this eval is what makes that a decidable question instead of a taste argument.

### 4.8 EV-07 — Latency and real-time budget conformance

**Measures.** Whether the system meets the conversational timing that makes the whole approach viable, and specifically whether principle 5 holds in practice: **the grader finishes the previous turn inside the trainee's own speaking time.**

**Single source of truth.** The budget constants live in `src/rehearsal/runtime/budget.py` and are documented in `docs/05-voice-pipeline.md`. EV-07 imports them; it does not restate them. If a budget changes, one file changes and this eval enforces the new value automatically — there is no second copy to drift.

**Computed.** Replay `data/fixtures/sessions/*.json` through the live path with real models and real TTS on the target hardware class, N ≥ 200 turns:

| Metric | Definition |
|---|---|
| `p50_first_audio_ms`, `p95_first_audio_ms` | End of trainee speech → first counterpart audio frame |
| `p99_barge_in_stop_ms` | Trainee speech onset detected → TTS output silent |
| `grader_backlog_rate` | Fraction of turns where grading of turn *n* is incomplete when turn *n+1* begins |
| `grader_wall_ms` distribution | Grader latency in its own right, against the observed distribution of trainee speaking durations |
| `resident_memory_peak_gb` | Peak resident set across all three models during a full session |
| `audio_underrun_count` | TTS buffer underruns — audible glitches |

`grader_backlog_rate` is the operational statement of principle 5. The comparison is against the *observed* distribution of human speaking durations, not a nominal constant, because the latency budget **is** the human's speaking time and humans vary.

**Gate.** `grader_backlog_rate ≤ 0.05`; `p95_first_audio_ms` and `p99_barge_in_stop_ms` within the imported budget; `resident_memory_peak_gb` within the target envelope for the reference machine; `audio_underrun_count = 0`.

**Blocks on failure.** Release, and enabling any in-session coach feedback. A backlog-rate failure specifically triggers the fallback path in `docs/05-voice-pipeline.md` — grading degrades to end-of-session rather than per-turn, and the UI must say so, because a trainee who believes they are being scored per turn and is not has been misled by the interface.

**Reporting rule.** Latency is reported as a distribution with percentiles and the hardware class it was measured on. A mean latency figure is not accepted in this project: it hides exactly the tail that ruins a conversation.

### 4.9 EV-08 — End-to-end session completion and trainer-override rate

**Measures.** The L7 rung: whether full session orchestration with human gates actually completes, and whether the humans at the gates agree with the machine.

**Computed — completion.** Over all sessions started (replay fixtures plus any real sessions in local logs):

| Metric | Definition |
|---|---|
| `session_completion_rate` | Sessions reaching a written fidelity report / sessions started |
| `turn_capture_loss_rate` | Turns with missing or unusable trainee audio / total turns |
| `abandonment_stage` | Histogram of where incomplete sessions stopped (setup, briefing, mid-session, review) |
| `report_write_success` | Reports written and re-readable from SQLite + the content-addressed blob store |
| `recovery_rate` | Sessions that hit a recoverable error and still completed |

**Computed — trainer override.** Every reviewing trainer's edits are recorded as a diff against the grader's output. From `docs/06-scoring-engine.md`'s review record:

```
trainer_override_rate = (errors_added + errors_removed + severity_changed) / errors_proposed
```

broken out by direction (`added` / `removed` / `severity_up` / `severity_down`) and by category. Direction matters enormously and the aggregate hides it: heavy `removed` means the grader over-flags; heavy `added` means it misses; heavy `severity_up` is the dangerous one, because it means the grader is systematically under-calling clinical consequence, which is EV-02's failure showing up in the field.

**Gate.** `session_completion_rate ≥ 0.90`; `turn_capture_loss_rate ≤ 0.02`. `trainer_override_rate` is banded, not gated: **0.02–0.25**.

**Blocks on failure.** Completion failures block any pilot with real trainees and L7 sign-off. An out-of-band override rate blocks the *claim* that the grader is trusted in practice and forces a written interpretation in the report.

**Both tails of the override band are findings.** Above 0.25: trainers are rewriting the grader, and the score is theatre. Below 0.02: either the grader is genuinely excellent, or trainers are rubber-stamping — and the second is far more likely than the first. A suspiciously low override rate is treated as a review-process problem until proven otherwise, because principle 1 puts the human at the end of the chain and a human who always agrees is not a gate.

### 4.10 EV-09 — Regression suite on every prompt or model change

**Measures.** Whether a change that improved one thing quietly broke another. This is the cheapest eval in the suite and the one that prevents the most damage.

**Trigger — any of:** a prompt file changes (`prompts/**`), the grader or live model id / quantisation / runtime version changes, an extractor changes, the matching logic changes, the taxonomy or rubric changes, decode parameters change.

**Computed.** Re-run EV-00, EV-01 (DEV), EV-02 (DEV), EV-04 and EV-07 at fixed seeds and diff every metric against `data/evals/baselines/<eval_id>.json`. The report prints the delta table and, for EV-01/EV-02, the **item-level churn list**: which specific calibration items flipped from correct to incorrect and back. Aggregate stability hiding two offsetting item flips is a real event and the churn list is how it is seen.

**Gate.**

| Rule | Threshold |
|---|---|
| `extractor_conformance` | = 1.00 |
| `critical_recall` | ≥ baseline − 0.05 **and** ≥ 0.90 |
| `fp_rate_clean` | ≤ baseline + 0.05 |
| `kappa_macro` | ≥ baseline − 0.05 |
| `persona_consistency` | ≥ baseline − 0.02; canary = 0 |
| `p95_first_audio_ms`, `grader_wall_ms` p95 | ≤ baseline × 1.10 |

**Blocks on failure.** The merge. `make check` is the enforcement point, and the intended experience is that a regression is impossible to merge accidentally.

**Baseline discipline.** Baselines are re-frozen only by an explicit `rehearsal-evals baseline --freeze`, only on a clean git tree, and the freeze is recorded in the registry with the commit and a reason. Silently re-freezing a baseline after a regression converts this suite into decoration, and it is the single easiest dishonest move available in the whole project.

---

## 5. DEV/TEST split discipline

The calibration set is 40 items: **DEV 25**, **TEST 15**, split before any results were seen. The construction protocol is `SETUP.md` §6; this section is the operational discipline that keeps the split meaningful.

**Why the same split cannot be both optimised on and reported from.** Optimisation searches for a configuration that scores well on the data it can see. With 25 items and a handful of prompt candidates, a meaningful part of any observed gain is fitting the idiosyncrasies of those 25 items — including their labelling noise. Reporting that gain on the same items measures *how well the search worked*, not how well the grader generalises. The number is not merely optimistic; it is uninterpretable, because there is no way afterwards to separate real improvement from search artefact. A sealed split, touched rarely and never used as a signal, is the only thing that recovers the ability to say "this actually got better".

**The rules.**

1. **DEV is for everything.** Development, prompt iteration, automated optimisation, error analysis, staring at outputs. No restrictions.
2. **TEST is opened only to produce a reported number,** and only for a candidate that has already been chosen and pre-registered on DEV. TEST results never feed back into a prompt, an extractor, a threshold, or a rubric line.
3. **A deterministic guard enforces it.** `src/rehearsal/evals/seal.py` refuses to load `data/calibration/test.jsonl` unless the process was started through `rehearsal-evals unseal --reason "<text>"`. The reason is required, non-empty, and appended with the git commit and the run id to `data/calibration/TEST_ACCESS.log`, which is append-only. This is principle 1 applied to our own process: the human intends to be disciplined, and deterministic code makes the discipline hold at 2am.
4. **Every TEST access is reported.** The count of TEST evaluations to date is printed in every report that quotes a TEST number. Ten unseals with the best one reported is optimisation-by-multiple-comparison, and the visible count is what makes that impossible to do quietly.
5. **Never re-split, never rebalance.** If the split ever needs to change, it is a new calibration set with a new dataset hash, and all prior TEST numbers are retired rather than compared across.
6. **Corrections are logged, never silent.** A label found to be genuinely wrong is corrected in `data/calibration/CHANGELOG.md` with the reason, and every affected number is recomputed and re-reported. Editing a label to make a metric look better is the fastest available route to a dishonest project.

**Honest statement of what 15 items buys.** A sealed TEST split of 15 items yields wide intervals: it can distinguish "the grader roughly works" from "it doesn't", and it cannot distinguish κ = 0.70 from κ = 0.80. Every TEST number is therefore reported as a point estimate with its interval and its n, and comparisons inside the interval are reported as *not distinguishable*, never as improvements. The right fix is more labelled items, and that is a named gap, not something to be argued around.

---

## 6. The prompt-optimisation loop and its honest reporting protocol

The L10 rung runs a DSPy/GEPA-style optimiser over the **grader's prompt**, using agreement with the human calibration labels as the metric. Scope, stated once: **prompt-level optimisation only.** No weight training, no fine-tuning, no reinforcement learning, no LoRA adapters — a deliberate exclusion, because the project's credibility rests on reproducibility and on being able to point at exactly what changed, and a changed weight file is not inspectable in the way a diffed prompt is.

**The metric the optimiser sees.** A composite over DEV, weighted so the optimiser cannot trade away safety:

```python
def optimisation_metric(r: EvalResult) -> float:
    """Grader-prompt optimisation objective. Safety-dominant by construction."""
    if r.metrics["critical_recall"] < 0.90:      # hard floor, not a penalty term
        return 0.0
    return (
        0.60 * r.metrics["critical_recall"]
        + 0.25 * r.metrics["kappa_macro"]
        + 0.15 * (1.0 - r.metrics["fp_rate_clean"])
    )
```

The floor is a hard zero rather than a soft penalty deliberately: a soft penalty is a price, and an optimiser will pay a price. A floor is a wall.

**The protocol, in dependency order.**

1. **Freeze the baseline.** Record the current prompt version, its DEV metrics and its most recent TEST metrics into the registry. Nothing that follows is comparable without this.
2. **Optimise on DEV only.** The optimiser never sees TEST. `seal.py` makes this structural, not a matter of care.
3. **Record the search budget.** Candidates evaluated, total tokens, wall time, seeds. A gain from 400 candidates and a gain from 8 are different claims about generalisation, and the budget is what lets a reader tell them apart.
4. **Pre-register the single candidate.** Before unsealing, write to the registry: the chosen prompt version, its DEV metrics, and the expected direction and rough size of the TEST change. One candidate. Choosing after seeing TEST is the contamination this whole section exists to prevent.
5. **Unseal once,** with a reason string, and evaluate baseline and candidate on TEST in the same run under identical conditions.
6. **Report all four cells.** Baseline-DEV, candidate-DEV, baseline-TEST, candidate-TEST, each with its interval. The DEV gain and the TEST gain are printed side by side; **the gap between them is the overfitting estimate** and is reported as such, not buried.
7. **Apply the honesty rule on the outcome.** If the TEST improvement is smaller than the width of its interval, the reported result is **"no measurable improvement on the sealed split"** — even when DEV improved substantially, even when the new prompt is obviously more sensible to read. The prompt may still ship on the strength of DEV plus judgement; what may not happen is describing an unmeasurable change as a measured gain.
8. **Ship as a versioned artifact.** The winning prompt is committed as `prompts/grader/vN+1.md` — new file, never an in-place edit — with the run id in its header. Prompts are code: version-controlled, diffed, reviewed. Never a value pasted into a dashboard.
9. **Re-baseline EV-09** explicitly, with the reason recorded.

**A regression is reported too.** If optimisation makes things worse on TEST, that goes in the report and in `plans/metrics-snapshot.md` with the same prominence a gain would get. A measurement system that only publishes its wins has stopped being a measurement system.

---

## 7. The eval registry

Every eval run appends one immutable record. Without it, a metric is an anecdote: nobody can tell which model, which prompt, which data or which seed produced it, and a number that cannot be reproduced cannot be defended.

**Storage.** SQLite at `data/evals/registry.db` (the project's local store; see the storage design in `docs/06-scoring-engine.md`), with a JSON mirror per run at `data/evals/runs/<run_id>.json` so records survive independently of the database file and diff readably in review.

```sql
-- data/evals/registry.db
CREATE TABLE eval_runs (
    run_id            TEXT PRIMARY KEY,        -- ULID, lexicographically ordered
    created_at        TEXT NOT NULL,           -- ISO-8601 UTC
    suite_version     TEXT NOT NULL,           -- version of the eval harness itself
    eval_id           TEXT NOT NULL,           -- 'EV-02'
    split             TEXT NOT NULL,           -- dev | test | fixture | live | replay

    git_commit        TEXT NOT NULL,
    git_dirty         INTEGER NOT NULL,        -- 1 = uncommitted changes; a dirty run may never be cited

    prompt_role       TEXT,                    -- grader | clinician | patient | coach
    prompt_version    TEXT,                    -- 'grader/v7'
    prompt_sha256     TEXT,                    -- hash of the exact rendered prompt text

    model_role        TEXT NOT NULL,           -- live | grader | tts
    model_id          TEXT NOT NULL,
    model_quant       TEXT NOT NULL,           -- e.g. 'q4_k_m'
    model_sha256      TEXT NOT NULL,           -- weights hash
    runtime           TEXT NOT NULL,           -- 'mlx 0.x' | 'llama.cpp <build>'

    dataset_path      TEXT NOT NULL,
    dataset_sha256    TEXT NOT NULL,           -- detects silent label edits
    n_items           INTEGER NOT NULL,

    seed              INTEGER NOT NULL,
    temperature       REAL NOT NULL,
    top_p             REAL NOT NULL,
    max_tokens        INTEGER NOT NULL,

    host_class        TEXT NOT NULL,           -- 'apple-silicon-48gb'
    metrics_json      TEXT NOT NULL,           -- {"critical_recall": <r>, ...}
    intervals_json    TEXT NOT NULL,
    gate              TEXT NOT NULL,           -- pass | fail | report_only | skipped
    gate_detail       TEXT NOT NULL,
    artifact_path     TEXT,
    unseal_reason     TEXT,                    -- required when split = 'test'
    notes             TEXT NOT NULL DEFAULT ''
);

CREATE INDEX idx_eval_runs_eval  ON eval_runs(eval_id, created_at);
CREATE INDEX idx_eval_runs_split ON eval_runs(split, created_at);

-- Append-only, enforced by the database rather than by discipline.
CREATE TRIGGER eval_runs_no_update BEFORE UPDATE ON eval_runs
BEGIN SELECT RAISE(ABORT, 'eval_runs is append-only'); END;

CREATE TRIGGER eval_runs_no_delete BEFORE DELETE ON eval_runs
BEGIN SELECT RAISE(ABORT, 'eval_runs is append-only'); END;
```

```python
# src/rehearsal/evals/registry.py
def record_run(result: EvalResult, ctx: RunContext) -> str:
    """Append one immutable run record; returns the run_id.

    Raises RegistryError if ctx.git_dirty and ctx.split in {"test", "live"} —
    a number produced from uncommitted code cannot be reproduced, so it is not
    allowed to enter the record at all for the splits people quote.
    """
```

**Rules.**

- **Append-only, enforced by triggers.** Corrections are new rows referencing the superseded `run_id` in `notes`. Nothing is ever edited.
- **A dirty tree cannot produce a citable number.** Fixture and DEV runs on a dirty tree are recorded with `git_dirty = 1` and are refused by `report.py` as sources for `plans/metrics-snapshot.md`. TEST and live runs on a dirty tree are refused outright.
- **`dataset_sha256` is the tamper check.** If the calibration file changes without a `CHANGELOG.md` entry, the hash mismatch surfaces at the next run.
- **Seeds are recorded, never defaulted implicitly.** Every run states its seed; stochastic evals are run at ≥ 3 seeds and reported as a distribution, per principle 7.
- **The registry is local and git-ignored** (it contains session-derived material). What *is* committed is `plans/metrics-snapshot.md` — the single place current headline numbers live, updated in the same working session as the run that changed them, per `SETUP.md` §9.

---

## 8. Statistical conventions

Fixed once here so no eval invents its own and no two numbers turn out incomparable.

| Convention | Choice | Why |
|---|---|---|
| Interval level | 95% throughout | One level, stated everywhere |
| Proportions with small n | **Wilson score interval** | The normal approximation is badly wrong at n ≈ 10–15, which is most of this project |
| Complex statistics (κ, macro-averages) | Percentile bootstrap, 2000 resamples, **resampled over items** | Errors within an item are not independent; resampling errors would understate the interval |
| Paired A/B tests | Permutation test, 10 000 permutations, two-sided, α = 0.05 | Distribution-free, appropriate at this N, no normality assumption to defend |
| Paired binary outcomes | McNemar's test | The correct test for discordant pairs |
| Effect size | Cliff's delta (ordinal), absolute difference (rates) | Report the size, not only the p-value — a significant trivial effect is still trivial |
| Multiple comparisons | Report the number of comparisons made; no automatic correction | With this few pre-registered tests, transparency beats a correction procedure argued over after the fact |
| Rounding | Two decimals for rates and κ; milliseconds as integers | False precision is a reporting bug |
| Stochastic evals | ≥ 3 seeds, report median and range | Principle 7: rates and distributions, never a single lucky run |
| Denominators | **Always printed** next to every rate | "0.90" over 10 items and over 1000 items are different claims |

---

## 9. What these evals cannot tell you

The most important section, and the one that must not be softened.

### 9.1 They do not establish that trainees improve in real practice

Nothing in this suite is evidence that a person who practises with Rehearsal becomes a better interpreter in a real clinical encounter. Every number here measures **the system's internal validity**: whether the grader agrees with a human labeller, whether the agents stay in character, whether the loop meets its timing budget. That is a claim about the instrument, not about the outcome.

Stated plainly, as it must be stated in any public description of the project: **Rehearsal has not been shown to improve interpreting performance.** It has been shown to score interpreting turns in measurable agreement with a human expert's labels on a small held-out set. Those are different claims and the gap between them is not rhetorical.

### 9.2 What a legitimate efficacy claim would require

A prospective, pre-registered, controlled study — designed before data collection, not assembled from usage logs afterwards:

| Element | Requirement |
|---|---|
| Design | Two-arm randomised controlled trial, randomised at the trainee level, ideally stratified by baseline proficiency |
| Arms | Rehearsal practice vs an **equal-time** active control (conventional practice: role-play, recorded drills). Not a no-treatment control — that measures only that practice beats no practice. |
| Primary outcome | Fidelity performance on a **live or OSCE-style encounter that is not part of the training system**, scored by certified interpreter raters who are blind to arm assignment |
| Secondary outcomes | Critical-error rate specifically; certification-exam pass rate; supervisor ratings in real clinical placement |
| Retention | A delayed post-test after a no-practice interval — immediate gains that vanish are not learning |
| Sample size | Determined by an a-priori power analysis on the minimum clinically meaningful reduction in critical-error rate, not by however many trainees happen to be available |
| Blinding | Raters blind to arm; trainees cannot be blinded, so expectancy effects must be measured, not assumed absent |
| Registration | Protocol and analysis plan registered before enrolment, with the primary outcome named in advance |
| Ethics | Institutional review, informed consent, and a clear position that this is a training aid — never an assessment of employability or competence for credentialing |

Until such a study exists, the defensible claim is: *unlimited private practice with measured, standards-referenced feedback, where the feedback's agreement with expert human judgement has itself been measured and reported with its uncertainty.* That is a real and useful claim. It is not an efficacy claim and must never be dressed as one.

### 9.3 The other named gaps

| Gap | What it means | Would be closed by |
|---|---|---|
| **n = 1 labeller** | The "human standard" is one person's careful application of the published standard. `kappa_inter` on ~15 items is the only check, and it may be absent. | Multiple certified interpreter labellers across the full set |
| **40 items is small** | Intervals are wide; per-category κ for rare categories is barely estimable; the sealed split cannot resolve moderate differences. | More labelled items; the growth path is more expensive labelling, not cleverer statistics |
| **Seeded, not naturalistic, errors** | Calibration errors were deliberately introduced to cover the taxonomy. The severity mix does **not** estimate real-world error prevalence, and nothing here should be read as an epidemiological claim about how often interpreters make which errors. | An observational corpus of real interpreted encounters, labelled the same way — with all the consent and privacy work that entails |
| **Simulated speech ≠ real patients** | The counterpart agents produce clean, well-formed, single-accent speech. Real encounters bring overlapping speech, distress, dialect variation, background noise and interruption. Persona consistency measures fidelity to a state graph, not fidelity to a real human. | Evaluation against recorded real encounters |
| **es-MX only** | One Spanish variant, one voice pair. Generalisation to other variants is unmeasured. | Variant-stratified calibration items |
| **Indigenous languages are out of scope** | The population this project is grounded in — Watsonville and the Pajaro Valley — includes substantial Mixteco and Triqui speakers, for whom Spanish is a second language and interpreting is often relayed. **Rehearsal does not serve them.** This is a real limitation of who the tool helps, not a technical footnote, and it is stated in every description of scope. | Out of reach at model and data level; the honest position is to name the exclusion, not to imply coverage |
| **The proxy trainee in EV-05/EV-06** | The A/Bs use a scripted renderer, not humans. They measure what the *system* does differently, not what a *person* would do differently. | Human-in-the-loop arms, which require the study design in §9.2 |
| **Grader-as-yardstick circularity in secondary outcomes** | Where an eval scores an arm using our own grader, the grader's error profile is inherited by that measurement. Primary outcomes are therefore deterministic wherever it is possible to make them so. | Human scoring of A/B arms |
| **Out of scope by design** | No weight training, fine-tuning, RL or LoRA; no custom inference server; no multi-tenant fleet scaling. These are deliberate exclusions in service of reproducibility and a single inspectable local runtime — not gaps to be closed later. | n/a — reasoned exclusions |

### 9.4 The rule that follows from all of it

Every published number in this project carries, in the same breath: **its denominator, its interval, and its ceiling.** A metric without those three is not permitted in the report, the UI, `plans/metrics-snapshot.md`, or any description of the product. `report.py` enforces the ceiling rule mechanically for the headline metric; the rest is the standing editorial rule for this documentation set.

---

## 10. Status register

| Item | Status | Note |
|---|---|---|
| Metric hierarchy and headline/safety naming | **Decided** | Headline = grader agreement with human labels; safety = critical-error recall |
| EV-00 … EV-09 suite composition | **Decided** | Each rung of the layer vertical owns at least one |
| Span matching at IoU ≥ 0.5, greedy | **Decided**, flagged | Revisit if turns routinely exceed ~5 overlapping errors |
| κ computed over turn×category presence | **Decided** | Provides the fixed decision opportunities κ requires |
| `kappa_macro ≥ 0.60` gate value | **Proposed** | Should be re-derived as a fraction of the measured human ceiling once `kappa_intra` exists |
| `fp_rate_clean ≤ 0.15` gate value | **Proposed** | Coarse at 12 clean items; tighten as the bucket grows |
| EV-05 difficulty-index feature weights | **Proposed** | Must be frozen and registered *before* the leakage run; weights are currently reasoned, not empirically derived |
| EV-05 sample size (24 scenarios ≈ 288 paired turns) | **Proposed** | Pre-register; report the minimum detectable effect achieved |
| Trainer-override band 0.02–0.25 | **Proposed** | Both edges are judgement; will be re-set from observed data |
| Inter-rater agreement (`kappa_inter`) | **Open** | Depends on securing a second qualified labeller; absence is reported as a named gap, never omitted |
| Efficacy evidence | **Open — and out of current scope** | Requires the study design in §9.2. No claim of trainee improvement is made until it exists. |

---

## Related documents

| Document | Relationship |
|---|---|
| `SETUP.md` §6 | The calibration set: construction, labelling protocol, the split. This document consumes it and does not restate it. |
| `SETUP.md` §9 | The living-numbers update rule: `plans/metrics-snapshot.md` is updated in the same session as the run that changed a number. |
| `docs/01-research.md` | The error taxonomy and the standards it derives from |
| `docs/05-voice-pipeline.md` | The latency budget EV-07 enforces, and the degradation path on failure |
| `docs/06-scoring-engine.md` | The scorer under test: extractors, the structured call, the review record EV-08 reads |
| `docs/07-data-and-scenarios.md` | Scenario bank and the clinical state graphs EV-04 checks against |

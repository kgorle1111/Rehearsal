# Changelog

All notable changes to Rehearsal are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), adapted for a system whose observable behaviour is determined by **prompts and model weights as much as by code**. Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html), with the compatibility surface defined in §3.

**No dates appear in this file.** Entries are ordered by version, newest first. Release ordering is a dependency fact; calendar time is not.

---

## 1. Why this changelog is not a normal changelog

A conventional changelog assumes that reading the diff tells you what changed. That assumption fails here in three specific ways:

1. **A prompt edit changes behaviour with no code diff.** Promoting `prompts/grader/v3.md` to `v4.md` can move critical-error recall by more than any refactor in `src/`. A changelog that only lists code changes would report that release as "no changes".
2. **A model or runtime swap changes behaviour with no repository diff at all.** Re-quantising the grader, or moving from MLX to the llama.cpp fallback, alters outputs while every tracked file stays byte-identical.
3. **Scoring behaviour is a safety surface.** Rehearsal tells a trainee that they omitted a dosage. If the release that changed that judgement did not record how agreement with the human calibration labels moved, no reviewer — and no trainer deciding whether to trust the report — can evaluate the release at all.

Hence the project-specific rule below. It is not stylistic; `make check` and the release gate in `docs/13-deployment-ops.md` enforce parts of it mechanically.

---

## 2. The four-part release record (mandatory)

> **RULE — every release entry MUST record all four of the following. A release entry missing any part is incomplete and must not be tagged.**
>
> | # | Part | What it records | Where the fact comes from |
> |---|---|---|---|
> | 1 | **Code** | Every user-visible or behaviour-affecting source change, filed under the §4 section taxonomy | The diff |
> | 2 | **Prompts** | The version of every prompt file in play, before → after, for `prompts/grader/`, `prompts/clinician/`, `prompts/patient/`, plus the coach prompt when present. Unchanged prompts are listed as unchanged, never omitted | `prompts/**` heads |
> | 3 | **Models** | Model id, parameter class, quantisation, and local runtime + version for every model in the loop (live agents, grader, TTS voices), before → after. Unchanged models are listed as unchanged | `make smoke-models` output; `models.lock.json` |
> | 4 | **Eval delta** | `kappa_macro` and `critical_recall` **before and after**, on DEV and TEST, each with its interval, plus the `run_id` of the eval registry rows the numbers came from | `make evals` → `data/evals/registry.db` |
>
> **A release that changes scoring behaviour without recording the eval delta is unreviewable.** Publishing one is the single failure mode this document exists to prevent.

### 2.1 Scope of "changes scoring behaviour"

The eval delta is mandatory for **every** release, but a *re-run* of the eval suite is mandatory when any of the following changed — the same trigger list as the regression gate EV-09 in `docs/08-evals.md` §5:

- any file under `prompts/**`
- the grader or live model id, parameter class, quantisation, or runtime version
- any deterministic extractor in `src/rehearsal/scoring/extractors/`
- the span-matching or merge logic in `src/rehearsal/scoring/`
- the error taxonomy, severity rules, or rubric
- decode parameters (temperature, top-p, seed, max tokens) for any model

If none of those changed, the eval delta is still recorded, as **"unchanged — no re-run trigger; carried from `run_id` …"**. An empty cell is never acceptable; a stated reason is.

### 2.2 Reporting the eval numbers honestly

Per principle 7 and `docs/08-evals.md` §7, numbers in this file obey the same reporting rules as every other report the project emits:

- **DEV and TEST are labelled separately.** DEV is the tunable split. TEST is sealed and is **reported, never gated** — a release is never justified by a TEST movement.
- **Every point estimate carries its interval.** `critical_recall` on TEST is a proportion over ~15 sealed items; a bare "0.93" implies a precision the sample cannot support. Wilson interval, always.
- **The human ceiling is printed adjacent.** `kappa_macro` may not appear in this file without `kappa_intra` beside it. `report.py` enforces this for generated reports; here it is on the author, and reviewers must reject entries that omit it.
- **Regressions are stated in the entry, not buried in a linked run.** If `critical_recall` fell, the entry says so, in the entry, with the enumerated missed items' ids.
- **Overlapping changes are not attributed to a single cause.** If a release changes both a prompt and an extractor, the entry does not claim which one moved the number unless an ablation run id is cited.

### 2.3 Release gates that block a tag

Recorded here for reference; the authority is `docs/08-evals.md` §4 and `docs/13-deployment-ops.md`.

| Gate | Condition to tag a release | On failure |
|---|---|---|
| `critical_recall` (DEV) | ≥ 0.90 **and** ≥ frozen baseline − 0.05 | Release blocked. No exceptions, no "known issue" waiver |
| `kappa_macro` (DEV) | ≥ 0.60 **and** ≥ frozen baseline − 0.05 | Release blocked for any change touching the scorer |
| `fp_rate_clean` | ≤ 0.15 **and** ≤ baseline + 0.05 | Release blocked |
| `extractor_conformance` | = 1.00 | Release blocked |
| Latency p95 | ≤ baseline × 1.10 | Release blocked (see `docs/05-voice-pipeline.md`) |
| `kappa_intra` present | Must exist to publish any `kappa_macro` | Number may not be published |
| Per-category recall < 0.50 | Permitted, **but** the category must be labelled "not reliably detected" in the UI and named in the entry | Silent shipping is the violation |

---

## 3. Versioning policy

`MAJOR.MINOR.PATCH`. The compatibility surface is broader than the HTTP API, because trainees, trainers and stored sessions all depend on things a normal API contract does not cover.

| Bump | Triggered by |
|---|---|
| **MAJOR** | Breaking change to the session API or WebSocket protocol (`docs/11-backend-api.md`); a SQLite schema migration that is not backward-readable; a change to the error taxonomy's category set or severity definition; any change that makes previously stored session reports mean something different than when they were generated |
| **MINOR** | New scenario, new extractor, new UI surface, new eval; a **grader prompt promotion**; a model swap within the same parameter class; additive API fields |
| **PATCH** | Bug fixes with no scoring-behaviour change; docs; dependency bumps; performance work that leaves all gated metrics inside their baselines |

Additional rules:

- **A grader prompt promotion is never a PATCH.** It changes what the system tells a human about their clinical language. It is at minimum a MINOR, and it is a MAJOR if it changes what a category *means* rather than how well it is detected.
- **Prompt versions are independent of the release version.** `prompts/grader/v4.md` is a file identity, not a semver. Both are recorded.
- **Model versions are pinned in `models.lock.json`,** and the lock hash appears in the Models block. A release that regenerates the lock without a Models block entry is invalid.
- **`0.x` releases:** MINOR carries breaking changes; the compatibility table above applies from `1.0.0`.

---

## 4. Section taxonomy

Use these headings, in this order, omitting any that are empty. The first six are Keep-a-Changelog standard; **Evaluation** is project-specific and is never omitted.

| Section | Contents | Not this |
|---|---|---|
| **Added** | New capabilities: scenarios, extractors, evals, UI surfaces, endpoints, CLI targets | Improvements to something that already existed |
| **Changed** | Behaviour changes to existing capability, including prompt promotions, model swaps, rubric wording, threshold changes, UI reworks | Fixes to something that was broken |
| **Deprecated** | Still present and working, scheduled for removal; must name the replacement and the release that will remove it | Things already removed |
| **Removed** | Deleted capability, endpoint, prompt version, scenario or eval; must name the migration path for stored data | Refactors with no external effect |
| **Fixed** | Defects corrected; must state the observable symptom, not just the internal cause | Behaviour changes that were not bugs |
| **Security** | Anything touching the trust boundary in `docs/12-security-privacy.md`: audio/transcript handling, retention, local-only guarantees, file permissions, dependency CVEs | Generic hardening with no threat-model bearing |
| **Evaluation** | The eval delta, gate outcomes, calibration-set changes, new or retired evals, and any honest caveat about what the numbers do and do not support. **Mandatory in every release.** | Marketing summaries of the numbers |

Two conventions inside sections:

- **Write the observable behaviour first, the mechanism second.** "Dosage omissions in compound frequency phrases ('twice daily with food') are now flagged — the frequency extractor previously stopped at the first token" beats a description of the regex.
- **Link by exact filename.** Cross-reference `docs/06-scoring-engine.md`, `docs/08-evals.md`, `SETUP.md` §6 and so on by name, and reference eval runs by `run_id`. Never paste an eval table that already lives in `data/evals/runs/`.

### 4.1 Explicitly out of scope for this file

Rehearsal does no weight training, fine-tuning, RL or LoRA adaptation (see `docs/00-dossier.md`). There is therefore **no "Training" section and no checkpoint lineage** to record — the Models block records *which released weights were loaded and how they were quantised*, and nothing more. Prompt-level optimisation (`docs/08-evals.md` §6) is recorded under **Changed** (the prompt promotion) and **Evaluation** (the before/after on the sealed split).

---

## 5. Unreleased

### Added
_Nothing yet._

### Changed
_Nothing yet._

### Deprecated
_Nothing yet._

### Removed
_Nothing yet._

### Fixed
_Nothing yet._

### Security
_Nothing yet._

### Evaluation

**Prompts**

| Component | Before | After |
|---|---|---|
| `prompts/grader/` | — | — |
| `prompts/clinician/` | — | — |
| `prompts/patient/` | — | — |

**Models**

| Role | Model | Class | Quantisation | Runtime | Change |
|---|---|---|---|---|---|
| Live agents (clinician, patient) | — | Gemma 4 E4B | — | — | — |
| Fidelity grader | — | Gemma 12B | — | — | — |
| TTS (en-US, es-MX) | — | — | — | — | — |

**Eval delta**

| Metric | Split | Before | After | Δ | Gate |
|---|---|---|---|---|---|
| `critical_recall` | DEV | — | — | — | ≥ 0.90 |
| `critical_recall` | TEST (sealed) | — | — | — | reported, not gated |
| `kappa_macro` | DEV | — | — | — | ≥ 0.60 |
| `kappa_macro` | TEST (sealed) | — | — | — | reported, not gated |
| `kappa_intra` (human ceiling) | — | — | — | — | must be present |

_Run ids: —. Calibration set: `data/calibration/` unchanged; see `SETUP.md` §6 for the protocol._

---

## 6. Contributor template

Copy this block verbatim into a new version heading above **Unreleased** at release time. Delete empty sections **except Evaluation**, which is never deleted.

```markdown
## X.Y.Z

### Added
- <capability> — <what a user can now do>. See `docs/<file>.md`.

### Changed
- <observable behaviour change first, mechanism second>.
- Grader prompt promoted `prompts/grader/vN.md` → `vN+1.md` (optimiser run `<run_id>`;
  candidates rejected: <n>, including <the tempting one and why it was rejected>).

### Deprecated
- <thing> — replaced by <thing>; scheduled for removal in <version>.

### Removed
- <thing> — migration for existing sessions: <path>.

### Fixed
- <symptom a user would have observed> — <cause> (`src/rehearsal/<path>`).

### Security
- <change> — threat addressed, per `docs/12-security-privacy.md` §<n>.

### Evaluation

**Prompts**

| Component | Before | After |
|---|---|---|
| `prompts/grader/` | vN | vN+1 |
| `prompts/clinician/` | vN | unchanged |
| `prompts/patient/` | vN | unchanged |

**Models**

| Role | Model | Class | Quantisation | Runtime | Change |
|---|---|---|---|---|---|
| Live agents | <model id> | Gemma 4 E4B | <q> | MLX <ver> / llama.cpp <ver> | unchanged |
| Fidelity grader | <model id> | Gemma 12B | <q> | MLX <ver> | <q_old> → <q_new> |
| TTS en-US / es-MX | <voice ids> | — | — | <runtime> | unchanged |

`models.lock.json` sha256: `<before>` → `<after>`. Resident memory p95: <n> GB (budget 20–24 GB).

**Eval delta**

| Metric | Split | Before | After | Δ | Gate |
|---|---|---|---|---|---|
| `critical_recall` | DEV | 0.XX | 0.XX | +0.0X | ≥ 0.90 — PASS/FAIL |
| `critical_recall` | TEST (sealed) | 0.XX [Wilson a–b] | 0.XX [Wilson a–b] | +0.0X | reported |
| `kappa_macro` | DEV | 0.XX | 0.XX | +0.0X | ≥ 0.60 — PASS/FAIL |
| `kappa_macro` | TEST (sealed) | 0.XX | 0.XX | +0.0X | reported |
| `fp_rate_clean` | DEV | 0.XX | 0.XX | −0.0X | ≤ 0.15 — PASS/FAIL |
| `kappa_intra` (ceiling) | — | 0.XX | 0.XX | — | must be present |

Run ids: before `<run_id>`, after `<run_id>`. Calibration set: unchanged / corrected
(see `data/calibration/CHANGELOG.md`, entry `<id>`).

Re-run trigger: <which item from §2.1 fired>, or "none — carried from `<run_id>`".

Caveats: <what these numbers do NOT support — e.g. n=15 on TEST cannot distinguish a
0.03 movement from noise; category X remains below 0.50 recall and is labelled
"not reliably detected" in the UI>.
```

### 6.1 Checklist before tagging

- [ ] All four parts of §2 present (code, prompts, models, eval delta)
- [ ] `make check` green (lint, types, tests, evals)
- [ ] Every gate in §2.3 evaluated, with PASS/FAIL written in the entry
- [ ] `kappa_intra` printed adjacent to every `kappa_macro`
- [ ] TEST numbers labelled sealed and used for reporting only
- [ ] Every missed critical item enumerated by item id if `critical_recall` fell
- [ ] Any category below 0.50 recall named here and labelled in the UI
- [ ] Version bump matches §3 (grader prompt promotion is never a PATCH)
- [ ] No dates anywhere in the entry
- [ ] No secrets, no trainee audio, no transcript excerpts from real sessions

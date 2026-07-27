# Contributing to Rehearsal

Rehearsal scores how faithfully a human interpreted a clinical utterance. A wrong finding is not a cosmetic bug — it either tells a trainee they mangled a dosage when they did not, or tells them they were fine when they dropped a negation. Every rule in this document exists to keep that specific failure from shipping.

Read `README.md` for what the product is, `SETUP.md` for how to run it, and `docs/15-workstreams.md` for who owns which files. This document covers only how to change the code.

---

## 1. Ground rules

These are not style preferences. A change that violates one is rejected regardless of how good it looks.

| # | Rule | What it means concretely | How it is enforced |
|---|---|---|---|
| G1 | **A model never decides anything consequential.** | A language model may generate text, extract structure, or propose a label. It may not be the last thing between a dosage discrepancy and a `critical` finding. If a check is decidable — numbers, units, frequency, negation, laterality, allergy, temporal marker — it is written in Python and covered by an EV-00 fixture row. | Review; `import-linter` (`rehearsal.runtime` may not import `rehearsal.scoring`); `extractor_conformance = 1.00` gate |
| G2 | **Every non-trivial change ships a test or an eval.** | New branch, loop, parser, merge rule, or numeric path → a test that fails if the logic breaks. New model-facing behaviour → an eval suite result, not a test. "I ran it by hand and it looked right" is not a state this project recognises. | `make check`; review checklist §11 |
| G3 | **No capability claim without a measurement behind it.** | You may not write "handles Spanish decimal commas" in a docstring, a README, a UI string or a commit message unless a fixture row or an eval number demonstrates it. Claims live next to their number or they do not live. | Review; `plans/metrics-snapshot.md` is the only place headline numbers live |
| G4 | **Ground truth stays unblurred.** | No code path may merge, overwrite, or derive `TurnRecord.source` from `TurnRecord.rendering` or vice versa. The whole scoring problem is tractable only because these are independently known (`docs/15-workstreams.md` §5.1). | Schema (`additionalProperties: false`); contract round-trip tests |
| G5 | **Isolation is a code property, not an intention.** | The clinician and patient agents never receive rubric text, taxonomy vocabulary, learner-model content, or score records. Every context passes through `ContextAssembler`; nothing else builds a model context. | Static + runtime leak assertion in EV-05; rubric-vocabulary canary = 1.00 |
| G6 | **Never widen a gate to make a change pass.** | A gate threshold change is a contract change (§9) with a written rationale, landed on its own. Lowering a number so your branch goes green is the single most damaging thing you can do here. | Review; `plans/contract-changes.md` |
| G7 | **Honest reporting.** | Rates and distributions with stated uncertainty. A null result is a reportable outcome. A known gap is written down, not smoothed. | Review; `docs/08-evals.md` conventions |
| G8 | **Behaviour change updates its document in the same change.** | See §12. | Review; pre-commit gate reminder |

---

## 2. Development environment

Do not duplicate setup here. `SETUP.md` is authoritative:

| You need | Section |
|---|---|
| Prerequisites, Python 3.12, `uv`, Node | `SETUP.md` §1–§2 |
| Environment variables | `SETUP.md` §3 (and `.env.example`) |
| Models and the ~20–24 GB memory layout | `SETUP.md` §4 |
| Scenario and fixture data | `SETUP.md` §5 |
| **The calibration set protocol** | `SETUP.md` §6 — read this before touching anything in `rehearsal.scoring` or `prompts/grader/` |
| First-run checklist | `SETUP.md` §10 |

Minimum to be productive:

```bash
make install        # uv venv + editable install + frontend deps
make models         # download + verify the model set
make smoke-models   # one inference per model; must pass before you build anything
make check          # lint, types, tests, evals — the gate
```

`make help` lists every target. If a workflow you need is not a `make` target, it is not yet a supported workflow — add the target in your workstream's banner-commented block (`docs/15-workstreams.md` §3.1) rather than documenting a bare command.

Never commit `.env`, model weights, `data/calibration/test.jsonl` contents, or anything under `plans/` other than the files that workstream owns. `.gitignore` covers the known cases; the pre-commit gate scans the diff for the rest.

---

## 3. Repository layout

```
rehearsal/
├── src/rehearsal/
│   ├── contracts/            # WS-0. Generated from schemas/. NEVER hand-edited.
│   ├── store/                # WS-0. EventLog, BlobStore, projections, migrations/
│   ├── config.py             # WS-0. All environment reading happens here, once.
│   ├── scoring/              # WS-1. The L4 application.
│   │   ├── extractors/       #   deterministic, decidable checks — see §6
│   │   ├── grader.py         #   the single structured model call
│   │   ├── merge.py          #   VerdictMerger: extractor findings win over model findings
│   │   └── taxonomy.py       #   the nine error types, severities, span types
│   ├── runtime/              # WS-2/WS-3/WS-5. Live loop. May NOT import scoring.
│   │   ├── agents/           #   clinician.py, patient.py, context.py (the isolation chokepoint)
│   │   ├── audio_in.py, tts.py, hosts.py, budget.py
│   ├── content/              # WS-7. graph.py, bank.py, terms.py
│   ├── orchestrator/         # WS-4. Session state machine, SeedLedger, TurnScheduler
│   ├── learner/              # WS-5. Learner model + coach. Never visible to counterpart agents.
│   ├── optimise/             # WS-6. Prompt optimisation (L10 rung 1). Prompt-level only.
│   ├── evals/                # WS-9. EV-00…EV-09, metrics.py, seal.py, run registry
│   ├── api/                  # WS-8. FastAPI surface + /ws/session/{id}
│   ├── tools/                # fetch_models, smoke_models, make_label_sheet, split_calibration
│   └── cli.py                # WS-4 owns this file. Do not add your subcommand directly.
├── schemas/*.schema.json     # WS-0. The five frozen contracts. Source of truth.
├── prompts/                  # versioned prompt files — clinician/ patient/ coach/ grader/
├── skills/session-protocol/  # WS-4. The L6 packaged skill.
├── data/
│   ├── scenarios/            # the scenario bank
│   ├── fixtures/extractors/  # the EV-00 grid, one .jsonl per extractor
│   ├── calibration/          # dev.jsonl (25), test.jsonl (15, SEALED), TEST_ACCESS.log
│   └── evals/baselines/      # frozen baselines for regression_delta
├── frontend/                 # WS-8. SPA, no heavy framework.
├── tools/check_ownership.py  # the mechanical ownership guard
├── templates/                # ADR-template.md, scenario-template.md, calibration-label-sheet.md
├── plans/                    # git-ignored working material; metrics-snapshot.md lives here
└── docs/                     # numbered documents; see the table in README.md
```

**Exclusive write ownership is real.** The table in `docs/15-workstreams.md` §3 is the authority and `tools/check_ownership.py` enforces it against your merge base. You may read the entire repository — you are encouraged to — and write only your workstream's paths.

---

## 4. Branches and commits

**Branch per concern, named for the workstream:** `ws1/decimal-comma-extractor`, `ws3/barge-in-under-metal-contention`, `ws8/review-gate-keyboard-path`. A branch whose diff spans two workstreams' paths is rejected by the gate before a human reads it.

**Conventional commits.** `<type>(<scope>): <subject>`, imperative, ≤ 72 characters.

| Type | Use for |
|---|---|
| `feat` | new behaviour a user or another workstream can observe |
| `fix` | a defect with a reproducer that now passes |
| `perf` | latency or memory, with the before/after number in the body |
| `test` | tests or fixture rows only |
| `eval` | eval suites, metrics, baselines, calibration tooling |
| `prompt` | anything under `prompts/**` — always paired with a rerun eval (§8) |
| `contract` | `schemas/**` or generated `contracts/**`, landed alone (§9) |
| `docs` | documentation only, no behaviour change |
| `refactor` | no behaviour change, no new capability, gates unchanged |
| `chore` | tooling, deps, housekeeping |

Scope is the module or workstream: `scoring`, `extractors`, `runtime`, `orchestrator`, `api`, `frontend`, `evals`, `ws3`.

**The body explains why, not what.** The diff shows what changed. Say what was wrong, what would break if the change were reverted, and what you deliberately did not do.

```
fix(extractors): treat "0,5 mg" as a dose, not a range

Spanish clinical speech uses the decimal comma. The dose extractor read
"0,5 mg" as two tokens and emitted no finding, so a halved-dose rendering
scored clean — a critical miss in exactly the class the extractors exist
to catch. Found while labelling calibration item 013.

Fixture rows added for es decimal comma, en decimal point, and the
"1,5-2 mg" range case that is genuinely ambiguous and now raises.

Not fixed: thousands separators ("1.000 mg"). No clinical dose in the
scenario bank reaches four digits; add a row when one does.

CONTRACT-CHANGE: none
```

Required trailers when applicable:

| Trailer | When |
|---|---|
| `CONTRACT-CHANGE: CC-00NN` | the change touches a contract, or intentionally spans workstreams (§9) |
| `EVAL: <suite> <metric> <before> → <after>` | any change that moves a gated number |
| `UNSEAL: <reason>` | the change is the one reported TEST-split run (§8) |

Never rewrite a landed branch's history after review has started. Never force-push a shared branch.

---

## 5. Code standards

**Python 3.12.** Type hints on every function, including tests. `from __future__ import annotations` at the top of every module. `mypy rehearsal` runs in `make check` and is not advisory.

**ruff** for lint and format. Do not hand-format; do not reformat files you do not own — formatting churn in someone else's file is an invisible merge conflict.

**`Decimal` for anything numeric that affects a finding. No `float` anywhere in a scoring path.** This is the rule contributors most often get wrong, so it is stated exactly:

```python
from decimal import Decimal

# CORRECT — parsed from text, compared exactly
dose = Decimal("0.5")
if source_dose != rendering_dose:
    yield Finding(error="substitution", severity="critical", ...)

# WRONG — 0.1 + 0.2 != 0.3, and a trainee gets told they misread a dosage
dose = float(match.group("value"))
if abs(source_dose - rendering_dose) > 1e-9:
    ...
```

| Value | Type | Why |
|---|---|---|
| Doses, quantities, counts, frequencies-per-interval | `Decimal` | Exact comparison is the entire point; binary floats are not exact for decimal literals |
| Durations, timings, offsets | `int` milliseconds | Integers, monotonic, replayable |
| Severity, error type, direction, language | `enum.StrEnum` | Never bare strings in logic |
| Confidence, agreement, κ, rates | `float` | Statistics, not findings. Confined to `rehearsal.evals` and `verbatim_confidence`. |

A `float` appearing anywhere under `src/rehearsal/scoring/` is a review rejection. If you need one, you have found a design problem — raise it, do not cast it.

Other standards:

- **`Decimal` never round-trips through `float`.** Construct from `str`, never `Decimal(0.5)`.
- **No silent `except`.** Catch what you can name; every recovery path emits a `SessionEvent` or logs with the turn id.
- **Errors are prescriptive.** `raise ExtractorError(f"unit {unit!r} not in manifest; add it to data/scenarios/terms.yaml or extend UNIT_ALIASES")` — never "invalid input".
- **Deliberate shortcuts carry a `kn:` comment naming the ceiling and the upgrade path.** `# kn: linear scan over findings; index by span if a turn ever exceeds ~50`.
- **Delete dead code on sight** in files you own. Do not comment it out.
- **Comments state constraints the code cannot show.** Never narrate the next line.
- **Seeds are explicit.** Anything stochastic takes its seed from `SeedLedger`. No module-level `random` calls, no unseeded model calls. Replay determinism is a shipped guarantee.
- **Input validation at trust boundaries is never simplified away** — API payloads, audio device data, scenario files, calibration files. Same for error handling that prevents data loss.

**Frontend** (`frontend/`, WS-8): the design system in `docs/09-ui-ux.md` and the token contract in `docs/10-frontend-spec.md` are binding. Colours come from tokens, never literals. WCAG 2.1 AA is a gate (`make a11y`), including dark mode contrast tested independently rather than derived by inversion, and including "never colour alone" — a `critical` finding is marked by an icon and a label, not by `#DC2626`.

---

## 6. Adding a deterministic extractor

**This is the highest-value contribution in the repository.** Every extractor moves a class of clinically consequential error out of the model's hands and into provable code — which is principle 3 in its literal form. The extractors are also where critical recall actually comes from.

An extractor is a pure function: text and language in, a set of typed structures out. No I/O, no model, no session state, no clock.

### 6.1 The interface

```python
# src/rehearsal/scoring/extractors/base.py
from __future__ import annotations
from decimal import Decimal
from typing import Protocol, Sequence

class Extractor(Protocol):
    name: str          # stable id, matches the fixture filename: data/fixtures/extractors/<name>.jsonl
    langs: frozenset[str]   # {"en", "es"}

    def extract(self, text: str, lang: str) -> Sequence[Extraction]: ...

    def compare(
        self, source: Sequence[Extraction], rendering: Sequence[Extraction]
    ) -> Sequence[Finding]: ...
```

`extract` is what EV-00 grades: exact set equality against `expect`, no partial credit. `compare` turns a source/rendering pair into taxonomy findings and is graded through EV-01/EV-02.

### 6.2 Step by step

1. **Prove it is decidable.** Write the rule in one sentence with no hedging. "A dose is a decimal quantity followed by a mass or volume unit from the manifest." If you cannot, it belongs in the semantic residue the grader handles — say so and stop here.
2. **Claim the name.** Add a row to the extractor table in `docs/06-scoring-engine.md` in the same change. The name is the module name, the fixture filename, and the `Finding.detector` value forever.
3. **Write the fixtures first.** `data/fixtures/extractors/<name>.jsonl`, one JSON object per line:
   ```json
   {"id": "dose-es-comma-01", "text": "Tome media pastilla, 0,5 mg, cada 8 horas", "lang": "es",
    "expect": [{"kind": "dose", "value": "0.5", "unit": "mg"}]}
   {"id": "dose-clean-neg-01", "text": "No tome nada por la boca", "lang": "es", "expect": []}
   ```
   The grid **must** cover, per `docs/08-evals.md` §4.1: the plain case in both languages; Spanish diacritics; decimal comma vs decimal point; unit abbreviation variants (`mcg` / `µg` / `microgramos`); the negative case that must produce nothing; and at least three adversarial cases. `expect: []` rows are not optional — they are what measures false alarms.
4. **Implement it.** `src/rehearsal/scoring/extractors/<name>.py`. `Decimal` from strings. No `float`. Deterministic ordering of the returned sequence — sort by span start — because set equality with unstable order produces flaky evals.
5. **Write `compare`.** Decide, explicitly, what a mismatch is: an `omission` (present in source, absent from rendering), a `substitution` (present in both, different value), or a `distortion` (negation scope flipped). Assign `severity` from `taxonomy.SEVERITY_RULES`, not by hand at the call site.
6. **Register it.** Add the class to `EXTRACTOR_REGISTRY` in `src/rehearsal/scoring/extractors/__init__.py`. Registration is what puts it in `VerdictMerger` and in EV-00's coverage report; an unregistered extractor is invisible and will report as an uncovered row.
7. **Write the unit test.** `tests/scoring/test_<name>.py` — the fixture grid is driven generically by EV-00, so this file holds the cases fixtures cannot express: `compare` behaviour, error paths, and the ordering guarantee.
8. **Run the numbers and record them.**
   ```bash
   pytest -q tests/scoring/test_<name>.py
   uv run rehearsal-evals run EV-00 --extractor <name>   # must be exactly 1.00
   make evals                                            # EV-01/EV-02 on DEV; check source_split
   ```
   Report `critical_recall` and `fp_rate_clean` before and after in the commit body. A new extractor that raises recall while raising false alarms on clean items is a trade, not a win — say which you made.

### 6.3 Test requirement (non-negotiable)

| Requirement | Gate |
|---|---|
| A fixture file exists at `data/fixtures/extractors/<name>.jsonl` | EV-00 coverage report: 0 uncovered rows |
| `extractor_conformance = 1.00` for the new extractor | `make check` fails otherwise. This is decidable code; a failure is a bug, never a score. |
| At least one `expect: []` row per language | Review |
| ≥ 3 adversarial rows | Review |
| `fp_rate_clean` on DEV did not regress past its gate | `make evals` |

**The regression rule:** every extractor bug found anywhere — in a live session, in calibration labelling, in review — gets a fixture row *before* it gets a fix. The grid only grows. This is the mechanism by which the deterministic layer stays deterministic.

---

## 7. Adding a scenario

Scenarios are WS-7 (`data/scenarios/**`). Start from `templates/scenario-template.md`; the schema is `ScenarioRecord` (`schemas/scenario_record.schema.json`).

1. **Pick an encounter archetype the bank lacks.** The bank targets ≥ 1 per archetype; `make scenarios` prints current coverage. Duplicating an archetype adds volume, not signal.
2. **Write the clinical state graph.** Nodes are clinical moments; edges are the counterpart's legal transitions. Invariants checked by `make scenarios`: no dead-end node, every node reachable from entry, and **every persona fact assigned to exactly one role** — a fact both agents know is a fact that leaks.
3. **Write the term manifest.** The terms the generator will deliberately place in source utterances: doses, frequencies, laterality, allergies, negations, temporal markers. This is what makes ground truth by construction concrete — the scorer knows which hazards were planted. Every term id must resolve in `content/terms.py`.
4. **Set the personas.** Register, dialect notes, health literacy, emotional state. Grounding is Santa Cruz County — Watsonville and the Pajaro Valley — so es-MX regional usage is correct and generic neutral Spanish is a realism defect. Where a patient would plausibly be a Mixteco or Triqui speaker using Spanish as a second language, model that explicitly rather than silently rendering them as a fluent Spanish speaker.
5. **No rubric vocabulary anywhere in the file.** Not in persona notes, not in node descriptions, not in comments. The scenario is loaded into counterpart agent contexts; taxonomy words there defeat isolation. The rubric-vocabulary canary is binary and will catch it.
6. **Validate and review.**
   ```bash
   make scenarios                                     # schema + graph invariants, 100% must pass
   uv run rehearsal session --scenario <id> --dry-run # walk the graph without audio
   ```
7. **Clinical review.** A scenario asserting anything clinical — a dosage, an interaction, a red-flag symptom — needs sign-off from someone qualified, recorded in the scenario file's `review` block. Deterministic code cannot check whether 500 mg q8h is plausible; a human must.

---

## 8. Changing a prompt

**Prompts are code.** They live in `prompts/`, are versioned as files, are diffed in review, and are never edited in a running process or a dashboard.

Layout and ownership:

| Path | Owner | Isolation class |
|---|---|---|
| `prompts/grader/v1.md … vN.md` | WS-1 (WS-6 for optimised candidates) | May contain the rubric and taxonomy |
| `prompts/clinician/`, `prompts/patient/` | WS-2 | **Must never contain rubric, taxonomy, or learner content** |
| `prompts/coach/` | WS-5 | May see scores; never feeds a counterpart agent |

Procedure:

1. **New file, new version.** `prompts/grader/v4.md`. Never mutate a landed version — a landed prompt version is the only way an old eval number stays interpretable.
2. **State the hypothesis in the file header:** what you think is failing, what the edit changes, which metric should move and in which direction. An edit with no predicted direction cannot be evaluated, only rationalised.
3. **Point the config at it** in `src/rehearsal/config.py` (or the workstream's prompt selector) — one line, in the same change.
4. **Rerun the eval suite.** A prompt change is one of the explicit triggers in `docs/08-evals.md` §"re-run triggers":
   ```bash
   make evals        # EV-01/EV-02 on DEV, plus regression_delta vs data/evals/baselines/
   make calibrate    # agreement, reported beside kappa_intra as the ceiling
   ```
5. **Record the results.** Numbers go in the commit body as an `EVAL:` trailer and into `plans/metrics-snapshot.md` (WS-9 writes it) in the same working session. A prompt change with no recorded before/after is reverted, however good it looks.
6. **DEV only.** All iteration happens on the 25-item DEV split. The 15-item TEST split is sealed; `rehearsal-evals` refuses it without `unseal --reason`, and every access is appended to `data/calibration/TEST_ACCESS.log`. Unseal to *report* a chosen candidate, never to choose one.
7. **Counterpart prompt changes additionally require** the rubric-vocabulary canary at 1.00 and an EV-04 persona-consistency run across ≥ 3 seeds, reported as a distribution.

Optimised prompts (WS-6) follow the same path with one extra rule: **promotion is rejected if `critical_recall` regresses at all, regardless of the κ gain.** Trading missed critical errors for macro agreement is precisely the trade this product exists to refuse.

Out of scope, deliberately: no weight training, no fine-tuning, no RL, no LoRA. Prompt-level optimisation only. If a change seems to need weights, the honest answer is that the capability is not yet earned — write it down in `docs/17-decisions.md`.

---

## 9. Proposing a contract change

A contract is any of: `schemas/**`, generated `src/rehearsal/contracts/**`, an existing `SessionEvent` payload shape, a public signature another workstream imports, a gate threshold, or a `pyproject.toml` dependency.

1. Append an entry to **`plans/contract-changes.md`** using the `CC-00NN` template in `docs/15-workstreams.md` §10.4 — kind, requester, contract owner, why, consumers affected, migration, fixtures to regenerate, rollback, status.
2. **Land the contract change alone**, touching no workstream implementation. Regenerate with `make contracts` and commit the schema and generated model together — hand-editing generated Python is a build failure, and a schema out of sync with its model breaks everyone else's build.
3. Consumers migrate afterwards, on their own branches.
4. `additive-optional` is the common case and needs no acknowledgement. `additive-required`, `narrowing` and `breaking` require every named consumer to acknowledge in the note before the schema lands.
5. **A gate threshold change is a contract change** with a written rationale (G6).

If you find a bug in another workstream's code: open an issue with a failing test **in your own package's test directory**. Do not fix it. The other alternatives — for helpers, CLI wiring, prompt suggestions and reformatting temptations — are tabulated in `docs/15-workstreams.md` §10.3.

New third-party dependency: contract-change note, always. The stack is deliberate and stdlib-first. Name the exact pain the dependency removes; "it's standard" is not an argument. An agent framework is a standing rejection — reproducibility, seed control and inspectable failure points are the product's credibility, and a framework hides exactly what has to stay visible.

---

## 10. The pre-commit gate

```bash
make check     # lint → types → test → evals. Everything green or nothing lands.
```

| Stage | Command | Fails on |
|---|---|---|
| Lint | `ruff check . && ruff format --check .` | any violation |
| Types | `mypy rehearsal` | any error |
| Ownership | `tools/check_ownership.py` | diff spans >1 workstream without a `CONTRACT-CHANGE` trailer |
| Imports | import-linter over `docs/15-workstreams.md` §4 | any banned import, especially `runtime → scoring` |
| Contracts | round-trip property test, 10 000 records per schema | any mismatch; schema/model drift |
| Tests | `pytest -q` | any failure; no `xfail` added to make a branch pass |
| EV-00 | `rehearsal-evals run EV-00` | `extractor_conformance < 1.00` |
| Evals | `make evals --diff-snapshot plans/metrics-snapshot.md` | `regression_delta` outside tolerance |
| Secrets | diff scan | any credential, token, key, or `.env` content |
| a11y (frontend changes) | `make a11y` | any WCAG 2.1 AA violation, light or dark |

`record_run` refuses to register a metric from a dirty tree, for `test` and `live` splits especially. This is deliberate: a number you cannot reproduce from a commit is not a number.

If the gate is slow for your loop, run the subset (`pytest -k <pattern>`, `rehearsal-evals run EV-00`) while iterating — but the full gate runs before you ask for review, not after.

---

## 11. Review checklist

Reviewers: assume bugs exist and hunt until you find them or can say why the code is sound. "LGTM" without naming what you checked is not a review.

**Correctness**
- [ ] Every consequential decision is made by deterministic code, not a model output (G1)
- [ ] No `float` in any scoring path; `Decimal` constructed from strings
- [ ] `source` and `rendering` never blur (G4)
- [ ] Stochastic behaviour draws from `SeedLedger`; the change replays identically
- [ ] Error paths are prescriptive and emit an event or log with the turn id
- [ ] Input validation intact at every trust boundary the change touches

**Evidence**
- [ ] A test exists that fails if the logic breaks (G2)
- [ ] Extractor changes: fixture rows added, `extractor_conformance = 1.00`
- [ ] Prompt changes: eval rerun, before/after in the commit body and the snapshot (§8)
- [ ] No claim in code, docs or UI without a number behind it (G3)
- [ ] No gate widened; no `xfail`, `skip`, or tolerance loosened to go green (G6)

**Boundaries**
- [ ] Diff stays inside the branch's workstream, or carries a `CONTRACT-CHANGE` trailer
- [ ] Contract changes landed alone, with a `CC-00NN` note and regenerated models
- [ ] No rubric, taxonomy, or learner vocabulary reachable from a counterpart context (G5)
- [ ] No new dependency without a note naming the pain it removes

**Hygiene**
- [ ] Commit message explains why, and names what was deliberately not done
- [ ] Shortcuts marked `kn:` with a ceiling and an upgrade path
- [ ] No secrets, no `.env`, no model weights, no sealed calibration data in the diff
- [ ] Relevant document updated in the same change (§12)
- [ ] Frontend: tokens not literals, AA contrast in both themes, keyboard path intact, `prefers-reduced-motion` respected, meaning never carried by colour alone

---

## 12. The documentation rule

**A change to behaviour updates the relevant document in the same change.** Not a follow-up, not an issue.

| You changed | Update |
|---|---|
| An extractor, the merge logic, the taxonomy, the structured call | `docs/06-scoring-engine.md` |
| A schema or an event payload | `docs/03-system-architecture.md`, `docs/15-workstreams.md` §5, `plans/contract-changes.md` |
| A gate, a metric, an eval suite | `docs/08-evals.md`, `plans/metrics-snapshot.md` |
| Latency budgets, barge-in, degradation | `docs/05-voice-pipeline.md` |
| Agent roster, context assembly, isolation | `docs/04-ai-engineering.md` |
| Scenario structure, term manifests, retention | `docs/07-data-and-scenarios.md` |
| Screens, tokens, accessibility behaviour | `docs/09-ui-ux.md`, `docs/10-frontend-spec.md` |
| API surface or the WS protocol | `docs/11-backend-api.md` |
| Anything a data asset or a model touches | `DATA_CARD.md`, `MODEL_CARD.md` |
| A consequential choice with a price | `docs/17-decisions.md`, from `templates/ADR-template.md` |
| A user-visible behaviour | `CHANGELOG.md` |

Cross-reference sibling documents by exact filename. Never duplicate another document's content — a fact stated twice will be true in one place and stale in the other.

`plans/metrics-snapshot.md` is the single place headline numbers live, and it is WS-9's. When an eval produces a number that differs materially from the snapshot, update the snapshot in the same session and then correct everything downstream that the new number invalidates. A number that changes in the test output but not in the prose derived from it is how a project ends up contradicting itself.

---

## 13. Good first contributions

Ordered by value, not difficulty. All of these are real, scoped, and land inside one workstream.

| # | Contribution | Workstream | Why it matters | Done when |
|---|---|---|---|---|
| 1 | **Add adversarial rows to an existing extractor fixture grid** — Spanish decimal comma (`0,5 mg`), unit variants (`mcg`/`µg`/`microgramos`), frequency near-misses (`cada 8 horas` vs `3 veces al día`), laterality with `bilateral`, negation scope (`no tome` vs `no sólo tome`) | WS-7 | The cheapest way to learn where the deterministic layer actually stands, and the grid only grows | Rows land, `extractor_conformance` still 1.00 (or a genuine bug is now reproducible) |
| 2 | **Implement the temporal-marker extractor** — symptom onset, duration, "since Tuesday" / `desde el martes`, `hace tres días`. Onset is a `critical` severity trigger and is currently semantic residue | WS-1 | Moves a critical error class out of the model's hands (principle 3) | Full §6 checklist; `critical_recall` before/after on DEV reported |
| 3 | **Add a scenario for an archetype the bank lacks** — e.g. a medication-reconciliation visit, or a pesticide-exposure occupational-health encounter grounded in Pajaro Valley agricultural work | WS-7 | Coverage is the ceiling on training realism | `make scenarios` passes; graph invariants hold; clinical review recorded |
| 4 | **Write the `expect: []` clean rows nobody enjoys writing** across every extractor | WS-7 | False-alarm rate is a headline gate (`fp_rate_clean ≤ 0.15`) and is under-measured relative to recall | Every extractor has ≥ 2 clean rows per language |
| 5 | **Harden `TTSRouter` voice fallback** — what happens when the es-MX voice is missing on a fresh machine. Today it is a degradation path with thin coverage | WS-3 | Silent English-voice Spanish is a realism failure that scores as trainee error | Test with the voice absent; degradation event emitted; `SETUP.md` §4 note added |
| 6 | **Fixture-replay test for a frontend screen** — render a full session from a recorded event log with no backend running | WS-8 | The frontend contract is "renders from the event log alone"; each replayed screen proves it | 0 console errors, screen renders, AA audit passes light and dark |
| 7 | **A keyboard-only traversal test for the review gate** | WS-8 | The trainer's override is a human gate (principle 1); a gate you cannot reach by keyboard is not universally available | Recorded test completes the gate with no mouse |
| 8 | **An adversarial test that the seal guard actually holds** — attempt TEST access without `unseal` and assert `SealViolation` | WS-9 | The sealed split is the credibility of every reported number; it should be provably hard to breach, not politely respected | Test asserts the exception and the empty `TEST_ACCESS.log` |
| 9 | **Improve one prescriptive error message** — find an exception that says what failed but not what to do, and fix it | any | Tool errors are read by contributors and by agents; "X failed because Y; try Z" is the standard | Message names the cause and the next action |
| 10 | **Fix a document that contradicts the code** | any | Documentation drift is the failure mode this repository's rules are built to prevent | The document matches the code; if the code was wrong, an issue names it |

Before you start: state your workstream in the first line of the change description (`WS-1: temporal-marker extractor`), and check `docs/15-workstreams.md` §3 to confirm the paths you need are yours.

---

## 14. Getting unstuck

- **The behaviour question** — `docs/03-system-architecture.md` for how a session flows, `docs/18-glossary.md` for any interpreting or clinical term you are unsure of. Do not guess at taxonomy vocabulary; the words have precise professional meanings.
- **The "is this decidable" question** — if you cannot state the rule in one unhedged sentence, it is semantic residue. Say so and route it to the grader.
- **The "my number moved and I don't know why" question** — `make evals` prints `source_split` (extractor vs model contribution to TP/FP/FN). Read that before touching a prompt.
- **The disagreement** — object once with evidence, then comply, and record the disagreement and its outcome in `docs/17-decisions.md`. Positions worth holding are worth writing down.

Reporting a security or privacy issue: `SECURITY.md`. Never open a public issue containing session audio, transcripts, or calibration content — all three are sensitive by construction.

# 14 — Testing Strategy

**Status:** decided unless marked otherwise.
**Scope:** software correctness. Whether the code does what it says.
**Not in scope:** model quality. Whether the grader agrees with a human, whether the counterpart agent stays in persona, whether the isolation claim holds — all of that lives in `docs/08-evals.md` and is measured, not asserted.

---

## 1. The boundary between this document and `docs/08-evals.md`

These two documents are frequently confused by newcomers, so the line is drawn once, here, and never blurred again.

| Question | Answer form | Owner |
|---|---|---|
| Does `frequency.py` flag "twice a day" → "al día" as a critical distortion? | Pass / fail. Deterministic. Same answer forever. | **This document** (unit test) |
| Does the grader agree with a human labeller on the semantic categories? | A rate with a confidence interval. Changes with the model and the prompt. | `docs/08-evals.md` (EV-01) |
| Does `merge_verdict()` ever downgrade a critical extractor finding? | Pass / fail. A universally quantified property. | **This document** (property test) |
| Does the system reach the trainee's competency goals? | Unproven; see the named gaps in `docs/08-evals.md` §9. | `docs/08-evals.md` |
| Does the orchestrator schedule scoring off the critical path with ≤ 40 ms of its own overhead? | Pass / fail against a fixed budget, models stubbed. | **This document** (latency regression) |
| Can this machine actually run a 12B grader inside the turn gap? | A p50/p95 distribution on real hardware. | `docs/08-evals.md` (EV-07) |

**The operative rule:** a check whose expected answer is a *fixed value* is a test and belongs here. A check whose expected answer is a *distribution* is an eval and belongs in `docs/08-evals.md`. Tests gate commits. Evals gate claims.

Two evals are nonetheless *run by* the test gates because they are cheap and fully deterministic: **EV-00** (extractor conformance over `data/fixtures/extractors/*.jsonl`) and **EV-09** (regression against frozen baselines). They are invoked from `make check`; they are still owned, specified and reported by `docs/08-evals.md`. This document does not redefine them.

---

## 2. What testing has to make true here

This system assesses people. That changes the cost asymmetry of its bugs, and the strategy is shaped around that asymmetry rather than around uniform coverage.

| Failure | Who notices | Cost | Test surface that must catch it |
|---|---|---|---|
| An extractor misses a real dosage change | Nobody. The trainee is told they were clean. | **Highest in the system.** A false negative on a critical error teaches the exact wrong lesson and silently undermines the product's central claim. | Extractor unit grid, critical-recall property, golden files |
| An extractor fires on a correct rendering | The trainee, immediately, and they stop trusting the tool | High | Extractor unit grid — the clean cases carry equal weight to the error cases |
| The merge silently downgrades a critical finding | Nobody | Highest | Property tests on `merge_verdict` |
| A finding quotes a span that is not in the text | The trainee, as an incoherent report | High — destroys credibility instantly | Property test: spans are always real substrings |
| A session reaches a scored, exported result without human confirmation | Possibly nobody, until the number is used against someone | Highest, and it is a product-integrity failure, not a bug | State-machine reachability tests |
| The audio device disappears mid-turn and the session hangs | The trainee | Medium; recoverable | Fault injection |
| A Spanish string is missing and the UI shows an English key | Every Spanish-speaking user | High for this product specifically | i18n tests |
| Latency regresses 80 ms in the orchestrator | Nobody, until the loop stops feeling real-time | Medium, and it compounds | Latency regression tests |

Everything below follows from that table. The deterministic extractors and the merge get disproportionate test investment because they are where an undetected wrong answer is both possible and consequential. The FastAPI route handlers get comparatively little, because a broken route fails loudly.

---

## 3. The pyramid

Not a pyramid of "unit / integration / e2e" — that taxonomy does not fit a system whose riskiest component is a pure function over two strings. The shape here is **wide at the deterministic base, deliberately thin at the top, with a separate off-to-the-side band for anything involving a model.**

```
                    ┌────────────────────────────┐
                    │  L7  Manual exploratory    │  not automated, checklist-driven
                    ├────────────────────────────┤
                    │  L6  E2E session smoke     │  ~4 tests, stubbed models
                    ├────────────────────────────┤
                    │  L5  a11y / i18n / contract│  ~40 tests
                    ├────────────────────────────┤
                    │  L4  Fault injection       │  ~25 tests
                    ├────────────────────────────┤
                    │  L3  Golden files          │  ~30 cases
                    ├────────────────────────────┤
                    │  L2  State machine + props │  ~60 tests + N properties
                    ├────────────────────────────┤
                    │  L1  Unit — extractors,    │  ~700 table rows
                    │      merge, fold, budget   │
                    └────────────────────────────┘

        ══ off to the side, never in the same gate ══
        ┌──────────────────────────────────────────┐
        │  Model-quality evals — docs/08-evals.md  │  rates, not pass/fail
        └──────────────────────────────────────────┘
```

**The required layer table.**

| Layer | What it tests | Tooling | Gate |
|---|---|---|---|
| **L1 Unit — extractors** | Every extractor rule, every normalisation case, every clean case. Table-driven from JSONL fixtures. | `pytest`, `pytest.mark.parametrize` over `data/fixtures/extractors/*.jsonl` | pre-commit |
| **L1 Unit — pure logic** | `merge_verdict`, `fold`, `derive_seed`, `TurnBudget`, `ClinicalStateGraph.advance`, blob addressing, canonical JSON | `pytest` | pre-commit |
| **L2 Property** | Invariants of merge, severity, span validity, seed determinism, event-log fold idempotence | `hypothesis` | pre-commit |
| **L2 State machine** | Reachability and gate properties over `TRANSITIONS`; stateful driving of `SessionOrchestrator` | `pytest` + `hypothesis.stateful` | pre-commit |
| **L3 Golden files** | Whole `Verdict` JSON for fixed (source, rendering) pairs; whole report projection; whole `openapi.json` | `pytest` + `tests/golden/**`, `--update-golden` | pre-merge |
| **L4 Fault injection** | Malformed model JSON, model refusal, socket death, device loss, disk full, SIGKILL mid-session | `pytest` + `FaultPlan` doubles + subprocess harness | pre-merge |
| **L4 Latency regression** | Orchestrator and scoring-plane overhead with model latency stubbed to fixed values | `pytest -m latency` + `tests/perf/budgets.json` | pre-merge |
| **L5 Contract** | HTTP request/response shapes, WS envelope shapes, error envelope, `openapi.json` drift | `schemathesis` + shared JSON Schema in `contracts/` | pre-merge |
| **L5 Audio pipeline** | VAD onset/endpoint, barge-in timing, resampling, echo guard — against recorded WAV fixtures | `pytest -m audio` + `tests/fixtures/audio/**` | pre-merge |
| **L5 Accessibility** | axe-class scan per screen × theme × locale, scripted keyboard-only path, reading-order snapshot | Playwright + `axe-core` (bundled, offline) | pre-merge |
| **L5 i18n** | Catalog key parity, no untranslated fallback, no hardcoded strings, plural categories, `lang` attributes | `pytest` + `node --test` catalog checks | pre-commit (catalogs), pre-merge (DOM) |
| **L6 E2E session smoke** | Four whole sessions end to end with stubbed models: nominal, degraded-to-L2, aborted, crash-resumed | `pytest -m e2e` driving the real API + real SQLite | pre-release |
| **L7 Manual exploratory** | Real voice, real device, real trainee behaviour; the things a fixture cannot reproduce | Checklist in §17.3 | pre-release |

`~N` counts are the intended steady-state order of magnitude, not a target to hit. A test that exists to raise a count is a liability.

---

## 4. Layout, naming and markers

### 4.1 Directory tree

```
tests/
├── conftest.py                     # session-scoped fixtures, marker registration, seed pinning
├── doubles/
│   ├── model_host.py               # FakeModelHost — replays recorded socket cassettes
│   ├── audio_device.py             # FakeAudioDevice — feeds WAV frames on a simulated clock
│   ├── tts.py                      # FakeTTS — emits silence of the recorded duration
│   ├── clock.py                    # ManualClock — monotonic time under test control
│   └── faults.py                   # FaultPlan, inject(), the fault catalogue of §11
├── unit/
│   ├── scoring/
│   │   ├── test_extractors_table.py    # the JSONL-driven grid — §5
│   │   ├── test_extractor_units.py     # per-extractor internals not expressible as a row
│   │   ├── test_merge.py
│   │   └── test_taxonomy.py
│   ├── orchestrator/
│   │   ├── test_budget.py  test_seeds.py  test_scheduler.py  test_resume_fold.py
│   ├── store/
│   │   ├── test_events_hashchain.py  test_blobs.py  test_canonical_json.py
│   ├── content/
│   │   └── test_graph.py  test_terms.py
│   └── learner/
│       └── test_model.py  test_coach_suppression.py
├── property/
│   ├── test_merge_properties.py    # P1–P9 — §6
│   ├── test_findings_properties.py
│   ├── test_fold_properties.py
│   └── strategies.py               # Hypothesis strategies for Finding, Verdict, Event, TurnContext
├── statemachine/
│   ├── test_transitions_static.py  # graph reachability over the TRANSITIONS table
│   ├── test_human_gate.py          # the no-result-without-confirmation proofs — §8
│   └── test_orchestrator_stateful.py
├── golden/
│   ├── test_verdict_golden.py
│   ├── test_report_golden.py
│   ├── test_openapi_golden.py
│   └── files/
│       ├── verdicts/<case_id>.json
│       ├── reports/<session_fixture>.json
│       └── openapi.json
├── contract/
│   ├── test_openapi_conformance.py     # schemathesis against the live app
│   ├── test_ws_envelopes.py
│   └── test_error_envelope.py
├── audio/
│   ├── test_vad.py  test_endpointing.py  test_bargein.py  test_resample.py
│   └── test_echo_guard.py
├── faults/
│   ├── test_model_faults.py  test_audio_faults.py
│   ├── test_store_faults.py  test_process_kill.py
├── perf/
│   ├── test_latency_regression.py
│   └── budgets.json                # per-stage ceilings for the stubbed harness
├── i18n/
│   └── test_catalogs.py
├── e2e/
│   └── test_session_smoke.py
└── QUARANTINE.md                   # the flaky register — §15

frontend/tests/
├── unit/*.test.js                  # node --test, no framework
├── contract/event_tape.test.js     # replays tests/fixtures/tapes/*.jsonl through the store
└── e2e/
    ├── a11y.spec.js  keyboard.spec.js  reading-order.spec.js
    └── snapshots/reading-order/*.txt
```

Backend tests use `pytest`. Frontend unit tests use **`node --test`**, the runtime's built-in runner — the SPA has no build-time framework (`docs/10-frontend-spec.md`), and adding a test framework to test a framework-free frontend is the exact inversion this project avoids. Browser-level tests use Playwright, which is required anyway for the accessibility work and is not replaceable by a lighter tool.

### 4.2 Markers

Registered in `pyproject.toml` under `[tool.pytest.ini_options] markers`. An unregistered marker is an error (`--strict-markers` is on).

| Marker | Meaning | In `make check`? |
|---|---|---|
| *(none)* | Pure, fast, hermetic. The default and the majority. | Yes |
| `property` | Hypothesis-driven. Deterministic under the pinned `derandomize` profile. | Yes |
| `golden` | Compares against a checked-in artifact. | Yes |
| `audio` | Reads WAV fixtures. No device. | Yes |
| `contract` | Boots the FastAPI app in-process. | Yes |
| `fault` | Injects a fault; may spawn a subprocess. | Yes |
| `latency` | Asserts a time budget with models stubbed. | Yes, with a widened multiplier — §12 |
| `e2e` | Full session through the real API and a real SQLite file. | No — pre-release |
| `browser` | Requires Playwright and a built frontend. | No — pre-merge |
| `requires_models` | Needs real weights resident. **Never a correctness gate.** | No — this is eval territory |
| `requires_audio_device` | Needs a real microphone. **Never runs unattended.** | No — manual only |

The last two markers exist to make a rule enforceable: **no automated gate in this project depends on a model producing a particular output, or on a physical device being present.** A gate that can fail because a model felt different today is not a gate, it is a coin flip that blocks commits.

### 4.3 Determinism controls

Set once in `tests/conftest.py`, applied to every test:

```python
# tests/conftest.py
@pytest.fixture(autouse=True)
def _pinned_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("PYTHONHASHSEED", "0")
    monkeypatch.setenv("TZ", "UTC")
    monkeypatch.setenv("REHEARSAL_HOME", str(tmp_path / "rehearsal"))
    monkeypatch.setenv("REHEARSAL_NO_NETWORK", "1")   # any socket() to a non-UNIX family raises
    random.seed(0)

settings.register_profile("ci", derandomize=True, max_examples=400, deadline=None)
settings.register_profile("dev", max_examples=50)
settings.register_profile("soak", max_examples=20_000, deadline=None)
```

`REHEARSAL_HOME` is redirected for every test, so no test can touch a developer's real `~/.rehearsal/`. A test that writes outside `tmp_path` fails on a `conftest` teardown assertion. `REHEARSAL_NO_NETWORK` is belt-and-braces: the product has no network config at all (`docs/03-system-architecture.md` §4), and a test that starts needing one is reporting a regression in that property.

Test ordering is randomised by `pytest-randomly` with the seed printed in the header. Order-dependence is a real bug in a system with a global event log, and finding it by accident later is more expensive than finding it now.

---

## 5. Unit testing the deterministic extractors — the highest-value surface

The seven extractors (`numbers`, `dosage`, `frequency`, `negation`, `laterality`, `allergy`, `temporal`) own the **critical** error class. Their contract is in `docs/03-system-architecture.md` §7; their rule semantics are in `docs/06-scoring-engine.md`. This section specifies only how they are tested.

**Every extractor rule gets a table row. Every rule also gets at least one clean row that must produce nothing.** A rule with only positive cases measures nothing but the author's confidence.

### 5.1 Fixture format

One JSONL file per extractor at `data/fixtures/extractors/<name>.jsonl`. The same files feed EV-00 in `docs/08-evals.md`; they are written once and consumed twice.

```json
{
  "id": "freq-es-0007",
  "extractor": "frequency",
  "rule": "F-03-collapse-to-daily",
  "source": "Take one tablet twice a day with food.",
  "rendering": "Tome una pastilla al día con comida.",
  "ctx": {
    "source_lang": "en", "target_lang": "es",
    "scenario_id": "scn-dm2-titration-01", "term_manifest": "tm-dm2-01"
  },
  "expect": [
    {
      "kind": "distortion", "severity": "critical",
      "source_span": [17, 28], "span": [19, 26],
      "extractor_name": "frequency", "note_contains": "twice a day"
    }
  ],
  "why": "BID collapsed to QD — halves the delivered dose; the canonical critical frequency error"
}
```

| Field | Rule |
|---|---|
| `id` | Stable forever. Referenced from bug reports, the changelog and EV-00 output. Never renumbered. |
| `rule` | The identifier of the extractor rule this row exercises. Enables the coverage check in §5.4. |
| `expect` | Exact expected findings, order-insensitive. `[]` means **must produce nothing** — the false-alarm cases. |
| `note_contains` | Substring, not equality. Note wording is allowed to improve; note *content* is not allowed to lose the offending text. |
| `why` | Mandatory free text. A row nobody can explain is a row nobody can safely delete when it starts failing. |

### 5.2 The runner

```python
# tests/unit/scoring/test_extractors_table.py
CASES = load_extractor_fixtures(Path("data/fixtures/extractors"))

@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_extractor_row(case: ExtractorCase) -> None:
    extractor = EXTRACTORS[case.extractor]
    found = extractor(case.source, case.rendering, case.ctx)
    assert_findings_equal(found, case.expect, case_id=case.id)
```

`assert_findings_equal` compares as an unordered multiset on `(kind, severity, span, source_span, extractor_name)` and asserts `note_contains` as a substring. Its failure message prints the source, the rendering, both spans rendered as carets under the text, and the `why` string — because the person reading the failure is usually not the person who wrote the row.

### 5.3 Cross-lingual normalisation cases — mandatory per extractor

This is where extractors actually break. Every extractor ships at least the rows below; each is a distinct `rule` and each has a matching clean row.

**`numbers`**

| Case | Source | Rendering | Expected |
|---|---|---|---|
| Decimal comma vs point | `0.5 mg` | `0,5 mg` | *clean* — same value |
| Spelled-out Spanish numeral | `500 milligrams` | `quinientos miligramos` | *clean* |
| Spelled-out compound | `one hundred twenty over eighty` | `ciento veinte sobre ochenta` | *clean* |
| Thousands separator inversion | `1,500 mg` | `1.500 mg` | *clean* — `.` is a Spanish thousands separator |
| Genuine transposition | `120/80` | `102/80` | `substitution`, **critical** |
| Digit dropped | `1500 mg` | `150 mg` | `distortion`, **critical** |
| Fraction ↔ decimal | `half a tablet` | `medio comprimido` | *clean* |
| Fraction ↔ fraction | `1/2 tablet` | `un cuarto de comprimido` | `substitution`, **critical** |
| Ordinal | `the second dose` | `la segunda dosis` | *clean* |

**`dosage`**

| Case | Source | Rendering | Expected |
|---|---|---|---|
| Unit preserved across language | `10 units of insulin` | `10 unidades de insulina` | *clean* |
| Unit dropped | `10 mg` | `10` | `omission`, **critical** |
| Unit changed | `10 mg` | `10 ml` | `substitution`, **critical** |
| µg vs mcg vs microgramos | `50 mcg` | `50 microgramos` | *clean* |
| Form change | `one tablet` | `una cucharada` | `substitution`, **critical** |
| Route change | `by mouth` | `inyectado` | `substitution`, **critical** |

**`frequency`**

| Case | Source | Rendering | Expected |
|---|---|---|---|
| BID equivalence | `twice a day` | `dos veces al día` | *clean* |
| BID equivalence, alternate | `twice daily` | `cada doce horas` | *clean* — decided equivalence, see `docs/06-scoring-engine.md` |
| TID ≠ q8h **[decided]** | `three times a day` | `cada ocho horas` | *clean* — treated as equivalent for adherence purposes |
| PRN preserved | `as needed for pain` | `según sea necesario para el dolor` | *clean* |
| PRN dropped | `as needed` | *(absent)* | `omission`, **critical** — turns rescue medication into scheduled |
| Collapse to daily | `twice a day` | `al día` | `distortion`, **critical** |
| Duration ≠ frequency | `for three days` | `tres veces` | `substitution`, **critical** |
| Bare `al día` | `every day` | `al día` | *clean* |

**`negation`**

| Case | Source | Rendering | Expected |
|---|---|---|---|
| Negative concord is single negation | `You do not have any allergies` | `No tiene ninguna alergia` | *clean* — Spanish `no…ninguna` is **not** a double negative |
| Flip | `You are not allergic to penicillin` | `Es alérgico a la penicilina` | `distortion`, **critical** |
| Flip, other direction | `No tiene fiebre` | `He has a fever` | `distortion`, **critical** |
| Scope narrowing | `Do not take it with food or alcohol` | `No lo tome con comida` | `omission`, **critical** |
| Litotes | `not uncommon` | `es común` | `distortion`, non-critical |
| `sin` as negation | `without fever` | `sin fiebre` | *clean* |
| `nunca` preserved | `never take two at once` | `nunca tome dos a la vez` | *clean* |

**`laterality`**

| Case | Source | Rendering | Expected |
|---|---|---|---|
| Basic | `left knee` | `rodilla izquierda` | *clean* |
| Flip | `left knee` | `rodilla derecha` | `substitution`, **critical** |
| Bilateral → unilateral | `both knees` | `la rodilla` | `omission`, **critical** |
| Unilateral → bilateral | `left knee` | `ambas rodillas` | `addition`, **critical** |
| Adjective agreement | `left arm` | `brazo izquierdo` | *clean* (not `izquierda`) |
| Dropped entirely | `left knee` | `la rodilla` | `omission`, **critical** |

**`allergy`**

| Case | Source | Rendering | Expected |
|---|---|---|---|
| Cognate | `penicillin` | `penicilina` | *clean* |
| Class name | `sulfa drugs` | `sulfas` | *clean* |
| Brand ↔ generic via term manifest | `Tylenol` | `paracetamol` | *clean* |
| Brand ↔ wrong generic | `Tylenol` | `ibuprofeno` | `substitution`, **critical** |
| Reaction dropped | `penicillin — she goes into anaphylaxis` | `alergia a la penicilina` | `omission`, **critical** |
| Allergy invented | `no known allergies` | `es alérgica a la penicilina` | `addition`, **critical** |

**`temporal`**

| Case | Source | Rendering | Expected |
|---|---|---|---|
| Onset | `three days ago` | `hace tres días` | *clean* |
| Onset ≠ duration | `three days ago` | `por tres días` | `distortion`, **critical** |
| Since-marker | `since Tuesday` | `desde el martes` | *clean* |
| Relative → absolute drift | `this morning` | `ayer` | `distortion`, **critical** |
| Vague preserved | `for a while now` | `desde hace tiempo` | *clean* |
| Quantity dropped | `for two weeks` | `por un tiempo` | `omission`, non-critical |

**Orthography and encoding — applied to every extractor as a shared parametrised suite** (`tests/unit/scoring/test_extractor_units.py::test_orthographic_robustness`):

| Case | Behaviour required |
|---|---|
| NFC vs NFD (`día` composed vs `dia` + U+0301) | Identical results. Inputs are NFC-normalised at the extractor boundary. |
| Missing accent (`dia`, `dias`, `medicion`) | Identical results. Trainee speech transcription frequently drops accents; scoring must not punish it. |
| `ñ` is **not** foldable (`año` vs `ano`) | **Different** results. This is the one case where accent-insensitivity is wrong, and it is wrong in a way that is both clinically and socially unacceptable. It has its own dedicated test. |
| Inverted punctuation (`¿`, `¡`) | Stripped for matching, preserved in spans |
| Case and surrounding whitespace | Insensitive for matching; spans still index the original string |
| Smart quotes, en-dashes | Normalised for matching only |

The span rule that makes all of the above safe: **normalisation happens in a parallel buffer with an index map back to the original string. Every emitted span indexes the original, un-normalised text.** A dedicated property test (P4, §6) enforces it, because the alternative — emitting a span into a normalised string the trainee never sees — produces reports that quote text that does not exist.

### 5.4 Rule-coverage check

```python
# tests/unit/scoring/test_extractors_table.py
def test_every_rule_has_a_positive_and_a_clean_case() -> None:
    for name, extractor in EXTRACTORS.items():
        for rule_id in extractor.RULES:                       # declared, not inferred
            rows = [c for c in CASES if c.rule == rule_id]
            assert any(c.expect for c in rows), f"{rule_id}: no positive case"
            assert any(not c.expect for c in rows), f"{rule_id}: no clean case"
```

Each extractor module declares `RULES: tuple[str, ...]`. Adding a rule without adding both cases fails the pre-commit gate. This is the one place the project accepts a coverage-shaped mandate, because here the coverage number and the risk actually coincide.

Line/branch coverage is additionally held at **100 % branch** on `src/rehearsal/scoring/extractors/**`, `src/rehearsal/scoring/merge.py` and `src/rehearsal/orchestrator/states.py`, enforced by `--cov-fail-under` scoped to those paths. Everywhere else coverage is reported and ratcheted (§16.4), never mandated.

---

## 6. Property-based tests — merge logic and severity

`merge_verdict(deterministic, semantic, policy) -> Verdict` is the last deterministic step before a number is shown to a human. It is short, and it is the single easiest place to introduce a silent, systematic, invisible error. It therefore gets universally quantified tests rather than examples.

Strategies live in `tests/property/strategies.py`:

```python
# tests/property/strategies.py
def texts() -> st.SearchStrategy[str]:
    """Realistic clinical text: ASCII, Spanish diacritics, digits, units, punctuation."""

def spans_within(text: str) -> st.SearchStrategy[tuple[int, int]]:
    """Always a valid, non-empty (start, end) with start < end <= len(text)."""

def findings(*, text: str, source: str, origin: str | None = None) -> st.SearchStrategy[Finding]: ...

def finding_pairs() -> st.SearchStrategy[tuple[str, str, list[Finding], list[Finding]]]:
    """(source, rendering, deterministic_findings, semantic_findings) — spans always real."""
```

### 6.1 The invariants

| # | Property | Statement | Why it is a property and not an example |
|---|---|---|---|
| **P1** | Spans quote real text | For every finding in the merged verdict with `span is not None`, `rendering[span[0]:span[1]]` is a non-empty string, and likewise `source_span` into the source. | A report that quotes text the trainee never said destroys trust in one screen. There is no set of examples that covers this. |
| **P2** | No finding without a locus | Every finding has `span is not None` **or** `source_span is not None`. An `omission` has `source_span` (what was lost) and may have `span is None`. No other kind may have both `None`. | The UI has no way to render a finding it cannot point at; `docs/09-ui-ux.md` §5.4 renders every finding as a highlighted diff. |
| **P3** | Critical is never silently downgraded | For every deterministic finding `f` with `f.severity == "critical"`, the merged verdict contains a finding with the same `source_span` and `severity == "critical"`. | This is principle 3 in executable form. |
| **P4** | Spans index the original text | Given any input containing NFD sequences, inverted punctuation or mixed case, every emitted span still resolves in the *original* string. | The normalisation/index-map machinery of §5.3 has many paths; enumerating them is exactly what Hypothesis is for. |
| **P5** | The grader cannot manufacture critical | No finding with `origin == "grader"` and `kind` in the extractor-owned categories survives the merge with `severity == "critical"`. | The severity of a decidable category is a deterministic decision, always. |
| **P6** | Overrules are recorded, never deleted | `len(verdict.findings) + len(verdict.overruled) >= len(deterministic) + len(semantic)`, and every input finding appears by identity in exactly one of the two lists. | The disagreement rate is a reported number (`docs/08-evals.md` §4.2). A merge that drops evidence makes that number a lie. |
| **P7** | Merge is idempotent | `merge_verdict(merge_verdict(d, s, p).findings, [], p) == merge_verdict(d, s, p)` modulo the `overruled` list. | Re-scoring and replay both re-run the merge; a non-idempotent merge means `rehearsal replay --verify` reports false divergences. |
| **P8** | Merge is order-insensitive | Shuffling either input list yields an equal verdict under the canonical ordering (`source_span`, then `kind`, then `origin`). | Extractors run concurrently; their completion order is not stable. |
| **P9** | Empty in, clean out | `merge_verdict([], [], p)` yields a verdict with no findings, `partial is False`, and an explicit `assessed_categories` list — never an implicit "no error found". | Silence and "not assessed" are different claims (`docs/03-system-architecture.md` §14, L2). Conflating them is the degradation ladder's central failure mode. |

### 6.2 Representative implementation

```python
# tests/property/test_merge_properties.py
@given(finding_pairs())
def test_p3_critical_never_downgraded(case) -> None:
    source, rendering, det, sem = case
    verdict = merge_verdict(det, sem, DEFAULT_POLICY)
    for f in det:
        if f.severity != "critical":
            continue
        assert any(
            g.source_span == f.source_span and g.severity == "critical"
            for g in verdict.findings
        ), f"critical extractor finding {f.extractor_name}@{f.source_span} lost or downgraded"


@given(finding_pairs())
def test_p1_spans_quote_real_text(case) -> None:
    source, rendering, det, sem = case
    verdict = merge_verdict(det, sem, DEFAULT_POLICY)
    for f in verdict.findings:
        if f.span is not None:
            assert rendering[f.span[0]:f.span[1]]
        if f.source_span is not None:
            assert source[f.source_span[0]:f.source_span[1]]
```

### 6.3 Other property targets

| Target | Property |
|---|---|
| `derive_seed(root, turn_index, role)` | Deterministic, collision-free over the tested domain, independent of call order |
| `fold(events)` | `fold(events) == fold(events[:k]) ⊕ events[k:]` for every split point; folding a prefix never yields a state the full log cannot reach |
| Event hash chain | Any single-byte mutation of any payload breaks verification; appending never rewrites a prior hash |
| `canonical_json` | Round-trips; byte-identical for semantically equal dicts regardless of key insertion order |
| `BlobStore` | `put(x)` twice yields one file; `get(sha)` returns bytes hashing to `sha` or raises `BlobCorrupt` |
| `TurnBudget` | Deadlines are monotone in the degrade level; no level ever grants more time than the level below |

Hypothesis's example database is committed at `.hypothesis/examples/` **[decided]** — a falsifying example found on one machine is a permanent regression test everywhere, and losing it to a clean checkout is a needless repeat of an expensive discovery.

---

## 7. Golden-file tests

Properties prove that nothing is *wrong*. Golden files make it visible when something *changed*. Both are needed: a merge refactor can preserve every invariant and still quietly reorder every report.

### 7.1 What is goldened

| Artifact | Path | Trigger for a legitimate change |
|---|---|---|
| Full `Verdict` JSON for ~30 fixed (source, rendering) pairs | `tests/golden/files/verdicts/<case_id>.json` | An extractor rule change, a merge policy change, a taxonomy change |
| Full report projection for 4 recorded session fixtures | `tests/golden/files/reports/<fixture>.json` | A report schema change, a projection change |
| `openapi.json` | `tests/golden/files/openapi.json` | Any API change — and this file is the contract the frontend is tested against (§9) |
| Rendered finding microcopy, both locales | `tests/golden/files/microcopy/<locale>.json` | A wording change, reviewed by a bilingual speaker |
| Screen-reader reading order per screen | `frontend/tests/e2e/snapshots/reading-order/*.txt` | A DOM-order change — see §13 |

The verdict goldens use **stubbed grader output**, taken from a recorded cassette, so they are fully deterministic. They test the *assembly* of a verdict, not the model. The model side of the same inputs is EV-01's job.

### 7.2 Mechanics

Non-deterministic fields are normalised before comparison by `tests/golden/normalise.py`: `ts_ms`, `mono_ms`, `session_id`, `run_id`, `hash`, `prev_hash` and absolute paths are replaced by stable placeholders (`"<ts>"`, `"<sha>"`). Everything else — including ordering — is compared exactly.

```
uv run pytest tests/golden --update-golden      # rewrites the files
make golden-update                              # the same, plus a `git diff --stat` reminder
```

**Rules.** A golden update is a reviewed diff, never a reflex. `--update-golden` is refused when the working tree is dirty outside `tests/golden/files/`, so an update cannot be smuggled in alongside the change that caused it. Golden files are canonical JSON (sorted keys, two-space indent, trailing newline) so that diffs are line-readable — a golden file that diffs as one 40 KB line is not reviewable and therefore is not a test.

Each golden directory carries a `README.md` naming what the case is *for*. When a golden fails, the first question is "should this have changed?", and that question is unanswerable without knowing what the case was demonstrating.

---

## 8. State-machine tests — proving the human gate

The product claim is that the human decides. `docs/03-system-architecture.md` §8.2 encodes that as: the only edge into `complete` originates at `review` and carries `review.signed`. That claim is tested three independent ways, because a single test of a load-bearing property is a single point of failure.

### 8.1 Static reachability over the transition table

```python
# tests/statemachine/test_human_gate.py
from rehearsal.orchestrator.states import SessionState, TRANSITIONS

def test_no_path_reaches_complete_without_review() -> None:
    graph = {s: [t for t in TRANSITIONS if t.frm is s] for s in SessionState}
    for path in all_simple_paths(graph, SessionState.INIT, SessionState.COMPLETE):
        assert SessionState.REVIEW in path, f"gate bypass: {path}"
        entry = path[path.index(SessionState.REVIEW) + 1:]
        assert entry == [SessionState.COMPLETE]

def test_complete_has_exactly_one_inbound_edge() -> None:
    inbound = [t for t in TRANSITIONS if t.to is SessionState.COMPLETE]
    assert len(inbound) == 1
    assert inbound[0].frm is SessionState.REVIEW
    assert "review.signed" in inbound[0].emits

def test_terminal_states_are_terminal() -> None:
    for s in (SessionState.COMPLETE, SessionState.ABORTED, SessionState.FAILED):
        assert not [t for t in TRANSITIONS if t.frm is s]
```

This is a test of the table, and the table is the specification. The next two tests check that the code obeys its own table.

### 8.2 Stateful driving

A `hypothesis.stateful.RuleBasedStateMachine` drives a real `SessionOrchestrator` with `FakeModelHost`, `FakeAudioDevice` and `ManualClock`, emitting arbitrary sequences of legal and illegal triggers, including aborts, pauses, device losses and host restarts at arbitrary points.

Invariants checked after **every** step:

| Invariant | Assertion |
|---|---|
| Gate holds | `orch.state is COMPLETE` ⟹ a `review.signed` event exists in the log |
| No orphan turns | Every `turn.opened` has a matching `turn.closed` or `turn.abandoned`, except at most one in flight |
| Log validity | The hash chain verifies after every step |
| Foldability | `fold(log)` equals the orchestrator's in-memory view, field for field |
| Blob integrity | Every blob referenced by an event exists and hashes correctly |
| Seeds | Every turn has exactly one `seed.drawn` record, and a re-opened turn reuses it |
| Degrade monotonicity within a level | `degrade_max` never decreases |
| No silent scoring | No `verdict.merged` exists for a turn with no `rendering.emitted` |

### 8.3 The export-surface test

The gate is only real if it constrains what leaves the system. A separate test asserts the *output* side rather than the state:

```python
# tests/statemachine/test_human_gate.py
@pytest.mark.parametrize("state", [s for s in SessionState if s is not SessionState.COMPLETE])
def test_reports_before_review_are_labelled_unreviewed(state) -> None:
    report = build_report(session_in_state(state))
    assert report["review_status"] in {"unreviewed", "in_review"}
    assert report["review_status"] != "agreed"
    assert report["exportable"] is False
```

and the corresponding API-level check that `POST /api/sessions/{id}/export` on a non-`complete` session returns `409` with `reason: "unreviewed"`. Three tests, three levels — table, behaviour, boundary. Removing the gate requires deliberately deleting all three, which is the point.

---

## 9. Contract tests — frontend ↔ backend

The two sides are separately built and separately tested, so the contract must be an artifact, not a convention.

**Single source of truth:** `contracts/`.

```
contracts/
├── openapi.json           # generated from FastAPI, committed, goldened
├── ws-envelope.schema.json    # the {"t", "seq", "turn", "d"} envelope
├── ws-payloads/<event.kind>.schema.json   # one per event kind in §10.2 of docs/03
└── error-envelope.schema.json
```

| Test | Side | What it asserts |
|---|---|---|
| `test_openapi_golden` | backend | `app.openapi()` byte-equals `contracts/openapi.json`. An unintentional API change fails the build; an intentional one is a reviewed diff. |
| `test_openapi_conformance` | backend | Schemathesis generates requests from the schema against the in-process app. Checks: no 500s, every response validates against its declared schema, every declared status code is reachable. |
| `test_ws_envelope_conformance` | backend | Every event kind the orchestrator can emit is serialised through the WS encoder and validated against `ws-envelope.schema.json` plus its payload schema. A kind with no schema fails. |
| `test_event_kind_coverage` | backend | The set of kinds in `contracts/ws-payloads/` equals the set of kinds the code can emit. Neither drift direction is allowed. |
| `test_error_envelope` | backend | Every raised `RehearsalError` subclass serialises to `{code, message, detail, retryable}`; `code` is unique and stable; no traceback text ever appears (a hard requirement from `docs/12-security-privacy.md`, boundary B7) |
| `event_tape.test.js` | frontend | Replays `tests/fixtures/tapes/*.jsonl` — real recorded event streams — through the frontend store, asserting the derived view state. Catches the frontend ignoring a field the backend now sends. |
| `test_tape_freshness` | backend | Every recorded tape validates against the *current* WS schemas. A stale tape is a stale contract test, which is worse than none. |
| `openapi_client.test.js` | frontend | The hand-written fetch wrappers in `frontend/src/api.js` name only paths and fields present in `contracts/openapi.json`. AST scan, no code generation. |

**Deliberately not done:** no generated TypeScript client, no runtime schema validation in the browser. The frontend is vanilla JS by decision (`docs/10-frontend-spec.md`); a code generator would reintroduce a build step to solve a problem that an AST scan over a dozen call sites already solves.

---

## 10. Audio pipeline tests

No live microphone anywhere in an automated gate. `docs/05-voice-pipeline.md` specifies the DSP; this section specifies how it is proven.

### 10.1 Fixtures

```
tests/fixtures/audio/
├── README.md                       # provenance and consent status of every file
├── vad/
│   ├── clean_speech_es_3s.wav      # 16 kHz mono PCM16, known onset 0.42 s, endpoint 3.11 s
│   ├── clean_speech_en_4s.wav
│   ├── trailing_silence_8s.wav     # onset then 6 s silence — endpointing timeout case
│   ├── no_speech_5s.wav            # room tone only — must never trigger onset
│   ├── clipped_loud.wav            # 0 dBFS clipping — level meter and warning path
│   ├── whisper_low_snr.wav         # 8 dB SNR — the hardest legitimate onset case
│   ├── clinic_babble_bg.wav        # multi-talker background — false-onset case
│   └── cough_then_speech.wav       # non-speech transient before real onset
├── bargein/
│   ├── overlap_at_800ms.wav        # trainee begins 800 ms into playback
│   └── overlap_at_50ms.wav         # immediate barge-in, the tight case
├── echo/
│   ├── speaker_bleed_tts_es.wav    # TTS output recaptured by the mic — the no-headphones case
│   └── headphones_clean.wav        # the same content with no bleed — must not trigger the guard
├── rates/
│   ├── src_44100.wav  src_48000.wav  src_8000.wav
└── manifest.json                   # per-file: sha256, sample rate, duration, ground-truth markers
```

Every fixture is **synthetic or consented, synthetic by default**. No fixture contains real patient audio; no fixture contains real trainee audio without written consent recorded in `README.md`. `manifest.json` carries the ground-truth onset/endpoint markers in samples, hand-marked once, and a `sha256` so a silently re-encoded fixture (which would move every marker) fails loudly.

### 10.2 What is asserted

| Test | Assertion |
|---|---|
| `test_vad_onset_within_tolerance` | Detected onset is within ±30 ms of the manifest marker for every `vad/` fixture |
| `test_vad_no_false_onset` | `no_speech_5s.wav` and `clinic_babble_bg.wav` produce zero onsets across the whole file |
| `test_endpoint_timeout` | `trailing_silence_8s.wav` endpoints at `capture_max_ms`, and the turn is emitted with `empty: false` |
| `test_silence_produces_empty_rendering` | `no_speech_5s.wav` through the full capture path yields `rendering.emitted` with `empty: true`, scored as a full omission (`docs/03-system-architecture.md` §8.2) |
| `test_bargein_stops_tts_within_budget` | On `overlap_at_50ms.wav`, `tts.interrupted` is emitted and the fake TTS `stop()` is called within 120 ms of simulated time |
| `test_bargein_offset_recorded` | The `tts.interrupted` payload's offset matches the fixture's overlap point ±20 ms |
| `test_echo_guard_fires` | `speaker_bleed_tts_es.wav` raises the energy-correlation guard |
| `test_echo_guard_does_not_fire` | `headphones_clean.wav` does not — the false-alarm half, which is the half that actually gets broken |
| `test_resample_all_rates` | 8/44.1/48 kHz inputs resample to 16 kHz with the same VAD result and no sample-count drift over 60 s |
| `test_frame_alignment` | Frame boundaries never split a sample; no partial-frame writes reach the blob |
| `test_blob_content_addressing` | The captured blob's sha256 equals the value in `rendering.emitted` |

All of it runs on `ManualClock`: the harness advances simulated time in frame-sized increments, so a 60-second fixture is tested in milliseconds and the result never depends on machine load. Timing assertions are on *simulated* time, which is exactly what makes them non-flaky.

**Deliberately not tested automatically:** actual device enumeration, actual driver behaviour, actual acoustic echo on real hardware. Those are the pre-release manual checklist (§17.3), because a CoreAudio behaviour cannot be faked honestly and faking it badly would produce a green test that means nothing.

---

## 11. Fault injection

Every fault has a **named safe state**. The test asserts arrival in that state, and asserts the record left behind — because "did not crash" is not the requirement; "left a complete, valid, honest record" is.

Faults are injected by `tests/doubles/faults.py`:

```python
# tests/doubles/faults.py
@dataclass(frozen=True, slots=True)
class FaultPlan:
    at: FaultPoint                 # "grader.request" | "live.request" | "capture.frame" | "store.append" | ...
    on_call: int = 1               # 1-indexed occurrence to fault
    mode: FaultMode                # MALFORMED_JSON | REFUSAL | TRUNCATED | SOCKET_CLOSE | HANG | ENOSPC | EIO | SIGKILL
    payload: str | None = None     # for MALFORMED_JSON / REFUSAL, the exact bytes returned

def inject(plan: FaultPlan) -> AbstractContextManager[None]: ...
```

### 11.1 The catalogue

| # | Fault | Injection | Required safe state | Also asserted |
|---|---|---|---|---|
| F-01 | Grader returns malformed JSON | `grader.request`, `MALFORMED_JSON` | One retry at temp 0 with the schema echoed; on second failure the turn is scored extractor-only | `grader.failed` emitted with reason `schema`; verdict `partial is True`; semantic categories reported *not assessed*, never *no error* |
| F-02 | Grader returns valid JSON of the wrong shape | `MALFORMED_JSON` with a plausible-but-wrong body | Same as F-01 | Pydantic error is captured as a code, not as free text |
| F-03 | Grader refuses ("I can't help with that") | `REFUSAL` | Extractor-only verdict, flagged `grader_refusal` | The refusal text is **never** shown to the trainee |
| F-04 | Grader output truncated mid-JSON | `TRUNCATED` | Same as F-01 | No partially parsed findings enter the merge |
| F-05 | Grader hangs past the wall deadline | `HANG` | `budget.exceeded`, then DegradeLevel 2 | The **live** loop's turn cadence is unaffected — this is principle 5, tested |
| F-06 | Grader socket dies | `SOCKET_CLOSE` | One restart + 20 s health probe; second failure → DegradeLevel 2, session continues | `host.restarted` emitted; the session does **not** abort — the grader is off the critical path |
| F-07 | Live host socket dies once | `live.request`, `SOCKET_CLOSE` | One restart; the in-flight turn is abandoned, the same seed reused | `turn.abandoned` then `turn.opened` with an identical derived seed |
| F-08 | Live host dies twice in one session | `SOCKET_CLOSE`, twice | `aborted`, reason `host_unavailable` | Complete replayable log prefix; all prior turns scored and reported |
| F-09 | Live host returns no `heard_verbatim` | `MALFORMED_JSON` | Turn marked `rendering_unavailable`; **not** scored | A missing rendering scored as an omission would manufacture a fake critical error |
| F-10 | Audio device disappears mid-turn | `capture.frame`, `EIO` | `paused` + `capture_lost`; 10 s recovery window | Partial audio retained as a blob, `partial: true`, never scored |
| F-11 | Device does not return within 10 s | `EIO` sustained | `aborted`, reason `audio_device` | Prior turns intact and reported |
| F-12 | Device returns within 10 s | `EIO` then recovery | `resume` to the previous durable state | The turn restarts from its boundary; TTS is **not** replayed |
| F-13 | Disk full on event append | `store.append`, `ENOSPC` | `paused` first; abort only if the retry also fails | Reason `store_full`. **An unlogged session is a failure, not a session.** |
| F-14 | Disk full on blob write | `blobs.put`, `ENOSPC` | Turn marked `blob_unavailable`, session continues | Text-based scoring proceeds; the report names the gap |
| F-15 | Blob corrupted on read | Flip a byte on disk | `blob_quarantined`; transcript-based report still produced | The corrupted blob is quarantined, never deleted |
| F-16 | Process SIGKILLed mid-turn | Subprocess harness, `SIGKILL` after `turn.opened` | On restart: `recovering` → fold → re-open the same `turn_index` with the same seed | Hash chain verifies; no duplicate verdict (idempotent by `verdict_key`) |
| F-17 | SIGKILL during `verdict.merged` write | `SIGKILL` inside the transaction | The transaction rolls back; the score is re-enqueued on resume | Exactly one verdict per `verdict_key` after recovery |
| F-18 | SIGKILL during `review` | `SIGKILL` while a human is overriding | Resume to `review`, not to `complete` | An unsigned session never becomes signed by way of a crash |
| F-19 | Two API processes on one DB | Start a second `rehearsal-api` | The second exits with a named lock error | No interleaved writes; WAL not corrupted |
| F-20 | Clock jumps backwards (sleep/wake) | `ManualClock` regression | Latency arithmetic uses `mono_ms` and is unaffected; `ts_ms` records the jump | No negative durations anywhere in the projections |
| F-21 | TTS load failure | `tts.start`, `EIO` | DegradeLevel 3, system voices | `degraded.entered` with the trigger; the UI banner state is set |
| F-22 | Scenario bank empty or corrupt | Corrupt `data/scenarios/` | Session start refused with a named error | Nothing is created — no half-session row |
| F-23 | Score queue saturated | Enqueue past the bound | DegradeLevel 1 (hints shed), then 2 | Queue never drops a request silently |
| F-24 | Degrade floor breached | Config floor above the required level | Clean abort, reason `degrade_floor` | "The system refuses to produce numbers it cannot stand behind" is a test, not a slogan |
| F-25 | WS client disconnects mid-session | Close the socket | Session continues headless; on reconnect the client receives the gap from its last `seq` | No runtime state existed only in the browser |

### 11.2 Shape of a fault test

```python
# tests/faults/test_model_faults.py
@pytest.mark.fault
async def test_f01_malformed_grader_json_degrades_not_crashes(session_harness) -> None:
    with inject(FaultPlan(at="grader.request", on_call=1, mode=FaultMode.MALFORMED_JSON,
                          payload='{"findings": [{"kind": "omis')):
        await session_harness.run_turns(2)

    log = session_harness.events()
    assert kinds(log).count("grader.failed") == 1
    assert kinds(log).count("grader.started") == 2          # exactly one retry
    verdict = session_harness.verdict(turn=0)
    assert verdict.partial is True
    assert verdict.assessed_categories == EXTRACTOR_CATEGORIES
    assert "register_shift" not in verdict.assessed_categories   # not assessed ≠ no error
    assert session_harness.state is SessionState.AWAITING_RENDERING   # the loop kept running
```

The last two assertions are the ones that matter. F-01 is not really a test that the parser handles bad JSON; it is a test that a degraded scoring pass is *reported as degraded*.

---

## 12. Latency regression tests

**These do not measure the models.** Model latency on real hardware is EV-07 in `docs/08-evals.md`, and it is a distribution. What this section gates is the part that is the project's own fault: orchestration overhead, scheduling correctness, and the absence of accidental blocking on the critical path.

The harness replaces both model hosts with `FakeModelHost` configured to consume a **fixed, declared** amount of simulated time per call, and runs the orchestrator on `ManualClock`. Wall-clock is used only for the orchestrator's own CPU work.

```json
// tests/perf/budgets.json
{
  "orchestrator_overhead_ms":      { "p50": 8,   "p95": 20  },
  "turn_close_to_next_source_ms":  { "p50": 25,  "p95": 60  },
  "event_append_ms":               { "p50": 1.5, "p95": 5   },
  "fold_1000_events_ms":           { "p50": 40,  "p95": 90  },
  "merge_verdict_ms":              { "p50": 0.5, "p95": 2   },
  "extractors_all_seven_ms":       { "p50": 6,   "p95": 15  },
  "ws_fanout_ms":                  { "p50": 2,   "p95": 8   },
  "bargein_stop_ms":               { "p50": 40,  "p95": 110 }
}
```

| Test | Assertion |
|---|---|
| `test_stage_budgets` | Each stage's measured p95 over 200 simulated turns is within `budgets.json` × `REHEARSAL_PERF_MULTIPLIER` (default 1.0 locally, **2.5** in an unattended run) |
| `test_scoring_is_off_the_critical_path` | With grader latency stubbed at 400 ms, 4 s and 40 s, the *turn cadence* is byte-identical. This is principle 5 as a regression test — and it is the single most valuable test in this section. |
| `test_no_blocking_io_on_the_loop` | The event loop's `slow_callback_duration` is set to 50 ms and any warning fails the test; a synchronous `sqlite3` call or file read on the critical path surfaces here |
| `test_extractors_scale_linearly` | Extractor time over renderings of 20/200/2000 chars stays within a linear fit + 20 % — catches an accidental quadratic scan |
| `test_fold_scales_linearly` | Same shape, over logs of 100/1000/10000 events — resume time is a user-visible cost after a crash |

The generous unattended multiplier is deliberate: these tests exist to catch a 5× algorithmic regression, not a 15 % scheduling jitter. A latency test tuned tightly enough to catch jitter will fail on load and get disabled, at which point it catches nothing.

Results are appended to `data/perf/history.jsonl` with the git SHA, so a slow drift across many green runs is visible even though no single run failed. **[proposed]** A `make perf-trend` renderer over that file; currently the file is written and read manually.

---

## 13. Accessibility tests

`docs/09-ui-ux.md` §6 sets the obligations. Automated scanning covers perhaps half of WCAG 2.1 AA; the rest is scripted interaction and human review, and this project needs all three because bilingual blind interpreters are a real and natural user group.

### 13.1 Automated scan

Playwright + `axe-core`, bundled locally (no CDN — the product has no network dependency and neither do its tests).

```javascript
// frontend/tests/e2e/a11y.spec.js
const SCREENS = ['/', '/scenarios', '/preflight', '/encounter?fixture=tape-nominal',
                 '/turn-review?fixture=tape-nominal', '/report/FIXTURE', '/progress',
                 '/trainer/queue', '/settings'];

for (const path of SCREENS)
  for (const theme of ['light', 'dark'])
    for (const locale of ['en', 'es'])
      test(`axe ${path} ${theme} ${locale}`, async ({ page }) => {
        await visit(page, path, { theme, locale });
        const { violations } = await runAxe(page, {
          runOnly: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'],
        });
        expect(violations, formatViolations(violations)).toEqual([]);
      });
```

Zero violations, no allow-list. If a rule genuinely cannot be satisfied, the exemption is recorded in `frontend/tests/e2e/a11y-exemptions.json` with a reason and an owner, and the count of exemptions is printed on every run so it stays uncomfortable.

Additional scripted checks beyond what axe covers:

| Check | Assertion |
|---|---|
| Contrast, both themes | Every foreground/background pair from the token set computes ≥ 4.5:1 for body, ≥ 3:1 for large text and UI boundaries. Dark tokens are tested independently — they are tonal variants, not inverted light values, so inheriting the light result would be wrong. |
| Never colour alone | Every state conveyed by colour (critical vs non-critical findings, level meter states, preflight pass/fail) also carries text or an icon. Asserted per component from the inventory in `docs/09-ui-ux.md` §9. |
| Target size | Every interactive element's bounding box ≥ 44×44 px with ≥ 8 px separation |
| `prefers-reduced-motion` | With the media query forced, no element has a non-zero `animation-duration` or `transition-duration`; `LevelMeter` renders its static variant |
| Focus visibility | Every focusable element has a computed outline ≥ 2 px on `:focus-visible`; `outline: none` without a replacement fails |
| `lang` correctness | Every text node's effective `lang` matches the language of its content; Spanish content under `lang="en"` fails. This is the bilingual screen-reader requirement, and it is the one most likely to regress silently. |
| Live-region discipline | No `aria-live="assertive"` anywhere in the encounter view; turn-change announcements are `polite`; no score announcement fires while `SessionState` is a live state |

### 13.2 Scripted keyboard-only path

One test walks a whole session using only the keyboard map from `docs/09-ui-ux.md` §6, asserting the focused element by accessible name at each step:

```
Tab → "Scenario: Diabetes titration" → Enter
Tab ×3 → "Start pre-flight" → Enter
(preflight completes) → focus lands on "Begin encounter" → Enter
Space (hold)  → push-to-talk engaged, aria-live announces "Interpret to Spanish"
Space (release) → capture ends
R → "Repetition requested"
J / K → transcript scrollback moves, focus does not leave the transcript
? → keyboard help overlay opens, focus trapped
Esc → overlay closes, focus returns to the element that opened it
Esc → exit confirmation, focus trapped, Tab cycles within the dialog only
```

Two properties are asserted throughout: **focus never moves during an active turn**, and **no mouse event is dispatched at any point**. The second is enforced by failing the test if any `mousedown`/`click` with `detail > 0` occurs.

### 13.3 Reading-order snapshot

The Playwright accessibility tree for each screen is serialised to a flat, indented text file and goldened at `frontend/tests/e2e/snapshots/reading-order/<screen>.txt`. A DOM reorder that is visually invisible but changes what a screen-reader user hears first shows up as a reviewable diff. Updated with `--update-snapshots`, reviewed like any other golden.

### 13.4 What stays manual

A real screen reader (VoiceOver on the target platform), driven by a human through one full session in each locale, once per release. Automated tools verify structure; only a person verifies whether the result is *usable*. Checklist in §17.3.

---

## 14. Internationalisation tests

Every user-facing string exists in `en` and `es` from the start — there is no English-first phase (`docs/09-ui-ux.md` §7). Tests enforce it mechanically, because "we'll add the Spanish later" is a decision that gets made by omission rather than deliberately.

Catalogs: `frontend/i18n/en.json`, `frontend/i18n/es.json`, and backend-side `src/rehearsal/i18n/{en,es}.json` for finding notes and error messages.

| Test | Assertion | Gate |
|---|---|---|
| `test_key_parity` | `set(en) == set(es)` for every catalog pair. Missing and orphaned keys both fail, and the message lists them. | pre-commit |
| `test_no_empty_values` | No value is empty, whitespace-only, or `"TODO"` | pre-commit |
| `test_no_untranslated_fallback` | No `es` value equals its `en` value, except keys listed in `i18n/allowed-identical.json` (proper nouns, `"OK"`, units like `"mg"`). The allow-list carries a reason per entry. | pre-commit |
| `test_no_fallback_at_runtime` | The `t()` implementation raises in test/dev when a key is missing, instead of returning the key or the English string. A missing string must fail loudly in development and never leak to a user. | pre-commit |
| `test_all_call_sites_resolve` | AST scan of `frontend/src/**/*.js` and `src/rehearsal/**/*.py` collects every literal key passed to `t()`; every one exists in both catalogs. Dynamic keys must be registered in `i18n/dynamic-keys.json` or fail. | pre-commit |
| `test_no_hardcoded_user_strings` | No string literal of ≥ 2 words containing a space appears in JSX-equivalent template output or in a user-facing error path without going through `t()`. Heuristic, with an explicit `# i18n-exempt:` escape hatch that requires a reason. | pre-commit |
| `test_plural_categories` | Every ICU plural message declares the categories the locale requires (`one`/`other` for both en and es) | pre-commit |
| `test_interpolation_parity` | The set of `{placeholders}` in `es` equals that in `en` for every key. A dropped placeholder renders a broken sentence. | pre-commit |
| `test_no_string_concatenation` | Grep-level check for `t(...) + "..."` patterns — sentence assembly by concatenation is unlocalisable | pre-commit |
| `test_pseudolocale_no_overflow` | Rendering every screen in a pseudo-locale (`es` values expanded 40 % and accented) produces no clipped text, no horizontal scroll, no overlapping targets at every breakpoint in `docs/09-ui-ux.md` §8 | pre-merge |
| `test_diacritic_rendering` | The Noto Sans body face renders `á é í ó ú ü ñ ¿ ¡` with no `.notdef` glyph. This is why Noto Sans was chosen; a font-stack change that silently breaks it must fail. | pre-merge |
| `test_lang_attributes` | Covered in §13.1 — the bilingual screen-reader requirement is an a11y test and an i18n test at once, and lives in one place |

**Deliberately out of scope:** additional locales. Mixteco and Triqui are the languages of a real and underserved part of the population this product's users serve, but interpreting *into* them is a different product with different linguistic tooling. The i18n machinery is built so a third catalog is possible; no test pretends one exists.

---

## 15. Test data management and fixtures

### 15.1 The four data kinds, and their different rules

| Kind | Location | Mutable? | Owner | Rule |
|---|---|---|---|---|
| **Extractor fixtures** | `data/fixtures/extractors/*.jsonl` | Append yes; edit only with a changelog entry | Scoring | Shared with EV-00. IDs are permanent. |
| **The calibration set** | `data/calibration/{dev,test}.jsonl` | **Frozen.** TEST is sealed. | Evals | **Not test data.** Never read by anything under `tests/`. Protocol in `SETUP.md` §6. |
| **Session fixtures / tapes** | `tests/fixtures/tapes/*.jsonl` | Regenerated from recorded sessions | Orchestrator | Synthetic content only |
| **Model cassettes** | `tests/fixtures/cassettes/<hash>.json` | Re-recorded deliberately | Runtime | Keyed by a hash of the request; a cassette miss is an error, never a live call |

**The hardest rule in this document:** *no test may read `data/calibration/test.jsonl`.* It is enforced, not requested — `tests/conftest.py` installs an `audit` hook that raises on any open of a path under `data/calibration/test*`. The sealed split is the external anchor of every claim the project makes; a test that touched it, even read-only, even accidentally, would be indistinguishable from optimisation against it. `uv run rehearsal-evals unseal` remains the only path, and it writes `TEST_ACCESS.log`.

### 15.2 Cassettes

`FakeModelHost` replays recorded socket exchanges keyed by `sha256(canonical_json(request))`.

```
uv run rehearsal-testkit record --scenario scn-dm2-titration-01 --seed 7 \
    --out tests/fixtures/cassettes/
```

| Rule | Reason |
|---|---|
| A cassette miss raises `CassetteMiss` naming the missing hash and the command to re-record | A test that silently falls through to a live model is a test that passes for the wrong reason and fails on someone else's machine |
| Cassettes are canonical JSON, one request/response per file, human-readable | They are read during debugging more often than they are recorded |
| Re-recording requires `--reason` and appends to `tests/fixtures/cassettes/CHANGELOG.md` | A quietly re-recorded cassette makes a broken change look like a passing test |
| Cassettes carry the model id, quantisation and prompt version they were recorded against | Otherwise a cassette outlives the thing it was recording |

### 15.3 Synthetic content only

Every string, WAV and transcript under `tests/` and `data/fixtures/` is synthetic or consented-synthetic. No real patient content exists anywhere in the repository — the encounters are synthetic by construction (`docs/00-dossier.md`), and the test corpus inherits that property rather than relying on scrubbing. A CI check greps fixtures for anything resembling a real identifier (MRN-shaped strings, US phone numbers, SSN patterns, dates of birth) and fails on a hit.

### 15.4 Builders over literals

```python
# tests/factories.py
def a_finding(**over) -> Finding: ...
def a_verdict(*, findings=(), partial=False, **over) -> Verdict: ...
def a_session(*, state=SessionState.ARMED, turns=0, **over) -> SessionView: ...
def a_turn_context(*, source_lang="en", target_lang="es", **over) -> TurnContext: ...
```

Every builder is keyword-only with sane defaults, so a test names *only* the fields it is actually about. A test that spells out an eight-field `Finding` to assert one of them is a test whose intent is invisible, and it will be updated wrongly when the dataclass grows a field.

---

## 16. Flaky-test policy

A flaky test is a defect. It is filed, owned and fixed like one — because the real damage is not the failed run, it is that the team learns to re-run red builds, and after that a genuine failure is indistinguishable from noise.

### 16.1 Rules

1. **No automatic retries in any gate.** No `pytest-rerunfailures`, no `retries: 2` in a workflow. A test that passes on re-run has told you something true and you are choosing not to hear it.
2. **First observed flake → quarantine within one working session.** The test is marked `@pytest.mark.flaky_quarantined("QT-014")` and moved out of the gating selection. It still runs, and its result is still reported — it just no longer blocks.
3. **Quarantine has a cost and a register.** `tests/QUARANTINE.md`, one row per entry: id, test, first-observed SHA, hypothesis, owner, exit criterion. The count is printed at the end of every run.
4. **Quarantine has a cap: three.** At four, no new feature work merges until one is resolved. A quarantine list is a debt ledger, and an uncapped ledger is a bin.
5. **Nothing ships with a quarantined test.** Pre-release requires an empty quarantine — every entry is fixed, or deleted with a written reason.
6. **A quarantined test that is deleted must be replaced or explicitly renounced.** "It was flaky so we removed it" without naming what is now untested is how coverage evaporates.

### 16.2 The usual causes, pre-empted

| Cause | Structural prevention |
|---|---|
| Real time | `ManualClock` everywhere; wall-clock sleeps are banned by a grep check in `make check` |
| Real network | `REHEARSAL_NO_NETWORK=1`; the product has no network config to begin with |
| Real device | `requires_audio_device` never runs unattended |
| Shared state between tests | `REHEARSAL_HOME` per test; fresh SQLite per test; randomised order via `pytest-randomly` |
| Model nondeterminism | Cassettes; a cassette miss is an error |
| Hypothesis finding a new example | `derandomize=True` in the CI profile; the `soak` profile explores, and runs outside the gate |
| Async races | `asyncio` debug mode on in tests; unawaited-coroutine warnings are errors |
| Filesystem ordering | Directory listings are sorted at every read site; a test that depends on `os.listdir` order is the bug |

### 16.3 The soak profile

`make soak` runs the property suite at `max_examples=20_000` with a random seed, plus 500 simulated sessions through the stateful machine, plus the whole fault catalogue at randomised injection points. It runs on demand and before a release, never in a commit gate. New falsifying examples it finds are committed to `.hypothesis/examples/` and become permanent regression cases — that is the whole point of committing that directory.

### 16.4 Coverage ratchet

Outside the 100 %-branch paths named in §5.4, coverage is measured and **may not decrease**. `make check` compares against `tests/coverage-floor.json` and fails on a drop; raising the floor is a deliberate commit. A ratchet produces slow real improvement; a fixed target produces tests written to hit a number.

---

## 17. The gates

Three gates, each defined by what it must catch and how long it may take. A gate that is too slow gets bypassed, and a bypassed gate is worse than no gate because it produces false confidence.

### 17.1 Pre-commit — target < 10 s

Installed as a git hook by `make hooks`. Runs on **changed files only** where possible.

```
make precommit
├── ruff format --check
├── ruff check
├── ty check                             # type check, changed modules + dependents
├── secret scan                          # gitleaks-class; also refuses any *CLAUDE.md*
├── pytest tests/unit tests/property -m "not slow" -q -x
├── pytest tests/i18n -q                 # catalog parity is cheap and breaks constantly
└── forbidden-pattern grep               # time.sleep, print(, breakpoint(, .only(, xfail without reason
```

The secret scan additionally refuses to stage any `CLAUDE.md` at any path, and refuses `.env*`, `*secret*`, `*.pem`, `*.key`.

### 17.2 Pre-merge — target < 6 min

```
make check
├── everything in `make precommit`, on the whole tree
├── pytest -m "not e2e and not browser and not requires_models and not requires_audio_device"
│     (unit, property, statemachine, golden, contract, audio, fault, latency)
├── rehearsal-evals run --eval EV-00     # extractor conformance — deterministic
├── rehearsal-evals run --eval EV-09     # regression vs frozen baselines
├── coverage: 100% branch on the named paths; ratchet elsewhere
├── npm run test:unit                    # node --test
├── npx playwright test frontend/tests/e2e/{a11y,keyboard,reading-order}.spec.js
└── quarantine report                    # prints the register; fails at > 3 entries
```

`make check` is the gate named in `SETUP.md` §"Commands" and is the definition of "green" for this project.

### 17.3 Pre-release

Everything in `make check`, plus:

```
make release-check
├── pytest -m e2e                        # four full sessions, stubbed models
├── make soak                            # §16.3
├── make evals                           # the full model-quality suite, DEV + fixtures
│                                        #   (owned by docs/08-evals.md; TEST stays sealed)
├── make perf-trend                      # [proposed] latency drift review
├── quarantine must be EMPTY
├── metrics snapshot diff                # plans/metrics-snapshot.md vs the latest eval run
├── migration test                       # every migration applied forward against a
│                                        #   populated DB from the previous release tag
└── golden diff review                   # any golden change since the last tag, read by a human
```

**Manual checklist — done by a person, recorded in the release notes:**

| # | Check |
|---|---|
| M-1 | One full voice session on real hardware, headphones on, both directions, no crash |
| M-2 | One full voice session with headphones **off** — the echo guard fires and the warning is legible |
| M-3 | Unplug the audio device mid-turn; confirm the pause, the countdown and the recovery |
| M-4 | Kill `rehearsal-api` mid-session; restart; confirm resume to the turn boundary with the same seed |
| M-5 | VoiceOver, full session, `es` locale — announcements correct, Spanish pronounced in Spanish |
| M-6 | VoiceOver, full session, `en` locale |
| M-7 | Keyboard-only session with the trackpad physically disabled |
| M-8 | Dark mode, every screen, on a real display — tonal variants read as designed, not as inverted |
| M-9 | Trainer review flow: override a finding, sign, confirm the original verdict is still in the record |
| M-10 | Read one generated report end to end as a trainee would. Is every finding defensible? |

M-10 is not a formality. It is the only check that asks whether the system is producing something a professional would accept, and it has caught things no assertion did.

---

## 18. What this strategy deliberately does not test

Stated so that the absences are decisions rather than oversights.

| Not tested | Why | What would change it |
|---|---|---|
| Model output quality | It is not a fixed value; it is `docs/08-evals.md` | Nothing. This boundary is permanent. |
| Real inference latency in a commit gate | Machine-dependent; would make gates hardware-coupled and flaky | Nothing. EV-07 owns it. |
| The inference runtime (MLX, llama.cpp) | Not ours; we test our *use* of it via cassettes and health probes | A runtime bug that our code must work around gets a regression test naming the upstream issue |
| Multi-user / concurrent sessions | Out of scope by decision — no multi-tenant fleet scaling (`docs/17-decisions.md`). F-19 asserts the single-writer guarantee instead. | A decision to support concurrent sessions |
| Browser matrix beyond the target | The product targets one modern browser on macOS; a matrix would multiply cost against no user | A second supported platform |
| Load and stress | One machine, one trainee, one session. Load testing a single-user local application measures nothing. | Nothing foreseeable |
| Security penetration testing | Local-only, loopback-bound, no auth surface, no network egress. Boundaries are in `docs/12-security-privacy.md`; the tests here assert the *code* respects them (no traceback text in errors, no network calls, redaction on export). | Any remote surface at all — at which point this row becomes a whole document |
| Mutation testing | Considered and deferred. The extractor grid plus 100 % branch coverage plus the property suite already exercise the paths mutation testing would target, and `mutmut` over a codebase with a 200-row parametrised suite is slow enough to go unused. **[proposed]** — worth a one-off run against `src/rehearsal/scoring/` to check the assumption. | A one-off run showing a meaningful surviving-mutant rate |

---

## 19. Status register

| Item | Status | Note |
|---|---|---|
| Extractor table-driven grid and fixture format | **decided** | §5 |
| Merge properties P1–P9 | **decided** | §6.1 |
| Human-gate proofs at three levels | **decided** | §8 |
| Contracts directory as the single source of truth | **decided** | §9 |
| Audio fixtures with manifest ground truth | **decided** | §10.1 |
| Fault catalogue F-01…F-25 with named safe states | **decided** | §11.1 |
| Latency budgets in `tests/perf/budgets.json` | **proposed** | Numbers are first estimates and must be re-derived from `rehearsal doctor` on the target machine, not inherited from this table |
| `make perf-trend` renderer | **proposed** | History file is written today; the renderer is not built |
| Mutation testing | **open** | One exploratory run against the scoring package would settle it |
| Frequency equivalence set (TID ≡ q8h, BID ≡ q12h) | **decided**, with a review obligation | The equivalence table lives in `docs/06-scoring-engine.md` and should be reviewed by a practising interpreter or clinician before release; if it changes, §5.3's frequency rows change with it |
| Second labeller for reading-order and microcopy review | **open** | Bilingual review of finding microcopy is a named dependency of M-10 and has no assigned owner |

---

## Related documents

| Document | Relationship |
|---|---|
| `docs/03-system-architecture.md` | Source of the state machine, event kinds, component contracts and module layout this document tests |
| `docs/06-scoring-engine.md` | Extractor rule semantics and the equivalence tables; §5 tests them, it does not define them |
| `docs/08-evals.md` | Model quality. The other half of the pair; see §1 for the boundary |
| `docs/05-voice-pipeline.md` | DSP specification behind the audio tests in §10 |
| `docs/09-ui-ux.md` | Accessibility obligations, keyboard map, component inventory and microcopy tested in §13–§14 |
| `docs/10-frontend-spec.md` | Frontend structure; the reason the frontend tests use `node --test` |
| `docs/11-backend-api.md` | The API surface the contract tests in §9 pin |
| `docs/12-security-privacy.md` | Trust boundaries; §11 and §15.3 assert the code respects them |
| `docs/13-deployment-ops.md` | Where the gates in §17 are wired up and how a release is cut |
| `SETUP.md` §6 | The calibration-set protocol, including the seal that §15.1 enforces |

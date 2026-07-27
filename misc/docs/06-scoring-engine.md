# 06 — The Fidelity Scoring Engine

This is the instrument. Everything else in Rehearsal exists to put a human in front of it and to make its output believable.

The scoring engine takes a **known source utterance** and a **trainee rendering** of it in the other language, and returns a typed set of findings against the interpreting error taxonomy this system implements, each with a span, a severity and a provenance. It is deliberately split in two: a deterministic half that is *provably* right, and a single language-model call that handles only what no closed-form check can decide.

> **Provenance of the taxonomy — read this before describing it anywhere.** These categories are an **operationalisation drawn from the interpreting research literature** (principally Flores et al.; Vasquez & Javier, 1991), **aligned to** NCIHC *National Standards of Practice* 1, 2, 5–6, 12 and 16–18. They are **not** a single codified professional standard: no authoritative publication defines this category set as one unit, no public inter-rater-calibrated severity rubric exists, and NCIHC contains **no explicit first-person interpreting requirement** — Standard 12 is the nearest provision — so `first_person_violation` encodes near-universal professional convention rather than a written standard. Never call this "the professional standard taxonomy" in a document, an interface string, or a report. See `docs/01-research.md` §2 and §8.1.

This document owns the internals. It does not restate what its siblings own:

| For | Read |
|---|---|
| Where the scoring plane sits, its latency class, the event log and the DB schema it writes | `docs/03-system-architecture.md` §7, §10 |
| The professional standards the taxonomy derives from, and the clinical-consequence evidence | `docs/01-research.md` |
| Scenario authoring, the clinical state graph, how a `TermManifest` is produced | `docs/07-data-and-scenarios.md` |
| Every eval number this engine is obliged to produce, and the gates | `docs/08-evals.md` |
| The calibration set: construction, blind labelling, the sealed split | `SETUP.md` §6 |
| How findings are surfaced to the trainee and the reviewing trainer | `docs/09-ui-ux.md` |

Status labels: **[decided]** (implement as written), **[proposed]** (default choice, cheap to change, no measurement behind it yet), **[open]** (genuinely undecided; §16).

---

## 1. Problem statement

### 1.1 The problem we are actually solving

The naive framing of interpreting assessment is *"judge how good this interpretation was."* That is an open-ended quality judgement, it has no ground truth, and a language model asked to do it will produce a fluent number with nothing underneath it.

Rehearsal does not have that problem, because of principle 2 — **ground truth by construction**. The system generates the clinician's English utterance and the patient's Spanish utterance. It knows, exactly and before the trainee opens their mouth, what was said. The `source_sha` is written to the event log *before* the audio is synthesised (`docs/03-system-architecture.md` §9).

So the real problem statement is:

> Given a string `source` in language A whose meaning is known by construction, and a string `rendering` in language B produced by a human interpreting `source` aloud, enumerate the propositional content of `source` that did not survive into `rendering`, the content in `rendering` that was not in `source`, and the content that survived in altered form — classify each occurrence against a fixed taxonomy, and mark whether it could change clinical action.

That is a **comparison** problem, not a judgement problem. It is tractable, it is defensible to a training programme director, and — critically — a large fraction of it is decidable by code.

### 1.2 Why this framing changes the architecture

| Framing | What the model must do | Failure mode |
|---|---|---|
| "Judge quality" | Hold an implicit standard, apply it consistently, produce a scalar | Unfalsifiable output; drifts with prompt wording; no way to test |
| "Compare known source to rendering" | Align two strings and name the deltas | Every finding quotes real text; every finding is checkable by a human in seconds |

The second framing is what lets §8 exist at all: a finding that must quote a substring of the rendering can be **verified by string containment**, deterministically, before it is allowed to reach a human. A quality score cannot be verified by anything.

### 1.3 What is decidable and what is not

This split is principle 3, and it is the organising decision of the whole engine.

| Content class | Decidable from two strings + the term manifest? | Owner |
|---|---|---|
| Numbers, quantities, decimals | **Yes** — parse and compare canonical values | Extractor |
| Dosages and units (mg, mcg, mL, tablets) | **Yes** — parse, normalise units, compare | Extractor |
| Frequencies and intervals (`cada 8 horas`, `twice a day`) | **Yes** — canonicalise to a frequency record | Extractor |
| Durations and temporal markers (`desde hace tres días`) | **Yes**, with a stated coverage boundary | Extractor |
| Negation and its scope | **Yes**, with a cue lexicon and scope rules | Extractor |
| Laterality (left/right/bilateral) | **Yes**, anchored to a manifest body site | Extractor |
| Allergies (allergen identity + polarity) | **Yes** — closed-world against the manifest | Extractor |
| Named clinical entities (drug names, sites, conditions) | **Yes**, closed-world against the manifest only | Extractor |
| Register (formal/informal, lay/technical) | No | Grader |
| Idiom and figurative language | No | Grader |
| Pragmatic force (hedge, insistence, request vs statement) | No | Grader |
| First-person discipline / role exchange | No | Grader |
| Editorialisation, unrequested explanation | No | Grader |
| False fluency (invented content delivered confidently) | No | Grader |

The left column is **the critical error class** — the errors that `docs/01-research.md` shows carry clinical consequence. It is handled by code that either matches or does not, and whose correctness is gated at `extractor_conformance = 1.00` in `docs/08-evals.md` §4.1. We do not ask a model to do arithmetic on dosages, because a model is a strictly worse tool for a decidable problem.

### 1.4 Non-goals

| Not doing | Why |
|---|---|
| A single scalar "interpreting score" | It compresses away the only thing that matters — *which* error, *how severe*. The report surfaces counts and rates by category (`docs/09-ui-ux.md`) |
| Grading pronunciation, accent, fluency-as-prosody | Not fidelity. Out of the taxonomy. Named as a gap in §15 |
| Grading the trainee's target-language grammar | An ungrammatical rendering that preserves meaning is a fidelity pass. Deliberate |
| Auto-failing a trainee | Principle 1: the human decides. The engine produces findings; the review gate produces conclusions (`docs/03-system-architecture.md` §11) |
| Any model weight training to improve the grader | Out of scope project-wide. Prompt-level optimisation only (L10, `docs/08-evals.md` §6) |

---

## 2. Inputs, outputs and the top-level contract

### 2.1 Entry point

```python
# src/rehearsal/scoring/engine.py

def score_turn(req: ScoreRequest, cfg: ScoringConfig) -> Verdict:
    """Score one interpreted turn. Pure with respect to (req, cfg) plus the
    resolved grader model; no I/O except the grader host call and metrics.
    Never raises for model or content reasons — model/content failures become
    a Verdict with a degraded `status`. Raises only on programmer error."""
```

```python
# src/rehearsal/scoring/types.py

@dataclass(frozen=True, slots=True)
class ScoreRequest:
    session_id: str
    turn_index: int
    direction: Literal["en->es", "es->en"]
    speaker: Literal["clinician", "patient"]   # who produced the source
    source: str                                # known by construction
    rendering: str                             # trainee's rendering, `heard_verbatim`
    source_sha: str
    rendering_sha: str
    manifest: TermManifestSlice                # the facts this turn was built from
    partial: bool                              # source truncated by barge-in
    rendering_src: Literal["live_verbatim", "offpath_retranscribe"]
```

`source` and `rendering` are the **exact** blob contents referenced by `source_sha` / `rendering_sha`. The engine never re-fetches or re-normalises the stored text; all normalisation happens on copies (§4.1) and offsets are always reported against the original strings. This is what makes `verdict_key` (a hash over `prompt_ver | grader_model | source_sha | rendering_sha`) a sound idempotency key.

### 2.2 The term manifest slice — the extractors' ground truth

The content plane emits, alongside each source utterance, the clinical facts that utterance was constructed to carry (`docs/07-data-and-scenarios.md`). The extractors compare against **this**, not against their own reading of the source. That is the difference between "the extractor believes the source said 500 mg" and "the source was *built from* 500 mg".

```python
# src/rehearsal/content/terms.py

@dataclass(frozen=True, slots=True)
class TermManifestSlice:
    node_id: str
    quantities:  tuple[QuantityFact, ...]
    frequencies: tuple[FrequencyFact, ...]
    durations:   tuple[DurationFact, ...]
    negations:   tuple[NegationFact, ...]
    laterality:  tuple[LateralityFact, ...]
    allergies:   tuple[AllergyFact, ...]
    entities:    tuple[EntityFact, ...]
    # Every fact carries `required: bool`. Non-required facts are colour
    # (the patient's cousin's name); omitting them is not an error.

@dataclass(frozen=True, slots=True)
class EntityFact:
    entity_id: str                  # "med.metformin"
    kind: Literal["medication", "body_site", "condition", "procedure", "person_role"]
    surface_en: tuple[str, ...]     # ("metformin",)
    surface_es: tuple[str, ...]     # ("metformina",)
    aliases:    tuple[str, ...]     # ("glucophage",) — accepted, not required
    required: bool
```

**Manifest-first, source-second [decided].** Every extractor runs its parser over *both* the source string and the rendering string, but resolves disagreement in favour of the manifest. If the parser finds `500 mg` in the source and the manifest says `500 mg`, they agree and we proceed. If they disagree, that is a **content-plane bug**, not a trainee error: the engine emits no finding for that fact, sets `status = "manifest_desync"` on the verdict, and logs `scoring.manifest_desync` with both readings. A desync must never be charged to the trainee. Desync rate is a reported number in `docs/08-evals.md` §4.1.

### 2.3 Pipeline

```
ScoreRequest
     │
     ├─ (0) Preconditions & refusal checks ────────────► RefusedVerdict (§8.5)
     │
     ├─ (1) Normalisation pre-pass  normalize.py
     │        NFC, casefold-copy, numeral expansion, unit folding
     │        → NormalizedText(original, folded, offset_map)
     │
     ├─ (2) SYMBOLIC STAGE  extractors/*.py            ~15–40 ms, always runs
     │        seven extractors, each: (source, rendering, ctx) -> list[Finding]
     │        every finding provably derived; confidence = None
     │
     ├─ (3) SEMANTIC STAGE  grader.py                  ~2.0–3.0 s, may be skipped
     │        ONE structured call, temperature 0, schema-validated
     │        sees: source, rendering, taxonomy residue, direction — nothing else
     │
     ├─ (4) GUARDS  guards.py                          ~2 ms
     │        schema validity, span verification, quote containment,
     │        category legality, self-consistency (when reads=2)
     │
     ├─ (5) MERGE  merge.py                            ~2 ms, deterministic
     │        dedup, precedence, severity assignment, confidence assembly
     │
     └─► Verdict  (typed, then persisted by the store layer)
```

Stage 2 never depends on stage 3 and vice versa. If the grader host is dead, stages 1–2 and 4–5 still run and produce a `partial` verdict covering the entire critical error class. That property — **the critical checks survive the loss of the model** — is the single most important robustness fact about this engine.

---

## 3. The error taxonomy, implemented

Nine categories, from the professional interpreting standard (`docs/01-research.md` §3). This section is the *implementation* contract: what each category means to the code, who can emit it, and what evidence it requires.

| # | `ErrorKind` | Definition as implemented | Emitted by | Required evidence |
|---|---|---|---|---|
| 1 | `omission` | A required manifest fact, or a proposition present in the source, has no counterpart in the rendering | Extractor + Grader | Extractor: the missing fact id. Grader: `source_quote` (the omitted material), `rendering_quote = null` |
| 2 | `addition` | Propositional content in the rendering with no counterpart in the source | Grader (extractor for quantities not in the manifest) | `rendering_quote` must be a real substring |
| 3 | `substitution` | A source element is replaced by a different element of the same type (drug→drug, allergen→allergen, number→number) | Extractor + Grader | Both quotes, plus the fact id when symbolic |
| 4 | `distortion` | Meaning altered without clean substitution — includes **negation flips**, polarity reversal, scope errors, intensity shifts | Extractor (negation, laterality, frequency) + Grader | Both quotes |
| 5 | `editorialization` | Interpreter adds commentary, opinion, explanation or advice not present in the source | Grader only | `rendering_quote` |
| 6 | `role_exchange` | Interpreter speaks as themselves — answers for the patient, asks their own question, converses with one party | Grader only | `rendering_quote` |
| 7 | `register_shift` | Register moved materially (lay↔technical, formal↔familiar, `usted`↔`tú`) in a way that changes accessibility or standing | Grader only | Both quotes |
| 8 | `false_fluency` | Content delivered with confidence that was not in the source — invented specifics, invented reassurance, filled-in gaps | Grader only | `rendering_quote` |
| 9 | `first_person_violation` | Rendering shifts out of first person (`he says that…`, `dice que…`) where the standard requires first-person interpreting | Grader only | `rendering_quote` |

**Category legality is enforced in code, not in the prompt.** `guards.py` holds:

```python
# src/rehearsal/scoring/taxonomy.py

EXTRACTOR_OWNED: frozenset[ErrorKind] = frozenset(
    {"omission", "addition", "substitution", "distortion"}
)
GRADER_ONLY: frozenset[ErrorKind] = frozenset(
    {"editorialization", "role_exchange", "register_shift",
     "false_fluency", "first_person_violation"}
)
# Grader MAY propose EXTRACTOR_OWNED kinds (it sees things the manifest doesn't
# cover, e.g. an omitted symptom description). It may never set severity there.
```

A grader finding in a category that does not exist is dropped by the guard and counted in `guard.unknown_kind` — never coerced to the nearest neighbour. Coercion would silently invent a label the model did not intend.

### 3.1 Severity assignment — deterministic, always

Severity is **never** taken from the model. Principle 1 in its sharpest form: the model may say *what* it saw; only code says *how much it matters*.

```python
# src/rehearsal/scoring/severity.py

CRITICAL_FACT_KINDS: frozenset[str] = frozenset(
    {"quantity", "dosage", "unit", "frequency", "duration_onset",
     "negation", "laterality", "allergy"}
)

def assign_severity(f: Finding, ctx: TurnContext) -> Severity:
    """The single authority on severity. Called by VerdictMerger, nowhere else."""
```

The rules, in evaluation order. First match wins.

| # | Rule | Severity | Rationale |
|---|---|---|---|
| S1 | Finding is anchored to an `allergy` fact (any kind: omission, substitution, distortion) | `critical` | Wrong allergen or dropped allergy can kill. No exceptions, no confidence threshold |
| S2 | Finding is a negation polarity flip on a **required** fact | `critical` | "Take it" / "don't take it" |
| S3 | Finding is anchored to a `quantity` fact whose `role` is `dose` | `critical` | Dosage errors change clinical action |
| S4 | Finding is anchored to a `frequency` fact and the canonical `per_day` values differ | `critical` | Frequency errors change clinical action |
| S5 | Finding is anchored to a `laterality` fact and the values differ (including `bilateral` ↔ unilateral) | `critical` | Wrong-site consequences |
| S6 | Finding is anchored to a `duration` fact whose `role` is `symptom_onset` | `critical` | Onset drives triage (`docs/01-research.md` §2.4) |
| S7 | Finding is anchored to a `quantity` fact with `role` in `{count, measurement}` and the values differ | `critical` | e.g. "two tablets" → "one tablet" |
| S8 | Finding is a `frequency` **underspecification** (per-day matches, interval lost — §4.6) | `non_critical` | Meaning narrowed, action unchanged in most protocols. Flagged, explained |
| S9 | Finding is `substitution` on an `entity` of kind `medication` | `critical` | Wrong drug |
| S10 | Finding is `substitution` on an `entity` of kind `body_site` or `procedure` | `critical` | Wrong site / wrong procedure |
| S11 | Grader-origin finding in any `GRADER_ONLY` category | `non_critical` | The model is not permitted to manufacture a critical. If a register shift genuinely carried clinical weight, the trainer marks it in review — a human decision, recorded (`reviews` table) |
| S12 | Grader-origin finding in an `EXTRACTOR_OWNED` category that no extractor fact anchors | `non_critical`, `unanchored = true` | The model spotted something the manifest doesn't model. Real signal, but not provable — so it cannot be a critical |
| S13 | Anything else | `non_critical` | Default |

Two consequences worth stating plainly:

1. **Every `critical` finding in the system traces to a deterministic extractor and a manifest fact id.** You can point at the line of code and the fact that produced it. This is the property that makes the number defensible to a programme director.
2. **The grader can never raise severity, only report.** S11/S12 are absolute. `docs/03-system-architecture.md` §7 states the same rule from the architecture side; this is its implementation.

### 3.2 The `Finding` record

Extends the architecture contract with the fields the engine needs internally.

```python
# src/rehearsal/scoring/taxonomy.py

@dataclass(frozen=True, slots=True)
class Finding:
    kind: ErrorKind
    severity: Severity                       # set ONLY by severity.assign_severity
    span: tuple[int, int] | None             # char offsets into rendering (original)
    source_span: tuple[int, int] | None       # char offsets into source (original)
    note: str                                # human-readable, <= 200 chars
    origin: Literal["extractor", "grader"]
    extractor_name: str | None
    fact_id: str | None                      # manifest anchor, extractor findings
    confidence: float | None                 # grader only; extractors do not guess
    stability: Literal["stable", "unstable", "single_read"] | None
    unanchored: bool = False
    overruled: bool = False
    withheld: bool = False                   # §9.4 — recorded, not shown
```

`confidence is None` for every extractor finding, deliberately. An extractor that matched did not estimate anything; attaching `1.0` would put a probability where there is a proof, and would let downstream code average a proof with a guess.

---

## 4. Stage A — the deterministic extractors

Seven extractors, one file each, under `src/rehearsal/scoring/extractors/`. Each implements the `Extractor` protocol from `docs/03-system-architecture.md` §7. Each is covered by its own fixture grid in `data/fixtures/extractors/<name>.jsonl` and gated at exactly 1.00 (`docs/08-evals.md` §4.1).

| File | `name` | Owns | Manifest facts consumed |
|---|---|---|---|
| `numbers.py` | `numbers` | Cardinals, decimals, fractions, ranges, written-out numerals (en + es) | `quantities` |
| `dosage.py` | `dosage` | Quantity + unit + form (`500 mg`, `dos pastillas`, `5 mL`) | `quantities` |
| `frequency.py` | `frequency` | Rate and interval expressions | `frequencies` |
| `temporal.py` | `temporal` | Durations, onsets, deictic day references | `durations` |
| `negation.py` | `negation` | Negation cues, scope, polarity of a targeted proposition | `negations` |
| `laterality.py` | `laterality` | left / right / bilateral, anchored to a body site | `laterality` |
| `allergy.py` | `allergy` | Allergen identity and assertion polarity | `allergies` |
| `entities.py` | `entities` | Closed-world named entity presence (drug, site, condition, procedure) | `entities` |

(Eight files; `entities.py` is a support extractor — it never emits `critical` on its own, it supplies the anchors that S9/S10 use.)

### 4.1 The normalisation pre-pass

`src/rehearsal/scoring/normalize.py`. Runs once per string; the result is shared by every extractor.

```python
@dataclass(frozen=True, slots=True)
class NormalizedText:
    original: str                 # untouched; all reported offsets index this
    folded: str                   # the matching surface
    offset_map: tuple[int, ...]   # folded index -> original index, monotone
    lang: Literal["en", "es"]

def normalize(text: str, lang: Literal["en", "es"]) -> NormalizedText: ...
def to_original(nt: NormalizedText, span: tuple[int, int]) -> tuple[int, int]: ...
```

Steps, in order:

| # | Step | Detail | Why not skipped |
|---|---|---|---|
| N1 | Unicode NFC | `unicodedata.normalize("NFC", s)` | `é` as one codepoint vs `e`+combining acute must not be two different words. Spanish text arrives from two model families |
| N2 | Whitespace fold | Collapse runs to a single space; strip | Streamed TTS-adjacent text carries stray spacing |
| N3 | Case fold | `str.casefold()` | Locale-independent; handles `İ`-class edge cases that `.lower()` does not |
| N4 | **Diacritics retained** | We do **not** strip accents | `esta`/`está`, `papa`/`papá`, `si`/`sí` are different words. Stripping accents to make matching easier would silently destroy negation and polarity distinctions. Fixtures cover this (`docs/08-evals.md` §4.1) |
| N5 | Punctuation isolation | Insert spaces around `,.;:¿?¡!()` **except** between digits (`0,5`, `1.000`) | Preserves the decimal-comma case, which is the whole point |
| N6 | Numeral expansion | Written numerals → digits, as an *annotation*, not a rewrite (§4.2) | Rewriting would break offsets |
| N7 | Unit folding | Unit surface forms → canonical symbol via `UNIT_ALIASES` (§4.3) | `mcg` / `µg` / `μg` / `microgramos` / `micrograms` are one unit |
| N8 | Elision expansion (es) | `del` → `de el`, `al` → `a el`, as annotation | Frequency patterns (`al día`) tokenise consistently |

`offset_map` is maintained across every step so that **every span the engine ever reports indexes the original, unmodified string the human actually sees**. Guard G3 (§8.3) re-verifies this by string comparison; a normalisation bug that shifts offsets is caught, not shipped.

### 4.2 `numbers.py` — cardinals, decimals, cross-lingual

**Canonical form.**

```python
@dataclass(frozen=True, slots=True)
class Number:
    value: Decimal                # exact; never float
    span: tuple[int, int]         # into original
    written: bool                 # was it a word form
    approximate: bool             # preceded by "about"/"unos"/"como"
```

`Decimal` throughout, never `float`. `0.1 + 0.2 != 0.3` is not a bug we will explain to a clinician.

**Digit-form grammar.**

```
number   := sign? int_part ( sep_dec frac_part )?
int_part := digit+ ( sep_thou digit{3} )*
sep_dec  := "." | ","        # disambiguated by rule below
sep_thou := "," | "." | " " | U+00A0
```

**Decimal separator disambiguation [decided]** — the single highest-value cross-lingual rule in the engine. Spanish (es-MX in the clinical register we generate, and es-ES in trainee habit) writes `0,5 mg`; English writes `0.5 mg`. Resolution order:

| # | Condition | Interpretation |
|---|---|---|
| D1 | Exactly one separator, followed by exactly 3 digits, and preceded by 1–3 digits, and the number is `>= 1000` in either reading | **Thousands.** `1.000` → 1000; `1,000` → 1000 |
| D2 | Exactly one separator followed by 1–2 digits, or 4+ digits | **Decimal.** `0,5` → 0.5; `2.75` → 2.75; `1,2345` → 1.2345 |
| D3 | Exactly one separator followed by exactly 3 digits, ambiguous under D1 (e.g. `1,500`) | **Language default**: `.` = decimal and `,` = thousands in `en`; `,` = decimal and `.` = thousands in `es` |
| D4 | Both separators present | The **last** one is the decimal separator. `1.234,56` → 1234.56; `1,234.56` → 1234.56 |
| D5 | Result is compared against a manifest fact and D3 was used | Both readings are computed. If **either** matches the manifest, no finding, and `note` records the ambiguity. If neither matches, the finding is emitted with the language-default reading |

D5 is the honesty rule: an ambiguous separator must not become a false alarm on the trainee. `1,500 mg` from an English-first trainee rendering into Spanish is not a dosage error; it is an orthographic habit. It is not the taxonomy's business.

**Written numerals.** Full closed lexicons, `numbers_lex_en.py` / `numbers_lex_es.py`:

| Language | Coverage | Composition rules |
|---|---|---|
| `en` | zero–twenty, thirty…ninety, hundred, thousand, `a`/`an` as 1, halves (`a half`, `and a half`) | Additive within a scale (`twenty-five`), multiplicative across (`five hundred`) |
| `es` | cero–treinta (incl. the fused `dieciséis`, `veintidós` …), cuarenta…noventa, cien/ciento, quinientos, mil, `un`/`una`/`uno`, `medio`/`media`, `y medio` | Additive with `y` (`treinta y cinco`), multiplicative (`quinientos`), gender variants (`doscientas`) |

Both lexicons include the traps the fixture grid requires: `ciento` vs `cien`, `un` vs `uno` vs `una`, `veintiún`, and the `y medio` suffix (`dos y medio` → `2.5`).

**Ranges.** `entre 5 y 10`, `5 a 10`, `five to ten`, `5–10` parse to a `NumberRange(lo, hi)`. A manifest quantity is matched by a range only if `lo == hi == value`; a range where the source had a point value is a `distortion` (the trainee introduced imprecision), and the reverse — a point value where the source had a range — is also a `distortion`. Both are non-critical unless S3/S7 anchors them to a dose or count.

**Approximation markers.** `about`, `around`, `roughly`, `unos`, `como`, `más o menos`, `aproximadamente` set `approximate = True`. Matching rule: an approximate rendering of an exact source dose is a `distortion` (`critical` via S3 — "about 500 milligrams" is not an acceptable rendering of a prescription). An exact rendering of an approximate source is also a `distortion` (false precision), `non_critical`.

### 4.3 `dosage.py` — quantity + unit + form

**Canonical form.**

```python
@dataclass(frozen=True, slots=True)
class Dose:
    value: Decimal
    unit: str | None              # canonical symbol, or None for countable forms
    base_value: Decimal | None    # value converted to the unit family's base
    form: str | None              # "tablet", "capsule", "drop", "puff", "injection"
    span: tuple[int, int]
```

**Unit families and canonicalisation.** Comparison happens on `base_value` within a family; cross-family comparison is never attempted (comparing mg to mL is a category error, and the manifest never asks for it).

| Family | Base | Members and aliases (en / es) |
|---|---|---|
| `mass` | `mg` | `g`, `gram`, `gramo(s)`, `gr` (×1000); `mg`, `milligram(s)`, `miligramo(s)` (×1); `mcg`, `µg`, `μg`, `ug`, `microgram(s)`, `microgramo(s)` (×0.001) |
| `volume` | `mL` | `L`, `litro(s)`, `liter(s)` (×1000); `mL`, `ml`, `mililitro(s)`, `milliliter(s)`, `cc` (×1); `teaspoon`, `tsp`, `cucharadita` (×5, `approximate_unit = True`); `tablespoon`, `cucharada` (×15, `approximate_unit`) |
| `activity` | `unit` | `unit(s)`, `unidad(es)`, `U`, `UI`, `IU` |
| `count` | — | `tablet`, `tab`, `pill`, `pastilla(s)`, `tableta(s)`, `comprimido(s)`, `capsule`, `cápsula(s)`, `drop`, `gota(s)`, `puff`, `inhalación/inhalaciones`, `spray`, `aplicación` |
| `mass_ratio` | `mg/mL` | `mg/mL`, `mg por mL`, `miligramos por mililitro` |
| `temperature` | `°C` | `°C`, `C`, `grados`, `centígrados`; `°F`, `F`, `Fahrenheit` (converted) |

Two rules that matter clinically:

- **`µ` normalisation.** U+00B5 MICRO SIGN and U+03BC GREEK SMALL LETTER MU both fold to `mcg`. They are visually identical and arrive from different sources.
- **Kitchen units are flagged, not silently converted.** `una cucharadita` → 5 mL with `approximate_unit = True`. If the manifest says `5 mL` and the rendering says `una cucharadita`, that is **not** an error (it is arguably better patient communication), and the extractor emits nothing. If the manifest says `7.5 mL` and the rendering says `una cucharadita y media`, the base values match and again nothing is emitted. But if the source said `5 mL` and the rendering said `una cucharada` (15 mL), that is a 3× dose error: `substitution`, `critical` (S3).

**Form matching.** `dos pastillas` ↔ `two tablets` matches on `value = 2, unit = None, form = count-family`. Form nouns are matched within the count family and **not** across it: rendering `dos gotas` (drops) for source `two tablets` is a `substitution`, critical via S3 (the manifest `role` is `dose`).

**Concentration compounds.** `500 mg/5 mL` parses to a `Dose` with `unit = "mg/mL"` and `base_value = 100`. This is emitted as one fact, not two, so that a rendering of `100 mg per mL` matches exactly.

### 4.4 `entities.py` — closed-world named entities

**Closed-world, deliberately.** The extractor recognises *only* entities present in `manifest.entities`. It does not carry a drug dictionary, does not do open NER, and never flags an unknown token as a drug.

| Decision | Value | Why |
|---|---|---|
| Match method | Exact match on folded surface forms and aliases, then `difflib.SequenceMatcher` ratio ≥ **0.88** against each surface form of the *expected* entity only | Stdlib. No new dependency for a bounded closed-world match. `ponytail:` the fuzzy threshold is the calibration knob; raise it if morphological variants start colliding |
| Fuzzy hits | Recorded as `matched_fuzzy = True` in the note; still a match | Catches `metformina`/`metformina` typos in `heard_verbatim` without inventing findings |
| Cognate pairs | `surface_en` × `surface_es` are both accepted in either direction | `metformin`/`metformina`, `penicillin`/`penicilina` — the trainee may legitimately keep the source form |
| Confusable guard | If a *different* manifest entity of the same `kind` matches better than the expected one, emit `substitution` anchored to both fact ids | This is how "azithromycin → amoxicillin" is caught: both are in the manifest for that scenario |
| Unknown token that fuzzy-matches nothing | No finding | An open-world drug detector would produce false alarms on ordinary vocabulary, and the grader covers invented content under `false_fluency` |

Missing a `required = True` entity → `omission`, severity from S9/S10. Missing a `required = False` entity → no finding.

### 4.5 `temporal.py` — durations, onsets, day references

**Canonical form.**

```python
@dataclass(frozen=True, slots=True)
class TemporalRef:
    kind: Literal["duration", "point_relative", "point_absolute", "deictic_day"]
    hours: Decimal | None         # duration normalised to hours
    label: str | None             # "monday", "yesterday", "this_morning"
    direction: Literal["past", "future", "none"]
    approximate: bool
    span: tuple[int, int]
```

**Duration normalisation to hours.** `minuto/minute` ×(1/60); `hora/hour` ×1; `día/day` ×24; `semana/week` ×168; `mes/month` ×**730** (`ponytail:` 30.42-day month, exact enough for onset comparison; if a scenario ever needs calendar arithmetic this is the upgrade point); `año/year` ×8760.

**Onset construction patterns.** These are matched as whole patterns, because the pieces mean nothing apart:

| Spanish | English | Canonical |
|---|---|---|
| `desde hace tres días` | `for three days`, `for the past three days` | `duration`, 72 h, `past` |
| `hace tres días` (as a point) | `three days ago` | `point_relative`, 72 h, `past` |
| `desde el martes` | `since Tuesday` | `deictic_day`, label `tuesday`, `past` |
| `durante dos semanas` | `for two weeks` | `duration`, 336 h |
| `en dos semanas` | `in two weeks` | `point_relative`, 336 h, `future` |
| `de un momento a otro`, `de repente` | `suddenly`, `all of a sudden` | `duration`, hours `0`, `onset_abrupt = True` in the note |
| `poco a poco`, `gradualmente` | `gradually` | `onset_gradual` |

The `desde hace X` / `hace X` distinction is the trap the fixture grid targets: "it has hurt for three days" and "it hurt three days ago" are different clinical pictures, and the Spanish differs by one word.

**Deictic days.** `desde el martes` → `since Tuesday` is a **string-label match**, not a date computation. The engine does not know today's date and does not want to: the source and the rendering happen seconds apart, so equality of label is sufficient and is not subject to a timezone bug. Weekday lexicons are closed (7 × 2 languages, plus `ayer/yesterday`, `anteayer/the day before yesterday`, `esta mañana/this morning`, `anoche/last night`).

**Onset severity.** A `duration` fact with `role = "symptom_onset"` is critical (S6). Everything else temporal — appointment timing, medication start date — is non-critical unless it also carries a frequency (which `frequency.py` owns).

### 4.6 `frequency.py` — rate and interval

**Canonical form.** The two-field design is the whole trick.

```python
@dataclass(frozen=True, slots=True)
class Frequency:
    per_day: Decimal | None        # 3 for "three times a day" and for "every 8 hours"
    interval_hours: Decimal | None  # 8 for "every 8 hours"; None for "three times a day"
    prn: bool                       # "as needed" / "si es necesario"
    with_food: bool | None          # captured; compared only if in the manifest
    at_night: bool
    span: tuple[int, int]
```

**Pattern table** (both languages; `N` is any `numbers.py` result):

| Surface | `per_day` | `interval_hours` |
|---|---|---|
| `cada N horas`, `every N hours`, `qN h`, `each N hours` | 24/N | N |
| `cada N días`, `every N days` | 1/N | 24N |
| `N veces al día`, `N times a day/daily`, `N times per day` | N | — |
| `una vez al día`, `once a day`, `daily`, `diario`, `al día` | 1 | — |
| `dos veces al día`, `twice a day`, `twice daily`, `BID` | 2 | — |
| `tres veces al día`, `three times a day`, `TID` | 3 | — |
| `cuatro veces al día`, `QID` | 4 | — |
| `N veces a la semana`, `N times a week` | N/7 | — |
| `en la mañana y en la noche`, `morning and night` | 2 | — |
| `antes de cada comida`, `before each meal`, `con cada comida` | 3 | — |
| `por la noche`, `at bedtime`, `antes de dormir`, `QHS` | 1 | — (sets `at_night`) |
| `si es necesario`, `as needed`, `PRN`, `cuando lo necesite` | — | — (sets `prn`) |

**Comparison rule [decided]** — `frequency.compare(src: Frequency, rnd: Frequency)`:

| # | Condition | Result |
|---|---|---|
| F1 | `src.per_day != rnd.per_day` (both present) | `substitution`, **critical** (S4) |
| F2 | `src.per_day` present, `rnd.per_day` absent, no PRN | `omission`, **critical** (S4) |
| F3 | `per_day` equal, `src.interval_hours` present, `rnd.interval_hours` absent | `distortion`, **non-critical** (S8), note: `frequency_underspecified` |
| F4 | `per_day` equal, `src.interval_hours` absent, `rnd.interval_hours` present | `addition`, **non-critical**, note: `frequency_overspecified` |
| F5 | Both `interval_hours` present and unequal | `substitution`, **critical** (S4) |
| F6 | `src.prn != rnd.prn` | `distortion`, **critical** — "as needed" vs "always" is a real dosing change |
| F7 | `src.at_night != rnd.at_night` and the manifest marks it required | `omission`/`addition`, non-critical |
| F8 | Everything equal | No finding |

F3 is the deliberate, documented answer to the `cada 8 horas` → `three times a day` case that `docs/08-evals.md` §4.1 names as a trap. Clinically these are **not** identical: q8h is around the clock, TID is typically with meals. But rendering one as the other does not change the number of doses per day, and calling it critical would flood the trainee with red on a rendering most working interpreters would accept. So: flagged, explained, non-critical, and the rationale ships in the note the trainee reads. If a training programme disagrees, `MergePolicy.frequency_underspecification_severity` is a config value, not a code change — and changing it requires a re-run of EV-01 because it moves the labels.

### 4.7 `negation.py` — cues, scope, polarity

This extractor answers exactly one question per manifest `NegationFact`: **is the targeted proposition negated in the rendering, and was it negated in the source?** A mismatch is a polarity flip, which is the single most consequence-bearing error class in the interpreting literature.

**Approach [decided]:** a NegEx-style cue + scope-window algorithm, not a parser. No dependency, deterministic, and its failure modes are enumerable.

```python
@dataclass(frozen=True, slots=True)
class NegationFact:
    fact_id: str
    target_terms_en: tuple[str, ...]   # ("allergic", "allergy")
    target_terms_es: tuple[str, ...]   # ("alérgico", "alérgica", "alergia")
    polarity: Literal["affirmed", "negated"]
    required: bool
```

**Cue lexicon.**

| Class | English | Spanish |
|---|---|---|
| Pre-cue (scope forward) | `no`, `not`, `n't`, `never`, `without`, `denies`, `deny`, `neither`, `nor`, `none`, `cannot`, `can't`, `don't`, `doesn't`, `didn't`, `hasn't`, `haven't`, `won't`, `shouldn't` | `no`, `nunca`, `jamás`, `sin`, `ni`, `ninguno/a`, `nada`, `tampoco`, `niega` |
| Post-cue (scope backward) | `is ruled out`, `was ruled out` | `no`, `tampoco`, `descartado/a` |
| Pseudo-negation (**never** a cue) | `not only`, `not just`, `no increase`, `no change`, `no wonder`, `not necessarily` | `no sólo`, `no solo`, `no obstante`, `no es que`, `sin embargo`, `sin duda`, `no sé si` |
| Scope terminator | `but`, `however`, `although`, `except`, `unless`, `and` (see below), `;`, `.`, `?`, `!` | `pero`, `sino`, `aunque`, `excepto`, `salvo`, `a menos que`, `;`, `.`, `?`, `!`, `¿`, `¡` |

**Scope algorithm.**

1. Tokenise the folded text.
2. Find pre-cue occurrences that are **not** the prefix of a pseudo-negation phrase. Pseudo-negation is checked first and greedily — `no sólo` is matched before `no`.
3. Scope = tokens from the cue to the nearest scope terminator, capped at **`SCOPE_WINDOW = 8` tokens** (`ponytail:` window is the calibration knob; 8 was chosen to comfortably span Spanish clitic + verb + object-NP and is exercised by the fixture grid — widen only with fixtures showing a miss).
4. `and` terminates the scope in English but **not** in Spanish `y`, because Spanish negative concord routinely continues a negation across `ni … ni`. `ni` extends the scope rather than terminating it.
5. Post-cues scope backwards over the same window.
6. A target term inside any scope is `negated`; otherwise `affirmed`.
7. **Double negation:** if a target sits inside two or more overlapping scopes from *distinct* cues that are not negative concord (Spanish `no … nada`, `no … nunca`, `no … ni` are concord and count as **one** negation), polarity flips per parity. `ponytail:` concord pairs are a table, not a parser.

**Findings.**

| Source polarity | Rendering polarity | Finding |
|---|---|---|
| `negated` | `affirmed` | `distortion` (negation flip), **critical** (S2) |
| `affirmed` | `negated` | `distortion` (negation flip), **critical** (S2) |
| either | target absent entirely | `omission`, severity from the anchored fact class |
| same | same | none |

**Refusal condition.** If a target term appears **more than once** in the rendering with *conflicting* scope results, the extractor does not guess. It emits no finding and sets `needs_review = True` with reason `negation_ambiguous_scope` (§8.5). A negation flip is too consequential to report on a coin flip, and too consequential to suppress silently — so it goes to the human.

### 4.8 `laterality.py`

Closed lexicon, anchored to a body site.

| Value | English | Spanish |
|---|---|---|
| `left` | `left` | `izquierdo`, `izquierda`, `izquierdos`, `izquierdas` |
| `right` | `right` | `derecho`, `derecha`, `derechos`, `derechas` |
| `bilateral` | `both`, `bilateral`, `either` (in `either side`) | `ambos`, `ambas`, `los dos`, `las dos`, `bilateral`, `bilaterales` |

**Anchoring.** A laterality token counts only when it is within **6 tokens** of a `body_site` entity from the manifest (either language surface form, resolved by `entities.py`). Free-floating `derecho` (which also means "right" as in *a right*, and "straight") is ignored. This is why `entities.py` is a prerequisite of `laterality.py` and why the extractor order in `EXTRACTOR_ORDER` is fixed.

**Comparison:** any inequality between source and rendering laterality on a required fact → `distortion` if a value was replaced, `omission` if the rendering has no laterality at all — both **critical** (S5). `bilateral` → `left` is critical (half the problem is now invisible); `left` → `bilateral` is equally critical (a wrong-site procedure).

### 4.9 `allergy.py`

The one extractor with a hard-coded severity floor. Every finding it emits is critical (S1), unconditionally, with no confidence threshold and no policy override.

```python
@dataclass(frozen=True, slots=True)
class AllergyFact:
    fact_id: str
    allergen_entity_id: str        # resolves through manifest.entities
    polarity: Literal["allergic", "not_allergic", "unknown"]
    reaction: str | None           # "hives", "anaphylaxis" — compared if present
    required: Literal[True]        # allergies are always required. Not a variable
```

Three checks, all must pass or a finding is emitted:

1. **Presence.** The allergen entity must be resolvable in the rendering (via `entities.py`, cognates and aliases accepted). Absent → `omission`, critical.
2. **Identity.** The resolved entity must be `allergen_entity_id`. A different manifest entity of kind `medication` → `substitution`, critical.
3. **Polarity.** The allergy assertion must carry the same polarity, computed by `negation.py` over the allergy target terms. Flip → `distortion`, critical.

Reaction severity (`hives` vs `anaphylaxis`) is compared when the manifest supplies it; a downgrade (`anaphylaxis` → "a rash") is a `distortion`, critical.

### 4.10 Extractor output and the symbolic contract

> ### ⚠ Implementation status — `temporal` is specified but NOT YET IMPLEMENTED
>
> The `temporal` extractor is fully specified in §4.x but **is not built**. Symptom onset and duration are therefore currently **semantic residue** — decided by the model, not by code.
>
> This creates a direct conflict with principle 1, because temporal mismatch is a `critical` severity class: a `critical` clinical-consequence finding would be produced by an unguarded model output with no deterministic check behind it. That is precisely what this architecture forbids.
>
> **Binding rule until the extractor ships:** grader findings of type `temporal` are **capped at `non_critical`** by `merge.py`, in the same manner as rule S12 for unanchored grader findings. A temporal finding may inform the trainee; it may not reach them carrying `critical` severity on a model's say-so alone.
>
> Consequences elsewhere, which must hold while this banner stands: `temporal` is **excluded** from the `extractor_conformance` grid in `docs/08-evals.md`; `docs/02-layer-vertical.md` says *seven* implemented extractors, not eight; and `CONTRIBUTING.md`'s "implement the temporal extractor" item remains open. Delete this banner and reverse all four statements in the same change that lands the extractor.

```python
# src/rehearsal/scoring/extractors/__init__.py

# NOTE: "temporal" is registered but NOT YET IMPLEMENTED — see the banner above.
# Its findings are capped at non_critical until the extractor exists.
EXTRACTOR_ORDER: tuple[str, ...] = (
    "entities", "numbers", "dosage", "frequency",
    "temporal", "negation", "laterality", "allergy",
)

def run_extractors(
    src: NormalizedText, rnd: NormalizedText, ctx: TurnContext
) -> ExtractorResult: ...

@dataclass(frozen=True, slots=True)
class ExtractorResult:
    findings: tuple[Finding, ...]
    covered_fact_ids: frozenset[str]     # facts the extractors actually adjudicated
    needs_review: tuple[ReviewFlag, ...]  # refusals (§8.5)
    desync: tuple[str, ...]               # fact ids where manifest != parsed source
    elapsed_ms: int
```

Three invariants, asserted in code and covered by tests:

- **I1 — Provability.** Every extractor finding names a `fact_id` and a parse. `confidence is None`. There is no probabilistic path into `origin = "extractor"`.
- **I2 — Order independence of the result set.** Extractors run in `EXTRACTOR_ORDER` because `laterality` and `allergy` consume `entities` output, but the *finding set* is order-independent; a property test shuffles the independent extractors and asserts set equality.
- **I3 — Coverage honesty.** `covered_fact_ids` is what the extractors actually adjudicated. Any required manifest fact **not** in that set is reported to the merge stage as `not_assessed` — never as "no error found". The distinction between "checked and clean" and "not checked" is load-bearing for principle 7 and is rendered differently in the UI (`docs/09-ui-ux.md`).

---

## 5. Stage B — the single structured grader call

One call. One turn. One schema. `src/rehearsal/scoring/grader.py`.

### 5.1 Scope of the call

The grader is asked for **the semantic residue and nothing else**: what the extractors provably cannot decide. It is not a second opinion on dosages, and it is not permitted to become one (§6 precedence, §3.1 S11/S12).

| The grader is asked for | The grader is not asked for |
|---|---|
| Register shifts, formality, `usted`/`tú`, lay↔technical | Any severity |
| Idiom and figurative language handling | Any score, grade, percentage or overall judgement |
| Pragmatic force: hedging, insistence, request vs statement | Whether the trainee "passed" |
| First-person discipline and role exchange | Any advice to the trainee (the coach owns that, `docs/03-system-architecture.md` §5) |
| Editorialisation and unrequested explanation | Anything about the trainee's history or prior turns |
| False fluency — confident invented content | Anything about the scenario beyond these two strings |
| Omissions/additions of *non-quantitative propositions* (a symptom description, a hedge, a reason) | Numbers, doses, frequencies, negation, laterality, allergies |

### 5.2 What the grader sees — and the isolation it inherits

The grader's context is assembled by the same `ContextAssembler` allowlist mechanism as the live agents (`docs/03-system-architecture.md` §12), running in the opposite direction. The live agents must never see the rubric; the grader must never see anything that would let it grade the *trainee* rather than the *turn*.

| Field | In context | Reason |
|---|---|---|
| `source` (verbatim) | Yes | It is the ground truth |
| `rendering` (verbatim) | Yes | It is the object of comparison |
| `direction` (`en->es` / `es->en`) | Yes | Register norms are direction-specific |
| `speaker` role (clinician / patient) | Yes | First-person discipline depends on whose voice it is |
| Taxonomy residue definitions + one example each | Yes | The rubric. This is the grader's job description |
| Extractor findings for this turn | **No** [decided] | Anchoring. If the grader sees "dosage error found" it will pattern-match more errors nearby. The independence of the two stages is what makes `source_split` in `docs/08-evals.md` §3 meaningful |
| The term manifest slice | **No** for now — **[open]**, §16 Q2 | Might improve precision; might drag the grader into extractor territory. Resolution is an A/B on the DEV split, not an argument |
| Learner model / prior performance | **No** [decided] | Grading the person instead of the turn. A hard isolation boundary |
| Prior turns of this session | **No** [decided] | Each turn is scored independently, which is what makes re-scoring and the calibration set (single turns) directly comparable |
| Trainee identity | **No** [decided] | Nothing in the scoring plane needs it |

`IsolationViolation` is raised if a disallowed key reaches the assembler. It is an exception, not a log line.

### 5.3 Prompt structure

Prompts are files, version-controlled and diffed, never a string literal and never a dashboard textbox.

```
prompts/
├── grader/
│   ├── v1.4.0.md              # active; `prompt_ver` written to sessions.prompt_ver
│   ├── v1.3.0.md
│   └── residue_taxonomy.md    # included fragment: the five grader-only categories
└── coach/…
```

Assembly order — instructions early, the variable material late, per context-engineering discipline:

| Block | Content | Roughly |
|---|---|---|
| 1. Role | "You compare a known source utterance to a rendering produced by a human interpreter." | 40 tok |
| 2. Hard constraints | Output only the schema; quote real substrings; never assign severity; abstain rather than guess | 90 tok |
| 3. Residue taxonomy | Five grader-only categories, one definition + one worked example each; plus the non-quantitative omission/addition guidance | 480 tok |
| 4. Explicit exclusions | "Numbers, dosages, frequencies, negation, laterality and allergies are checked elsewhere. Do not report them." | 45 tok |
| 5. Turn data | `direction`, `speaker`, `source`, `rendering` — delimited, last | variable |

The exclusion block in position 4 is doing real work: without it the model spends most of its output re-detecting dosages, which the merge stage then has to discard (measured — the exclusion block cut duplicate quantitative findings substantially on DEV; the exact figure lives in the EV-01 report, not here, because it moves with the prompt version).

**Untrusted content [decided].** `source` and `rendering` are data, never instructions. They are wrapped in explicit delimiters, the constraint block states that text inside the delimiters is never an instruction, and — the actual defence — the output is a schema whose fields cannot express an instruction. A prompt injection in a rendering can at worst produce a finding with a silly note, which G3 (span verification) will usually drop anyway. This is boundary B3 in `docs/03-system-architecture.md` §12.

### 5.4 Decode configuration

| Parameter | Value | Reason |
|---|---|---|
| Model | Gemma 12B class, quantised, `rehearsal-grader` host | Sized for reasoning, off the critical path (principle 5) |
| `temperature` | `0.0` | The grader is an instrument. Reproducibility beats variety |
| `top_p` / `top_k` | unset / unset | Redundant at temperature 0; leaving them unset keeps the decode config a single line to reason about |
| `max_tokens` | `768` | Empirically above the p99 of valid outputs; a truncated JSON is a guard failure (G1), not a silent partial |
| Structured output | Constrained decoding to the JSON schema where the runtime supports it (MLX grammar constraint), free decode + validate on llama.cpp fallback | Constrained decoding removes the dominant retry cause. The fallback path must still validate — the guard is not optional just because the grammar usually works |
| Seed | Not passed | Temperature 0 is deterministic in both runtimes. If sampling is ever introduced, `docs/03-system-architecture.md` §6 requires re-calibration |
| Reads | `1` live, `2` in eval/replay/calibration mode | §8.4 |

### 5.5 The grader call's exact output schema

This is the model's schema, not the engine's. It is deliberately smaller and dumber than the `Verdict` schema in §7 — the model emits observations; code emits conclusions.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "rehearsal:grader-output/1.4.0",
  "title": "GraderOutput",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "abstain", "findings"],
  "properties": {
    "schema_version": { "const": "1.4.0" },

    "abstain": {
      "type": "boolean",
      "description": "True when the rendering cannot be meaningfully compared to the source (empty, unintelligible, wrong language, or apparently a different turn). When true, findings MUST be empty."
    },
    "abstain_reason": {
      "type": ["string", "null"],
      "enum": ["empty_rendering", "unintelligible", "wrong_language",
               "mismatched_content", "other", null]
    },

    "findings": {
      "type": "array",
      "maxItems": 12,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["kind", "rendering_quote", "source_quote", "note", "confidence"],
        "properties": {
          "kind": {
            "type": "string",
            "enum": ["omission", "addition", "substitution", "distortion",
                     "editorialization", "role_exchange", "register_shift",
                     "false_fluency", "first_person_violation"]
          },
          "rendering_quote": {
            "type": ["string", "null"],
            "maxLength": 240,
            "description": "EXACT substring of the rendering. null ONLY when kind == 'omission'."
          },
          "source_quote": {
            "type": ["string", "null"],
            "maxLength": 240,
            "description": "EXACT substring of the source. null ONLY when kind == 'addition'."
          },
          "note": {
            "type": "string",
            "maxLength": 200,
            "description": "One sentence: what changed and why it matters for meaning. No severity words, no advice."
          },
          "confidence": {
            "type": "string",
            "enum": ["high", "medium", "low"],
            "description": "How sure you are that a competent interpreter trainer would agree this is an error."
          }
        }
      }
    },

    "clean_reason": {
      "type": ["string", "null"],
      "maxLength": 200,
      "description": "When findings is empty and abstain is false: one sentence naming what was preserved. Forces a positive assertion rather than a silent empty array."
    }
  }
}
```

Three schema decisions worth defending:

- **`confidence` is an ordinal string, not a number.** A model asked for `0.0–1.0` produces `0.9` for everything. Three named buckets it can actually distinguish are more information than a float it cannot. Code maps the buckets to numbers in one place (§9.1) so the mapping is versioned and testable.
- **`severity` is absent from the schema entirely.** Not "ignored" — absent. The model cannot express it, so no prompt change can accidentally allow it.
- **`clean_reason` is required when clean.** An empty `findings` array with no assertion is indistinguishable from a lazy read. Requiring one sentence naming what survived measurably reduced misses on multi-error DEV items and gives the trainer something to disagree with.

### 5.6 Failure handling

| Failure | Response |
|---|---|
| Invalid JSON, or schema validation fails | **One** retry, temperature 0, with the validation error and the schema echoed in a minimal repair prompt. Second failure → `status = "grader_unavailable"` |
| Truncated at `max_tokens` | Treated as invalid JSON; same path |
| Grader host down / socket error | No retry storm. `status = "grader_unavailable"` immediately; the degradation ladder (`docs/03-system-architecture.md` §14, L2) shows the "critical checks only" banner |
| Grader exceeds `grader_wall_ms` | Cancelled. `status = "partial"`. The turn keeps its symbolic findings |
| `abstain = true` | Not a failure. `status = "complete"`, `abstained = true`, semantic categories reported as *not assessed* |

In every one of these paths, the symbolic findings survive and the verdict is honest about what was not assessed. **A degraded verdict never reports "no error found" for a category it did not examine.**

---

## 6. Merge — the deterministic combination

`src/rehearsal/scoring/merge.py`. This function is the only thing in Rehearsal that produces a score, and it contains no model call, no randomness, and no I/O.

```python
def merge_verdict(
    symbolic: ExtractorResult,
    semantic: GuardedGraderOutput | None,     # None => grader unavailable
    req: ScoreRequest,
    policy: MergePolicy,
) -> Verdict: ...
```

### 6.1 The nine steps

| # | Step | Rule |
|---|---|---|
| M1 | **Seed** | Start the finding set with every symbolic finding, unmodified. The symbolic set is never filtered by the semantic stage |
| M2 | **Admit** | Add guard-surviving semantic findings (§8) |
| M3 | **Category legality** | Drop any semantic finding whose `kind` is not in the taxonomy (counted, not coerced) |
| M4 | **Territory check** | If a semantic finding's `rendering_quote` or `source_quote` overlaps a span already covered by a symbolic finding in an `EXTRACTOR_OWNED` category → mark `overruled = true`, keep it in the record, exclude it from counts |
| M5 | **Territory check, clean case** | If a semantic finding overlaps a span the extractors *adjudicated and found clean* (i.e. the span belongs to a `covered_fact_id` with no finding) and the semantic `kind` is `EXTRACTOR_OWNED` → `overruled = true`. The extractor proved it; the model's contrary opinion is recorded as disagreement, not as a finding |
| M6 | **Dedup within origin** | Two semantic findings of the same `kind` with ≥ 60% span overlap collapse to one; the higher confidence survives and the notes concatenate |
| M7 | **Anchor** | For each surviving semantic finding, attempt to bind a `fact_id` by span overlap with a manifest fact's source span. Bound → `unanchored = false`. Unbound → `unanchored = true` (feeds S12) |
| M8 | **Severity** | Call `severity.assign_severity` on every finding in the set, in the S1…S13 order of §3.1. This is the only place severity is written |
| M9 | **Confidence & withholding** | Apply §9. Findings below the display threshold get `withheld = true` — they stay in the record and in the eval numbers, and are hidden from the trainee-facing view only |

M4 and M5 together are "the extractor wins on the critical categories" from `docs/03-system-architecture.md` §7, made precise. Note what they do **not** do: they never delete. The `findings` table keeps every overruled row, and `overrule_rate` broken out by category is a reported number in `docs/08-evals.md` §3 — it is how we find out whether the extractors are missing things the model can see.

### 6.2 Counts and status

```python
n_critical      = sum(1 for f in findings if f.severity == "critical" and not f.overruled)
n_non_critical  = sum(1 for f in findings if f.severity == "non_critical" and not f.overruled)
```

Withheld findings **are** counted in `n_*` and in every eval number. Withholding is a display decision, never a measurement decision — hiding a finding from the trainee and then also hiding it from the metric would be exactly the kind of quiet self-flattery principle 7 exists to prevent.

`Verdict.status`:

| `status` | Means | Semantic categories reported as |
|---|---|---|
| `complete` | Extractors ran, grader returned a guard-surviving result | assessed |
| `partial` | Extractors ran, grader timed out or was shed | **not assessed** |
| `grader_unavailable` | Extractors ran, grader host down or failed twice | **not assessed** |
| `manifest_desync` | A manifest fact disagreed with the parsed source (§2.2) | assessed, but the affected facts are excluded and named |
| `refused` | Preconditions failed (§8.5) | not assessed; nothing is charged to the trainee |

### 6.3 `MergePolicy`

Every tunable in one frozen dataclass, hashed into the eval report so no number is ever published without the policy that produced it.

```python
@dataclass(frozen=True, slots=True)
class MergePolicy:
    display_confidence_floor: float = 0.45          # §9.4
    dedup_overlap_ratio: float = 0.60               # M6
    frequency_underspecification_severity: Severity = "non_critical"  # F3
    range_for_point_severity: Severity = "non_critical"
    allow_unanchored_semantic: bool = True          # S12 findings shown at all
    reads: int = 1                                  # 2 in eval/replay mode
    unstable_finding_action: Literal["withhold", "drop", "show"] = "withhold"
    policy_ver: str = "merge-1.2.0"
```

Changing any field is a scoring-plane change: it triggers the regression eval (`docs/08-evals.md` §4.9) and requires re-running EV-01 on DEV, because it moves labels.

---

## 7. The complete verdict JSON schema

The engine's output, as persisted (`verdicts` + `findings` in `docs/03-system-architecture.md` §10.4) and as served by `GET /api/sessions/{id}/verdicts`.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "rehearsal:verdict/1.2.0",
  "title": "Verdict",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "schema_version", "verdict_key", "session_id", "turn_index",
    "direction", "speaker", "status", "source_sha", "rendering_sha",
    "provenance", "coverage", "counts", "findings", "timing"
  ],
  "properties": {
    "schema_version": { "const": "1.2.0" },
    "verdict_key": {
      "type": "string", "pattern": "^[0-9a-f]{64}$",
      "description": "sha256(prompt_ver|grader_model|source_sha|rendering_sha). Idempotency key."
    },
    "session_id": { "type": "string" },
    "turn_index": { "type": "integer", "minimum": 0 },
    "direction":  { "enum": ["en->es", "es->en"] },
    "speaker":    { "enum": ["clinician", "patient"] },

    "status": {
      "enum": ["complete", "partial", "grader_unavailable",
               "manifest_desync", "refused"]
    },
    "refusal_reason": {
      "type": ["string", "null"],
      "enum": ["empty_rendering", "rendering_too_short", "wrong_language",
               "source_truncated_unusable", "manifest_missing", null]
    },
    "abstained": { "type": "boolean", "default": false },
    "abstain_reason": { "type": ["string", "null"] },

    "source_sha":    { "type": "string", "pattern": "^[0-9a-f]{64}$" },
    "rendering_sha": { "type": ["string", "null"], "pattern": "^[0-9a-f]{64}$" },
    "rendering_src": { "enum": ["live_verbatim", "offpath_retranscribe"] },
    "source_partial": { "type": "boolean" },

    "provenance": {
      "type": "object",
      "additionalProperties": false,
      "required": ["grader_model", "prompt_ver", "policy_ver",
                   "extractor_ver", "taxonomy_ver", "reads", "temperature"],
      "properties": {
        "grader_model":  { "type": "string", "examples": ["gemma-12b-it-q4_K_M"] },
        "prompt_ver":    { "type": "string", "examples": ["grader-1.4.0"] },
        "policy_ver":    { "type": "string", "examples": ["merge-1.2.0"] },
        "extractor_ver": { "type": "string", "examples": ["extractors-2.1.0"] },
        "taxonomy_ver":  { "type": "string", "examples": ["taxonomy-1.0.0"] },
        "runtime":       { "enum": ["mlx", "llamacpp"] },
        "reads":         { "type": "integer", "enum": [1, 2] },
        "temperature":   { "type": "number", "const": 0.0 }
      }
    },

    "coverage": {
      "type": "object",
      "description": "Principle 7 made structural: what was checked, what was not, never conflated.",
      "additionalProperties": false,
      "required": ["symbolic_assessed", "semantic_assessed",
                   "facts_required", "facts_adjudicated", "facts_not_assessed"],
      "properties": {
        "symbolic_assessed": { "type": "boolean" },
        "semantic_assessed": { "type": "boolean" },
        "facts_required":    { "type": "integer", "minimum": 0 },
        "facts_adjudicated": { "type": "integer", "minimum": 0 },
        "facts_not_assessed": {
          "type": "array",
          "items": {
            "type": "object", "additionalProperties": false,
            "required": ["fact_id", "reason"],
            "properties": {
              "fact_id": { "type": "string" },
              "reason": {
                "enum": ["manifest_desync", "extractor_refused",
                         "ambiguous_scope", "unsupported_pattern"]
              }
            }
          }
        },
        "categories_not_assessed": {
          "type": "array",
          "items": { "type": "string" },
          "description": "Taxonomy categories with NO verdict this turn. Rendered as 'not checked', never as 'clean'."
        }
      }
    },

    "counts": {
      "type": "object",
      "additionalProperties": false,
      "required": ["critical", "non_critical", "withheld", "overruled"],
      "properties": {
        "critical":     { "type": "integer", "minimum": 0 },
        "non_critical": { "type": "integer", "minimum": 0 },
        "withheld":     { "type": "integer", "minimum": 0 },
        "overruled":    { "type": "integer", "minimum": 0 },
        "by_kind": {
          "type": "object",
          "additionalProperties": { "type": "integer", "minimum": 0 }
        }
      }
    },

    "findings": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["finding_uid", "kind", "severity", "origin", "note",
                     "rendering_span", "source_span", "display"],
        "properties": {
          "finding_uid": {
            "type": "string",
            "description": "sha256(verdict_key|kind|origin|span|source_span)[:16]. Stable across re-reads so a trainer review binds to a finding, not a row id."
          },
          "kind": {
            "enum": ["omission", "addition", "substitution", "distortion",
                     "editorialization", "role_exchange", "register_shift",
                     "false_fluency", "first_person_violation"]
          },
          "severity": { "enum": ["critical", "non_critical"] },
          "severity_rule": {
            "type": ["string", "null"],
            "description": "Which rule in docs/06-scoring-engine.md §3.1 fired. e.g. 'S4'.",
            "pattern": "^S([1-9]|1[0-3])$"
          },
          "origin": { "enum": ["extractor", "grader"] },
          "extractor_name": {
            "type": ["string", "null"],
            "enum": ["entities", "numbers", "dosage", "frequency", "temporal",
                     "negation", "laterality", "allergy", null]
          },
          "fact_id":    { "type": ["string", "null"] },
          "unanchored": { "type": "boolean", "default": false },

          "rendering_span": {
            "type": ["array", "null"],
            "items": { "type": "integer", "minimum": 0 },
            "minItems": 2, "maxItems": 2,
            "description": "Half-open [start, end) char offsets into the ORIGINAL rendering. null for omissions."
          },
          "source_span": {
            "type": ["array", "null"],
            "items": { "type": "integer", "minimum": 0 },
            "minItems": 2, "maxItems": 2
          },
          "rendering_quote": { "type": ["string", "null"] },
          "source_quote":    { "type": ["string", "null"] },

          "expected": {
            "type": ["string", "null"],
            "description": "Extractor findings only: the canonical value the manifest required, rendered for a human. e.g. '3/day (interval 8 h)'."
          },
          "observed": {
            "type": ["string", "null"],
            "description": "Extractor findings only: the canonical value parsed from the rendering. null = absent."
          },

          "note": { "type": "string", "maxLength": 240 },

          "confidence": {
            "type": ["number", "null"],
            "minimum": 0, "maximum": 1,
            "description": "null for extractor findings — they are proofs, not estimates."
          },
          "confidence_band": { "enum": ["proof", "high", "medium", "low"] },
          "stability": {
            "type": ["string", "null"],
            "enum": ["stable", "unstable", "single_read", null]
          },

          "display": {
            "type": "object",
            "additionalProperties": false,
            "required": ["shown_to_trainee", "flag"],
            "properties": {
              "shown_to_trainee": { "type": "boolean" },
              "withheld_reason": {
                "type": ["string", "null"],
                "enum": ["below_confidence_floor", "unstable_across_reads",
                         "overruled", "span_unverified", null]
              },
              "flag": { "enum": ["none", "uncertain", "needs_human"] }
            }
          },
          "overruled": { "type": "boolean", "default": false },
          "overruled_by": { "type": ["string", "null"] }
        }
      }
    },

    "guard_report": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "schema_retries":        { "type": "integer", "minimum": 0, "maximum": 1 },
        "dropped_unknown_kind":  { "type": "integer", "minimum": 0 },
        "dropped_span_unverified": { "type": "integer", "minimum": 0 },
        "dropped_illegal_null":  { "type": "integer", "minimum": 0 },
        "quotes_repaired_ws":    { "type": "integer", "minimum": 0 },
        "unstable_findings":     { "type": "integer", "minimum": 0 }
      }
    },

    "timing": {
      "type": "object",
      "additionalProperties": false,
      "required": ["extractor_ms", "total_ms"],
      "properties": {
        "extractor_ms": { "type": "integer", "minimum": 0 },
        "grader_ms":    { "type": ["integer", "null"], "minimum": 0 },
        "merge_ms":     { "type": "integer", "minimum": 0 },
        "total_ms":     { "type": "integer", "minimum": 0 },
        "created_ms":   { "type": "integer" }
      }
    }
  }
}
```

The schema is versioned and lives at `schemas/verdict-1.2.0.json`. `pytest` validates every fixture verdict against it, and `rehearsal replay --verify` validates every historical verdict on read — a schema change that would orphan old data fails loudly at the point of change rather than quietly at the point of reading.

---

## 8. Guards

Guards sit between the model and anything that counts. They are pure functions over the grader output plus the two strings; none of them calls a model, and none of them can be disabled by configuration.

`src/rehearsal/scoring/guards.py`

```python
def guard(raw: str, req: ScoreRequest, cfg: ScoringConfig) -> GuardedGraderOutput:
    """Parse, validate and verify a raw grader response. Never raises for
    model misbehaviour; returns a GuardedGraderOutput with a populated
    GuardReport describing exactly what was dropped and why."""
```

### 8.1 G1 — schema validation

`jsonschema` Draft 2020-12 against `rehearsal:grader-output/1.4.0`, `additionalProperties: false` everywhere. One repair retry (§5.6), then give up. Extra fields are a rejection, not a warning: a model that invented a field has departed from the contract, and quietly ignoring it means a later prompt version can start depending on a field nobody specified.

### 8.2 G2 — structural legality

Checks the schema cannot express:

| Check | Failure action |
|---|---|
| `abstain == true` ⟹ `findings == []` | Drop all findings; keep the abstention |
| `kind == "omission"` ⟹ `source_quote is not null` | Drop the finding (`dropped_illegal_null`) |
| `kind == "addition"` ⟹ `rendering_quote is not null` | Drop the finding |
| Any kind other than `omission` ⟹ `rendering_quote is not null` | Drop the finding |
| `findings == []` and `abstain == false` ⟹ `clean_reason` non-empty | Keep the clean verdict; count `clean_reason_missing` |
| `kind` in the taxonomy | Drop, count `dropped_unknown_kind` |

### 8.3 G3 — span verification (the important one)

**Every finding must quote real text.** This is the guard that makes the whole "compare, don't judge" framing pay off.

```python
def verify_quote(quote: str, haystack: str) -> tuple[int, int] | None:
    """Return half-open offsets into `haystack`, or None. Verification ladder:
       1. exact `haystack.find(quote)`
       2. whitespace-normalised match (collapse runs, strip) -> map back via offsets
       3. NFC + casefold match -> map back
       4. give up
    Ambiguity: if the quote occurs more than once, take the occurrence nearest
    the previously anchored finding's span; if there is none, take the first,
    and set `span_ambiguous` in the note."""
```

| Ladder rung | Permitted because | Counted as |
|---|---|---|
| 1. Exact | — | clean |
| 2. Whitespace-normalised | Models routinely re-space quotes; the words are unchanged | `quotes_repaired_ws` |
| 3. NFC + casefold | Diacritic composition and capitalisation differ between the model's copy and the stored string; the graphemes are unchanged | `quotes_repaired_ws` |
| 4. Fail | The model produced text that is not in the document | `dropped_span_unverified` — **the finding is dropped** |

Rung 4 is not negotiable and there is no fuzzy rung 3.5. A finding whose quote is not in the rendering is, definitionally, a hallucinated finding, and the correct thing to do with it is delete it and count it. `dropped_span_unverified` per 100 findings is a reported number in `docs/08-evals.md` — it is our direct measurement of grader fabrication rate, and it exists only because we required quotes.

Symbolic findings skip G3: their spans come from the parser, not from a model. A separate assertion (`assert rendering[a:b] == parsed_surface`) covers them, and it is an `assert`, because a mismatch there is a code bug.

### 8.4 G4 — self-consistency across repeated reads

| Mode | `reads` | Behaviour |
|---|---|---|
| Live session | 1 | `stability = "single_read"` on every semantic finding. The turn budget (`docs/03-system-architecture.md` §6, ~3.5 s of slack) does not fit two 2–3 s calls, and stalling the loop to be more certain is the wrong trade for formative practice |
| Eval, replay, calibration | 2 | Two reads, then agreement analysis |

At temperature 0 a literally identical prompt gives a literally identical answer, so a second identical read measures nothing. The two reads therefore use **presentation variants** of the same prompt file:

- Read A: source block first, rendering block second.
- Read B: rendering block first, source block second, and the residue taxonomy list in reversed order.

Both variants are in the same versioned prompt file (`prompts/grader/v1.4.0.md`, `## variant_a` / `## variant_b`) and both are diffed together.

Agreement rule: two findings match if `kind` is equal and their verified rendering spans overlap by ≥ 50%.

| Outcome | `stability` | Action |
|---|---|---|
| In both reads | `stable` | Confidence ×1.0 |
| In one read only | `unstable` | Confidence ×0.6, then `MergePolicy.unstable_finding_action` (default `withhold`) |
| Reads disagree on `abstain` | — | Treat as non-abstained; both reads' findings admitted; `unstable_findings` incremented |

The read-A/read-B disagreement rate is itself reported: it is an honest, cheap estimate of how much of the grader's semantic output is an artefact of presentation order rather than of the rendering. Because live sessions run `reads = 1`, that number is a **property of the instrument measured offline**, and the reports say so rather than implying live findings were double-checked.

### 8.5 G5 — refusal to conclude

Preconditions checked **before** any work (stage 0), and refusal conditions raised by extractors mid-run. In all of them the engine declines to produce a score rather than producing a bad one.

| Condition | Detection | Result |
|---|---|---|
| Empty rendering | `rendering.strip() == ""` | `status = "refused"`, `refusal_reason = "empty_rendering"`. **Not** scored as total omission — a trainee who said nothing may have had a microphone failure, and charging them nine omissions for a hardware fault is a lie |
| Rendering < 3 tokens against a source > 15 tokens | token counts | `refused`, `rendering_too_short`; flagged `needs_human` |
| Rendering is in the **source** language | Character/stopword profile over closed function-word lists (both languages), threshold 0.75 | `refused`, `wrong_language`. This catches the trainee repeating instead of interpreting, which is a real training event but not a *fidelity* measurement |
| Source truncated by barge-in below 40% of the node's scripted length | `req.partial` + length ratio | `refused`, `source_truncated_unusable`. See `docs/03-system-architecture.md` §16 Q2 — partial-source scoring is a live open question, and this is the conservative side of it |
| Manifest slice empty or missing | `req.manifest` | `refused`, `manifest_missing`. A content-plane bug |
| Negation scope ambiguous (§4.7) | Extractor | Fact excluded from `facts_adjudicated`, listed in `coverage.facts_not_assessed` with `ambiguous_scope`, turn flagged `needs_human`. The rest of the turn still scores |
| Manifest/source disagreement | §2.2 | `status = "manifest_desync"`; affected facts excluded and named |

**A refused turn is never counted as a clean turn and never counted as an error turn.** It is excluded from the denominator of every trainee-facing rate and reported as its own count. The `refused` and `needs_human` rates are session-level numbers the trainer sees (`docs/09-ui-ux.md`) — an instrument that quietly refuses 30% of turns and reports a beautiful score on the rest is worse than no instrument.

### 8.6 Guard summary

| Guard | Protects against | Failure is | Reported as |
|---|---|---|---|
| G1 schema | Malformed / free-text output | Recoverable once, then degraded status | `schema_retries` |
| G2 structural | Internally inconsistent findings | Per-finding drop | `dropped_illegal_null`, `dropped_unknown_kind` |
| G3 span | **Fabricated quotes** | Per-finding drop | `dropped_span_unverified` |
| G4 consistency | Presentation-order artefacts | Confidence penalty + withhold | `unstable_findings` |
| G5 refusal | Scoring the unscoreable | Whole-turn refusal | `refusal_reason`, session-level refusal rate |

None of the five can be turned off by config. They are the difference between a model's opinion and an instrument's reading.

---

## 9. The confidence model

### 9.1 Where confidence comes from

| Origin | Source of confidence | Value |
|---|---|---|
| Extractor | Nothing. It is a proof | `confidence = null`, `confidence_band = "proof"` |
| Grader | Ordinal bucket from the model, adjusted deterministically | `0.0–1.0` float |

```python
# src/rehearsal/scoring/confidence.py

BAND_BASE: dict[str, float] = {"high": 0.85, "medium": 0.60, "low": 0.35}

STABILITY_FACTOR: dict[str, float] = {
    "stable": 1.00, "single_read": 0.90, "unstable": 0.60,
}

KIND_PRIOR: dict[ErrorKind, float] = {
    # Calibrated on the DEV split only; TEST never informs these.
    "first_person_violation": 1.00,   # syntactically overt, model is reliable
    "role_exchange":          0.95,
    "editorialization":       0.90,
    "false_fluency":          0.80,
    "register_shift":         0.70,   # the most subjective category on DEV
    "omission":               0.85,   # grader-origin, non-quantitative only
    "addition":               0.85,
    "substitution":           0.80,
    "distortion":             0.75,
}

def score_confidence(f: Finding, guard: GuardReport) -> float:
    c = BAND_BASE[f.band] * STABILITY_FACTOR[f.stability] * KIND_PRIOR[f.kind]
    if f.unanchored:
        c *= 0.85                      # real signal, unprovable
    if f.quote_repaired:
        c *= 0.95                      # quote needed normalisation to verify
    return round(min(c, 0.95), 3)      # never 1.0 — see below
```

**No grader finding is ever assigned confidence 1.0.** The ceiling is 0.95. Certainty in this system is spelled `confidence = null, band = "proof"`, and only a deterministic extractor can produce it. Letting a model reach 1.0 would make a guess indistinguishable from a proof in any downstream sort, filter or average.

`KIND_PRIOR` is derived from per-category precision on the **DEV** split and is re-derived whenever the prompt version changes. It is a table in a versioned file, not a magic number in an expression, and `policy_ver` covers it. The TEST split never touches it (`docs/08-evals.md` §5).

### 9.2 What confidence is *not*

- Not a probability of an error existing. It is a monotone ordering signal calibrated on 25 DEV items — far too few to claim probabilistic meaning. `docs/08-evals.md` reports it as a ranking, never as a calibrated probability, and no reliability diagram is published off n=25.
- Not an input to severity. Severity is structural (§3.1). A low-confidence finding on an allergy fact cannot exist, because allergy findings are extractor-origin and have no confidence at all.
- Not aggregated into a turn-level or session-level "confidence score". Averaging confidences across findings produces a number with no referent.

### 9.3 Bands as displayed

| Band | Range | UI treatment (`docs/09-ui-ux.md`) |
|---|---|---|
| `proof` | n/a | Full weight. Shows `expected` vs `observed`. No hedging language |
| `high` | ≥ 0.70 | Shown normally |
| `medium` | 0.45 – 0.70 | Shown with an "uncertain" marker — an icon **and** a text label, never colour alone (WCAG, and colour alone would be meaningless to the trainer reviewing a printout) |
| `low` | < 0.45 | Withheld from the trainee view; visible in the trainer review view; always in the record |

### 9.4 Withholding rules

A finding is `withheld` (recorded, counted in metrics, hidden from the trainee-facing view) when **any** of:

| # | Condition | `withheld_reason` |
|---|---|---|
| W1 | `confidence < policy.display_confidence_floor` (0.45) | `below_confidence_floor` |
| W2 | `stability == "unstable"` and `policy.unstable_finding_action == "withhold"` | `unstable_across_reads` |
| W3 | `overruled == true` (M4/M5) | `overruled` |
| W4 | Quote verification needed rung 3 **and** confidence band is `low` | `span_unverified` |

A finding is **never** withheld when `origin == "extractor"`. Proofs are always shown.

A finding is flagged `needs_human` (shown, prominently, with an explicit "this needs a person" affordance) when:

- The turn carries an extractor refusal (`ambiguous_scope`), or
- A grader finding in an `EXTRACTOR_OWNED` category was **not** overruled and is `unanchored` and `confidence ≥ 0.70` — the model confidently saw something the manifest does not model. That is either a manifest gap or a genuine miss, and both want a person, not a rule.

### 9.5 The relationship to the human gate

Nothing here decides anything about the trainee. Confidence governs **display prominence** only. The trainer's review actions (`agree` / `reject` / `reclassify` / `add`) are appended to `reviews` and never mutate `findings` (`docs/03-system-architecture.md` §10.4), which is what makes trainer-override rate measurable — and trainer-override rate broken down by confidence band is the only honest calibration evidence this engine will ever have.

---

## 10. Worked examples

Five turns, end to end. Each shows the source, the manifest facts it was built from, the rendering, what each stage produced, and the merged output. These are the shape of `data/fixtures/scoring/*.json`; the calibration items in `SETUP.md` §6 have the same shape with a human label attached.

Verdict JSON is shown with `provenance`, `timing` and unchanged boilerplate elided as `…` for readability; the fixtures carry the full documents.

---

### 10.1 Example 1 — dosage and frequency dropped (two criticals)

**Direction** `en->es` · **Speaker** clinician

| | |
|---|---|
| **Source** | `Take one tablet of metformin, five hundred milligrams, twice a day with food.` |
| **Rendering** | `Tome una pastilla de metformina con la comida.` |

**Manifest slice**

| fact_id | kind | value | role | required |
|---|---|---|---|---|
| `q.dose.metformin` | quantity | `500 mg` | `dose` | ✔ |
| `q.count.tablet` | quantity | `1 tablet` | `dose` | ✔ |
| `f.metformin` | frequency | `per_day=2` | — | ✔ |
| `e.med.metformin` | entity | `metformin` / `metformina` | — | ✔ |

**Stage A — symbolic**

| Extractor | Source parse | Rendering parse | Finding |
|---|---|---|---|
| `entities` | `metformin` @ [19,28] | `metformina` @ [22,32] | — (match) |
| `numbers` | `500` (written, `five hundred`) @ [30,42]; `1` (`one`) @ [5,8] | `1` (`una`) @ [5,8] | — (handled by `dosage`) |
| `dosage` | `Dose(500, mg, mass)`; `Dose(1, None, tablet)` | `Dose(1, None, pastilla→tablet)` | `omission` of `q.dose.metformin` |
| `frequency` | `Frequency(per_day=2)` @ [58,69] | none | F2 → `omission` of `f.metformin` |
| `temporal`, `negation`, `laterality`, `allergy` | — | — | — |

Severity: `q.dose.metformin` has `role = dose` → **S3 critical**. `f.metformin` → **S4 critical**.

**Stage B — semantic.** The grader returns `findings: []`, `clean_reason: "The instruction to take the tablet with food and the medication name are both preserved; register is appropriate for a patient."` — correct behaviour: the quantitative material is explicitly excluded from its scope (prompt block 4), and it correctly declines to invent a register complaint. Note that it does **not** know about the two omissions, and that independence is deliberate (§5.2).

**Merged**

```json
{
  "schema_version": "1.2.0",
  "verdict_key": "3f9c…", "session_id": "s_01H…", "turn_index": 4,
  "direction": "en->es", "speaker": "clinician",
  "status": "complete", "abstained": false,
  "coverage": {
    "symbolic_assessed": true, "semantic_assessed": true,
    "facts_required": 4, "facts_adjudicated": 4,
    "facts_not_assessed": [], "categories_not_assessed": []
  },
  "counts": {
    "critical": 2, "non_critical": 0, "withheld": 0, "overruled": 0,
    "by_kind": { "omission": 2 }
  },
  "findings": [
    {
      "finding_uid": "a41c9de20b7f8c15",
      "kind": "omission", "severity": "critical", "severity_rule": "S3",
      "origin": "extractor", "extractor_name": "dosage",
      "fact_id": "q.dose.metformin", "unanchored": false,
      "rendering_span": null,
      "source_span": [30, 52], "source_quote": "five hundred milligrams",
      "rendering_quote": null,
      "expected": "500 mg", "observed": null,
      "note": "The strength (500 mg) is absent from the rendering.",
      "confidence": null, "confidence_band": "proof", "stability": null,
      "display": { "shown_to_trainee": true, "withheld_reason": null, "flag": "none" },
      "overruled": false
    },
    {
      "finding_uid": "77b0e5c9a1d43e02",
      "kind": "omission", "severity": "critical", "severity_rule": "S4",
      "origin": "extractor", "extractor_name": "frequency",
      "fact_id": "f.metformin", "unanchored": false,
      "rendering_span": null,
      "source_span": [58, 69], "source_quote": "twice a day",
      "rendering_quote": null,
      "expected": "2/day", "observed": null,
      "note": "No dosing frequency appears in the rendering.",
      "confidence": null, "confidence_band": "proof", "stability": null,
      "display": { "shown_to_trainee": true, "withheld_reason": null, "flag": "none" },
      "overruled": false
    }
  ],
  "guard_report": { "schema_retries": 0, "dropped_unknown_kind": 0,
                    "dropped_span_unverified": 0, "dropped_illegal_null": 0,
                    "quotes_repaired_ws": 0, "unstable_findings": 0 },
  "timing": { "extractor_ms": 21, "grader_ms": 2380, "merge_ms": 2, "total_ms": 2409, "…": "…" }
}
```

**Why this is the canonical case.** Two criticals, both proofs, both traceable to a manifest fact and a line of code. No model was involved in either. If the grader host had been dead, this verdict would be identical except `status = "partial"` and `semantic_assessed = false`.

---

### 10.2 Example 2 — negation flip (the highest-consequence error class)

**Direction** `es->en` · **Speaker** patient

| | |
|---|---|
| **Source** | `No he tomado la medicina desde el martes porque me daba náuseas.` |
| **Rendering** | `I have been taking the medicine since Tuesday because it was making me nauseous.` |

**Manifest slice**

| fact_id | kind | value | required |
|---|---|---|---|
| `n.adherence` | negation | target `tomar/take`, polarity `negated` | ✔ |
| `d.since_tuesday` | duration | `deictic_day`, `tuesday`, `past` | ✔ |
| `e.med.generic` | entity | `medicina` / `medicine` | ✔ |

**Stage A — symbolic**

| Extractor | Result |
|---|---|
| `negation` | Source: cue `no` @ [0,2], scope window covers `he tomado la medicina` → target `tomado` is **negated**. Rendering: no cue in scope of `taking` → **affirmed**. Polarity mismatch → `distortion` |
| `temporal` | Source `desde el martes` → `deictic_day/tuesday/past`; rendering `since Tuesday` → same. Match, no finding |
| `entities` | `medicina` ↔ `medicine`, match |

Severity: negation polarity flip on a required fact → **S2 critical**.

Note what the scope algorithm had to get right: `porque` is not a scope terminator in the cue lexicon, but the target `tomado` is reached before it, and the 8-token window closes before `náuseas` — so the nausea clause is not swept into the negation. The fixture grid for `negation.py` carries this exact sentence.

**Stage B — semantic.** One finding:

```json
{ "kind": "distortion",
  "rendering_quote": "I have been taking the medicine",
  "source_quote": "No he tomado la medicina",
  "note": "The rendering states the patient has been taking the medicine; the source states they have not.",
  "confidence": "high" }
```

This is a **correct** grader finding in extractor territory. Merge step M4: its rendering span overlaps the symbolic distortion's span, and `distortion` is `EXTRACTOR_OWNED` → `overruled = true`, kept in the record, excluded from counts. The trainee sees one critical finding, not two identical ones, and the agreement between the two independent stages is preserved as data (`overrule_rate` in `docs/08-evals.md` §3). This is the deduplication case, and it is *good news* — the two halves of the engine agreeing on a negation flip is exactly what we want to be able to observe.

**Merged (findings array only)**

```json
[
  {
    "finding_uid": "c02b8f4471ea9d36",
    "kind": "distortion", "severity": "critical", "severity_rule": "S2",
    "origin": "extractor", "extractor_name": "negation",
    "fact_id": "n.adherence", "unanchored": false,
    "rendering_span": [0, 31], "rendering_quote": "I have been taking the medicine",
    "source_span": [0, 24],   "source_quote": "No he tomado la medicina",
    "expected": "negated", "observed": "affirmed",
    "note": "Negation lost: the source denies taking the medicine, the rendering asserts it.",
    "confidence": null, "confidence_band": "proof", "stability": null,
    "display": { "shown_to_trainee": true, "withheld_reason": null, "flag": "none" },
    "overruled": false
  },
  {
    "finding_uid": "9d18a70c3b52ff44",
    "kind": "distortion", "severity": "non_critical", "severity_rule": "S12",
    "origin": "grader", "extractor_name": null,
    "fact_id": "n.adherence", "unanchored": false,
    "rendering_span": [0, 31], "rendering_quote": "I have been taking the medicine",
    "source_span": [0, 24],   "source_quote": "No he tomado la medicina",
    "note": "The rendering states the patient has been taking the medicine; the source states they have not.",
    "confidence": 0.638, "confidence_band": "medium", "stability": "single_read",
    "display": { "shown_to_trainee": false, "withheld_reason": "overruled", "flag": "none" },
    "overruled": true, "overruled_by": "c02b8f4471ea9d36"
  }
]
```

`counts`: `critical: 1, non_critical: 0, withheld: 1, overruled: 1`.

---

### 10.3 Example 3 — the semantic residue, with no symbolic finding at all

**Direction** `es->en` · **Speaker** patient

| | |
|---|---|
| **Source** | `Me duele mucho aquí, como si me clavaran algo. Ya no aguanto más.` |
| **Rendering** | `She says she has some pain in that area. She's probably exaggerating a bit — these patients often do.` |

**Manifest slice**: one entity (`e.site.abdomen`, not named explicitly in the source — the patient says `aquí`, "here", pointing), no quantities, no frequencies, no negation facts marked required (`ya no aguanto` is intensity, not a clinical polarity fact).

**Stage A — symbolic.** No findings. `covered_fact_ids` is empty of required facts beyond the entity, which is not asserted in either string (`aquí` / `that area`) — so `entities` reports it `not_assessed` with reason `unsupported_pattern` rather than pretending it checked. This is I3 in action: **the symbolic stage returning nothing here is not a claim that the turn was clean.**

**Stage B — semantic.** Four findings, all in grader-only territory:

```json
{ "abstain": false,
  "findings": [
    { "kind": "first_person_violation",
      "rendering_quote": "She says she has some pain",
      "source_quote": "Me duele mucho aquí",
      "note": "Rendered in the third person; the standard requires first-person interpreting.",
      "confidence": "high" },
    { "kind": "editorialization",
      "rendering_quote": "She's probably exaggerating a bit",
      "source_quote": null,
      "note": "Interpreter offers an assessment of the patient's credibility that is not in the source.",
      "confidence": "high" },
    { "kind": "role_exchange",
      "rendering_quote": "these patients often do",
      "source_quote": null,
      "note": "Interpreter addresses the clinician in their own voice about the patient population.",
      "confidence": "high" },
    { "kind": "omission",
      "rendering_quote": null,
      "source_quote": "como si me clavaran algo",
      "note": "The simile describing the pain as stabbing is dropped; the quality of the pain is lost.",
      "confidence": "medium" },
    { "kind": "distortion",
      "rendering_quote": "some pain",
      "source_quote": "Me duele mucho",
      "note": "Intensity is reduced from 'mucho' to 'some'.",
      "confidence": "high" }
  ],
  "clean_reason": null }
```

**Guards.** G3 verifies all five quotes — `"She's probably exaggerating a bit"` matches at rung 1; the apostrophe is U+2019 in the rendering and the model returned U+0027, so it actually matches at rung 3 (NFC + casefold does not fix that — **so it does not match, and it is dropped**).

That is the honest outcome and it is worth showing rather than hiding: our verification ladder does not normalise typographic apostrophes, so a model that "helpfully" straightens quotes loses a true finding. This was found on the DEV split. The fix is a rung 2.5 (Unicode punctuation folding: `’→'`, `“”→"`, `–—→-`) and it is **[decided, pending implementation]** — tracked in §16 Q4. For the purposes of this worked example the ladder is shown as specified today, with the drop counted:

`guard_report.dropped_span_unverified: 1`.

**Merged.** Four surviving findings, all `origin: "grader"`.

| kind | severity | rule | confidence | band | shown |
|---|---|---|---|---|---|
| `first_person_violation` | `non_critical` | S11 | 0.85 × 0.90 × 1.00 = **0.765** | high | ✔ |
| `role_exchange` | `non_critical` | S11 | 0.85 × 0.90 × 0.95 = **0.727** | high | ✔ |
| `omission` (`clavaran`) | `non_critical` | S12 (`unanchored`) | 0.60 × 0.90 × 0.85 × 0.85 = **0.390** | low | ✘ withheld, `below_confidence_floor` |
| `distortion` (intensity) | `non_critical` | S12 (`unanchored`) | 0.85 × 0.90 × 0.75 × 0.85 = **0.488** | medium | ✔ with `uncertain` marker |

`counts`: `critical: 0, non_critical: 4, withheld: 1, overruled: 0`, plus `dropped_span_unverified: 1` in the guard report.

**Read this turn honestly.** Every category here is `non_critical` by S11/S12 — and yet a working interpreter trainer would call this the worst rendering in this document. That is a real, named limitation of the severity model (§15, L3): **severity tracks clinical consequence, not professional seriousness.** The UI addresses it by showing role and first-person violations in a separate "professional conduct" group rather than burying them under a `non_critical` count (`docs/09-ui-ux.md`), and the trainer's `reclassify` action exists precisely for this. We do not paper over it by letting the grader mint criticals.

---

### 10.4 Example 4 — clean turn with a legitimate frequency reformulation (false-alarm control)

**Direction** `en->es` · **Speaker** clinician

| | |
|---|---|
| **Source** | `Take the amoxicillin every eight hours for ten days, and don't stop early even if you feel better.` |
| **Rendering** | `Tome la amoxicilina tres veces al día durante diez días, y no la deje antes de tiempo aunque se sienta mejor.` |

**Manifest slice**

| fact_id | kind | value | role | required |
|---|---|---|---|---|
| `f.amox` | frequency | `per_day=3, interval_hours=8` | — | ✔ |
| `d.course` | duration | `240 h` (`ten days`) | `treatment_course` | ✔ |
| `n.dont_stop` | negation | target `stop/dejar`, polarity `negated` | ✔ |
| `e.med.amoxicillin` | entity | `amoxicillin` / `amoxicilina` | — | ✔ |

**Stage A — symbolic**

| Extractor | Source | Rendering | Comparison |
|---|---|---|---|
| `frequency` | `per_day=3, interval_hours=8` | `tres veces al día` → `per_day=3, interval_hours=None` | **F3** — per-day equal, interval lost → `distortion`, non-critical (S8) |
| `temporal` | `ten days` → 240 h, role `treatment_course` | `diez días` → 240 h | match |
| `negation` | cue `don't` scoping `stop` → negated | cue `no` scoping `deje` → negated. Note `aunque` is a scope terminator, correctly excluding `se sienta mejor` | match |
| `entities` | `amoxicillin` | `amoxicilina` (cognate pair) | match |
| `numbers` | `8`, `10` | `3`, `10` | subsumed by `frequency` / `temporal` |

**Stage B — semantic.** `findings: []`, `clean_reason: "Register is appropriate (usted), the instruction and its rationale are both preserved, and the rendering stays in first person."`

**Merged**

```json
{
  "status": "complete", "abstained": false,
  "coverage": { "symbolic_assessed": true, "semantic_assessed": true,
                "facts_required": 4, "facts_adjudicated": 4,
                "facts_not_assessed": [], "categories_not_assessed": [] },
  "counts": { "critical": 0, "non_critical": 1, "withheld": 0, "overruled": 0,
              "by_kind": { "distortion": 1 } },
  "findings": [
    {
      "finding_uid": "5ae3117cbd809a26",
      "kind": "distortion", "severity": "non_critical", "severity_rule": "S8",
      "origin": "extractor", "extractor_name": "frequency",
      "fact_id": "f.amox", "unanchored": false,
      "rendering_span": [20, 37], "rendering_quote": "tres veces al día",
      "source_span": [24, 41],   "source_quote": "every eight hours",
      "expected": "3/day (interval 8 h)", "observed": "3/day (interval not stated)",
      "note": "Doses per day preserved; the eight-hour interval is not stated. 'Every 8 hours' is around the clock; 'three times a day' usually is not.",
      "confidence": null, "confidence_band": "proof", "stability": null,
      "display": { "shown_to_trainee": true, "withheld_reason": null, "flag": "none" },
      "overruled": false
    }
  ]
}
```

**Why this example exists.** It is the false-alarm control case, and it exercises four things at once: the F3 rule that keeps a defensible reformulation out of the critical bucket; the `aunque` scope terminator that stops a spurious negation finding; cognate entity matching; and a grader that correctly reports clean rather than manufacturing a register complaint to justify its call. `fp_rate_clean` in `docs/08-evals.md` §2 is the measurement that keeps this behaviour honest — an engine that never says "clean" is useless in training, because the trainee stops reading it.

---

### 10.5 Example 5 — allergy substitution + laterality flip (two criticals, one grader overrule, one refusal)

**Direction** `en->es` · **Speaker** clinician

| | |
|---|---|
| **Source** | `You're allergic to penicillin, so we'll use azithromycin instead. We also need an X-ray of your left knee.` |
| **Rendering** | `Usted es alérgico a la aspirina, entonces vamos a usar azitromicina. Y también necesitamos una radiografía de la rodilla derecha.` |

**Manifest slice**

| fact_id | kind | value | required |
|---|---|---|---|
| `a.penicillin` | allergy | allergen `e.med.penicillin`, polarity `allergic` | ✔ |
| `e.med.penicillin` | entity | `penicillin` / `penicilina` | ✔ |
| `e.med.azithromycin` | entity | `azithromycin` / `azitromicina` | ✔ |
| `e.med.aspirin` | entity | `aspirin` / `aspirina` (distractor in this scenario's bank) | ✘ |
| `e.site.knee` | entity | `knee` / `rodilla` | ✔ |
| `l.knee` | laterality | `left`, site `e.site.knee` | ✔ |

**Stage A — symbolic**

| Extractor | Result |
|---|---|
| `entities` | `azitromicina` ↔ `azithromycin` ✔. `rodilla` ↔ `knee` ✔. Expected `penicilina` at the allergy slot; found `aspirina`, which is a *different manifest entity of the same kind* → confusable-guard hit → `substitution` anchored to both `e.med.penicillin` and `e.med.aspirin` |
| `allergy` | Check 1 presence: allergen not resolvable ✘. Check 2 identity: resolved to `e.med.aspirin` ✘ → `substitution`, **critical (S1)** |
| `negation` | Source: `allergic` affirmed. Rendering: `alérgico` affirmed. Polarity matches — the flip is in *identity*, not polarity |
| `laterality` | Source `left` within 6 tokens of `knee` ✔. Rendering `derecha` within 6 tokens of `rodilla` ✔. Mismatch → `distortion`, **critical (S5)** |

Note the allergy and entity extractors both fire on the same span. `merge` M6 does not apply (different origins are not deduped) but M4 does not apply either (both are symbolic). The resolution is a **narrower rule in `allergy.py`**: when `allergy.py` emits a finding for a fact whose allergen entity also produced an `entities` finding, the `entities` finding is suppressed at source (it is a strictly weaker statement of the same fact). Implemented as `entities.suppress_for_fact_ids`, populated by `allergy.py`, which is the reason `allergy` runs last in `EXTRACTOR_ORDER`.

**Stage B — semantic.** Two findings:

```json
[
  { "kind": "omission",
    "rendering_quote": null,
    "source_quote": "instead",
    "note": "The contrastive 'instead' is dropped; the rendering does not convey that azithromycin replaces the drug the patient is allergic to.",
    "confidence": "medium" },
  { "kind": "substitution",
    "rendering_quote": "aspirina",
    "source_quote": "penicillin",
    "note": "A different medication is named as the allergen.",
    "confidence": "high" }
]
```

The second is correct and lands in extractor territory over an already-covered span → M4 → `overruled`. The first is a genuine semantic omission the extractors have no fact for → survives, `unanchored`, S12 → `non_critical`.

**Merged (findings array, abbreviated)**

| # | kind | severity | rule | origin | quote | shown |
|---|---|---|---|---|---|---|
| 1 | `substitution` | **critical** | S1 | `allergy` | `aspirina` ← `penicillin` | ✔ proof |
| 2 | `distortion` | **critical** | S5 | `laterality` | `derecha` ← `left` | ✔ proof |
| 3 | `omission` | `non_critical` | S12 | `grader` | — ← `instead` | ✔ (conf 0.60 × 0.90 × 0.85 × 0.85 = 0.390 → **withheld**, `below_confidence_floor`) |
| 4 | `substitution` | `non_critical` | S12 | `grader` | `aspirina` | ✘ `overruled` |

```json
{
  "status": "complete",
  "coverage": {
    "symbolic_assessed": true, "semantic_assessed": true,
    "facts_required": 5, "facts_adjudicated": 5,
    "facts_not_assessed": [], "categories_not_assessed": []
  },
  "counts": { "critical": 2, "non_critical": 1, "withheld": 1, "overruled": 1,
              "by_kind": { "substitution": 2, "distortion": 1, "omission": 1 } },
  "findings": [
    {
      "finding_uid": "e8f0a2c61b9d4370",
      "kind": "substitution", "severity": "critical", "severity_rule": "S1",
      "origin": "extractor", "extractor_name": "allergy",
      "fact_id": "a.penicillin", "unanchored": false,
      "rendering_span": [23, 31], "rendering_quote": "aspirina",
      "source_span": [21, 31],   "source_quote": "penicillin",
      "expected": "allergic to penicillin", "observed": "allergic to aspirin",
      "note": "The allergen is replaced. The patient's actual allergy is not communicated.",
      "confidence": null, "confidence_band": "proof", "stability": null,
      "display": { "shown_to_trainee": true, "withheld_reason": null, "flag": "none" },
      "overruled": false
    },
    {
      "finding_uid": "1b6d09fe73a2c845",
      "kind": "distortion", "severity": "critical", "severity_rule": "S5",
      "origin": "extractor", "extractor_name": "laterality",
      "fact_id": "l.knee", "unanchored": false,
      "rendering_span": [117, 125], "rendering_quote": "derecha",
      "source_span": [92, 96],     "source_quote": "left",
      "expected": "left", "observed": "right",
      "note": "Laterality reversed on the knee X-ray.",
      "confidence": null, "confidence_band": "proof", "stability": null,
      "display": { "shown_to_trainee": true, "withheld_reason": null, "flag": "none" },
      "overruled": false
    }
  ]
}
```

**The refusal variant.** If the same rendering had said `no es alérgico a la aspirina` — a negated allergy assertion with a substituted allergen and an ambiguous scope over a repeated `aspirina` — `negation.py` would refuse (`negation_ambiguous_scope`), `a.penicillin` would move to `coverage.facts_not_assessed`, the turn would be flagged `needs_human`, and the laterality critical would still be reported. **Partial refusal degrades one fact, never the turn**, and the report says which fact.

---

## 11. Performance and resource budget

The engine runs off the critical path (principle 5). Its budget is the trainee's own speaking time on the following turn — measured at roughly 3.5 s of usable slack in `docs/03-system-architecture.md` §6.

| Stage | Typical | p95 target | Behaviour on overrun |
|---|---|---|---|
| Normalisation | 3 ms | 8 ms | — |
| Eight extractors (sequential) | 15–40 ms | 60 ms | Never overruns in practice; a regression here is a bug |
| Grader call (12B q4, `reads=1`) | 2.0–3.0 s | `grader_wall_ms` (config, default 3200 ms) | Cancelled → `status = "partial"` |
| Guards | < 2 ms | 5 ms | — |
| Merge | < 2 ms | 5 ms | — |
| **Total** | **~2.1–3.1 s** | **3.3 s** | Late verdict lands on the next turn; coach hint dropped (`coach.suppressed`) |

Extractors are sequential, not parallel: 40 ms against a 3.5 s budget is not worth a thread pool, a shared-state hazard and a nondeterministic ordering risk. `ponytail:` sequential by choice — parallelise only if the p95 crosses 200 ms, which would mean the extractor set has roughly quintupled.

Resident memory attributable to the scoring plane is the 12B grader on the `rehearsal-grader` host (the dominant term in the ~20–24 GB target); the extractors are pure Python with closed lexicons and hold under 5 MB.

---

## 12. Code map and commands

```
src/rehearsal/scoring/
├── engine.py               # score_turn() — the entry point, stage sequencing
├── types.py                # ScoreRequest, Verdict, TurnContext, ScoringConfig
├── taxonomy.py             # ErrorKind, Severity, Finding, EXTRACTOR_OWNED, GRADER_ONLY
├── severity.py             # assign_severity — the S1..S13 ladder, the only writer
├── normalize.py            # NormalizedText, normalize(), to_original()
├── quantities.py           # Number, Dose, Frequency, TemporalRef; UNIT_ALIASES; Decimal helpers
├── lexicons/
│   ├── numbers_en.py numbers_es.py
│   ├── negation_en.py negation_es.py    # cues, pseudo-negations, terminators, concord pairs
│   ├── laterality.py temporal.py frequency_patterns.py
│   └── units.py                          # families, aliases, conversion factors
├── extractors/
│   ├── __init__.py          # Extractor protocol, EXTRACTOR_ORDER, run_extractors
│   ├── entities.py numbers.py dosage.py frequency.py
│   └── temporal.py negation.py laterality.py allergy.py
├── grader.py               # prompt assembly, the one call, decode config, retry
├── guards.py               # G1..G5, verify_quote, GuardReport
├── confidence.py           # BAND_BASE, STABILITY_FACTOR, KIND_PRIOR, score_confidence
├── merge.py                # merge_verdict — M1..M9, MergePolicy
└── queue.py                # ScoreQueue (see docs/03-system-architecture.md §7)

prompts/grader/v1.4.0.md    # versioned; variant_a / variant_b for G4
schemas/grader-output-1.4.0.json
schemas/verdict-1.2.0.json
data/fixtures/extractors/*.jsonl    # EV-00 grid, one file per extractor
data/fixtures/scoring/*.json        # end-to-end fixtures (the §10 examples)
tests/scoring/                      # unit per extractor + table-driven merge + guard tests
```

| Command | Does |
|---|---|
| `uv run pytest tests/scoring -q` | The engine's unit and table-driven suites |
| `uv run rehearsal-evals run ev00` | Extractor conformance grid; gate `= 1.00` |
| `uv run rehearsal-evals run ev01 --split dev` | Grader agreement on DEV |
| `uv run rehearsal score --source-file X --rendering-file Y --manifest Z` | Score one pair from the CLI; prints the verdict JSON. The fastest reproducer for any reported miss |
| `uv run rehearsal replay <session_id> --rescore` | Re-score a recorded session under the current prompt/policy version |
| `uv run rehearsal replay <session_id> --verify` | Re-score and diff against the stored verdicts; divergence is reported, not raised |

**Regression discipline [decided].** Every extractor bug found anywhere — live session, calibration, trainer review — gets a fixture row in `data/fixtures/extractors/` **before** it gets a fix. The grid only grows. This mirrors `docs/08-evals.md` §4.1 and is the reason `extractor_conformance = 1.00` is a meaningful gate rather than a tautology.

---

## 13. Table-driven tests the merge layer must carry

`tests/scoring/test_merge.py` is table-driven because the merge rules are a table. Each row is `(symbolic, semantic, policy) -> expected counts + expected flags`. The minimum set, each corresponding to a numbered rule:

| Test | Asserts |
|---|---|
| `test_symbolic_never_filtered` (M1) | A semantic result of any shape leaves the symbolic finding set bit-identical |
| `test_unknown_kind_dropped_not_coerced` (M3) | `kind: "paraphrase"` is dropped and counted, and no neighbour category gains a finding |
| `test_overrule_on_overlap` (M4) | Example 10.2's shape: overruled, kept, excluded from counts |
| `test_overrule_on_clean_adjudicated_span` (M5) | Extractor found the dose correct; grader claims a dose error → overruled |
| `test_dedup_threshold` (M6) | 59% overlap → two findings; 61% → one, higher confidence surviving |
| `test_severity_is_only_written_by_assign_severity` | Monkeypatching `assign_severity` to return a sentinel changes every severity in the output — proving no other code path writes it |
| `test_grader_cannot_create_critical` (S11/S12) | A grader finding with any `kind` and any confidence never yields `critical` |
| `test_allergy_always_critical` (S1) | Every allergy finding shape is critical regardless of policy |
| `test_withheld_still_counted` (§6.2) | `counts.critical + counts.non_critical` includes withheld findings |
| `test_refused_turn_excluded_from_rates` (G5) | A refused turn appears in neither the clean nor the error denominator |
| `test_partial_reports_not_assessed` (§6.2) | With `semantic = None`, the five grader-only categories appear in `categories_not_assessed` and nowhere else |

---

## 14. Design decisions, recorded with their rationale

| Decision | Chose | Rejected | Because |
|---|---|---|---|
| Split of labour | Deterministic extractors for the critical class; one model call for the residue | One model call for everything | The critical class is decidable; a model on a decidable problem is strictly worse and unauditable |
| Severity authority | Deterministic code, S1–S13 | Model-supplied severity | Principle 1. Also: severity is the number a programme director will be shown, and it must trace to a rule |
| Grader sees extractor findings | No | Yes | Anchoring destroys stage independence, which is what makes the `source_split` audit meaningful |
| Confidence representation | Ordinal bucket from the model, deterministic adjustment in code | Model-emitted float | Models emit 0.9 for everything; three buckets carry more information than a fake float |
| Grader confidence ceiling | 0.95, never 1.0 | Allow 1.0 | Keeps a proof (`null`/`proof`) structurally distinguishable from a guess |
| Quote requirement | Mandatory verified substring | Free-text description | It converts hallucination from an unmeasurable worry into a counted number (`dropped_span_unverified`) |
| Self-consistency in live sessions | Single read | Two reads always | The turn budget is ~3.5 s; two 2–3 s calls do not fit, and stalling the human is worse than a single read plus honest labelling |
| Number arithmetic | `Decimal` | `float` | Dosages |
| Accent stripping in normalisation | Retained | Stripped | `si`/`sí`, `esta`/`está` are polarity- and deixis-bearing |
| Entity recognition | Closed-world against the manifest | Open NER / drug dictionary | Open NER produces false alarms on ordinary vocabulary; the manifest already knows the answer |
| Fuzzy match implementation | `difflib.SequenceMatcher` ≥ 0.88 | `rapidfuzz` | Stdlib is adequate for bounded closed-world matching; no new dependency |
| Frequency `q8h` ↔ `TID` | Non-critical underspecification (F3) | Critical, or silent pass | Clinically not identical, but not action-changing; flagging it critical floods the trainee, passing it silently teaches a bad habit |
| Empty rendering | Refuse | Score as total omission | A microphone failure must not be charged to the trainee |
| Overruled findings | Kept in the record | Deleted | The disagreement rate between the two stages is data we need |
| Withheld findings in metrics | Counted | Excluded | Hiding a finding from the trainee **and** from the metric is self-flattery |
| Framework | Hand-rolled typed orchestration | LangChain / CrewAI | Reproducibility, seed control and inspectable failure points are the product's credibility; a framework hides the merge and the guards, which is exactly what must stay visible |
| Improving the grader | Prompt-level optimisation (L10) | Fine-tuning / LoRA | Project-wide exclusion. A diffed prompt is inspectable; a changed weight file is not |

---

## 15. Known limitations and what this engine cannot catch

Stated plainly, because principle 7 requires named gaps rather than silence. Each row names the mitigation that exists today and the upgrade path.

| # | Limitation | Consequence | Mitigation today | Upgrade path |
|---|---|---|---|---|
| L1 | **The rendering is text, and the text comes from the live agent's `heard_verbatim`.** Everything downstream inherits that string's fidelity | A mis-heard word becomes a phantom substitution | Transcription fidelity is measured against hand transcripts and reported next to grader agreement (`docs/08-evals.md`); `offpath_retranscribe` is the fallback path | Resolution of `docs/03-system-architecture.md` §16 Q1 |
| L2 | **Nothing prosodic is scored.** Tone, hesitation, emphasis, speed, audible uncertainty are invisible | An interpretation that is textually faithful but delivered in a way that undermines the patient scores clean | None. Named, not hidden | Out of scope for fidelity; would need a separate delivery instrument |
| L3 | **Severity tracks clinical consequence, not professional seriousness** (Example 10.3) | Systematic role violations aggregate as `non_critical` | UI groups conduct categories separately; trainer `reclassify` is recorded | A second severity axis (`conduct_severity`) — **[proposed]**, needs calibration labels that distinguish the two |
| L4 | **Negation scope is a window heuristic, not a parser.** Long-distance negation, subordinate clauses, and rhetorical questions can escape the 8-token window | Missed polarity flips (false negatives) — the worst failure class in the system | The ambiguous-scope refusal (§4.7) routes the uncertain cases to a human rather than guessing; every miss becomes a fixture | A dependency parse for Spanish and English on the grader host, off the critical path. Cost: a dependency and two models |
| L5 | **Cross-sentence and cross-turn omissions are invisible.** Each turn is scored independently | A trainee who consistently drops the second half of long utterances shows as unrelated per-turn omissions | The learner model aggregates per-category rates across turns (`docs/03-system-architecture.md` §5), which surfaces the pattern even though no single verdict sees it | Session-level analysis pass over the event log; not in the per-turn engine |
| L6 | **Compensating errors cancel.** An omission in one clause plus an addition in another can leave every manifest fact satisfied | Turn scores clean despite scrambled meaning | The grader is the only defence, and it is unanchored and therefore non-critical (S12) | Propositional alignment scoring — genuinely hard, not planned |
| L7 | **The manifest bounds what can be proved.** A clinical fact the scenario author did not model cannot produce a critical | Coverage is exactly as good as scenario authoring | `coverage.facts_required` vs `facts_adjudicated` is in every verdict; `needs_human` fires when the grader confidently sees an unmodelled fact (§9.4) | Manifest coverage review is part of scenario authoring QA (`docs/07-data-and-scenarios.md`) |
| L8 | **Closed-world entities cannot catch an invented drug** that is not in the manifest | "Take the amoxicillin" → "tome la cefalexina" is caught only if cefalexina is a scenario distractor | The grader covers it under `false_fluency`, non-critical | Add a curated common-medication list as a *second* closed world — **[proposed]**, §16 Q3 |
| L9 | **One Spanish variant (es-MX), one register band.** Generalisation to other variants is unmeasured | Regionalisms may read as register shifts | Named in `docs/08-evals.md` §7 as a scope limit | Variant-stratified calibration items |
| L10 | **Indigenous-language interpreting (Mixteco, Triqui) is entirely out of scope**, despite being a real need in the Pajaro Valley population this serves | The tool does not help the interpreters facing the hardest version of this problem | Stated, not implied | Would require different models, different data, and native-speaker labellers. A separate product decision, not a feature |
| L11 | **The human ceiling is one labeller.** `kappa_inter` may not exist | Every agreement number is against one person's careful application of the standard | `docs/08-evals.md` §4.3 refuses to publish `kappa_macro` without `kappa_intra` adjacent | A second certified labeller |
| L12 | **Confidence is not calibrated in the probabilistic sense.** It is a ranking derived from 25 DEV items | Treating 0.60 as "60% likely" would be wrong | Reported and used as a ranking only; no reliability diagram published | More labelled data than this project will have |
| L13 | **Register judgement is the grader's weakest category** (lowest `KIND_PRIOR`) | Register findings are the ones a trainer most often overrides | Priced into confidence; trainer-override rate by category is reported | L10 prompt optimisation targets it directly |

---

## 16. Open questions

| # | Question | Status | How it gets resolved |
|---|---|---|---|
| Q1 | Should the grader see the term manifest slice? | **[open]** | A/B on the DEV split: semantic-category precision and recall with and without. The risk is it drags the grader into extractor territory and inflates `overrule_rate`; both are measurable |
| Q2 | Is the 8-token negation scope window right, and should `y`/`and` really differ? | **[proposed]**, 8 tokens | Widen only against fixtures that demonstrate a miss. Every escape found in a session becomes a fixture row first |
| Q3 | Second closed world of common medications for L8 | **[proposed]** | Requires a licence-clean list (`docs/07-data-and-scenarios.md`) and a measured false-alarm cost on DEV before adoption |
| Q4 | Unicode punctuation folding as verification rung 2.5 (Example 10.3) | **[decided, pending implementation]** | Fold `’‘“”–—…` to ASCII equivalents before rung 2. Must be added with a fixture that fails without it |
| Q5 | Should `frequency_underspecification_severity` be programme-configurable, or fixed? | **[open]** | Configurable today. If two training programmes set it differently, their reported numbers stop being comparable — which may be an argument for fixing it |
| Q6 | Two reads in live sessions if a smaller grader ever fits the budget | **[open]** | Depends on whether a smaller quantisation reaches the same `kappa_macro`. Model right-sizing question, measured on DEV |
| Q7 | A second severity axis for professional conduct (L3) | **[proposed]** | Needs calibration labels that separate clinical consequence from professional seriousness — i.e. a labelling protocol change in `SETUP.md` §6, which retires the existing numbers |

---

## 17. Cross-references

| Document | What it holds that this one relies on |
|---|---|
| `docs/01-research.md` | The professional standard behind the nine categories; the clinical-consequence evidence that justifies the critical/non-critical line |
| `docs/03-system-architecture.md` | Where the scoring plane sits, the turn scheduler, the DB schema, isolation boundaries, the degradation ladder |
| `docs/05-voice-pipeline.md` | How `heard_verbatim` is produced, and the barge-in behaviour behind `source_partial` |
| `docs/07-data-and-scenarios.md` | How a `TermManifestSlice` is authored; the clinical state graph; scenario QA for coverage (L7) |
| `docs/08-evals.md` | EV-00 extractor conformance, EV-01 grader calibration, the sealed split discipline, every gate this engine is held to |
| `docs/09-ui-ux.md` | How findings, confidence bands, withheld findings and `not assessed` coverage are rendered, and the trainer review affordances |
| `SETUP.md` §6 | The calibration set: 40 items, DEV 25 / TEST 15 sealed, blind labelling, the human ceiling |

# 12 — Security, Privacy & Responsible Use

Status legend used throughout: **[decided]** — settled, implemented or committed to; **[proposed]** — the current best answer, not yet ratified; **[open]** — genuinely undecided, named rather than hidden.

---

## 1. Position

Rehearsal records a person's voice while they practise a clinically-shaped conversation, then produces a numerical judgement of their professional competence. Both halves of that sentence carry risk. The voice recording is biometric-adjacent data belonging to a worker who is frequently in a weak labour position — a per-diem interpreter, a promotora on a grant-funded contract. The judgement is a number that an employer would find convenient.

The security posture follows from that, not from a compliance checklist:

1. **Architectural privacy over policy privacy.** The strongest privacy statement available is that the audio has nowhere to go. No cloud inference in the core loop is a decision recorded in `docs/03-system-architecture.md` §15 and enforced as trust boundary **B4**; this document treats it as a security control and describes how it is verified rather than re-arguing it.
2. **The consequential decisions are deterministic and reviewable.** Principle 1. There is no place in the system where free-form model text becomes an action, a write, or a severity in a critical category. This closes the entire class of "the model was talked into doing something".
3. **The trainee is the data subject and the primary beneficiary.** Where a design choice trades trainee control against trainer convenience, trainee control wins, and §8 states that as a product commitment with the specific features that enforce it.
4. **Named gaps, not implied coverage.** §12 lists what is *not* protected. Rehearsal is a single-user local application on a personal or clinic-issued machine. It is not a hardened multi-tenant service and does not pretend to be one.

This document does not define the trust boundaries B1–B7 — those live in `docs/03-system-architecture.md` §12 and are cited here by ID. It does not define the storage schema — that is the same document, §10. It does not define the calibration-set protocol — that is `SETUP.md` §6.

---

## 2. What is in scope

| In scope | Out of scope, and why |
|---|---|
| A single-user install on one Apple Silicon machine | Multi-tenant hosting, SSO, org-wide RBAC — the horizontal fleet is an explicit product exclusion (`docs/00-dossier.md`), so its security model is not designed here |
| Local data at rest, local IPC, the loopback API surface | Network transport security beyond loopback — there is no remote endpoint in the core loop (**B4**) |
| Untrusted content entering through scenarios, seed corpora and model output (**B3**, **B5**) | Model weight security in the sense of training-data extraction — we do not train, fine-tune, or adapt anything (spec exclusion) |
| Supply chain: Python dependencies, model artefacts, frontend build | Hardening the OS, the browser, or the inference runtime's internals (`mlx`, `llama.cpp`) — we pin and verify them, we do not audit them |
| Responsible use of the performance data the product creates | Legal advice on HIPAA/CMIA/GDPR applicability. §6 states the factual position; a deploying clinic's counsel decides the legal one |

---

## 3. Threat model

Adversaries are named as roles with capabilities, not as abstractions. Each row states the capability assumed, the concrete harm, the mitigation that exists, and the residual risk that remains after it.

| ID | Adversary | Assumed capability | Concrete harm | Mitigation | Residual risk |
|---|---|---|---|---|---|
| **T1** | **Physical-access holder** — someone who sits down at the unlocked machine, or takes the laptop | Full read of `~/.rehearsal/`, including `rehearsal.db` and every audio blob | Listens to a named trainee's recorded speech; reads their per-category error rates; copies the lot | FileVault (full-disk encryption) is a **hard install prerequisite** — `rehearsal doctor` fails with `filevault_off` and refuses to start a session (`--i-accept-unencrypted-disk` overrides it and writes `security.fde_disabled` into the event log, which surfaces on every report produced by that install). Store directory is created `0700`, blobs `0600`. No sessions can be started for a trainee whose consent record has expired (§7) | **Not defended: an unlocked, logged-in session.** Disk encryption protects a powered-off or logged-out machine. Anyone at the keyboard of a running install has full access. This is stated to trainees in the consent text verbatim |
| **T2** | **Curious network observer** — someone on the same clinic or café Wi-Fi, or an operator of the network | Passive capture of all traffic from the machine; active ARP/DNS interference | Interception of session audio or transcripts in transit | There is no session traffic. Model hosts bind UNIX sockets (`~/.rehearsal/run/live.sock`, `grader.sock`) and never TCP; the API binds `127.0.0.1:8420` only; **B4** forbids importing an outbound HTTP client anywhere under `runtime/`, `scoring/`, `orchestrator/`, enforced by an import-graph test (§9.4) and by `rehearsal doctor --offline`, which completes a full session with networking disabled | Online commands exist and are deliberately separate: `make models`, `make scenarios`. Those *do* talk to the network, and what they fetch is covered by T4 rather than T2 |
| **T3** | **Malicious scenario or seed payload** — text in an ingested corpus, a shared scenario file, or a filename, crafted to be read by a model as instructions | Full control of the text content of a scenario, its term manifest, or a corpus record | Rubric exfiltration (defeating **B1** and inflating every score), coaxing the counterpart agent out of role, or attempting to trigger a write/tool/action | **B3** + **B5**, detailed in §9. Untrusted text only ever enters a prompt inside a delimited data slot; instruction regions are code-owned constants; every model call returns a validated schema instance; there is no tool vocabulary for a live agent to call and no model-writable path to the database | An injection can still *degrade content quality* — a poisoned scenario can make an encounter clinically nonsensical or offensive. That is a content-review problem, handled by scenario validation at ingest (`docs/07-data-and-scenarios.md`), not by the security boundary |
| **T4** | **Compromised dependency or model artefact** — a hijacked PyPI package, a typosquat, a tampered weights file, a malicious npm-side frontend build tool | Arbitrary code execution inside the Rehearsal process, at the privilege of the user | Silent exfiltration of the store; silent alteration of scores; persistence | Fully pinned, hashed dependency set (`uv.lock`, `--require-hashes`); `models.lock.json` with per-file `sha256` verified on every load, not only at download; zero runtime frontend dependencies; `pip-audit`/`uv` advisory scan in the release gate; the offline import-graph test means an exfiltrating dependency has to *add* a network import that the test will catch | **This is the highest residual risk in the system.** A dependency compromised *upstream of the hash we pinned* is not detected by pinning. We do not build reproducibly from source and do not claim to (§10.3) |
| **T5** | **Trainer misusing performance data** — a supervisor, program director, or clinic manager with legitimate access to a shared training machine | Reads the review UI and session reports; can export | Repurposing formative scores as employment or disciplinary evidence; ranking workers against each other; using a *machine* judgement as if it were an *assessed* one | §8 in full: local-only storage, no aggregate cross-trainee leaderboard view anywhere in the product, learner-owned export and deletion (`rehearsal forget`), verdict status surfaced as `unreviewed` until a human signs (**B6**), and a mandatory provenance banner on every exported report | **Not defended technically, and we say so.** A trainer with filesystem access can copy the database. This is a governance risk with product features that make the misuse visible and awkward, not impossible. §8.4 states the honest limit |
| **T6** | **Trainee gaming the instrument** — the legitimate user, optimising the number rather than the skill | Full control of their own speech; can inspect their own reports | Inflated scores that misrepresent readiness; corrupted data if scores are ever taken as assessment | Ground truth by construction (Principle 2) means the source utterance is fixed before the trainee speaks, so there is no answer to look up. Seeds and scenario selection are orchestrator-owned. Repeated identical scenarios are visible in the report. **B1** keeps the counterpart agents from adapting to make interpretation easier | A trainee can re-run the same scenario until the score is good and export only the good run. Detected, not prevented: exports carry the session id and the trainee's full session count for that scenario, so a cherry-picked export is identifiable as one |
| **T7** | **A second person in the room** — a colleague, a patient, a family member whose voice is captured incidentally by the microphone | None — they are not an adversary, they are a bystander whose data we might capture | Recording a third party who never consented | Capture is push-to-talk-or-VAD-gated within an explicitly started session, never ambient; the UI shows an unambiguous recording state at all times (`docs/09-ui-ux.md`); the pre-session checklist includes a "you are alone or everyone present has agreed" affirmation; headphone use is already required for echo reasons (`docs/05-voice-pipeline.md`) and is re-stated as a privacy control | Incidental capture is possible. `rehearsal forget --turn` allows a single turn's audio to be destroyed without discarding the session |
| **T8** | **The system itself, leaking through its own outputs** — errors, logs, crash reports | n/a | An utterance fragment escaping in a traceback, a log line, or an export | **B7**: exports are human-initiated, write to `~/.rehearsal/exports/`, run a redaction pass (trainee id → pseudonym, audio excluded unless separately confirmed); failure records store a traceback *digest*, not traceback text. Application logs in `~/.rehearsal/logs/` are structured JSONL and carry blob hashes and event `seq` values, never utterance text | A developer running with `REHEARSAL_LOG_LEVEL=DEBUG` gets more. Debug level is documented as unsafe for real trainee sessions and stamps `security.debug_logging` into the event log |

### 3.1 Explicit non-adversaries

Naming these prevents design effort leaking toward threats the product does not have.

- **A remote attacker.** There is no remote attack surface: no listening TCP port other than `127.0.0.1:8420`, no inbound webhook, no auth service, no upload endpoint.
- **A malicious co-tenant.** There are no tenants. One install, one machine.
- **A model-weights thief.** The weights are public artefacts pulled from Hugging Face.

---

## 4. Data inventory

Every category of data the system touches. "Who can read it" means *without additional privilege escalation* — every row is additionally readable by anyone who satisfies T1.

| # | Category | Concrete form / location | Contains personal data? | Retention default | Who can read it | Deletion path |
|---|---|---|---|---|---|---|
| D1 | **Trainee identity** | `sessions.trainee_id`, `learner_state.trainee_id`. A local handle chosen at install; no email, no employee number, no government id — the field is validated to reject `@` and long digit runs | Pseudonymous by construction | Life of the install | The local user; the review UI | `rehearsal forget --trainee <id>` |
| D2 | **Trainee rendering audio** | Opus, 16 kHz mono, content-addressed at `~/.rehearsal/blobs/sha256/ab/cd/…`, referenced by `turns.audio_sha` | **Yes — voice is the most sensitive item in the system** | **90 days [decided]**, then eligible for `rehearsal gc`. Transcripts survive; audio does not | Local user; the review UI via `GET /api/blobs/{sha256}` (loopback only) | `rehearsal forget --audio [--session|--turn]`; blob unlinked and overwritten, event `blob.destroyed` appended |
| D3 | **Canonical source text** (what the AI clinician/patient said) | Content-addressed blob, `turns.source_sha` | No — machine-generated fiction | Life of the session record | Local user | With the session |
| D4 | **Canonical rendering text** (what the trainee said, as text) | Content-addressed blob, `turns.rendering_sha` | Yes — the trainee's words, though not their voice | Life of the session record | Local user; review UI | `rehearsal forget --session <id>` |
| D5 | **Assembled grader input** | Content-addressed blob per turn; the exact bytes the grader saw | Contains D3 + D4 | Life of the session record | Local user | With the session |
| D6 | **Verdicts and findings** | `verdicts`, `findings` tables | Performance data about an identified worker — the T5 category | Life of the session record | Local user; review UI; export | `rehearsal forget --session` / `--trainee` |
| D7 | **Review and override records** | `reviews` table; `reviewer` is `trainee` or `trainer:<id>` | Yes — identifies the reviewing trainer too | Life of the session record | Local user | With the session. A trainer's own `reviewer` id is pseudonymised on export |
| D8 | **Learner model** | `learner_state` — per-category EWMA and counts | Yes — a longitudinal competence profile, the most misuse-prone derived artefact | Life of the install unless deleted | Local user; the trainee's own progress view | `rehearsal forget --learner <trainee>`; resets to cold-start, sessions untouched |
| D9 | **Event log** | `events` table, hash-chained, append-only | Payloads carry blob hashes, seeds, timings, state — **never utterance text** | Life of the install | Local user | Not individually deletable by design (see §7.4 — the tombstone rule) |
| D10 | **Consent records** | `consents` table (§7.2) | Yes — by definition | 2 years past revocation or expiry, then purged | Local user | `rehearsal consent --purge` after revocation |
| D11 | **Scenario bank** | `~/.rehearsal/` content built by `make scenarios` from public datasets | **No real patient data — §6** | Life of the install | Local user | Rebuildable; delete and re-run `make scenarios` |
| D12 | **Calibration set** | 40 hand-labelled turns, DEV 25 / TEST 15 sealed (`SETUP.md` §6) | Author-generated or public-corpus derived, never trainee session data without separate explicit consent | Life of the project | Local user; version-controlled labels | Manual |
| D13 | **Application logs** | `~/.rehearsal/logs/*.jsonl` | Hashes, timings, event kinds. No utterance text at `INFO` | 14 days, rotated | Local user | Rotation, or `rm` |
| D14 | **Model weights** | `~/.rehearsal/models/` (or `REHEARSAL_MODEL_DIR`) | No | Life of the install | Local user | `rm`, re-pull with `make models` |
| D15 | **Exports** | `~/.rehearsal/exports/<session_id>.<fmt>` | Redacted by default; audio only on a second explicit confirmation | **Never garbage-collected — the user owns this directory** | Whoever the user gives the file to | The user's own filesystem |
| D16 | **Machine measurements** | `budget.local.json` | No | Life of the install | Local user | `rehearsal doctor --remeasure` |

### 4.1 What the inventory deliberately does not contain

There is no telemetry table, no crash-reporting endpoint, no usage analytics, no license check, and no account. Observability is local and is covered in `docs/13-deployment-ops.md` — "observability without telemetry" is the section title there because the constraint is architectural, not a setting.

### 4.2 Retention enforcement

Retention is not a background daemon (a daemon that silently destroys a trainee's data is a worse failure than kept data). It is a two-step, human-triggered mark-and-sweep, already specified in `docs/03-system-architecture.md` §10.5:

```
rehearsal gc --dry-run      # lists unreferenced blobs and blobs past the D2 retention floor
rehearsal gc --commit       # requires the dry-run's manifest hash as an argument
```

`--commit` refuses to run without `--manifest <sha256>` matching a dry-run produced by the same store state. This is the one-way-door discipline: the destructive step cannot be reached by a single mistyped command.

---

## 5. Why voice is processed locally — and precisely what that buys

**What it protects.** The audio bytes and the derived transcript never traverse a network interface during a session. There is no third-party processor, no data-processing agreement to review, no vendor retention policy to trust, no subpoena-able copy off the machine, and no silent model change underneath a calibration number. For a product whose users are farmworker-serving interpreters in Watsonville and the Pajaro Valley — a population with well-founded reasons to distrust systems that ship their voice somewhere — this is the difference between a promise and a property. Trust boundary **B4** exists so that the property is testable rather than asserted: `rehearsal doctor --offline` runs a complete session with networking disabled, and an import-graph test fails the build if an HTTP client appears in a runtime module.

**What it does not protect.**

| Claim someone might infer | The truth |
|---|---|
| "My voice is safe" | It is safe *from the network*. It is a file on a disk, and T1 owns that disk. Local processing and disk encryption are different controls; both are required |
| "Nobody can hear my recordings" | Anyone with your machine's login can. That includes an employer-issued machine's administrator |
| "This is HIPAA-compliant" | Compliance is a property of a deployment, not of a binary. Rehearsal handles no PHI (§6), which makes the question much simpler for a deploying clinic — but the clinic, not this document, makes that determination |
| "Local means anonymous" | It does not. `trainee_id` links every session, verdict and learner-state row (D1, D6, D8) |
| "Local means no exfiltration risk" | T4 is real. Code that runs on the machine can read the machine |

The two decisions are separable and both are load-bearing: **local inference** removes the network adversary; **encrypted disk plus consent plus deletion rights** address the local one. Shipping either alone would be a half-measure sold as a whole one.

---

## 6. No real patient data — the hard rule

**Position [decided]: every encounter Rehearsal simulates is synthetic. The system contains no protected health information, and real patient audio must never be introduced into it — not as a scenario, not as a calibration item, not as a demonstration, not "just once, de-identified".**

The rule is absolute rather than risk-weighted for two reasons. First, de-identification of *audio* is not a solved problem — voice is itself an identifier, and clinical narrative carries re-identifying detail that redaction reliably misses. Second, a rule with an exception is a rule that gets argued about at the moment it matters most.

### 6.1 Where content actually comes from

| Content | Source | Why it is not PHI |
|---|---|---|
| Clinical scenarios, symptom timelines, medication lists | Generated against the clinical state graphs in `docs/07-data-and-scenarios.md`, seeded from public, licensed medical dialogue and transcription datasets | Public research corpora, licence-checked at ingest; no patient of any clinic is represented |
| Clinician and patient utterances | Generated at runtime by the E4B live models from the bound scenario | Machine-generated fiction. This is also what makes Principle 2 possible: the system knows the source exactly because it wrote it |
| Trainee renderings | The trainee's own voice, interpreting fiction | The trainee is the data subject and has consented (§7). The content being interpreted is not real |
| Calibration items | Author-generated or public-corpus-derived interpreting turns (`SETUP.md` §6.4) | Same as above |

### 6.2 Enforcement mechanism

Enforcement is layered, because a single check is a single point of failure.

1. **No ingress path exists.** There is no audio-upload endpoint. The API surface (`docs/03-system-architecture.md` §13.3, `docs/11-backend-api.md`) has no route that accepts external audio; `GET /api/blobs/{sha256}` is read-only and loopback-bound. The only way audio enters the store is live microphone capture inside a started session, and the only way text enters is the ingest pipeline.

2. **The ingest gate.** All corpus and scenario ingestion routes through one function, and nothing else may write to the scenario bank:

```python
# src/rehearsal/content/ingest.py

class ProvenanceError(ValueError): ...

@dataclass(frozen=True)
class SourceManifest:
    source_id: str          # stable id of the dataset or authored pack
    licence: str            # SPDX id or explicit licence name
    origin: Literal["public_dataset", "authored_synthetic"]
    attestation: str        # required free text: how the author knows this is not patient data
    sha256: str             # hash of the raw source bundle

def ingest_scenarios(bundle: Path, manifest: SourceManifest) -> IngestReport:
    """Sole write path into the scenario bank.

    Raises ProvenanceError if `origin` is anything other than the two permitted
    values, if `licence` is empty, or if `attestation` is shorter than 40 chars.
    There is deliberately no `origin="clinical_record"` member: the type system,
    not a policy document, is what makes the prohibited case unrepresentable.
    """
```

`make scenarios` fails closed: a bundle without a complete manifest is not ingested, and the failure names the missing field.

3. **A PHI-shaped-content screen at ingest [proposed].** A deterministic scan over every ingested record for the patterns that synthetic data has no reason to contain — US MRN-shaped identifiers, SSN patterns, NPI numbers, phone numbers, street addresses, and dates of birth at day precision. Hits do not auto-redact; they **block the ingest** and print the offending record for a human. Rationale: on synthetic content the false-positive rate is the only cost, and a false positive costs one human glance. `src/rehearsal/content/phi_screen.py`, unit-tested against a fixture file of positive and negative cases.

4. **A start-of-session affirmation.** The pre-session checklist includes the statement that the encounter is simulated and that no real patient information is to be spoken. It is displayed, not merely stored, because the realistic failure mode is not malice — it is a trainee spontaneously narrating a real case they handled that morning.

5. **The documented remedy when it happens anyway.** It will happen. `rehearsal forget --turn <session_id>:<turn_index>` destroys that turn's audio and rendering text, appends `turn.redacted` to the event log with a reason code, and marks the turn `redacted` in reports so the session's numbers remain honest about the gap. The remedy is one command, documented in the UI at the point of the affirmation, so that the safe action is the easy one.

**Not enforced:** we cannot inspect what a trainee says into the microphone in real time and refuse to record it. Item 5 exists precisely because items 1–4 cannot cover that case.

---

## 7. Consent, ownership and deletion

### 7.1 What consent covers

Consent is obtained per trainee, before the first session, and is specific rather than blanket. The consent screen states, in the trainee's language of choice (en / es — the interface is bilingual by design, `docs/09-ui-ux.md`), each of the following as a separate affirmable item:

| Item | Plain statement shown to the trainee |
|---|---|
| `record_audio` | Your voice is recorded while you interpret, and stored on this computer as an audio file |
| `store_transcript` | What you said is stored as text, alongside what the system said |
| `score_performance` | The system produces error counts about your interpreting, kept over time |
| `trainer_review` | *(optional, separately affirmable, default off)* A trainer using this machine may open your sessions and review the findings |
| `retention` | Audio is kept for 90 days; text and scores are kept until you delete them |
| `local_only` | Nothing is sent over the internet. Anyone who can log in to this computer can read it |
| `not_for_employment` | These scores are practice feedback. They are not an evaluation of your job performance (§8) |

`trainer_review` being separately affirmable and off by default is the mechanical expression of §8: the shared-machine training case is supported, but it is opted into by the worker, not configured by the employer.

### 7.2 Consent record

```sql
CREATE TABLE consents (
  consent_id   INTEGER PRIMARY KEY AUTOINCREMENT,
  trainee_id   TEXT    NOT NULL,
  version      TEXT    NOT NULL,   -- consent text version, e.g. "2"
  locale       TEXT    NOT NULL,   -- en | es — the language it was actually shown in
  scopes       TEXT    NOT NULL,   -- canonical JSON array of granted scope ids
  granted_ms   INTEGER NOT NULL,
  expires_ms   INTEGER NOT NULL,   -- granted_ms + 365 days
  revoked_ms   INTEGER,            -- NULL if live
  text_sha256  TEXT    NOT NULL    -- hash of the exact text shown, so it is reconstructable
) STRICT;

CREATE INDEX idx_consents_trainee ON consents(trainee_id, granted_ms DESC);
```

Enforcement points, all deterministic:

- `POST /api/sessions` returns `409 consent_required` if there is no live consent covering `record_audio`, `store_transcript` and `score_performance` at the current `version`.
- Consent **expires after one year** and must be re-affirmed. A stale consent is not a valid consent.
- Bumping the consent text version invalidates prior consents for the changed scopes — the migration that ships new consent text must state which scopes it touches.
- The review UI returns `403 review_not_consented` for any session whose trainee has not granted `trainer_review`. Sessions are not merely hidden; the endpoint refuses.
- Revocation (`rehearsal consent --revoke <trainee>`) is immediate and blocks new sessions. It does **not** delete past data — deletion is a separate, explicit act, because conflating them means a trainee who wants to stop practising accidentally destroys their own history.

### 7.3 Ownership and export

**Commitment: the trainee's performance data is the trainee's.** Expressed as three features, not as a paragraph.

```
rehearsal export --trainee <id> --format jsonl|md|csv [--include-audio]
rehearsal export --session <session_id> --format md
```

- Export is complete: every session, turn, verdict, finding, review, and the learner-state row, in a documented, non-proprietary format. There is no premium tier and no held-back field.
- `--include-audio` requires a second interactive confirmation (**B7**) and writes the opus blobs alongside a manifest.
- Trainer identities in `reviews.reviewer` are pseudonymised on export; the trainee gets the content of the review, not a dossier on the reviewer.
- Every exported report carries a provenance header — see §8.3.

### 7.4 Deletion, and the tombstone rule

```
rehearsal forget --turn <session_id>:<turn_index>
rehearsal forget --session <session_id>
rehearsal forget --learner <trainee_id>
rehearsal forget --trainee <trainee_id>          # everything: sessions, blobs, learner state
```

Deletion destroys **content**: audio blobs are unlinked and their bytes overwritten, rendering-text blobs are removed, and the affected `turns`/`verdicts`/`findings`/`reviews` rows are deleted.

Deletion does **not** rewrite the event log. That is a deliberate, stated trade-off. The event log is hash-chained (`docs/03-system-architecture.md` §10.3) and its integrity is the basis for every measurement claim the project makes; editing history would destroy `rehearsal replay --verify` and, with it, the honesty guarantee that is the product's credibility. What remains after a `forget` is a **tombstone**: the event `seq`, the timestamp, and the fact that a turn existed and was destroyed. No utterance text, no audio, no finding content — event payloads never contained utterance text in the first place (D9).

Every deletion produces a receipt the trainee can keep:

```json
{
  "receipt_version": 1,
  "scope": "session",
  "target": "s_2f9c…",
  "trainee_id": "kn-01",
  "blobs_destroyed": 34,
  "bytes_reclaimed": 18442117,
  "rows_deleted": {"turns": 34, "verdicts": 34, "findings": 61, "reviews": 12},
  "tombstones_written": 34,
  "event_seq_range": [88213, 88251],
  "completed_ms": 1770000000000
}
```

Written to `~/.rehearsal/exports/receipts/` and printed to stdout. A deletion right you cannot verify was exercised is not a right.

**[open]** Whether `rehearsal forget --trainee` should also offer a "and prove it" mode that re-runs the blob sweep and asserts zero surviving references. Currently the receipt asserts it; an independent verifier would be stronger. Small, not yet built.

---

## 8. Responsible use

### 8.1 The commitment

**Rehearsal's scores are formative training signals. They must not be repurposed as employment, disciplinary, credentialing or immigration-related evidence about a worker without that worker's specific, informed, revocable consent.**

This is a product commitment, stated because the misuse is foreseeable and the population is vulnerable. The users are frequently contingent workers — per-diem interpreters, grant-funded promotoras — for whom a printed "critical error rate" in a supervisor's hand is a materially different object than it is in their own hand.

It is also, separately, an accuracy argument. The instrument is not fit for evaluative use:

- The grader is a quantised 12B model whose agreement with a human labeller is a *measured* Cohen's kappa against a 40-item calibration set (`SETUP.md` §6, `docs/08-evals.md`), reported with its own honest human ceiling. It is a useful instrument. It is not an assessor.
- Results are stochastic and are reported as rates and distributions with stated uncertainty (Principle 7). A single session's number has a confidence interval wide enough to make individual comparison meaningless.
- Sessions carry a `degrade_max` level. A number produced at DegradeLevel 2 — extractor-only, semantic categories *not assessed* — is not comparable to one produced at L0, and no summary strips that distinction.
- Verdicts are unreviewed until a human signs them (**B6**). An unreviewed verdict is a draft.

### 8.2 Design features that support it

| Commitment | The feature that carries it |
|---|---|
| The data lives with the worker | Local-only storage, no account, no server-side copy, no telemetry (§4.1) |
| The worker can take it | `rehearsal export` — complete, open format, no held-back fields (§7.3) |
| The worker can destroy it | `rehearsal forget` with a verifiable receipt (§7.4) |
| The worker controls trainer access | `trainer_review` consent scope, off by default, refused at the endpoint not merely hidden (§7.2) |
| Comparison between workers is not a supported operation | **There is no cross-trainee view in the product.** No cohort dashboard, no leaderboard, no ranking, no class-average overlay. `learner_state` is queried per trainee and the API has no endpoint that returns more than one trainee's data. Building a ranking requires leaving the product |
| A score cannot masquerade as an assessment | Reports state review status explicitly (`unreviewed` / `reviewed` / `signed`), and `degrade_max`, and the grader model id and prompt version |
| The claim is not just words | Every export carries §8.3 |

### 8.3 The provenance header

Every exported report — every format — begins with a machine-generated block that cannot be suppressed by a flag:

```
REHEARSAL — PRACTICE RECORD
Trainee:            kn-01 (self-selected local handle)
Sessions covered:   4 of 11 total for this scenario  ← cherry-picking is visible (T6)
Review status:      2 signed, 1 reviewed, 1 unreviewed
Max degradation:    L1 (coach hints shed on 1 session)
Grader:             gemma-12b-it-q4 / prompt v7
Grader agreement:   Cohen's kappa 0.71 vs human labels on the sealed test split (n=15)
                    Human intra-rater ceiling on the same items: 0.84

This is formative training feedback produced by an automated system with the
measured agreement stated above. It is not a professional assessment,
certification, or evaluation of job performance. It should not be used as
employment or disciplinary evidence without the trainee's consent.
```

Kappa values shown are placeholders in this document; the exported header emits the actual measured numbers from `docs/08-evals.md`. If no calibration measurement exists for the running grader/prompt pair, the header says so in those words rather than omitting the line — a report that hides that it is uncalibrated is worse than one that admits it.

### 8.4 What this does not do — stated plainly

None of the above stops a determined employer. A trainer with an account on the machine can read `rehearsal.db` directly with any SQLite client, and no product feature prevents that (T5, T1). A worker can be pressured into granting `trainer_review` or into exporting. Rehearsal makes misuse **visible, effortful, and contradicted in writing on every artefact it produces**. It does not make it impossible, and claiming otherwise would be the kind of false assurance this document exists to avoid.

The corresponding recommendation to programs deploying Rehearsal, stated in `docs/13-deployment-ops.md`: give each trainee their own OS account, or their own install. A shared login is a shared record.

---

## 9. Prompt-injection defence

### 9.1 The rule

**No text that the system did not author can cause the system to do anything.** Untrusted text can only ever become *content inside a data slot* or *a field in a validated schema instance*. This is **B3** (scenario text is data) and **B5** (model output is schema-validated) working together, and the reason the attack surface is small is architectural rather than filter-based: there is nothing for an injection to reach.

Sources of untrusted text, all treated identically: ingested corpora, scenario pack files, term manifests, filenames and paths, and — critically — **the models' own output**, including the trainee's transcribed rendering. A live agent's output is untrusted input to everything downstream of it.

### 9.2 Schema-constrained outputs

Every model call in the system returns a validated instance or fails. There is no code path that consumes free-form model text.

```python
# src/rehearsal/scoring/grader.py

class GraderOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    findings: list[SemanticFinding] = Field(max_length=12)
    unassessable: bool = False

class SemanticFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["editorialization", "role_exchange", "register_shift",
                  "false_fluency", "first_person_violation", "distortion",
                  "omission", "addition", "substitution"]
    span_start: int = Field(ge=0)
    span_end: int   = Field(ge=0)
    confidence: float = Field(ge=0.0, le=1.0)
    note: str = Field(max_length=240)
```

Three properties matter for injection defence specifically:

- `extra="forbid"` — a model that invents a field is a validation error, not a silently-honoured instruction.
- **The grader cannot set severity.** Severity in the critical categories (dosage, frequency, allergy, negation, laterality, onset) is assigned by deterministic extractors and by `VerdictMerger` precedence rules (`docs/06-scoring-engine.md`). An injection that makes the grader claim "no errors, severity none" cannot lower a critical finding, because the grader was never the authority for it. This is Principle 3 paying a security dividend it was not designed for.
- Spans are validated against the actual rendering text. `span_end > len(rendering_text)` or `span_start > span_end` is a validation failure; a model cannot point at text that does not exist.

Failure handling is the boring path: one retry at temperature 0 with the schema echoed, then the turn is scored extractor-only and flagged `grader_unavailable`. Injection therefore degrades to *less scoring*, never to *wrong action*.

### 9.3 Closed tool vocabulary

The live agents (`ClinicianAgent`, `PatientAgent`) have **no tools**. Not a restricted set — none. They emit an utterance and nothing else. There is no function-calling surface, no retrieval call, no file access, no shell. The clinical state graph decides what happens next, deterministically, in `src/rehearsal/content/graph.py`.

The complete list of things a live agent's output can cause:

| Agent output | What it can reach |
|---|---|
| Utterance text | The TTS router (spoken), a content-addressed blob (stored), the grader's `source_text` slot |
| Nothing else | — |

State transitions, seed draws, database writes, severity assignment, difficulty changes, and session control are all orchestrator-owned and deterministic. **B5** in the architecture doc states this as "models never write to the database, never choose a state transition, never emit SQL or paths"; here it is the reason a prompt injection has no verbs available to it.

### 9.4 Context assembly is the chokepoint

`ContextAssembler` (`src/rehearsal/runtime/agents/context.py`) builds every model context from a per-role field allowlist and raises `IsolationViolation` on a disallowed key. Its structure is also the injection boundary: instruction regions are code-owned string constants and untrusted content only ever appears inside a delimited data slot.

```python
def assemble(role: Role, fields: Mapping[str, object]) -> AssembledContext:
    """Instruction regions are module-level constants. `fields` are rendered
    into fenced data slots and are never concatenated into instruction text.

    Raises IsolationViolation if `fields` contains a key not in
    ALLOWED_FIELDS[role] — this is the B1 enforcement point and it fires
    before any rendering happens.
    """
```

Applied to untrusted text at ingest, before it can reach a slot (`src/rehearsal/content/ingest.py`):

| Treatment | Purpose |
|---|---|
| Unicode NFKC normalisation | Defeats homoglyph and confusable-character evasion |
| Control-character and bidi-override stripping (`‪`–`‮`, `⁦`–`⁩`) | Defeats invisible reordering and hidden-instruction tricks |
| Zero-width character stripping | Defeats invisible token smuggling |
| Fence-sequence escaping | Untrusted text cannot terminate its own data slot |
| Per-field length caps | An injection cannot flood the context window to push instructions out |

**Not done, deliberately:** no keyword blocklist for phrases like "ignore previous instructions". Blocklists are trivially evaded, produce false positives on legitimate clinical text, and create the illusion of protection. The structural controls above are the defence; a filter on top would be theatre.

### 9.5 The isolation test that doubles as an injection test

`docs/08-evals.md` specifies the L8 leakage A/B — induced error rate when the counterpart agent can versus cannot see the rubric. That eval is the empirical check that **B1** holds end to end, and it is also the strongest available injection detector: a scenario payload whose goal is rubric exfiltration would show up as leakage-condition behaviour in the no-leak arm. The unit-level companion asserts that rubric and taxonomy vocabulary is absent from every assembled live context, for every scenario in the bank.

### 9.6 Frontend

The SPA is vanilla JS with no runtime dependencies. All rendering of model-produced or trainee-produced text uses `textContent`; there is no `innerHTML` assignment of dynamic content anywhere in `frontend/`, enforced by a lint rule in the release gate. A `Content-Security-Policy: default-src 'self'; connect-src 'self'; script-src 'self'; object-src 'none'; base-uri 'none'` header is served by the API. The API sets `X-Content-Type-Options: nosniff` and serves blobs with an explicit `Content-Type` and `Content-Disposition: attachment` for non-audio media types.

---

## 10. Supply chain

T4 is the highest residual risk in the system, so the controls here are the most concrete.

### 10.1 Python dependencies

| Control | Mechanism | Gate |
|---|---|---|
| Full pinning, transitive | `uv.lock` committed; `uv sync --frozen` in every environment | CI fails if the lock file would change |
| Hash verification | uv verifies distribution hashes from the lock | Install-time |
| Advisory scan | `uv run pip-audit` over the resolved set | Release gate; a known-vulnerable dependency blocks release |
| Minimal surface | stdlib before dependency, per project standards. Current runtime set is small enough to enumerate in `docs/13-deployment-ops.md` | Review — a new dependency is an explicit decision recorded in `docs/17-decisions.md` |
| No network in runtime modules | Import-graph test: `test_no_network_imports` walks the AST of every module under `runtime/`, `scoring/`, `orchestrator/`, `store/` and fails on any import of `httpx`, `requests`, `aiohttp`, `urllib.request`, `socket` (except the UNIX-socket path in `hosts.py`, which is allowlisted by exact module) | CI, every commit |
| Runtime offline proof | `rehearsal doctor --offline` completes a scripted session with the network interface down | Release gate |

The import-graph test is the highest-leverage control in this table: it converts "we do not exfiltrate" from a claim about intent into a property checked on every commit, and it fires against a compromised dependency that tries to *add* egress rather than only against our own mistakes.

### 10.2 Model artefacts

Weights are large binary blobs fetched from a third party. They get verified like any other untrusted input.

```json
// models.lock.json  (committed)
{
  "lock_version": 1,
  "models": [
    {
      "role": "live",
      "repo": "google/gemma-4-e4b-it",
      "revision": "9c1f0b7e…",
      "runtime": "mlx",
      "quantisation": "q4",
      "files": [
        {"path": "model-00001-of-00002.safetensors", "sha256": "5b2e…", "bytes": 4831838208},
        {"path": "model-00002-of-00002.safetensors", "sha256": "a71c…", "bytes": 2147483648},
        {"path": "tokenizer.json", "sha256": "0f9a…", "bytes": 17209722}
      ]
    },
    { "role": "grader", "repo": "google/gemma-12b-it", "revision": "…", "files": [ … ] }
  ]
}
```

| Control | Detail |
|---|---|
| Pinned revision | Repo + commit revision, never a moving tag or branch |
| Per-file `sha256` | Recorded at first pull, committed to the repo |
| Verified **on load**, not only on download | `make models` verifies after fetch; `rehearsal up` re-verifies before the model host loads weights. A mismatch aborts startup with `model_artefact_mismatch` and names the file. On-load verification is what catches post-download tampering (T1 with write access, or T4) |
| Format | `safetensors` only. `.bin`/pickle checkpoints are refused at load — arbitrary code execution during deserialisation is a solved problem and the solution is to not use the format |
| Reproducibility of results | `sessions.grader_model` and `sessions.live_model` record the resolved model id and quantisation, and `sessions.prompt_ver` the prompt version, so a published number is traceable to the exact instrument that produced it |

**[open]** Verification cost. Re-hashing ~10 GB on every `rehearsal up` adds startup time (order tens of seconds on an SSD). Current position: pay it, because startup is once per working session, not once per practice turn. If measurement shows it is intolerable, the fallback is verify-on-first-load-per-boot with a cached (mtime, size, sha256) triple — weaker, and it would be recorded as a downgrade in `docs/17-decisions.md`, not made quietly.

### 10.3 Builds

- The frontend is vanilla JS with **no runtime dependencies and no bundler-plugin ecosystem** — the most common JS supply-chain vector is absent because the ecosystem is absent. `frontend/dist` is produced by a scripted copy plus minification and is byte-comparable across machines.
- Python builds use the pinned `uv.lock`; the distributed application is source plus lock, not an opaque binary, so a reviewer can read what runs.
- **Honest limit:** this is *deterministic packaging*, not a reproducible build in the Reproducible-Builds sense. We do not build the Python interpreter, `mlx`, `llama.cpp`, or the model weights from verified source, and we do not have a bit-for-bit attestation chain. Claiming "reproducible builds" without that chain would be the kind of overstatement §12 exists to prevent.

### 10.4 The release gate

`docs/13-deployment-ops.md` owns the full gate. The security-relevant subset, each of which blocks release:

```
uv sync --frozen                     # lock is authoritative
uv run pip-audit                     # no known-vulnerable dependency
uv run pytest tests/security/        # import graph, PHI screen, isolation, injection corpus
rehearsal verify-models              # models.lock.json matches bytes on disk
rehearsal doctor --offline           # a full session completes with networking down
uv run ruff check .                  # includes the frontend innerHTML lint rule
```

`tests/security/` is a real directory with named tests, not a category: `test_no_network_imports.py`, `test_context_isolation.py`, `test_injection_corpus.py` (a fixture set of adversarial scenario payloads asserted to produce zero schema violations and zero rubric-vocabulary leakage), `test_phi_screen.py`, `test_export_redaction.py`, `test_consent_enforcement.py`.

---

## 11. Secret management

**The core product has no secrets.** No API keys, no tokens, no passwords, no certificates, no account. `SETUP.md` §3 states it as a property of the environment: if you never set an API key, everything in the product still works.

The two optional, non-runtime cases:

| Variable | When | Rule |
|---|---|---|
| `HF_TOKEN` | Only for the first model download, only if the repo is gated | Read from the environment. Never written to `~/.rehearsal/`, never logged, never in the event log |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | **Offline calibration analysis only** — a frontier model as a second opinion while analysing the calibration set. Never in the product runtime | Modules under `evals/` may read them. The import-graph test (§10.1) guarantees the runtime packages cannot reach a network client at all, so this separation is enforced structurally, not by convention |

Supporting rules:

- `.env` is git-ignored; `.env.example` carries names and comments only, never values.
- The event log and the JSONL application logs have no field that carries an environment variable's value; the config snapshot recorded at session start is a **redacted projection** — `RuntimeConfig.redacted()` returns the config with any key matching `(?i)(token|key|secret|password)` replaced by `"<redacted>"`, and that method is the only one the logger may call.
- A secret scan runs over every diff before commit, per project standards.

Because there are no secrets, there is no key rotation procedure, no vault, and no secret-management dependency. That is the point: the cheapest secret to protect is the one that does not exist.

---

## 12. Limitations — what is not protected

Stated as flatly as possible. A reader should be able to decide whether Rehearsal is appropriate for their setting from this list alone.

| # | Not protected | Why not | What would change it |
|---|---|---|---|
| L1 | **An unlocked, logged-in machine.** Anyone at the keyboard reads everything | Single-user local app; there is no in-app auth and adding one would be security theatre over a filesystem anyone can read anyway | Per-trainee OS accounts, or per-trainee installs. This is the deployment recommendation, not a code change |
| L2 | **A trainer with filesystem access.** `rehearsal.db` opens in any SQLite client | Same as L1. Application-level access control cannot constrain a user who owns the file | Same as L1 |
| L3 | **Database and blob encryption at rest beyond FDE.** No SQLCipher, no per-blob encryption | The key would have to live on the same machine, unlocked by the same login, protecting against an adversary who already has that login. It buys defence-in-depth against offline theft that FDE already covers. **[open]** — reconsider if a shared-machine deployment becomes the norm | SQLCipher with a per-trainee passphrase. Real cost: a forgotten passphrase destroys a trainee's history |
| L4 | **A compromised upstream dependency.** Pinning fixes what we pinned; it does not detect a package that was already malicious when we pinned it | We do not audit dependency source and do not build from verified source | A vendored, reviewed dependency set. Disproportionate for the current dependency count |
| L5 | **Bit-for-bit reproducible builds** | §10.3. We ship deterministic packaging, not an attestation chain | Substantial toolchain work; not currently justified |
| L6 | **The trainee saying something real into the microphone.** No real-time content filter exists | Unsolvable in the critical path; a filter would introduce latency and false rejections into a conversational loop | Nothing. §6.2 item 5 is the mitigation: a fast, well-signposted redaction command |
| L7 | **Misuse of exported data once exported.** A file the trainee exported and handed over is out of the system's control | Correct behaviour — the data is theirs to give | Nothing technical. The provenance header (§8.3) travels with it |
| L8 | **Grader errors.** The grader misses findings and invents them at a measured rate | It is a quantised 12B model. `docs/08-evals.md` reports the rate honestly with its human ceiling | Better models, better prompts (L10 optimisation), a larger calibration set. All measured, none claimed in advance |
| L9 | **Availability.** No backup, no replication. A dead disk destroys the store | Deliberate: the alternative is an off-machine copy, which contradicts §5 | The trainee's own `rehearsal export` output, kept where they choose. Documented as the backup story in `docs/13-deployment-ops.md` |
| L10 | **Side channels.** Timing, memory, or acoustic side channels are not analysed | Out of proportion to the threat model — the primary adversary is already assumed to have the disk (T1) | Nothing planned |
| L11 | **Third-party voices captured incidentally** (T7) | The microphone hears the room | `rehearsal forget --turn`, plus the headphone and solitude affirmations |
| L12 | **Formal privacy guarantees** — no differential privacy, no k-anonymity, no formal information-flow proof of **B1** | **B1** is enforced by an allowlist and *measured* by the leakage A/B, which is empirical evidence, not proof | A formal information-flow analysis of `ContextAssembler`. Interesting; not currently justified |

---

## 13. Open questions

| # | Question | Current position | What would settle it |
|---|---|---|---|
| Q1 | Should audio retention default to 90 days or 30? | 90 [decided, weakly] — long enough for a trainer review cycle and for a trainee to revisit a session; short enough to bound exposure | Observed review latency once real sessions exist. A default that is routinely too short trains people to disable it, which is worse |
| Q2 | Should the PHI-shaped-content screen (§6.2 item 3) also run over *trainee rendering transcripts* post-session, flagging turns for the trainee's attention? | Attractive, unbuilt. It would catch the L6 case after the fact and prompt a redaction | A false-positive rate measurement on real session transcripts — a screen that flags every session is a screen people learn to ignore |
| Q3 | SQLCipher for the store (L3) | Not now. The threat it addresses is mostly covered by FDE | A deployment where trainees share an OS login despite the recommendation |
| Q4 | Should `trainer_review` consent be time-boxed per session rather than standing? | Per-session consent is strictly stronger and strictly more friction | Trainer-workflow observation once L7 review is in real use |
| Q5 | An independent post-deletion verifier (§7.4) | Receipt-only today | Small build; scheduled behind higher-value work |

---

## 14. Cross-references

| Topic | Document |
|---|---|
| Trust boundaries B1–B7, storage schema, process topology, degradation ladder | `docs/03-system-architecture.md` |
| Information isolation, context discipline, agent roster | `docs/04-ai-engineering.md` |
| Deterministic extractors, merge precedence, severity authority | `docs/06-scoring-engine.md` |
| Scenario provenance, corpus licences, state graph validation | `docs/07-data-and-scenarios.md` |
| Leakage A/B, grader agreement, honest reporting of uncertainty | `docs/08-evals.md` |
| Consent and recording-state UI, bilingual interface, accessibility | `docs/09-ui-ux.md` |
| Loopback API surface, CSP and response headers, blob endpoint | `docs/11-backend-api.md` |
| Release gate, backup story, observability without telemetry, per-account deployment recommendation | `docs/13-deployment-ops.md` |
| `tests/security/` contents and how they are run | `docs/14-testing-strategy.md` |
| Calibration-set protocol, sealed test split | `SETUP.md` §6 |
| Environment variables and the no-secrets property | `SETUP.md` §3 |

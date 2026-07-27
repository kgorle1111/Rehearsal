# 13 — Deployment & Operations

Rehearsal is a single-machine, single-user application that happens to be shaped like a server. That
shape is a packaging convenience — a local FastAPI process serving a local browser — and never a
distribution model. Everything below follows from three constraints that are not negotiable:

1. **No cloud inference in the core loop.** There is no inference endpoint to point at, no API key to
   rotate, no rate limit to plan around, and no vendor outage that can stop a session.
2. **Nothing is transmitted.** No telemetry, no crash reporting, no usage pings, no license check, no
   update ping. Observability is entirely local and export is entirely human-initiated. See §7.
3. **The event log is the record.** Deployment operations are ranked by their blast radius on
   `~/.rehearsal/rehearsal.db` and `~/.rehearsal/blobs/`. Anything that can corrupt or lose those is a
   one-way door and gets a rollback plan before it gets a runbook.

The process topology, filesystem layout and interface surface this document operates are defined in
`docs/03-system-architecture.md` §13 and are not restated here. This document covers how those
processes get onto a machine, how they are versioned, how you know they are healthy, and what you do
when they are not.

---

## 1. Deployment targets

Two targets. Both are single-tenant. There is no third.

| | **T1 — Local workstation** (primary) | **T2 — Single-tenant on-premises** (optional) |
|---|---|---|
| Who | An individual trainee, promotora, or trainer | A training program or safety-net clinic running practice on one shared machine |
| Hardware | Apple Silicon, 48 GB unified memory | Same, or a single Linux box with ≥ 48 GB RAM and a GPU capable of the 12B grader |
| Runtime | MLX | MLX on Apple Silicon; llama.cpp on Linux (the portable fallback, see §2.4) |
| Install method | `rehearsal-installer` bundle, user-owned, no admin rights | Same bundle, plus a service unit and a shared data root |
| Who runs the processes | The logged-in user, on demand (`rehearsal up`) | A dedicated service account, supervised (`launchd` / `systemd`) |
| Data root | `~/.rehearsal/` | `/var/lib/rehearsal/` (configurable via `REHEARSAL_HOME`) |
| Concurrent sessions | 1 | **1.** Voice sessions do not multiplex; see §9 |
| Network binding | `127.0.0.1:8420` | `127.0.0.1:8420` **still** — remote access, if any, is the operator's reverse proxy over their own TLS and their own auth, and is out of scope for this project |
| Identity | Local trainee ids, no accounts | Local trainee ids, still no accounts; a trainer role flag on the review gate |
| Backup | User-driven `rehearsal backup` | Operator-scheduled `rehearsal backup` to the program's own storage |
| Update cadence | User applies bundles when they choose | Operator applies bundles; can pin a version indefinitely |

### 1.1 What actually changes between T1 and T2

Very little, and deliberately so. The list is short because every difference is a divergent code path
that has to be tested twice.

| Concern | T1 | T2 | Mechanism |
|---|---|---|---|
| Data root | `~/.rehearsal` | `/var/lib/rehearsal` | `REHEARSAL_HOME` |
| Process lifetime | Foreground, dies with the terminal | Supervised, restarts on boot | `deploy/launchd/com.rehearsal.api.plist`, `deploy/systemd/rehearsal-api.service` |
| Model directory | Inside the data root | Read-only shared path, group-readable | `REHEARSAL_MODEL_DIR` |
| Multi-user | Not applicable | Multiple trainee ids in one store, one at a time at the mic | `trainees` rows; no OS-level isolation is claimed |
| Trainer review | Same machine, same browser | Same machine, same browser, `--role trainer` on the review view | `docs/09-ui-ux.md` |
| Retention | User deletes what they like | Operator sets a retention floor for `rehearsal gc` | `REHEARSAL_RETENTION_DAYS` |
| Backup | Manual | Scheduled by the operator's own scheduler | §10 |

**What T2 explicitly is not:** it is not multi-tenant, not horizontally scalable, and has no fleet
management, no central admin console, and no cross-machine aggregation of trainee data. That exclusion
is deliberate and reasoned in `docs/17-decisions.md`: horizontal fleet scaling is out of scope for this
project, and the privacy posture in `docs/12-security-privacy.md` — session audio never leaves the
machine that recorded it — is materially easier to keep true when there is nowhere for it to go. A
program that wants twenty trainees practising simultaneously buys twenty machines, not a cluster. That
is stated up front rather than discovered later.

---

## 2. Packaging and distribution

### 2.1 What ships

An installable release is four separable artefacts. They are separable because they change at wildly
different rates and have wildly different sizes: the Python package is megabytes and changes often, the
weights are gigabytes and change rarely.

| Artefact | Name pattern | Size (order) | Contents |
|---|---|---|---|
| Python distribution | `rehearsal-<version>-py3-none-any.whl` | ~2 MB | `src/rehearsal/**`, prompts, migrations, scenario bank, the built frontend as package data |
| Source distribution | `rehearsal-<version>.tar.gz` | ~3 MB | The above plus tests and eval harness |
| Model manifest | `models-<manifest_version>.json` + `.minisig` | ~4 KB | Model ids, quantisations, sha256s, sizes, licence pointers |
| Offline bundle | `rehearsal-bundle-<version>-<platform>.tar` | ~18–26 GB | Wheel + a resolved, hash-pinned dependency wheelhouse + the weights the manifest names + the manifest + signatures |

The frontend is **not** a separate artefact. `frontend/` is built during packaging and the output is
placed at `src/rehearsal/api/static/` as package data, so the wheel is self-contained and the API's
static mount can never be pointed at a stale or missing build directory. A version of the SPA that does
not match the API it talks to is not a possible state.

### 2.2 Build

```bash
make build            # runs the three steps below in order, refuses on a dirty tree
# 1. frontend
npm --prefix frontend ci
npm --prefix frontend run build          # -> frontend/dist
cp -R frontend/dist/. src/rehearsal/api/static/
# 2. python
uv build                                  # -> dist/*.whl, dist/*.tar.gz
# 3. record
uv run rehearsal-release manifest --out dist/models-<manifest_version>.json
```

`make build` refuses to run on a dirty git tree for the same reason `rehearsal-evals` refuses to record
a citable number from one (`docs/08-evals.md` §7): an artefact whose exact source cannot be recovered is
not an artefact, it is a rumour. The version embedded in the wheel is derived from the git tag, never
hand-edited.

### 2.3 Model artefact fetch and verify

Weights are never bundled into the wheel and never fetched implicitly at runtime. Fetching is an
explicit, user-initiated command with an explicit verification step.

```jsonc
// models-3.json  — the model manifest; signed alongside the release
{
  "manifest_version": 3,
  "compatible_app_range": ">=0.6.0,<0.8.0",
  "models": [
    {
      "role": "live",
      "id": "gemma-4-e4b-it",
      "quant": "q4_k_m",
      "runtime": "mlx",
      "files": [
        { "path": "live/gemma-4-e4b-it-q4_k_m.safetensors",
          "sha256": "9f2c…",
          "bytes": 4831838208 },
        { "path": "live/tokenizer.json", "sha256": "1ab4…", "bytes": 17209344 }
      ],
      "resident_gb_est": 7.0,
      "native_audio_input": true,
      "licence": "docs/licences/gemma-terms.md"
    },
    {
      "role": "grader",
      "id": "gemma-12b-it",
      "quant": "q4_k_m",
      "runtime": "mlx",
      "files": [ { "path": "grader/gemma-12b-it-q4_k_m.safetensors", "sha256": "77de…", "bytes": 7516192768 } ],
      "resident_gb_est": 9.0,
      "native_audio_input": false
    },
    {
      "role": "tts",
      "id": "local-neural-tts",
      "voices": { "en-US": "…", "es-MX": "…" },
      "files": [ { "path": "tts/…", "sha256": "c410…", "bytes": 1073741824 } ],
      "resident_gb_est": 1.5,
      "optional": true
    }
  ]
}
```

```bash
rehearsal models fetch                 # downloads every non-optional file the manifest names
rehearsal models fetch --role tts      # optional components, explicit
rehearsal models verify                # re-hashes everything on disk against the manifest
rehearsal models verify --quick        # size + mtime only; for a fast preflight
rehearsal models list                  # what is installed, what the manifest wants, the delta
rehearsal models gc --keep 2           # drop all but the N most recent verified versions per role
```

Rules, all enforced in code, not in documentation:

- **Verify before use, always.** `rehearsal up` refuses to spawn a model host whose weights fail
  `models verify --quick`, and a full hash verification runs on first use of a newly fetched file and is
  recorded in `~/.rehearsal/models/.verified.json`. A corrupt half-download must fail at startup with a
  named error, never as garbled Spanish forty minutes into a session.
- **Content-addressed on disk.** Weights land at `models/<role>/<id>-<quant>-<sha256[:12]>/`. Two app
  versions can therefore hold two model versions simultaneously, which is what makes model rollback
  (§11.4) a symlink flip rather than a re-download.
- **`sha256` mismatch is fatal and loud.** The file is moved to `models/.quarantine/` with the expected
  and actual hashes in the error, never silently retried.
- **Resume is by range request; integrity is by hash.** A resumed download that hashes correctly is
  correct; there is no other definition of done.
- **The manifest is signed and its signature is checked before it is parsed.** An unsigned or
  bad-signature manifest is refused outright — this is the file that says which bytes are trusted, so it
  cannot itself be untrusted.

### 2.4 The portable fallback

llama.cpp is the fallback runtime, selected by `REHEARSAL_RUNTIME=llamacpp`, and exists so the project is
not hostage to one accelerator vendor. It is a *supported* path, not the *tested-to-parity* path: the
latency gates in `docs/08-evals.md` (EV-07) are stated against MLX on Apple Silicon, and any number
produced under llama.cpp is recorded with `runtime` in the eval registry so it is never quietly compared
to an MLX number. Building our own inference server remains out of scope (`docs/17-decisions.md`); both
runtimes are consumed as dependencies.

### 2.5 Offline install path

The target population includes clinics whose practical bandwidth makes a 20 GB download a multi-day
event, and machines whose network egress is restricted by policy. The bundle exists for them.

```bash
# On a connected machine
rehearsal bundle build --out /Volumes/transfer/rehearsal-bundle-0.6.2-macos-arm64.tar
```

```
rehearsal-bundle-0.6.2-macos-arm64.tar
├── MANIFEST.json                  # bundle version, app version, platform, per-entry sha256
├── MANIFEST.json.minisig
├── wheels/                        # rehearsal-0.6.2-*.whl + every transitive dependency, hash-pinned
│   └── requirements.lock          # uv-generated, hashes included
├── models/                        # the exact tree models-<n>.json describes
│   └── models-3.json{,.minisig}
├── scenarios/                     # the scenario bank at this release (docs/07-data-and-scenarios.md)
├── install.sh                     # verifies, then installs; no network calls, ever
└── CHECKSUMS.sha256
```

```bash
# On the target machine, no network required
tar -xf rehearsal-bundle-0.6.2-macos-arm64.tar && ./install.sh
rehearsal doctor
```

`install.sh` performs exactly three things: verify the bundle signature and every checksum, `uv pip
install --no-index --find-links wheels/`, and copy models into `REHEARSAL_MODEL_DIR`. It makes no network
call — asserted by the CI stage `offline-install` (§6), which runs the installer inside a
network-namespace-isolated container and fails if any socket is opened. "It should work offline" is not
a claim we are entitled to make without that test.

---

## 3. Environment and configuration

### 3.1 The three layers

Configuration resolves in one direction with no ambiguity. Later wins.

```
1. Code defaults            src/rehearsal/config.py           (typed, the source of truth for shape)
2. Machine file             $REHEARSAL_HOME/config.toml       (operator-owned, persistent)
3. Machine-measured file    $REHEARSAL_HOME/budget.local.json (written by `rehearsal doctor`, latency only)
4. Environment variables    REHEARSAL_*                       (session-scoped overrides, CI)
5. Explicit CLI flags       --model-dir, --port, …            (one invocation)
```

`rehearsal config show --resolved` prints the final values with the layer each came from. Every support
conversation that starts with "it's using the wrong model" ends with that command.

### 3.2 Variables

| Variable | Default | Purpose | Changing it requires |
|---|---|---|---|
| `REHEARSAL_HOME` | `~/.rehearsal` | Data root: db, blobs, logs, run sockets | Full restart |
| `REHEARSAL_MODEL_DIR` | `$REHEARSAL_HOME/models` | Weight tree; may be read-only and shared | Full restart |
| `REHEARSAL_RUNTIME` | `mlx` | `mlx` \| `llamacpp` | Full restart |
| `REHEARSAL_API_PORT` | `8420` | Loopback port for the API/SPA | Full restart |
| `REHEARSAL_LOG_LEVEL` | `info` | `debug` \| `info` \| `warn` \| `error` | SIGHUP |
| `REHEARSAL_LOG_AUDIO_TEXT` | `0` | If `1`, transcript text may appear in app logs | SIGHUP; see §7.4 |
| `REHEARSAL_TTS_BACKEND` | `neural` | `neural` \| `system` — forces DegradeLevel 3 when `system` | Next session |
| `REHEARSAL_GRADER_ENABLED` | `1` | `0` runs the loop extractor-only (DegradeLevel 2) | Next session |
| `REHEARSAL_RETENTION_DAYS` | `unset` | Floor below which `rehearsal gc` will not consider blobs | Next `gc` |
| `REHEARSAL_SEED` | `unset` | Pins the root seed; for reproduction and CI only | Next session |
| `REHEARSAL_ALLOW_DIRTY` | `0` | Permits build/eval commands on a dirty tree; never set in CI | — |

There is no configuration key for a remote endpoint, an API key, a telemetry URL, or an update server,
because no code path consumes one. `config.py` has no network section (`docs/03-system-architecture.md`
§4). That is the enforcement: the absence is structural, not policy.

### 3.3 Secrets

There are none to manage in the product. No API keys, no tokens, no database credentials (SQLite is a
file, protected by filesystem permissions), no service accounts. The only sensitive material in the
release process is the **signing key**, which lives on the release machine, never in the repository,
never in CI environment variables, and never in `~/.rehearsal/`. See §5.4.

### 3.4 Filesystem permissions

| Path | T1 mode | T2 mode | Why |
|---|---|---|---|
| `$REHEARSAL_HOME` | `0700` | `0750`, group `rehearsal` | Contains trainee audio |
| `$REHEARSAL_HOME/blobs` | `0700` | `0750` | Same |
| `$REHEARSAL_HOME/run/*.sock` | `0600` | `0600` | The socket *is* the model host's access control (`docs/03-system-architecture.md` §13.1) |
| `$REHEARSAL_MODEL_DIR` | `0755` | `0555` shared | Weights are not secret; read-only prevents accidental corruption |
| `$REHEARSAL_HOME/exports` | `0700` | `0700` | Human-initiated exports; the one place data is *meant* to leave |

`rehearsal doctor` checks these and reports a widened mode as a warning, not a silent fix. Changing a
user's filesystem permissions without asking is not our decision to make.

---

## 4. Health checks and model warm-up

### 4.1 Endpoints

```
GET /healthz    -> 200 {"ok": true, "version": "0.6.2"}     liveness: the process is answering
GET /readyz     -> 200 | 503 {...}                           readiness: a session could start now
GET /api/doctor -> 200 {...}                                 the full diagnostic, same data as the CLI
```

`/readyz` is the only one that matters operationally, and it is deliberately strict — it answers "would
`POST /api/sessions/{id}/start` succeed right now", not "is the process alive".

```jsonc
// GET /readyz
{
  "ready": false,
  "checks": {
    "store_open":        { "ok": true },
    "migrations":        { "ok": true,  "schema_version": 7 },
    "blob_root":         { "ok": true,  "writable": true, "free_gb": 84.2 },
    "models_verified":   { "ok": true,  "mode": "quick" },
    "host_live":         { "ok": true,  "warm": true,  "probe_ms": 141 },
    "host_grader":       { "ok": true,  "warm": false, "probe_ms": null },
    "scenario_bank":     { "ok": true,  "n_scenarios": 24, "graphs_valid": true },
    "audio_in":          { "ok": true,  "device": "MacBook Pro Microphone", "rate_hz": 48000 },
    "audio_out":         { "ok": true,  "device": "External Headphones" },
    "tts_voices":        { "ok": true,  "en_US": "…", "es_MX": "…" },
    "headphones":        { "ok": false, "detail": "output device is not a headset; echo risk" },
    "memory_headroom":   { "ok": true,  "resident_gb": 21.4, "total_gb": 48 },
    "budget_calibrated": { "ok": true,  "measured_at_commit": "a91f0c2" }
  },
  "blocking": ["host_grader"],
  "warnings": ["headphones"]
}
```

The split between `blocking` and `warnings` is the whole design. `headphones: false` is a warning
because a trainee may legitimately choose to proceed and accept that the echo guard
(`docs/03-system-architecture.md` §5) may flag turns; `host_grader: warm=false` is blocking for a
*graded* session because starting a session whose first three turns will be scored late produces a
misleading debrief. `rehearsal up --no-grader` makes that a deliberate DegradeLevel 2 session instead of
an accidental one.

### 4.2 Warm-up

Cold weights are the single largest startup cost and the most common cause of "the first turn felt
broken". Warm-up is therefore explicit and gated, not hoped for.

| Stage | What happens | Typical | Blocks |
|---|---|---|---|
| `spawn` | Host process forks, opens its socket | < 1 s | Everything |
| `load` | Weights mapped and, on MLX, resident pages touched | 20–60 s (live), 30–90 s (grader) | Session start |
| `probe` | One tiny inference per host — live: a 1 s audio clip; grader: a 40-token fixture turn | 1–3 s | `readyz` |
| `warm` | A second probe measured against `budget.local.json`; the host is `warm` only if it lands inside budget | 1–2 s | `readyz` for graded sessions |
| `steady` | Idle; hosts hold weights resident until `rehearsal down` | — | — |

The probes are **fixtures, not live content**: `data/fixtures/warmup/probe_en.wav` and
`data/fixtures/warmup/probe_turn.json`. Their outputs are compared to a recorded reference, so a warm-up
probe also catches a wrong-model-loaded error — the case where everything is healthy and the answers are
subtly wrong. A latency-only warm-up would pass happily while the grader ran the live model's weights.

Hosts are never spawned lazily on the first turn. `rehearsal up` blocks until warm, prints progress, and
the UI does not offer a start button before `/readyz` is green (`docs/09-ui-ux.md`).

---

## 5. Release process

### 5.1 Versioning

`MAJOR.MINOR.PATCH`, applied to a product that has more than one thing that can change incompatibly, so
the meaning is spelled out rather than assumed:

| Bump | Triggered by |
|---|---|
| **MAJOR** | A change that makes existing session data unreadable or existing numbers incomparable in a way migration cannot repair |
| **MINOR** | New capability; a forward-only schema migration; a prompt version change; a model id or quantisation change; a taxonomy or rubric change |
| **PATCH** | Bug fix with no schema, prompt, model or rubric change |

Four version numbers travel with every artefact and every eval record, and they are versioned
independently because they change independently:

| Version | Lives in | Changes when |
|---|---|---|
| `app_version` | git tag → wheel metadata | Any release |
| `schema_version` | `store/migrations/`, `PRAGMA user_version` | A migration is added |
| `prompt_version` | `prompts/<role>/vN.md`, hashed into the eval registry | Any prompt text change |
| `skill_version` | The packaged session skill (L6) | Protocol, rubric or taxonomy change |
| `manifest_version` | `models-<n>.json` | Model id, quant, or weight hash change |

A prompt change is a MINOR bump even when the wheel is otherwise identical, because
`docs/08-evals.md` treats prompt version as a first-class input to every number. A number attributed to
"0.6.2" must uniquely determine the prompt that produced it.

### 5.2 Changelog discipline

`CHANGELOG.md`, Keep-a-Changelog structure, one section per released version, **no unreleased entries
merged without a category**. Categories are the ones this product actually needs:

```markdown
## 0.6.2

### Scoring
- Negation extractor now handles Spanish double negation ("no … nada") as a single negation.
  Affects calibration items 07, 19, 31. `critical_recall` DEV 0.91 -> 0.93.

### Models
- Grader quantisation q4_0 -> q4_k_m (manifest 2 -> 3). Resident +0.8 GB. `kappa_macro` DEV 0.64 -> 0.67.

### Data
- Migration 0008: adds `sessions.degrade_max`. Forward-only. Rollback requires the pre-upgrade backup.

### Fixed
- Audio device change mid-session no longer aborts when a device with identical channel layout appears.

### Known gaps
- `kappa_inter` still absent; every published kappa is one rater's application of the taxonomy.
```

Two rules that are not optional:

- **Any entry that moves a gated metric quotes the before and after number and the split it was measured
  on.** A scoring change described only in prose is unreviewable.
- **The "Known gaps" section is never empty and is never allowed to shrink silently.** Removing a gap
  requires the entry that closed it. This is principle 7 applied to the changelog: gaps are stated, not
  papered over.

### 5.3 Release gates

A release is cut only when every gate below is green **on a clean tree at the tagged commit**. The eval
gates are not restated here — they are owned by `docs/08-evals.md` §1.1 and this table links to them so
there is exactly one definition of each threshold.

| Gate | Source of truth | Threshold | Why it blocks a release |
|---|---|---|---|
| `extractor_conformance` | `docs/08-evals.md` EV-00 | `= 1.00` | The neuro-symbolic split assumes this layer is provably correct; below 1.00 nothing downstream is trustworthy |
| `critical_recall` | `docs/08-evals.md` EV-02 | `≥ 0.90` DEV, TEST reported with interval | This is the clinical-consequence class |
| `fp_rate_clean` | `docs/08-evals.md` EV-01 | `≤ 0.15` DEV | False alarms teach trainees to distrust the instrument |
| `regression_delta` | `docs/08-evals.md` EV-09 | Full table in EV-09 | Prevents a fix in one place silently breaking another |
| `persona_consistency` | `docs/08-evals.md` EV-04 | `≥ 0.95`; rubric-vocabulary canary `= 1.00` | The canary is the runtime proof of information isolation |
| `p95_first_audio_ms`, `p99_barge_in_stop_ms` | `docs/08-evals.md` EV-07 | Budget constants | Below-budget realism is a product failure |
| `session_completion_rate` | `docs/08-evals.md` EV-08 | `≥ 0.90` | A session that cannot finish produces no report |
| `grader_backlog_rate` | `docs/08-evals.md` EV-07 | `≤ 0.05` | Backlog is what breaks the off-critical-path premise |
| Migration round-trip | This document §11.2 | Green | Upgrade must be provably survivable |
| Offline install | This document §6 | Green, zero sockets opened | The bundle is a promise to bandwidth-constrained sites |
| Signature verification | §5.4 | All artefacts verify with the published key | An unverifiable artefact is not a release |
| Changelog completeness | §5.2 | Every gated metric that moved is quoted | A silent metric move is the easiest dishonest release |
| `plans/metrics-snapshot.md` current | `SETUP.md` §9 | Regenerated at the tagged commit | Headline numbers must describe the thing being released |

`make release-check` runs the machine-checkable subset and prints the table with each row green or red.
The human-checkable rows (changelog completeness, gap statement) are a printed checklist that the
releaser confirms; they are not automated because automating a judgement produces the appearance of one.

### 5.4 Signing

Artefacts are signed with `minisign` (small, auditable, no PKI to operate — appropriate for a project
that will never run a certificate authority).

```bash
minisign -Sm dist/rehearsal-0.6.2-py3-none-any.whl -s ~/.keys/rehearsal.key
minisign -Sm dist/models-3.json                    -s ~/.keys/rehearsal.key
minisign -Sm dist/rehearsal-bundle-0.6.2-macos-arm64.tar -s ~/.keys/rehearsal.key
```

- The public key is published in the repository at `deploy/rehearsal.pub` and in `SETUP.md`, so it can be
  compared across two independent channels.
- The private key never enters CI. CI produces unsigned artefacts and marks them `unsigned-ci`; a signed
  artefact is produced only by a human on the release machine.
- `install.sh` and `rehearsal models fetch` verify signatures before use and refuse on failure — no
  `--skip-verify` flag exists, because the flag that exists is the flag that gets used.
- Key rotation is a one-way door: publish the new public key alongside the old, sign the next two
  releases with both, then retire the old. The rollback plan is that the old key remains valid for
  verifying already-published artefacts forever; retirement means "stop signing with it", never
  "invalidate what it signed".

### 5.5 Release sequence (dependency order)

```
clean tree at tag
  └─► make check                     lint, types, tests, EV-00, EV-09
        └─► make evals               full DEV suite; gate table printed
              └─► rehearsal-evals unseal --reason "release 0.6.2"   TEST, reported not gated
                    └─► make build                wheel + sdist + manifest
                          └─► rehearsal bundle build
                                └─► install both artefacts on a clean machine; rehearsal doctor green
                                      └─► sign
                                            └─► regenerate plans/metrics-snapshot.md; write CHANGELOG
                                                  └─► tag pushed, artefacts published
```

The clean-machine install is before signing, not after, because an artefact that fails to install is not
one we want a signature attesting to.

---

## 6. Continuous integration

Stages run in dependency order. Each stage's gate is what it *blocks*, and a stage that blocks nothing is
deleted rather than kept as decoration.

| # | Stage | Command | Runs on | Typical | Blocks on failure | Why it is at this position |
|---|---|---|---|---|---|---|
| 1 | `lint` | `ruff check . && ruff format --check .` | Every push | 10 s | Everything after it | Cheapest signal first; a formatting diff pollutes every later review |
| 2 | `types` | `uv run mypy src/ --strict` | Every push | 40 s | 3+ | Typed orchestration is the credibility argument (`docs/03-system-architecture.md` §15); untyped code is a defect |
| 3 | `unit` | `uv run pytest tests/unit -q` | Every push | 90 s | 4+ | Pure logic: state machine transitions, budget arithmetic, merge precedence, seed derivation |
| 4 | `extractors` | `uv run rehearsal-evals run --eval EV-00` | Every push | 30 s | 5+ | EV-00 must be `1.00`; the neuro-symbolic split is void otherwise. No model required, so it runs before anything that needs weights |
| 5 | `isolation` | `uv run pytest tests/isolation -q` | Every push | 20 s | 6+ | Asserts `ContextAssembler` field allowlists per role and that the rubric vocabulary never appears in a counterpart context. A static test of the project's central claim, and it needs no model |
| 6 | `migrations` | `uv run rehearsal-store migrate-test` | Any change under `store/` | 60 s | 7+ | Applies every migration to a golden fixture db, folds the event log, asserts projections match. Blocks §11.2 |
| 7 | `frontend` | `npm ci && npm run build && npm test` | Any change under `frontend/` | 3 min | 8+ | Includes the axe-core accessibility pass and contrast assertions for both themes (`docs/09-ui-ux.md`) |
| 8 | `integration` | `uv run pytest tests/integration -q` | Every push | 4 min | 9+ | Full orchestration against **stub model hosts** at fixed seeds: session lifecycle, crash-resume, degradation ladder, WS gap-fill. Deterministic, no weights |
| 9 | `package` | `make build` | Every push to a release branch, and tags | 2 min | 10+ | Proves the wheel builds and the SPA is embedded as package data |
| 10 | `offline-install` | `deploy/ci/offline_install_test.sh` | Tags | 6 min | 11+ | Installs the bundle in a network-isolated container; **fails if any socket is opened.** The offline promise is tested, not asserted |
| 11 | `smoke` | `rehearsal doctor --no-models && rehearsal replay --verify data/fixtures/sessions/` | Tags | 90 s | Release | Replays recorded sessions and asserts byte-identical projections; catches a fold-logic change that unit tests missed |
| 12 | `evals-full` | `make evals` | Manual / release only | 25 min+ | Release | Needs real weights and a real machine. Deliberately **not** on every push: a gate that takes half an hour on every commit gets bypassed, and a bypassed gate is worse than no gate |

**Runner reality.** Stages 1–10 run on a standard CI runner with no accelerator and no model weights,
which is why every one of them uses stub hosts or fixtures. Stage 12 requires the reference machine
(Apple Silicon, 48 GB) and is run on a self-hosted runner or by hand before a release; its results enter
the eval registry with `host_class` recorded, so a number produced on a different machine is never
silently compared to one produced on the reference machine.

**What CI deliberately does not do:** it does not publish, does not sign, does not touch the TEST split
(`rehearsal-evals` refuses without an explicit unseal reason), and does not have credentials for
anything. CI produces artefacts and verdicts; humans produce releases.

---

## 7. Observability without telemetry

### 7.1 The statement

**Nothing is transmitted. Ever.** No usage analytics, no crash reports, no error aggregation, no update
checks, no license validation, no anonymous metrics, no "help us improve" prompt. The application makes
no outbound network connection at any point during normal operation. The only commands that touch the
network are `rehearsal models fetch` and `rehearsal bundle build`, both explicitly invoked, both fetching
from a URL the user can read in the manifest.

This is enforced three ways rather than promised once:

1. **Structurally.** `config.py` contains no network configuration, and the runtime has no HTTP client
   dependency in its import graph outside the fetch commands.
2. **By test.** `tests/integration/test_no_egress.py` runs a full stub-model session with outbound
   sockets blocked at the loopback boundary and fails if anything attempts a connection. Stage 8.
3. **By observation.** `rehearsal doctor` reports the process's open sockets, so a user can check the
   claim themselves rather than believe it.

The reason is not ideology. It is that the data in this system is a trainee's recorded voice, their
error rates, and their improvement curve — material that is professionally sensitive and, in a small
community like the Pajaro Valley, effectively identifying. See `docs/12-security-privacy.md`. A telemetry
pipeline is a thing that can be misconfigured; an absent one cannot be.

### 7.2 Local structured logs

```
$REHEARSAL_HOME/logs/
├── api-2025-… .jsonl          # rotated at 64 MB, 10 files retained
├── live-… .jsonl
├── grader-… .jsonl
└── audio-… .jsonl
```

One JSON object per line, one schema, no free-form messages that a script cannot parse:

```jsonc
{
  "ts": "…",                 // ISO-8601 UTC, millisecond precision
  "lvl": "info",
  "proc": "api",             // api | live | grader | audio | tts
  "comp": "TurnScheduler",   // the component from docs/03-system-architecture.md §5
  "sid": "01J…",             // session id, ULID; null outside a session
  "turn": 14,                // null outside a turn
  "seq": 288,                // the event-log seq this line corresponds to, when there is one
  "evt": "turn.scored",
  "ms": 812,                 // duration when this line closes a timed span
  "msg": "verdict merged",
  "d": { "findings": 2, "critical": 0, "degrade": 0 }
}
```

**Logs are not the event log.** The event log in `rehearsal.db` is the record and is never truncated by
an operator action; `logs/` is operator convenience, is rotated, and is safe to delete at any time
(`docs/03-system-architecture.md` §13.4). Confusing the two is the mistake this separation exists to
prevent.

**Logs contain no transcript text by default.** Utterances are referenced by their blob `sha256`, never
inlined, because a log file has weaker handling discipline than the blob store and gets pasted into chat
windows. `REHEARSAL_LOG_AUDIO_TEXT=1` enables inline text for local debugging, prints a warning banner on
every startup while it is set, and is refused entirely when `REHEARSAL_HOME` is a T2 shared root.

### 7.3 Per-turn timing metrics

Every turn writes one timing row. This is the operational half of the latency budget that EV-07 gates,
and it exists so that "it felt laggy" becomes a number.

```sql
-- projection, rebuildable from the event log
CREATE TABLE turn_timings (
    session_id           TEXT NOT NULL,
    turn_index           INTEGER NOT NULL,
    speaker              TEXT NOT NULL,   -- clinician | patient
    capture_start_ms     INTEGER NOT NULL,   -- all offsets are relative to session start
    endpoint_ms          INTEGER NOT NULL,   -- VAD declared end of trainee speech
    first_token_ms       INTEGER,            -- counterpart model first token
    first_audio_ms       INTEGER,            -- first TTS frame out  -> p95_first_audio_ms
    barge_in_stop_ms     INTEGER,            -- onset -> silence     -> p99_barge_in_stop_ms
    grader_enqueued_ms   INTEGER,
    grader_started_ms    INTEGER,
    grader_wall_ms       INTEGER,            -- total grader latency, off critical path
    grader_backlog_depth INTEGER NOT NULL,   -- queue depth at enqueue -> grader_backlog_rate
    degrade_level        INTEGER NOT NULL,
    PRIMARY KEY (session_id, turn_index)
) STRICT;
```

```bash
rehearsal metrics --session <id>            # per-turn table for one session
rehearsal metrics --last 20 --p95           # rolling p50/p95/p99 across recent sessions
rehearsal metrics --compare-baseline        # against budget.local.json, the machine's measured budget
```

`grader_wall_ms` exceeding the trainee's own speaking time is the definition of the off-critical-path
premise failing, and `grader_backlog_depth > 0` is the leading indicator. Both are visible per turn, not
only in aggregate, because a backlog that appears on turns 12–15 of every session is a scheduling bug and
an aggregate p95 hides it.

### 7.4 The diagnostics bundle

The only way information leaves the machine, and it is a deliberate human action with a preview step.

```bash
rehearsal diag --out ~/Desktop/rehearsal-diag.tar.gz          # redacted by default
rehearsal diag --preview                                       # prints exactly what would be included
rehearsal diag --include-session <id> --include-audio          # requires an interactive confirmation
```

| Included by default | Excluded by default |
|---|---|
| `doctor` output: versions, config (resolved), hashes, device names | Any transcript text |
| The last 2000 log lines per process, with text fields stripped | Any audio blob |
| `turn_timings` for the last 10 sessions | Trainee ids (replaced with stable salted pseudonyms) |
| Event-log *kinds* and seq numbers, not payloads | Event payloads |
| Migration history, `schema_version`, integrity-check result | Scenario content the user has authored |
| Model manifest and verification state | The signing key, obviously |

`--preview` prints the exact tarball contents and a byte count before anything is written. Nothing is
uploaded; the file lands where the user asked and they decide what to do with it. Including a session's
transcripts or audio requires two explicit flags and a typed confirmation, because that is trainee voice
data and no default should make it easy to hand over.

---

## 8. Failure runbooks

### 8.1 Index

| # | Failure | Symptom the user reports | First diagnostic | Blast radius |
|---|---|---|---|---|
| R1 | Model fails to load | "It hangs on Starting, or quits with an error" | `rehearsal doctor --verbose`; tail `logs/live-*.jsonl` | Session cannot start |
| R2 | Latency budget exceeded | "It talks over me / long awkward pauses" | `rehearsal metrics --last 5 --p95` | Realism, not correctness |
| R3 | Audio device lost | "It stopped hearing me" | `/readyz` `audio_in`; `logs/audio-*.jsonl` | Turn, then session |
| R4 | Grader backlog | "Feedback catching up banner, scores arrive late" | `rehearsal metrics --session <id>` column `grader_backlog_depth` | Feedback timeliness |
| R5 | Corrupt session state | "The report is wrong / the session won't reopen" | `rehearsal replay --verify <id>` | One session's projections |
| R6 | Disk full | "Session paused, won't resume" | `df`; `rehearsal gc --dry-run` | All writes |
| R7 | Blob hash mismatch | "A turn's audio won't play" | `rehearsal blobs verify` | One turn's audio |
| R8 | Schema/version mismatch after upgrade | "It refuses to start after updating" | `rehearsal doctor`, `schema_version` row | Everything |

### 8.2 R1 — Model fails to load

**Symptom.** `rehearsal up` never reaches warm; `/readyz` shows `host_live` or `host_grader` not ok; the
host process exits, sometimes repeatedly. In the UI, the start control never enables.

**Diagnosis, in order — stop at the first that explains it.**

1. `rehearsal models verify` — a truncated or corrupt download is the most common cause and the easiest
   to confirm. A `sha256` mismatch names the file.
2. `rehearsal doctor --verbose | grep memory` — is another large process resident? MLX cannot map weights
   that do not fit, and the failure surfaces as an allocation error, not as "out of memory" in plain
   words.
3. `tail logs/live-*.jsonl` — distinguish a *load* error (bad file, unsupported quantisation, runtime
   mismatch) from a *probe* error (loads fine, produces wrong output). A probe mismatch means the wrong
   weights are installed for this app version — check `compatible_app_range` in the manifest.
4. `rehearsal models list` — is the installed manifest version compatible with this app version?

**Action.**

| Cause | Action |
|---|---|
| Hash mismatch | `rehearsal models fetch --role <role> --force` (re-downloads only the failing files), then `verify` |
| Memory pressure | Close the offending process; if it cannot be closed, `rehearsal up --no-grader` runs a valid DegradeLevel 2 session with critical checks only and the banner shown |
| Manifest incompatible with app | Roll the model version back (§11.4) or upgrade the app; never mix |
| Runtime mismatch (MLX weights on a Linux box) | `REHEARSAL_RUNTIME=llamacpp` with the llama.cpp-quantised files from the manifest |
| Repeated crash with no clear cause | `rehearsal diag --preview`, then file it. Do **not** loop restarts: two failed loads inside a session abort it by design (`docs/03-system-architecture.md` §5) |

**Do not:** delete `$REHEARSAL_HOME` to "start fresh". That destroys the event log and every recorded
session. Reinstalling models is `rehearsal models fetch --force`; nothing about a model problem requires
touching session data.

### 8.3 R2 — Latency budget exceeded

**Symptom.** The counterpart starts speaking noticeably after the trainee stops; barge-in does not stop
the voice promptly; `p95_first_audio_ms` above budget in `rehearsal metrics`.

**Diagnosis.**

1. `rehearsal metrics --last 5 --p95` — which stage? `first_token_ms` high implicates the live model host;
   `first_audio_ms - first_token_ms` high implicates TTS; `barge_in_stop_ms` high implicates the audio
   output path, not the model at all.
2. `rehearsal metrics --compare-baseline` — is this machine slower than the budget it was calibrated
   with? `budget.local.json` records the commit it was measured at; a stale calibration after a model
   change produces exactly this.
3. Is `degrade_level` already > 0? If the ladder is engaged, the user is seeing the *documented*
   degraded experience, which is a different conversation from a regression.
4. Thermal state and background load. A laptop at thermal limit produces this symptom and no code change
   fixes it.

**Action.**

| Cause | Action |
|---|---|
| Stale budget after a model or runtime change | `rehearsal doctor --recalibrate` rewrites `budget.local.json` from measured timings |
| TTS stall | `REHEARSAL_TTS_BACKEND=system` — DegradeLevel 3, visible in the UI and noted in the debrief |
| Live host slow under grader contention | `rehearsal up --no-grader` for the session; the grader is the shed-able one by design (principle 5) |
| Machine below spec | Text mode (DegradeLevel 4) is a legitimate, honest fallback; the session is marked `text_mode` and excluded from voice-latency statistics so it never contaminates a reported number |
| Genuine regression | Compare against `data/evals/baselines/`; EV-07 exists for this and a merge that regressed p95 by more than 10% should not have landed |

**Never:** widen the budget constants to make the gate pass. The budget describes what a conversation
needs to feel real, not what the current build achieves.

### 8.4 R3 — Audio device lost

**Symptom.** Capture stops mid-session; `capture_lost` in the log; the UI shows the input meter dead.
Typical trigger: Bluetooth headset disconnect, a USB interface unplugged, or macOS switching default
device when another app grabs it.

**Diagnosis.** `logs/audio-*.jsonl` names the device that vanished and whether a replacement with an
identical channel layout appeared. `GET /readyz` `audio_in` reports the current device.

**Action.** The orchestrator already implements the policy; the runbook is about what the human does
around it:

1. Reconnect the device within 10 seconds and the session resumes at the turn boundary — the in-flight
   turn is marked `capture_lost` and re-offered, not scored on partial audio. A partially captured turn
   must never be scored; a missing rendering scored as an omission would be a fabricated error against a
   trainee.
2. Beyond 10 seconds unrecoverable, the session aborts cleanly with reason `audio_device`. The event log
   prefix is complete and valid; `rehearsal session resume <id>` continues from the last committed turn.
3. If the trainee chooses to continue without audio, DegradeLevel 4 (text mode) is offered explicitly and
   the session is flagged.

**Prevention worth stating:** wired headphones. `readyz` warns when output is not a headset because
speaker output means the TTS voice enters the microphone and the echo-correlation guard has to
disambiguate the trainee from the machine. It usually can. "Usually" is not what you want scoring a
dosage.

### 8.5 R4 — Grader backlog

**Symptom.** "Feedback catching up" indicator persists; verdicts arrive several turns late; at the
extreme, DegradeLevel 2 engages and the debrief shows `partial` verdicts with semantic categories marked
*not assessed*.

**Diagnosis.**

1. `rehearsal metrics --session <id>` — `grader_backlog_depth` per turn. Monotonically rising means
   throughput is below arrival rate (structural); spiking on particular turns means those turns are
   unusually long or the grader retried.
2. `grader_wall_ms` versus the trainee's own speaking time on those turns. Principle 5 spends the human's
   speaking time as the latency budget; short trainee turns shrink that budget, and rapid-fire short
   renderings are the realistic worst case.
3. `logs/grader-*.jsonl` for schema-validation retries. One retry at temperature 0 is normal; a pattern
   of retries is a prompt or model regression and belongs in EV-09, not in a runbook.

**Action.**

| Cause | Action |
|---|---|
| Transient spike | None. The queue is bounded and durable via the event log; it drains. L1 shedding of coach hints exists exactly for this |
| Sustained, this machine | Reduce grader load: `REHEARSAL_GRADER_ENABLED=0` for extractor-only sessions, or accept L2. Both are visible to the trainee |
| Sustained after a change | Regression. `rehearsal-evals run --eval EV-07`, compare to baseline, and treat `grader_backlog_rate > 0.05` as a release blocker, which it is |
| Grader host killed under memory pressure | Expected behaviour, not a failure — the grader is the sacrificial process (`docs/03-system-architecture.md` §13.1). Verdicts are `partial`, the banner is shown, and the session continues |

**The thing to never do:** move the grader onto the critical path to "make feedback timely". Scoring the
current turn before the next one begins is the design being abandoned, not the design being tuned. Late
feedback with an honest banner beats prompt feedback that stalls the conversation.

### 8.6 R5 — Corrupt session state

**Symptom.** A session will not reopen, its report is missing turns, or `rehearsal replay --verify`
reports a divergence between the folded event log and the stored projections.

**Diagnosis.**

1. `rehearsal replay --verify <session_id>` — the authoritative check. It refolds the event log and diffs
   against `turns`, `verdicts`, `findings`, `turn_timings`.
2. `PRAGMA integrity_check` via `rehearsal store check` — distinguishes database-level corruption
   (rare; usually a hardware or forced-shutdown event) from projection drift (a code bug).
3. Hash-chain validation: `rehearsal store verify-chain <session_id>`. A break identifies the exact `seq`
   where the log stopped being trustworthy.

**Action.**

| Finding | Action |
|---|---|
| Projection drift, event log intact | `rehearsal store rebuild-projections --session <id>`. Projections are derived data by design and this is the routine repair |
| Hash chain intact up to seq N, garbage after | `rehearsal session truncate <id> --after <N>` — keeps the valid prefix as a completed short session. A truncated session is reported as truncated, never silently as a full one |
| SQLite integrity failure | Stop immediately. Restore from the most recent `rehearsal backup` (§10). Do not run `VACUUM` or `.recover` against the live file first — that is a one-way door that can destroy what a restore would have recovered |
| Blob referenced but absent or mismatched | R7. The turn is marked `blob_corrupt`; text-based scoring remains valid and the report says so |

**Why this is recoverable at all:** the event log is append-only and hash-chained, and every table that
matters is a projection of it (`docs/03-system-architecture.md` §10). Corruption of derived state is an
inconvenience. That property is worth the write amplification it costs.

### 8.7 R6, R7, R8 — briefly

| | Symptom | Diagnosis | Action |
|---|---|---|---|
| **R6 disk full** | Session pauses at a turn boundary, refuses to continue | `df -h $REHEARSAL_HOME`; `rehearsal gc --dry-run` | Free space, then `rehearsal session resume`. The pause is deliberate: an unlogged session is worse than a stopped one. `gc` deletion always requires a second explicit invocation |
| **R7 blob mismatch** | A turn's audio will not play; `blob_quarantined` event | `rehearsal blobs verify --session <id>` | Blob moves to `blobs/.quarantine/`; the turn is marked and its text-based verdict stands. Audio is not recoverable — this is why `rehearsal backup` includes blobs |
| **R8 version mismatch** | Refuses to start after an upgrade or a partial rollback | `rehearsal doctor`: app version vs `schema_version` vs `manifest_version` | If `schema_version` is ahead of the app, the app was rolled back past a forward-only migration — restore the pre-upgrade backup (§11.3). If the manifest is incompatible, roll the model version (§11.4) |

---

## 9. Capacity and scaling characteristics

### 9.1 What scales with what

| Dimension | Scales with | Shape | Practical ceiling |
|---|---|---|---|
| Resident memory | Number of loaded model roles, not sessions or users | Step function: ~7 GB live + ~9 GB grader + ~1.5 GB neural TTS + < 0.5 GB app ≈ 18–21 GB, target 20–24 GB with buffers on 48 GB | One set of weights per machine. A second concurrent session would double it and does not fit |
| Concurrent sessions | **Fixed at 1** | Not a scaling dimension | One microphone, one human, one turn at a time. This is a property of the product, not a limitation of the implementation |
| Turn throughput | Grader wall time versus trainee speaking time | The binding constraint | **The grader is the throughput bottleneck.** It is the largest model and it must finish turn *n* before turn *n+1* ends |
| Storage | Audio minutes retained | ~0.5 MB per trainee-minute (opus 16 kHz mono) + a few KB per turn of text and events | A 30-minute session ≈ 15–20 MB. 200 sessions ≈ 3–4 GB. Grows monotonically until `gc` |
| Database size | Turns and events, not audio | ~4–8 KB per turn across events and projections | Thousands of sessions before SQLite is remotely stressed |
| Startup time | Weight size and disk speed | 50–150 s cold, near-zero warm | Amortised across a session; §4.2 |
| CPU/GPU | One session's decode | Near-saturating during a turn, idle between | The machine is not doing anything else during a session, by design |

### 9.2 The bottleneck, stated precisely

The grader is the bottleneck and everything about the architecture is arranged around that fact.
Principle 5 buys the latency: grading turn *n* runs while the trainee speaks turn *n+1*, so grader wall
time is free as long as it is shorter than the trainee's next utterance. The system is therefore
throughput-limited by

```
grader_wall_ms  <  trainee_speaking_ms(next turn)
```

and the failure mode is not "slow", it is **backlog** (R4), which is measured directly as
`grader_backlog_rate` and gated at ≤ 0.05 in `docs/08-evals.md`. Short, rapid trainee renderings shrink
the budget; this is a real and expected regime, and the response is the degradation ladder, not a bigger
machine.

### 9.3 What T2 does and does not change

Nothing about the per-session numbers. A training program running T2 gets one session at a time on that
machine. Ten trainees means either a queue or ten machines. Sharing one machine changes only storage
growth (linear in total trainee-minutes across all users) and backup volume.

### 9.4 What has not been load-tested — stated honestly

This is the section that should not be smoothed over.

| Not tested | Why it matters | What would establish it |
|---|---|---|
| Sustained multi-hour operation | Memory fragmentation, MLX allocator behaviour, and thermal throttling over a long session are unmeasured. All latency numbers come from sessions of roughly 20–40 minutes | A soak test: 4 hours of continuous scripted sessions with `turn_timings` and RSS sampled throughout |
| Store behaviour at thousands of sessions | Projection rebuild time, `gc` mark-and-sweep time, and query latency at that scale are extrapolations from small data | A synthetic store generator plus timing of `rebuild-projections` and `gc` at 10× and 100× current volume |
| Concurrent-session behaviour | Explicitly unsupported, and **not merely untested** — there is no admission control preventing two `rehearsal up` invocations against one `REHEARSAL_HOME` today | Either a lock file that refuses the second instance (proposed, small) or a tested concurrency story. The lock is the right answer; see §12 |
| llama.cpp latency parity | The fallback runtime's latency has not been measured against the budget constants at all | EV-07 executed under `REHEARSAL_RUNTIME=llamacpp`, reported separately and never pooled with MLX numbers |
| Recovery from mid-write power loss | Crash-resume is tested by killing processes; it is not tested by cutting power during a WAL checkpoint | Hardware-level fault injection, or an honest statement that SQLite WAL durability is the guarantee we inherit and do not independently verify |
| Long-horizon storage growth in T2 | With several trainees on one machine, growth rate has not been observed in practice | Instrument `rehearsal gc --dry-run` output over a pilot and report actual MB/trainee-hour |

Every latency figure in this document is an order-of-magnitude planning estimate from a single reference
machine class, not a measured distribution. The measured distributions live in
`plans/metrics-snapshot.md` and are produced by EV-07. Where this document and that file disagree, that
file is right.

---

## 10. Backup and data portability

### 10.1 What must survive

| Data | Recoverable if lost? | Backup priority |
|---|---|---|
| `rehearsal.db` (event log) | **No.** This is the record | Highest |
| `blobs/` trainee audio | **No.** Re-recording is not the same data | Highest |
| `blobs/` canonical text | No, but recoverable from the event log if the log survives | High |
| `budget.local.json` | Yes — `rehearsal doctor --recalibrate` | Low |
| `models/` | Yes — `rehearsal models fetch` | Low (but 20 GB, so back up if bandwidth is scarce) |
| `logs/` | No, and it does not matter | None |
| `exports/` | Yes, regenerable | None |

### 10.2 Backup

```bash
rehearsal backup --out /Volumes/backup/rehearsal-<date>.tar.zst
rehearsal backup --out … --no-audio          # metadata and event log only; much smaller
rehearsal backup verify /Volumes/backup/…    # restores to a temp root and folds the log
rehearsal restore --from /Volumes/backup/… --to /tmp/restore-check   # never in place by default
```

- The database is captured with SQLite's online backup API, not a file copy. A file copy of a live WAL
  database is a corrupt database, and this is a mistake that only surfaces at restore time, which is the
  worst possible time.
- Blobs are copied by content hash and verified after copy. The backup is self-verifying: `backup verify`
  refolds the event log and checks every referenced blob is present and hashes correctly.
- `restore` writes to a new root by default. Restoring over a live root requires `--force` and a stopped
  application, because clobbering an event log with an older one is a one-way door.
- **Nothing about backup is automatic.** There is no background job writing to a location the user did
  not name. A scheduled backup in T2 is the operator's own cron invoking `rehearsal backup`.

### 10.3 Portability and export

The user's data is theirs and must be readable without this application ever running again. Two formats:

| Command | Format | For |
|---|---|---|
| `rehearsal export session <id> --format json` | One JSON document: turns, source text, rendering text, findings with spans and severities, verdicts, review overrides, timings | Programmatic reuse, research, moving to another machine |
| `rehearsal export session <id> --format md` | Human-readable fidelity report, the same content the debrief shows | A trainee keeping their own record; a trainer's file |
| `rehearsal export trainee <id> --format csv` | Per-category error rates over time, one row per session | Program-level review in a spreadsheet |
| `rehearsal export session <id> --with-audio` | The above plus opus files, named by turn | Full portability; requires explicit confirmation |

Exports run a redaction pass by default (`docs/03-system-architecture.md` §12, boundary B7) and land in
`$REHEARSAL_HOME/exports/`. They are a **human-initiated action**, never triggered by the application,
and the export view shows exactly what is included before writing. Schema documentation for the JSON
export lives with the scoring types in `docs/06-scoring-engine.md`; the export is the taxonomy structure
serialised, not a separate model.

---

## 11. Upgrade and rollback

### 11.1 Classification first

Applying the reversibility rule before any upgrade:

| Change | Door | Consequence |
|---|---|---|
| App version, no migration | Two-way | Reinstall the previous wheel |
| App version with a forward-only migration | **One-way** | The database is migrated; the old app cannot read it. The pre-upgrade backup is the only rollback |
| Frontend only | Two-way | Ships in the wheel; reverting the wheel reverts it |
| Model version | Two-way **by construction** | Content-addressed directories keep both versions; rollback is a pointer change (§11.4) |
| Prompt version | Two-way | Prompt files are package data; the old version comes back with the old wheel. Verdicts are keyed by prompt version and never overwritten, so old numbers remain valid |
| Scenario bank | Two-way | Content-addressed; sessions reference the scenario version they ran |

### 11.2 Upgrade procedure

```bash
rehearsal down                                    # 1. stop; never upgrade under a running session
rehearsal backup --out ~/rehearsal-pre-0.6.2.tar.zst    # 2. mandatory; the tool refuses to migrate without a backup newer than the db mtime
uv pip install --no-index --find-links wheels/ rehearsal-0.6.2-py3-none-any.whl   # 3.
rehearsal models fetch                            # 4. only if manifest_version changed
rehearsal migrate --dry-run                       # 5. prints every migration and whether it is reversible
rehearsal migrate                                 # 6. one transaction per migration
rehearsal doctor                                  # 7. must be green before use
rehearsal replay --verify --last 5                # 8. recent sessions must still fold identically
```

Step 2 is enforced in code: `rehearsal migrate` refuses to run when there is no backup newer than the
database's last modification, and there is no flag to skip it. This is the single most consequential
one-way door in the system and it gets a guard rather than a paragraph.

Step 8 is the real acceptance test. A migration that applies cleanly but changes how an existing event
log folds has silently altered recorded history, and a diff of the folded projections is the only thing
that catches it. CI stage 6 runs the same check against golden fixtures.

### 11.3 Rollback

| Situation | Procedure |
|---|---|
| No migration was applied | `uv pip install rehearsal-<previous>` and restart. Done |
| A migration was applied | `rehearsal down`; `rehearsal restore --from <pre-upgrade backup> --to $REHEARSAL_HOME --force`; reinstall the previous wheel; `rehearsal doctor`. **Sessions recorded after the upgrade are lost** — this is why the backup is mandatory and why the tool prints the count of post-backup sessions before restoring |
| Upgrade failed mid-migration | Each migration runs in one transaction, so the database is at a migration boundary, never inside one. `rehearsal doctor` reports `schema_version`; re-run `rehearsal migrate` or restore |
| Frontend broken, backend fine | Roll the wheel back; there is no independent frontend rollback and that is deliberate — a mismatched pair is not a state we permit |

### 11.4 Model version rollback

Model rollback is a first-class operation, separate from app rollback, because a model regression is at
least as likely as a code regression and needs to be reversible without touching session data.

```bash
rehearsal models list
# role    id                 quant   sha256[:12]   installed   active   verified
# live    gemma-4-e4b-it     q4_k_m  9f2ce41a08b1  yes         yes      2025-…
# grader  gemma-12b-it     q4_k_m  77de0a91c3f4  yes         yes      2025-…
# grader  gemma-12b-it     q4_0    41b8c02de77a  yes         no       2025-…

rehearsal models use --role grader --sha256 41b8c02d     # flip the active pointer
rehearsal down && rehearsal up                            # reload weights
uv run rehearsal-evals run --eval EV-09                   # re-establish where the numbers now stand
```

Why this is cheap: weights live in content-addressed directories (§2.3) and `active` is a symlink per
role. Rolling back is a pointer flip and a restart, with no download, provided `rehearsal models gc
--keep 2` has not reaped the old version — which is why the default keeps two.

Why it is not free: **a model change invalidates every gated number.** The active model id, quantisation
and weight hash are recorded in every eval registry row (`docs/08-evals.md` §7), so a rollback does not
corrupt the record — but it does mean the current headline numbers describe a model that is no longer
loaded. `rehearsal doctor` warns when the active model hashes differ from those in the most recent
`plans/metrics-snapshot.md` run, and EV-09 must be re-run before any number is quoted again. Verdicts
already stored are unaffected: `verdict_key` includes the model and prompt version, so old verdicts stay
attributed to the model that produced them and are never retroactively rewritten.

---

## 12. Status register

| Item | Status | Note |
|---|---|---|
| Two deployment targets, both single-tenant | **Decided** | Multi-tenant fleet scaling is out of scope (`docs/17-decisions.md`) |
| Zero telemetry, enforced structurally and by test | **Decided** | Non-negotiable; `docs/12-security-privacy.md` |
| Frontend embedded in the wheel, no separate artefact | **Decided** | Prevents API/SPA version skew |
| `minisign` for artefact signing | **Decided** | Chosen for auditability and no PKI; alternatives would need a reason to switch |
| Mandatory backup before migration, no skip flag | **Decided** | The largest one-way door in the system |
| Content-addressed model directories enabling pointer-flip rollback | **Decided** | Makes model rollback two-way |
| Single-instance lock on `REHEARSAL_HOME` | **Proposed** | Today nothing stops a second `rehearsal up` against the same root. Small fix, real risk. Named in §9.4 |
| Retention defaults for `rehearsal gc` | **Open** | No default retention floor is set. Correct value depends on a real program's record-keeping obligations, which we have not gathered |
| llama.cpp latency parity | **Open** | Fallback path is supported but unmeasured; numbers must stay segregated by `runtime` |
| Supervised service units for T2 | **Proposed** | `deploy/launchd/` and `deploy/systemd/` exist as templates; neither has run for a sustained period at a real site |
| Soak testing | **Open** | §9.4. No multi-hour continuous run has been performed |
| Signing key rotation procedure | **Proposed** | Written in §5.4, never exercised |

---

## Related documents

| Document | Relationship |
|---|---|
| `docs/03-system-architecture.md` | Process topology, filesystem layout, event log, degradation ladder. This document deploys what that one designs and does not restate it |
| `docs/05-voice-pipeline.md` | The latency budget the metrics in §7.3 measure and the runbook in §8.3 defends |
| `docs/06-scoring-engine.md` | The scorer whose model and prompt versions §11.4 rolls back; the export schema referenced in §10.3 |
| `docs/07-data-and-scenarios.md` | The scenario bank shipped in the wheel and the bundle |
| `docs/08-evals.md` | Every release gate in §5.3 and every CI eval stage in §6. The single source of truth for thresholds |
| `docs/09-ui-ux.md` | What the health and degradation states in §4 and §8 look like to the trainee |
| `docs/12-security-privacy.md` | The privacy posture the no-telemetry position in §7 implements |
| `docs/17-decisions.md` | The recorded reasons for the out-of-scope exclusions this document restates operationally |
| `SETUP.md` §6 | The calibration set the release gates ultimately rest on |
| `SETUP.md` §9 | The rule that `plans/metrics-snapshot.md` is updated in the same session as the run that changed a number |

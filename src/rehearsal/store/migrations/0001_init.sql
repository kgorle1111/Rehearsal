-- 0001_init.sql — rehearsal.db schema.
-- Adapted from misc/docs/11-backend-api.md §6.3. Applied by src/rehearsal/store/db.py.
--
-- Simplifications vs. the full DDL (each is a deliberate scope cut, not an
-- oversight — see the WS-API report for the ceiling on each):
--   * No `clinical_edges`, `utterances`, `verdicts`, `reviews`,
--     `idempotency_keys` tables: they back the state-graph editor, the
--     grader-merge pipeline, and the review/sign flow, none of which this
--     workstream builds. `findings` references (session_id, turn_index)
--     directly instead of a `verdicts` row, since there is no verdict
--     producer yet.
--   * `turns.source_sha` is nullable (no blob-producing orchestrator wired
--     to this API yet — nothing writes `turns` rows through this surface).
--   * No `eval_runs` / `calibration_items`: §6.9 places those in a
--     *separate* database (`data/evals/registry.db`) owned by the CLI eval
--     harness (WS9), not `rehearsal.db`. They were never part of this file.
--
-- Upgrade path: when the grader-merge and review workstreams land, add a
-- migration 0002 that introduces `verdicts`/`reviews` and repoints
-- `findings` at `verdicts(verdict_key)`, per the full DDL.

-- kn/ponytail: keep WAL + the append-only triggers on `events` (load-bearing
-- per the brief); drop the mmap/mmap-adjacent tuning pragmas that only
-- matter at production scale and add nothing a test can observe.
PRAGMA journal_mode  = WAL;
PRAGMA foreign_keys  = ON;
PRAGMA synchronous   = NORMAL;
PRAGMA busy_timeout  = 5000;
PRAGMA temp_store    = MEMORY;

-- ─────────────────────────────────────────────────────────────────────────
-- TRUTH
-- ─────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS events (
  seq         INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id  TEXT    NOT NULL,
  turn_index  INTEGER,
  ts_ms       INTEGER NOT NULL,
  mono_ms     INTEGER NOT NULL,
  kind        TEXT    NOT NULL,
  payload     TEXT    NOT NULL,
  prev_hash   TEXT    NOT NULL,
  hash        TEXT    NOT NULL
) STRICT;

CREATE INDEX        IF NOT EXISTS idx_events_session_seq ON events(session_id, seq);
CREATE INDEX        IF NOT EXISTS idx_events_kind        ON events(kind, seq);
CREATE INDEX        IF NOT EXISTS idx_events_turn        ON events(session_id, turn_index, seq)
                                                          WHERE turn_index IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_events_hash        ON events(hash);

CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
BEGIN SELECT RAISE(ABORT, 'events is append-only'); END;

CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
BEGIN SELECT RAISE(ABORT, 'events is append-only'); END;

CREATE TABLE IF NOT EXISTS blobs (
  sha256      TEXT PRIMARY KEY,
  bytes       INTEGER NOT NULL CHECK (bytes >= 0),
  media_type  TEXT    NOT NULL,
  role        TEXT    NOT NULL,
  created_ms  INTEGER NOT NULL,
  quarantined INTEGER NOT NULL DEFAULT 0,
  CHECK (length(sha256) = 64)
) STRICT;

CREATE INDEX IF NOT EXISTS idx_blobs_role_created ON blobs(role, created_ms);
CREATE INDEX IF NOT EXISTS idx_blobs_quarantined  ON blobs(quarantined) WHERE quarantined = 1;

-- ─────────────────────────────────────────────────────────────────────────
-- CONTENT (loaded from the scenario bank; not written by this API — the
-- read endpoints project WS7's ScenarioBank directly. Present so the table
-- a future `rehearsal content sync` writes to already has a home.)
-- ─────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS scenarios (
  scenario_id     TEXT PRIMARY KEY,
  version         TEXT    NOT NULL,
  title           TEXT    NOT NULL,
  setting         TEXT    NOT NULL,
  specialty       TEXT    NOT NULL,
  difficulty      INTEGER NOT NULL CHECK (difficulty BETWEEN 1 AND 5),
  est_turns       INTEGER NOT NULL CHECK (est_turns > 0),
  lang_a          TEXT    NOT NULL DEFAULT 'en-US',
  lang_b          TEXT    NOT NULL DEFAULT 'es-MX',
  skills_json     TEXT    NOT NULL,
  entry_node_id   TEXT    NOT NULL,
  manifest_sha    TEXT    NOT NULL REFERENCES blobs(sha256),
  source_ref      TEXT    NOT NULL DEFAULT '',
  licence         TEXT    NOT NULL DEFAULT '',
  content_sha     TEXT    NOT NULL,
  loaded_ms       INTEGER NOT NULL,
  retired         INTEGER NOT NULL DEFAULT 0
) STRICT;

CREATE INDEX IF NOT EXISTS idx_scenarios_difficulty ON scenarios(difficulty, retired);
CREATE INDEX IF NOT EXISTS idx_scenarios_specialty  ON scenarios(specialty, retired);

CREATE TABLE IF NOT EXISTS clinical_states (
  scenario_id     TEXT    NOT NULL REFERENCES scenarios(scenario_id) ON DELETE CASCADE,
  node_id         TEXT    NOT NULL,
  speaker         TEXT    NOT NULL CHECK (speaker IN ('clinician','patient')),
  intent          TEXT    NOT NULL,
  persona_json    TEXT    NOT NULL,
  facts_json      TEXT    NOT NULL,
  fallback_sha    TEXT        REFERENCES blobs(sha256),
  features_json   TEXT    NOT NULL,
  terminal        INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (scenario_id, node_id)
) STRICT;

-- ─────────────────────────────────────────────────────────────────────────
-- LEARNERS
-- ─────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS learners (
  trainee_id      TEXT PRIMARY KEY,
  display_name    TEXT    NOT NULL DEFAULT '',
  created_ms      INTEGER NOT NULL,
  difficulty      INTEGER NOT NULL DEFAULT 2 CHECK (difficulty BETWEEN 1 AND 5),
  langs_json      TEXT    NOT NULL DEFAULT '["en-US","es-MX"]',
  training_hours  INTEGER,
  notes           TEXT    NOT NULL DEFAULT ''
) STRICT;

CREATE TABLE IF NOT EXISTS skill_estimates (
  trainee_id      TEXT    NOT NULL REFERENCES learners(trainee_id) ON DELETE CASCADE,
  kind            TEXT    NOT NULL,
  ewma_rate       REAL,
  n_observed      INTEGER NOT NULL DEFAULT 0,
  n_errors        INTEGER NOT NULL DEFAULT 0,
  n_critical      INTEGER NOT NULL DEFAULT 0,
  interval_low    REAL,
  interval_high   REAL,
  last_session_id TEXT    REFERENCES sessions(session_id),
  updated_ms      INTEGER NOT NULL,
  PRIMARY KEY (trainee_id, kind)
) STRICT;

-- ─────────────────────────────────────────────────────────────────────────
-- SESSION PROJECTIONS (rebuildable from `events`; see store/projections.py)
-- ─────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS sessions (
  session_id     TEXT PRIMARY KEY,
  trainee_id     TEXT    NOT NULL REFERENCES learners(trainee_id),
  scenario_id    TEXT    NOT NULL,
  root_seed      INTEGER NOT NULL,
  state          TEXT    NOT NULL,
  difficulty     INTEGER NOT NULL,
  max_turns      INTEGER NOT NULL,
  text_mode      INTEGER NOT NULL DEFAULT 0,
  started_ms     INTEGER,
  ended_ms       INTEGER,
  abort_reason   TEXT,
  last_seq       INTEGER NOT NULL DEFAULT 0
) STRICT;

CREATE INDEX IF NOT EXISTS idx_sessions_trainee ON sessions(trainee_id, started_ms DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_state   ON sessions(state);
CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_one_live ON sessions(state)
  WHERE state IN ('configuring','armed','source_speaking','awaiting_rendering',
                  'rendering_capturing','turn_closing','paused','recovering');

CREATE TABLE IF NOT EXISTS turns (
  session_id     TEXT    NOT NULL REFERENCES sessions(session_id),
  turn_index     INTEGER NOT NULL CHECK (turn_index >= 0),
  speaker        TEXT    NOT NULL CHECK (speaker IN ('clinician','patient')),
  direction      TEXT    NOT NULL CHECK (direction IN ('en->es','es->en')),
  node_id        TEXT    NOT NULL,
  seed           INTEGER NOT NULL,
  source_sha     TEXT        REFERENCES blobs(sha256),
  rendering_sha  TEXT        REFERENCES blobs(sha256),
  audio_sha      TEXT        REFERENCES blobs(sha256),
  rendering_src  TEXT    NOT NULL DEFAULT 'live_verbatim',
  partial        INTEGER NOT NULL DEFAULT 0,
  abandoned      INTEGER NOT NULL DEFAULT 0,
  opened_ms      INTEGER NOT NULL,
  committed_ms   INTEGER,
  capture_ms     INTEGER,
  degrade_level  INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (session_id, turn_index)
) STRICT;

CREATE INDEX IF NOT EXISTS idx_turns_node ON turns(node_id);

CREATE TABLE IF NOT EXISTS findings (
  finding_id     INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id     TEXT    NOT NULL,
  turn_index     INTEGER NOT NULL,
  kind           TEXT    NOT NULL CHECK (kind IN (
                    'omission','addition','substitution','distortion','editorialization',
                    'role_exchange','register_shift','false_fluency','first_person_violation')),
  severity       TEXT    NOT NULL CHECK (severity IN ('critical','non_critical')),
  origin         TEXT    NOT NULL CHECK (origin IN ('extractor','grader')),
  extractor_name TEXT,
  src_start      INTEGER, src_end   INTEGER,
  span_start     INTEGER, span_end  INTEGER,
  confidence     REAL CHECK (confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)),
  note           TEXT    NOT NULL DEFAULT '',
  created_ms     INTEGER NOT NULL,
  CHECK (origin <> 'extractor' OR extractor_name IS NOT NULL),
  CHECK (src_start IS NOT NULL OR span_start IS NOT NULL),
  FOREIGN KEY (session_id, turn_index) REFERENCES turns(session_id, turn_index)
) STRICT;

CREATE INDEX IF NOT EXISTS idx_findings_session   ON findings(session_id, turn_index);
CREATE INDEX IF NOT EXISTS idx_findings_kind_sev  ON findings(kind, severity);

-- ─────────────────────────────────────────────────────────────────────────
-- STORE METADATA
-- ─────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS schema_migrations (
  version     INTEGER PRIMARY KEY,
  name        TEXT    NOT NULL,
  applied_ms  INTEGER NOT NULL,
  sql_sha256  TEXT    NOT NULL
) STRICT;

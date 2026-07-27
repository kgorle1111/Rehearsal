"""DB migration runner. DoD: "DB migrations run clean."

Covers: fresh connect succeeds, re-connecting to the same path is a
clean no-op (idempotent, no double-apply), and a tampered already-applied
migration file is a hard failure rather than a silent re-apply.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from rehearsal.store.db import MigrationError, apply_migrations, connect


def test_connect_on_fresh_path_applies_migrations(tmp_path: Path) -> None:
    conn = connect(tmp_path / "rehearsal.db")
    versions = conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
    assert [r["version"] for r in versions] == [1]
    # core tables from 0001_init.sql actually exist
    tables = {
        r["name"]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert {"events", "blobs", "sessions", "schema_migrations"} <= tables


def test_connect_twice_on_same_path_does_not_double_apply(tmp_path: Path) -> None:
    db_path = tmp_path / "rehearsal.db"
    connect(db_path)
    conn2 = connect(db_path)  # second open, migrations already recorded
    rows = conn2.execute("SELECT version FROM schema_migrations").fetchall()
    assert len(rows) == 1  # not two rows for version 1


def test_apply_migrations_second_call_applies_nothing(tmp_path: Path) -> None:
    conn = connect(tmp_path / "rehearsal.db")
    assert apply_migrations(conn) == []


def test_store_dir_created_with_owner_only_permissions(tmp_path: Path) -> None:
    db_path = tmp_path / "nested" / "rehearsal.db"
    connect(db_path)
    mode = db_path.parent.stat().st_mode & 0o777
    assert mode == 0o700


_FAKE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
  version     INTEGER PRIMARY KEY,
  name        TEXT    NOT NULL,
  applied_ms  INTEGER NOT NULL,
  sql_sha256  TEXT    NOT NULL
);
CREATE TABLE t (x INTEGER);
"""


def test_tampered_migration_file_is_a_hard_failure(tmp_path: Path) -> None:
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    migration_file = migrations_dir / "0001_init.sql"
    migration_file.write_text(_FAKE_SCHEMA_SQL)

    conn = sqlite3.connect(tmp_path / "rehearsal.db")
    conn.row_factory = sqlite3.Row
    apply_migrations(conn, migrations_dir)

    # Now the file on disk changes after being recorded — same version,
    # different hash. Re-applying must refuse, not silently re-run it.
    migration_file.write_text(_FAKE_SCHEMA_SQL + "\nCREATE TABLE u (y INTEGER);")
    with pytest.raises(MigrationError):
        apply_migrations(conn, migrations_dir)

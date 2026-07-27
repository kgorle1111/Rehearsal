"""SQLite connection + migration runner for `rehearsal.db`.

misc/docs/11-backend-api.md §6.10: numbered SQL files in
`store/migrations/NNNN_name.sql`, applied in order inside one pass at
connect time, recorded in `schema_migrations` with the file's sha256. An
already-applied migration whose file hash changed is a hard startup
failure — not a silent re-apply.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
import time
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

_FILENAME_RE = re.compile(r"^(\d{4})_(.+)\.sql$")


class MigrationError(RuntimeError):
    """An applied migration's file no longer matches what was recorded."""


def connect(path: Path | str) -> sqlite3.Connection:
    """Open (creating if absent) `rehearsal.db` and apply pending migrations.

    Safe to call repeatedly — already-applied migrations are skipped, and
    re-running the whole thing is a no-op (DoD: "migrations run clean").
    """
    path = Path(path)
    # misc/docs/12-security-privacy.md §3 T1: the store directory is 0700 —
    # this is what stops a second account on the same unlocked machine from
    # reading rehearsal.db, independent of whole-disk encryption (which
    # protects at rest, not from another logged-in user). mkdir's `mode` is
    # affected by umask and isn't reapplied if the dir already existed, so
    # chmod explicitly rather than trust the mkdir call alone.
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    apply_migrations(conn)
    return conn


def _applied_versions(conn: sqlite3.Connection) -> dict[int, str]:
    try:
        rows = conn.execute("SELECT version, sql_sha256 FROM schema_migrations").fetchall()
    except sqlite3.OperationalError:
        return {}
    return {int(r["version"]): str(r["sql_sha256"]) for r in rows}


def apply_migrations(conn: sqlite3.Connection, migrations_dir: Path = MIGRATIONS_DIR) -> list[int]:
    """Apply every migration not yet recorded. Returns the versions applied.

    Idempotent: calling this twice in a row applies nothing the second time.
    """
    applied = _applied_versions(conn)
    newly_applied: list[int] = []

    for migration_path in sorted(migrations_dir.glob("*.sql")):
        m = _FILENAME_RE.match(migration_path.name)
        if not m:
            continue  # ponytail: not our file, ignore rather than guess
        version, name = int(m.group(1)), m.group(2)
        sql = migration_path.read_text()
        digest = hashlib.sha256(sql.encode()).hexdigest()

        if version in applied:
            if applied[version] != digest:
                raise MigrationError(
                    f"migration {migration_path.name} (version {version}) was already applied "
                    f"with a different file hash — an installed migration must never be edited"
                )
            continue

        conn.executescript(sql)
        conn.execute(
            "INSERT INTO schema_migrations (version, name, applied_ms, sql_sha256) "
            "VALUES (?, ?, ?, ?)",
            (version, name, int(time.time() * 1000), digest),
        )
        conn.commit()
        newly_applied.append(version)

    return newly_applied

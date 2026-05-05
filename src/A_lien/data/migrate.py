"""Schema migrations for A-lien.

Tracks applied migrations via ``_schema_version`` table.
Migration scripts are numbered and applied in order.

Usage::

    from A_lien.data.storage import get_db
    from A_lien.data.migrate import migrate

    db = get_db()
    migrate(db)
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from A.data.base import SQLiteDB

# A migration step is either a raw SQL string or a callable(conn) -> None.
MigrationStep = str | Callable[[Any], None]


def _rename_mesagxoj_to_mesagoj(conn: Any) -> None:
    """Rename mesagxoj -> mesagoj if the old table exists."""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='mesagxoj'"
    ).fetchone()
    if row:
        conn.execute("DROP TABLE IF EXISTS mesagoj")
        conn.execute("ALTER TABLE mesagxoj RENAME TO mesagoj")


def _imap_uid_migration(conn: Any) -> None:
    """Ensure mesagoj has imap_uid INTEGER column and its unique index.

    Three scenarios:
    1. Legacy DB:  uid TEXT exists, imap_uid missing
       → drop old index, drop uid, add imap_uid, create new index
    2. Fresh DB:   imap_uid exists (from DDL), uid missing
       → create index only (column already exists)
    3. Re-run:     both exist, index exists
       → all IF NOT EXISTS → no-ops
    """
    has_uid = conn.execute(
        "SELECT COUNT(*) as cnt FROM pragma_table_info('mesagoj') WHERE name='uid'"
    ).fetchone()
    has_imap_uid = conn.execute(
        "SELECT COUNT(*) as cnt FROM pragma_table_info('mesagoj') WHERE name='imap_uid'"
    ).fetchone()

    # Legacy cleanup: drop old uid column and its index
    if has_uid and has_uid["cnt"] > 0:
        # Index may be named with old diacritic name (idx_mesagxoj_*)
        # if it was created before migration v2 renamed the table.
        conn.execute("DROP INDEX IF EXISTS idx_mesagoj_konto_uid")
        conn.execute("DROP INDEX IF EXISTS idx_mesagxoj_konto_uid")
        conn.execute("ALTER TABLE mesagoj DROP COLUMN uid")

    # Add imap_uid if column is missing (fresh DBs already have it)
    if has_imap_uid and has_imap_uid["cnt"] == 0:
        conn.execute("ALTER TABLE mesagoj ADD COLUMN imap_uid INTEGER")

    # Always ensure the index exists (idempotent for all scenarios)
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_mesagoj_imap_uid "
        "ON mesagoj(konto_id, dosierujo_id, imap_uid) "
        "WHERE imap_uid IS NOT NULL"
    )


# Migration registry: list of (version, description, steps)
_MIGRATIONS: list[tuple[int, str, list[MigrationStep]]] = [
    # Version 1 is reserved for initial schema creation (done in storage.py)
    (
        2,
        "Rename mesagxoj table to mesagoj (ASCII base-letter normalization)",
        [
            # Only rename if the old table exists (fresh installs use mesagoj)
            _rename_mesagxoj_to_mesagoj,
        ],
    ),
    (
        3,
        "Replace uid TEXT with imap_uid INTEGER for proper IMAP UID dedup",
        [_imap_uid_migration],
    ),
    (
        4,
        "Delete stale rows with imap_uid=NULL to prevent first-sync duplicates",
        ["DELETE FROM mesagoj WHERE imap_uid IS NULL AND dosierujo_id != ''"],
    ),
]


def _rename_mesagxoj_to_mesagoj(conn: Any) -> None:
    """Rename mesagxoj -> mesagoj if the old table exists."""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='mesagxoj'"
    ).fetchone()
    if row:
        conn.execute("DROP TABLE IF EXISTS mesagoj")
        conn.execute("ALTER TABLE mesagxoj RENAME TO mesagoj")


def get_schema_version(db: SQLiteDB) -> int:
    """Get the current schema version from the database.

    Args:
        db: Database connection

    Returns:
        Current schema version (0 if no version table)
    """
    try:
        row = db.execute_one(
            "SELECT COALESCE(MAX(version), 0) AS v FROM _schema_version"
        )
        return row["v"] if row else 0
    except Exception:
        return 0


def migrate(db: SQLiteDB, target: int | None = None) -> list[str]:
    """Apply pending migrations up to the target version.

    Each migration step is either a raw SQL string or a callable(conn).
    Steps are executed inside a single transaction per version.

    Args:
        db: Database connection
        target: Target version (None = latest)

    Returns:
        List of migration descriptions that were applied
    """
    current = get_schema_version(db)
    applied: list[str] = []

    for version, description, steps in _MIGRATIONS:
        if version <= current:
            continue
        if target is not None and version > target:
            break

        with db.transaction() as conn:
            for step in steps:
                if isinstance(step, str):
                    conn.execute(step)
                else:
                    step(conn)
            conn.execute(
                "INSERT INTO _schema_version (version, applied_je) VALUES (?, ?)",
                (version, datetime.now(timezone.utc).isoformat()),
            )

        applied.append(description)

    return applied


__all__ = [
    "get_schema_version",
    "migrate",
]

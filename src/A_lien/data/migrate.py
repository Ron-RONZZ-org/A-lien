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

from datetime import datetime, timezone

from A.data.base import SQLiteDB

# Migration registry: list of (version, description, sql_statements)
# Each migration must be idempotent (use IF NOT EXISTS / IF EXISTS).
_MIGRATIONS: list[tuple[int, str, list[str]]] = [
    # Version 1 is reserved for initial schema creation (done in storage.py)
]


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

    Args:
        db: Database connection
        target: Target version (None = latest)

    Returns:
        List of migration descriptions that were applied
    """
    current = get_schema_version(db)
    applied: list[str] = []

    for version, description, statements in _MIGRATIONS:
        if version <= current:
            continue
        if target is not None and version > target:
            break

        with db.transaction() as conn:
            for stmt in statements:
                conn.execute(stmt)
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

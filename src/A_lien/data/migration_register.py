"""Migration registration for A-lien.

This module registers the migration with A.core.migration framework.
Called via entry point "A.migrations" by A-core's unified migri command.
"""

from A.core.migration import register_migration, MigrationResult
from A_lien.data.migrate_from_autish import migrate as legacy_migrate


def _wrapper() -> MigrationResult:
    """Wrapper that converts old-style dict result to MigrationResult."""
    result = legacy_migrate()
    
    if isinstance(result, dict) and result.get("skipped"):
        return MigrationResult(
            module="A-lien",
            source_db="retposto.db",
            target_table="kontaktoj",
            source_rows=0,
            migrated_rows=0,
            skipped=True,
            skipped_reason=result.get("reason", "unknown"),
        )
    
    return MigrationResult(
        module="A-lien",
        source_db="retposto.db",
        target_table="kontaktoj",
        source_rows=result.get("source_rows", 0),
        migrated_rows=result.get("migrated_rows", 0),
        errors=result.get("errors", []),
    )


def register() -> None:
    """Register migration with A-core migration framework."""
    register_migration(
        module="A-lien",
        legacy_db="retposto.db",
        target_table="kontaktoj",
        migrator=_wrapper,
    )


__all__ = ["register"]
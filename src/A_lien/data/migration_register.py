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
            target_table="kontaktoj/kontoj",
            source_rows=0,
            migrated_rows=0,
            skipped=True,
            skipped_reason=result.get("reason", "unknown"),
        )
    
    details = result.get("details", {})
    contact_count = details.get("contacts", {}).get("migrated_rows", 0)
    account_count = details.get("accounts", {}).get("migrated_rows", 0)
    all_errors = result.get("errors", [])
    
    detail_str = f"contacts={contact_count}, accounts={account_count}"
    if all_errors:
        detail_str += f", errors={len(all_errors)}"
    
    return MigrationResult(
        module="A-lien",
        source_db="retposto.db",
        target_table="kontaktoj/kontoj",
        source_rows=result.get("source_rows", 0),
        migrated_rows=result.get("migrated_rows", 0),
        errors=all_errors,
    )


def register() -> None:
    """Register migration with A-core migration framework."""
    register_migration(
        module="A-lien",
        legacy_db="retposto.db",
        target_table="kontaktoj/kontoj",
        migrator=_wrapper,
    )


__all__ = ["register"]
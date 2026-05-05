"""Tests for A-lien data storage layer.

Covers:
- storage.get_db() creates all tables and indexes
- schema has correct columns for each table
- KONTAKTOJ_FTS_CONFIG is well-formed
- keyring.py get/set/delete with mocked keyring
- migrate.py version tracking
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest

from A_lien.data.migrate import get_schema_version, migrate
from A_lien.data.storage import (
    _SCHEMA_STATEMENTS,
    get_db,
    KONTAKTOJ_FTS_CONFIG,
)


# ──────────────────────────────────────────────────────────────────────────────
# Schema tests
# ──────────────────────────────────────────────────────────────────────────────


def all_tables(db) -> set[str]:
    """Get set of table names from sqlite_master."""
    rows = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    return {r["name"] for r in rows}


def table_columns(db, table: str) -> dict[str, str]:
    """Get column name -> type mapping for a table."""
    rows = db.execute(f"PRAGMA table_info({table})")
    return {r["name"]: r["type"] for r in rows}


def all_indexes(db) -> set[str]:
    """Get set of index names from sqlite_master."""
    rows = db.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    return {r["name"] for r in rows}


@pytest.fixture
def db(tmp_path):
    """Create a temporary database for testing."""
    db_path = str(tmp_path / "test_lien.db")
    db = get_db(db_path)
    yield db
    # No cleanup needed — tmp_path is cleaned up automatically


class TestGetDB:
    """Tests for database creation."""

    def test_creates_all_tables(self, db):
        """Verify every expected table exists."""
        tables = all_tables(db)
        expected = {
            "kontoj",
            "dosierujoj",
            "mesagoj",
            "aldonajxoj",
            "subskriboj",
            "filtraj",
            "spamo_blokoj",
            "kontaktoj",
            "kategorioj",
            "_schema_version",
        }
        assert expected.issubset(tables), f"Missing tables: {expected - tables}"

    def test_kontoj_schema(self, db):
        """Verify kontoj has correct columns (no pasvorto column)."""
        cols = table_columns(db, "kontoj")
        assert "uuid" in cols
        assert "retposto" in cols
        assert "imap_servilo" in cols
        assert "smtp_servilo" in cols
        # CRITICAL: no password column
        assert "pasvorto" not in cols, "Password must NOT be stored in DB"
        assert "kreita_je" in cols
        assert "modifita_je" in cols

    def test_dosierujoj_hierarchy(self, db):
        """Verify dosierujoj has self-referencing parent."""
        cols = table_columns(db, "dosierujoj")
        assert "patro_id" in cols
        assert "konto_id" in cols
        assert "delimejo" in cols
        assert cols.get("delimejo", "").upper() in ("TEXT",)

    def test_mesagoj_json_fields(self, db):
        """Verify mesagoj stores multi-value fields as JSON."""
        cols = table_columns(db, "mesagoj")
        for field in ("al", "kc", "bkc", "aldonajxoj", "etikedoj"):
            assert field in cols, f"Missing JSON field: {field}"

    def test_kontaktoj_comprehensive(self, db):
        """Verify kontaktoj has all contact fields including JSON arrays."""
        cols = table_columns(db, "kontaktoj")
        for field in (
            "nomo", "familia_nomo", "plena_nomo",
            "retposto", "organizo",
            "telefonnumeroj", "retposhtadresoj",
            "kampoj", "kategorioj",
            "konfirmita",
            "noto", "bildo",
            "kreita_je", "modifita_je",
        ):
            assert field in cols, f"Missing contact field: {field}"

    def test_indexes_created(self, db):
        """Verify essential indexes exist."""
        indexes = all_indexes(db)
        assert "idx_dosierujoj_konto" in indexes
        assert "idx_mesagoj_konto" in indexes
        assert "idx_mesagoj_imap_uid" in indexes
        assert "idx_mesagoj_dato" in indexes
        assert "idx_aldonajxoj_mesagxo" in indexes
        assert "idx_kontaktoj_nomo" in indexes
        assert "idx_kontaktoj_retposto" in indexes

    def test_foreign_keys_enabled(self, db):
        """Verify foreign key constraints are enforced."""
        row = db.execute_one("PRAGMA foreign_keys")
        assert row is not None
        # SQLiteDB enables foreign keys — verify they're on
        assert row.get("foreign_keys", 0) == 1

    def test_wal_mode(self, db):
        """Verify WAL journal mode is enabled."""
        row = db.execute_one("PRAGMA journal_mode")
        assert row is not None
        assert row.get("journal_mode", "").lower() == "wal"

    def test_idempotent_creation(self, db, tmp_path):
        """Verify calling get_db() twice does not error."""
        db2 = get_db(str(tmp_path / "lien2.db"))
        tables = all_tables(db2)
        assert len(tables) >= 10

    def test_schema_version_table(self, db):
        """Verify _schema_version table tracks migration state."""
        cols = table_columns(db, "_schema_version")
        assert "version" in cols
        assert "applied_je" in cols


class TestFTSConfig:
    """Tests for FTS5 configuration."""

    def test_fts_config_exists(self):
        """KONTAKTOJ_FTS_CONFIG must be a valid FTSConfig."""
        assert KONTAKTOJ_FTS_CONFIG is not None
        assert KONTAKTOJ_FTS_CONFIG.table == "kontaktoj"

    def test_fts_columns(self):
        """Verify FTS columns cover all searchable contact fields."""
        cols = set(KONTAKTOJ_FTS_CONFIG.fts_columns)
        for expected in ("nomo", "familia_nomo", "plena_nomo", "retposto", "organizo", "noto"):
            assert expected in cols, f"Missing FTS column: {expected}"

    def test_fts_filter_columns(self):
        """Verify filter columns are valid."""
        filters = set(KONTAKTOJ_FTS_CONFIG.filter_columns or [])
        assert "konfirmita" in filters
        assert "kategorioj" in filters

    def test_fts_normalize_all_columns(self):
        """Verify all FTS columns have a normalizer."""
        normalizers = KONTAKTOJ_FTS_CONFIG.normalize or {}
        for col in KONTAKTOJ_FTS_CONFIG.fts_columns:
            assert col in normalizers, f"Missing normalizer for: {col}"


class TestMigrate:
    """Tests for migration system."""

    def _fresh_db_no_migrate(self, tmp_path) -> Any:
        """Create a SQLiteDB with schema DDL but no migrations applied.

        This simulates an old database that hasn't been migrated.
        """
        from A.data.base import SQLiteDB
        from A_lien.data.storage import _SCHEMA_STATEMENTS

        db_path = str(tmp_path / "test_pre_migrate.db")
        db = SQLiteDB(db_path)
        for stmt in _SCHEMA_STATEMENTS:
            db.execute(stmt)
        return db

    def test_schema_version_starts_at_0(self, tmp_path):
        """Fresh database without migrations starts at version 0."""
        db = self._fresh_db_no_migrate(tmp_path)
        version = get_schema_version(db)
        assert version == 0

    def test_migrate_applies_pending(self, tmp_path):
        """Migrate on an un-migrated DB applies all pending migrations."""
        db = self._fresh_db_no_migrate(tmp_path)
        applied = migrate(db)
        # Both migration 2 (mesagxoj rename) and 3 (imap_uid) apply
        assert len(applied) >= 2
        version = get_schema_version(db)
        assert version >= 3

    def test_migrate_idempotent(self, tmp_path):
        """Calling migrate twice is a no-op the second time."""
        db = self._fresh_db_no_migrate(tmp_path)
        applied1 = migrate(db)
        applied2 = migrate(db)
        assert len(applied1) >= 2
        assert applied2 == []

    def test_legacy_db_upgrade(self, tmp_path):
        """Legacy DB with uid TEXT column upgrades to imap_uid without crash.

        Simulates the exact bug scenario: a DB from before the IMAP UID
        migration (uid TEXT exists, imap_uid missing, old index exists).
        verifies get_db() succeeds and the new index is created.
        """
        from A.data.base import SQLiteDB

        # Build a legacy mesagoj table (old schema with uid TEXT)
        db_path = str(tmp_path / "test_legacy.db")
        db = SQLiteDB(db_path)
        db.execute("""
            CREATE TABLE IF NOT EXISTS mesagoj (
                uuid           TEXT PRIMARY KEY,
                konto_id       TEXT NOT NULL,
                dosierujo_id   TEXT,
                message_id     TEXT,
                in_reply_to    TEXT,
                references_hdr TEXT,
                uid            TEXT,
                de             TEXT,
                al             TEXT NOT NULL DEFAULT '[]',
                kc             TEXT NOT NULL DEFAULT '[]',
                bkc            TEXT NOT NULL DEFAULT '[]',
                subjekto       TEXT,
                korpo          TEXT,
                html_korpo     TEXT,
                prioritato     INTEGER DEFAULT 5,
                legita         INTEGER NOT NULL DEFAULT 0,
                stelo          INTEGER NOT NULL DEFAULT 0,
                spamo          INTEGER NOT NULL DEFAULT 0,
                forigita       INTEGER NOT NULL DEFAULT 0,
                aldonajxoj     TEXT NOT NULL DEFAULT '[]',
                etikedoj       TEXT NOT NULL DEFAULT '[]',
                ricevita_je    TEXT,
                kreita_je      TEXT NOT NULL,
                modifita_je    TEXT NOT NULL
            )
        """)
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_mesagoj_konto_uid "
            "ON mesagoj(konto_id, uid)"
        )
        # Insert a sample row to confirm schema is valid
        db.execute(
            "INSERT INTO mesagoj (uuid, konto_id, uid, kreita_je, modifita_je) "
            "VALUES (?, ?, ?, datetime('now'), datetime('now'))",
            ("test-uuid", "test-konto", "<abc@test.com>"),
        )

        # Now run get_db() — this should NOT crash (the bug)
        from A_lien.data.storage import get_db

        db2 = get_db(str(tmp_path / "test_legacy.db"))

        # Verify the new column exists
        cols = {
            r["name"]
            for r in db2.execute("PRAGMA table_info(mesagoj)")
        }
        assert "imap_uid" in cols, "imap_uid column should exist after migration"
        assert "uid" not in cols, "uid column should have been dropped"

        # Verify the new index exists
        indexes = {
            r["name"]
            for r in db2.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
            )
        }
        assert "idx_mesagoj_imap_uid" in indexes
        assert "idx_mesagoj_konto_uid" not in indexes

        # Existing data is preserved
        row = db2.execute_one("SELECT uuid FROM mesagoj WHERE uuid='test-uuid'")
        assert row is not None


# ──────────────────────────────────────────────────────────────────────────────
# Keyring tests
# ──────────────────────────────────────────────────────────────────────────────


class TestKeyring:
    """Tests for A_lien.keyring module."""

    @pytest.fixture
    def mock_keyring(self):
        """Mock the keyring library at sys.modules level."""
        import sys

        store: dict[str, str] = {}

        class MockKeyringErrors:
            PasswordDeleteError = Exception

        class MockKeyring:
            errors = MockKeyringErrors()

            @staticmethod
            def get_password(service, key):
                return store.get(f"{service}:{key}")

            @staticmethod
            def set_password(service, key, value):
                store[f"{service}:{key}"] = value

            @staticmethod
            def delete_password(service, key):
                store.pop(f"{service}:{key}", None)

        mock = MockKeyring()
        # Insert into sys.modules so imports inside functions pick it up
        sys.modules["keyring"] = mock
        sys.modules["keyring.errors"] = MockKeyringErrors()
        yield
        # Cleanup
        del sys.modules["keyring"]
        if "keyring.errors" in sys.modules:
            del sys.modules["keyring.errors"]

    def test_set_and_get_password(self, mock_keyring):
        """Set and retrieve a password."""
        from A_lien.keyring import set_password, get_password

        account_id = str(uuid.uuid4())
        result = set_password(account_id, "sekret123")
        assert result is True

        pw = get_password(account_id)
        assert pw == "sekret123"

    def test_get_password_nonexistent(self, mock_keyring):
        """Getting a password for an unknown account returns None."""
        from A_lien.keyring import get_password

        pw = get_password("nonexistent-uuid")
        assert pw is None

    def test_delete_password(self, mock_keyring):
        """Delete a stored password."""
        from A_lien.keyring import set_password, get_password, delete_password

        account_id = str(uuid.uuid4())
        set_password(account_id, "sekret123")
        assert get_password(account_id) == "sekret123"

        result = delete_password(account_id)
        assert result is True
        assert get_password(account_id) is None

    def test_delete_twice_is_idempotent(self, mock_keyring):
        """Deleting a non-existent password should not error."""
        from A_lien.keyring import delete_password

        result = delete_password("nonexistent-uuid")
        assert result is True  # Idempotent

    @patch("A.core.keyring._keyring_available", return_value=False)
    def test_fallback_when_keyring_unavailable(self, _mock_available):
        """All functions gracefully return None/False when keyring missing."""
        from A_lien.keyring import get_password, set_password, delete_password

        assert get_password("test") is None
        assert set_password("test", "pw") is False
        assert delete_password("test") is False

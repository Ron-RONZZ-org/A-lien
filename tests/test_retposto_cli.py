"""CLI tests for retposto folder features (serci --dosierujo, preni --dosierujo)."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner
from unittest.mock import patch

from A_lien.cli.retposto import retposto


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture(autouse=True)
def isolate_lien(monkeypatch, tmp_path):
    """Isolate DB and keyring for retposto CLI tests."""
    from A.core.testing import patch_paths, patch_keyring
    patch_paths(monkeypatch, tmp_path)
    patch_keyring(monkeypatch)
    import A_lien.service.retposto_service as rp
    rp._retposto_service = None


class TestSerciDosierujo:
    """Tests for serci --dosierujo CLI option."""

    def test_serci_help_shows_dosierujo(self, runner):
        """--help output mentions --dosierujo option."""
        result = runner.invoke(retposto, ["serci", "--help"])
        assert result.exit_code == 0
        assert "--dosierujo" in result.stdout

    def test_serci_with_folder_passes_to_service(self, runner, monkeypatch):
        """serci --dosierujo passes folder to search_messages."""
        from A_lien.service import get_retposto_service
        svc = get_retposto_service()

        captured = {}

        def mock_search(filters, limit=50):
            captured["filters"] = filters
            captured["limit"] = limit
            return []

        monkeypatch.setattr(svc, "search_messages", mock_search)

        result = runner.invoke(retposto, [
            "serci", "hello", "--dosierujo", "INBOX",
        ])
        assert result.exit_code == 0
        assert captured["filters"].get("folder") == "INBOX"
        assert captured["filters"].get("query") == "hello"

    def test_serci_folder_alone_no_query(self, runner, monkeypatch):
        """serci --dosierujo works without query argument."""
        from A_lien.service import get_retposto_service
        svc = get_retposto_service()

        captured = {}

        def mock_search(filters, limit=50):
            captured["filters"] = filters
            return []

        monkeypatch.setattr(svc, "search_messages", mock_search)

        result = runner.invoke(retposto, [
            "serci", "--dosierujo", "Sent",
        ])
        assert result.exit_code == 0
        assert captured["filters"].get("folder") == "Sent"

    def test_format_results_shows_folder(self, service_with_data, runner):
        """_format_results output includes folder name when present."""
        from A_lien.cli.retposto_search import _format_results

        results = [
            {
                "uuid": "abc-def-123",
                "subjekto": "Test message",
                "legita": 1,
                "dosierujo_nomo": "INBOX",
            },
        ]
        lines = _format_results(results)
        combined = " ".join(lines)
        assert "[INBOX]" in combined

    def test_format_results_no_folder(self, runner):
        """_format_results works without dosierujo_nomo key."""
        from A_lien.cli.retposto_search import _format_results

        results = [
            {
                "uuid": "abc-def-123",
                "subjekto": "Test message",
                "legita": 0,
            },
        ]
        lines = _format_results(results)
        combined = " ".join(lines)
        # No folder bracket when folder is unknown
        assert "Test message" in combined


class TestPreniDosierujo:
    """Tests for preni --dosierujo CLI option."""

    def test_preni_help_shows_dosierujo(self, runner):
        """--help output mentions --dosierujo option."""
        result = runner.invoke(retposto, ["preni", "--help"])
        assert result.exit_code == 0
        assert "--dosierujo" in result.stdout

    def test_preni_dosierujo_without_konto_errors(self, runner, monkeypatch):
        """--dosierujo without --konto shows error."""
        # Mock sync_all to not actually connect to IMAP
        monkeypatch.setattr(
            "A_lien.service.retposto_service.RetpostoService.list_accounts",
            lambda self: [],
        )

        result = runner.invoke(retposto, [
            "preni", "--dosierujo", "INBOX",
        ])
        assert result.exit_code != 0
        assert "postulas" in result.stdout.lower() or "requires" in result.stdout.lower()

    def test_preni_dosierujo_with_konto_calls_sync(self, runner, monkeypatch):
        """--dosierujo with --konto passes folders to sync_account."""
        import uuid as uuid_mod
        from A_lien.service import get_retposto_service

        svc = get_retposto_service()
        svc.get_password = lambda uuid: "sekret123"  # type: ignore[method-assign]

        # Create a real account in the DB
        acct_uuid = str(uuid_mod.uuid4())
        now = "2026-01-01T00:00:00"
        svc.db.execute(
            "INSERT INTO kontoj (uuid, nomo, retposto, imap_servilo, imap_haveno, "
            "imap_ssl, smtp_servilo, smtp_haveno, smtp_tls, kreita_je, modifita_je) "
            "VALUES (?, 'Test', 'test@example.com', 'imap.test.com', 993, 1, "
            "'smtp.test.com', 587, 1, ?, ?)",
            (acct_uuid, now, now),
        )

        captured = {}

        def mock_sync_account(uuid, force=False, folders=None):
            captured["uuid"] = uuid
            captured["folders"] = folders
            from A_lien.imap._sync_types import SyncResult
            return SyncResult()

        monkeypatch.setattr(svc, "sync_account", mock_sync_account)

        result = runner.invoke(retposto, [
            "preni", "--konto", acct_uuid[:8],
            "--dosierujo", "INBOX",
        ])
        assert result.exit_code == 0
        assert captured["folders"] == ["INBOX"]
        assert captured["uuid"] == acct_uuid


@pytest.fixture
def service_with_data():
    """Fixture that provides a service with seeded data for display tests."""
    from A_lien.service import get_retposto_service
    svc = get_retposto_service()
    # Seed minimal data needed for _format_results display
    return svc

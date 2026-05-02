"""CLI tests for A-lien kontakto commands.

Uses typer.testing.CliRunner for in-process testing.
Each test gets its own service injected as the global singleton.
"""

from __future__ import annotations

import tempfile
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from A_lien.cli import app, kontakto
from A_lien.data.storage import get_db
from A_lien.service.kontakto_service import KontaktoService, get_kontakto_service


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def clean_service():
    """Create a fresh KontaktoService with temp DB and set as singleton."""
    import A_lien.service.kontakto_service as ks
    db_path = tempfile.mktemp(suffix=".db")
    db = get_db(db_path)
    svc = KontaktoService(db)
    old = ks._kontakto_service
    ks._kontakto_service = svc
    yield svc
    ks._kontakto_service = old
    import os
    try:
        os.unlink(db_path)
    except OSError:
        pass


@pytest.fixture
def seeded_service(clean_service):
    """A clean service with 3 sample contacts."""
    svc = clean_service
    for i, name in enumerate(["Alice Smith", "Bob Jones", "Charlie Brown"]):
        svc.create({
            "plena_nomo": name,
            "retposto": f"{name.lower().replace(' ', '.')}@example.com",
            "nomo": name.split()[0],
            "familia_nomo": name.split()[-1] if len(name.split()) > 1 else "",
        })
    return svc


class TestCLIKontakto:
    """Tests for kontakto CLI commands."""

    def test_ls_empty(self, runner, clean_service):
        """List shows appropriate message when no contacts."""
        result = runner.invoke(kontakto, ["ls"])
        assert result.exit_code == 0
        assert "Neniuj" in result.stdout or "No contacts" in result.stdout

    def test_ls_with_data(self, runner, seeded_service):
        """List shows contacts."""
        result = runner.invoke(kontakto, ["ls"])
        assert result.exit_code == 0
        assert "Alice Smith" in result.stdout
        assert "Bob Jones" in result.stdout

    def test_vidi_existing(self, runner, seeded_service):
        """View shows contact details."""
        contacts = seeded_service.list()
        uuid = contacts[0]["uuid"]
        result = runner.invoke(kontakto, ["vidi", uuid])
        assert result.exit_code == 0
        assert contacts[0]["plena_nomo"] in result.stdout

    def test_vidi_not_found(self, runner, clean_service):
        """View shows error for nonexistent UUID."""
        result = runner.invoke(kontakto, ["vidi", "nonexistent"])
        assert result.exit_code != 0
        assert "ne trovita" in result.stdout.lower() or "not found" in result.stdout.lower()

    def test_serci_found(self, runner, seeded_service):
        """Search finds matching contacts."""
        result = runner.invoke(kontakto, ["serci", "Alice"])
        assert result.exit_code == 0
        assert "Alice" in result.stdout

    def test_serci_not_found(self, runner, clean_service):
        """Search shows appropriate message for no matches."""
        result = runner.invoke(kontakto, ["serci", "Zzzz"])
        assert result.exit_code == 0
        assert "Neniuj" in result.stdout or "No results" in result.stdout

    def test_aldoni(self, runner, clean_service):
        """Add a contact via CLI."""
        result = runner.invoke(kontakto, [
            "aldoni",
            "--nomo", "Test",
            "--familia-nomo", "User",
            "--plena-nomo", "Test User",
            "--retposto", "test@example.com",
        ])
        assert result.exit_code == 0, f"aldoni failed: {result.stdout}"
        assert "kreita" in result.stdout.lower() or "created" in result.stdout.lower()

    def test_aldoni_requires_name(self, runner, clean_service):
        """Add requires a name."""
        result = runner.invoke(kontakto, ["aldoni"])
        assert result.exit_code != 0
        assert "Bezonata" in result.stdout or "Name or full name" in result.stdout

    def test_forigi(self, runner, seeded_service):
        """Delete a contact."""
        contacts = seeded_service.list()
        uuid = contacts[0]["uuid"]
        result = runner.invoke(kontakto, ["forigi", uuid])
        assert result.exit_code == 0, f"forigi failed: {result.stdout}"
        assert "forigita" in result.stdout.lower() or "deleted" in result.stdout.lower()

    def test_kategorio_ls(self, runner, clean_service):
        """List categories works."""
        result = runner.invoke(kontakto, ["kategorio", "ls"])
        assert result.exit_code == 0

    def test_kategorio_aldoni(self, runner, clean_service):
        """Add a category via CLI."""
        result = runner.invoke(kontakto, ["kategorio", "aldoni", "test-cat"])
        assert result.exit_code == 0
        assert "kreita" in result.stdout.lower() or "created" in result.stdout.lower()

    def test_kategorio_forigi(self, runner, seeded_service):
        """Delete a category via CLI."""
        cat = seeded_service.create_category("del-cat")
        result = runner.invoke(kontakto, ["kategorio", "forigi", cat["uuid"]])
        assert result.exit_code == 0, f"kategorio forigi failed: {result.stdout}"

    def test_malfari(self, runner, seeded_service):
        """Undo a delete operation."""
        contacts = seeded_service.list()
        uuid = contacts[0]["uuid"]
        runner.invoke(kontakto, ["forigi", uuid])
        result = runner.invoke(kontakto, ["malfermi"])
        assert result.exit_code == 0
        assert "Malfarita" in result.stdout or "Undone" in result.stdout

    def test_purigi(self, runner, seeded_service):
        """Cleanup shows no duplicates for clean data."""
        result = runner.invoke(kontakto, ["purigi"])
        assert result.exit_code == 0

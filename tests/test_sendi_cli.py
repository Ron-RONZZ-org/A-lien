"""CLI tests for retposto sendi and konton subskribo integration.

Covers:
- sendi --subskribo (override account default)
- sendi --dosiero/-D file body input
- sendi priority default (3)
- konton aldoni --subskribo
- konton modifi --subskribo
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from A_lien.cli import app
from A_lien.service.retposto_service import get_retposto_service


@pytest.fixture(autouse=True)
def isolate_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Isolate database to tmp_path to prevent leaking test data."""
    from A.core import paths
    monkeypatch.setattr(paths, "data_dir", lambda: tmp_path)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _run(args: list[str]) -> ...:
    """Invoke a lien command with CliRunner."""
    from typer.testing import Result
    return CliRunner().invoke(app, args)


def _seed_sig(nomo: str, teksto: str = "content", estas_html: bool = False) -> str:
    """Create a signature and return its UUID."""
    svc = get_retposto_service()
    sig = svc.create_signature(nomo, teksto, estas_html)
    return sig["uuid"]


def _seed_account(subskribo: str = "") -> str:
    """Create an account (optionally with a default signature) and return UUID."""
    svc = get_retposto_service()
    data = {
        "retposto": "user@test.com",
        "nomo": "Test User",
        "imap_servilo": "imap.test.com",
        "smtp_servilo": "smtp.test.com",
    }
    if subskribo:
        data["subskribo"] = subskribo
    acct = svc.create_account(data, password="pw")
    return acct["uuid"]


# ── konton aldoni --subskribo ────────────────────────────────────────────────


class TestKontonAldoniSubskribo:
    """konton aldoni --subskribo/-s."""

    def test_aldoni_with_signature_by_name(self, runner):
        """Create account with default signature by name."""
        sig_uuid = _seed_sig("My Sig")
        result = _run([
            "retposto", "konton", "aldoni",
            "--retposto", "alice@test.com",
            "--imap-servilo", "imap.test.com",
            "--smtp-servilo", "smtp.test.com",
            "--subskribo", "My Sig",
            "--pasvorto", "pw",
        ])
        assert result.exit_code == 0
        # Verify stored UUID
        svc = get_retposto_service()
        accounts = svc.list_accounts()
        acct = next(a for a in accounts if a["retposto"] == "alice@test.com")
        assert acct["subskribo"] == sig_uuid

    def test_aldoni_with_invalid_signature(self, runner):
        """Error when --subskribo name doesn't exist."""
        result = _run([
            "retposto", "konton", "aldoni",
            "--retposto", "bob@test.com",
            "--imap-servilo", "imap.test.com",
            "--smtp-servilo", "smtp.test.com",
            "--subskribo", "Nonexistent",
            "--pasvorto", "pw",
        ])
        assert result.exit_code == 1
        assert "ne trovita" in result.stdout or "not found" in result.stdout


class TestKontonModifiSubskribo:
    """konton modifi --subskribo/-s."""

    def test_modifi_signature(self, runner):
        """Modify account to add a default signature."""
        acct_uuid = _seed_account()
        sig_uuid = _seed_sig("Work Sig")
        result = _run([
            "retposto", "konton", "modifi",
            acct_uuid[:8],
            "--subskribo", "Work Sig",
        ])
        assert result.exit_code == 0
        svc = get_retposto_service()
        acct = svc.get_account(acct_uuid)
        assert acct["subskribo"] == sig_uuid

    def test_modifi_signature_not_found(self, runner):
        """Error when modifying with non-existent signature."""
        acct_uuid = _seed_account()
        result = _run([
            "retposto", "konton", "modifi",
            acct_uuid[:8],
            "--subskribo", "Nonexistent",
        ])
        assert result.exit_code == 1


# ── sendi --subskribo ────────────────────────────────────────────────────────


class TestSendiSubskribo:
    """sendi --subskribo option."""

    def test_sendi_with_subskribo(self, monkeypatch):
        """Send with --subskribo override."""
        _seed_sig("Personal Sig")
        _seed_account()  # Need at least one account for sendi to resolve
        monkeypatch.setattr("A_lien.smtp.SMTPClient", type("FakeSMTP", (), {
            "__init__": lambda *a, **kw: None,
            "connect": lambda *a, **kw: None,
            "disconnect": lambda *a, **kw: None,
            "send_email": lambda *a, **kw: None,
        }))
        result = _run([
            "retposto", "sendi",
            "--to", "bob@test.com",
            "--subject", "Test",
            "--body", "Hello",
            "--subskribo", "Personal Sig",
        ])
        assert result.exit_code == 0


class TestSendiDosiero:
    """sendi --dosiero/-D option."""

    def test_sendi_dosiero_txt(self, monkeypatch, tmp_path):
        """Send with --dosiero reading a .txt file."""
        _seed_account()
        monkeypatch.setattr("A_lien.smtp.SMTPClient", type("FakeSMTP", (), {
            "__init__": lambda *a, **kw: None,
            "connect": lambda *a, **kw: None,
            "disconnect": lambda *a, **kw: None,
            "send_email": lambda *a, **kw: None,
        }))
        f = tmp_path / "body.txt"
        f.write_text("Hello from file")
        result = _run([
            "retposto", "sendi",
            "--to", "bob@test.com",
            "--subject", "Test",
            "--dosiero", str(f),
        ])
        assert result.exit_code == 0

    def test_sendi_dosiero_html(self, monkeypatch, tmp_path):
        """Send with --dosiero reading a .html file (auto HTML body)."""
        _seed_account()
        monkeypatch.setattr("A_lien.smtp.SMTPClient", type("FakeSMTP", (), {
            "__init__": lambda *a, **kw: None,
            "connect": lambda *a, **kw: None,
            "disconnect": lambda *a, **kw: None,
            "send_email": lambda *a, **kw: None,
        }))
        f = tmp_path / "body.html"
        f.write_text("<h1>Hello</h1>")
        result = _run([
            "retposto", "sendi",
            "--to", "bob@test.com",
            "--subject", "Test",
            "--dosiero", str(f),
        ])
        assert result.exit_code == 0

    def test_sendi_dosiero_not_found(self):
        """Error when --dosiero file doesn't exist."""
        _seed_account()  # Need account to reach file-existence check
        result = _run([
            "retposto", "sendi",
            "--to", "bob@test.com",
            "--subject", "Test",
            "--dosiero", "/nonexistent/file.txt",
        ])
        assert result.exit_code == 1
        # Accept either Esperanto or English output
        assert "ne ekzistas" in result.stdout or "not found" in result.stdout

    def test_sendi_body_and_dosiero_mutual_exclusion(self):
        """Error when both --body and --dosiero are provided."""
        _seed_account()  # Need account to reach mutual-exclusion check
        result = _run([
            "retposto", "sendi",
            "--to", "bob@test.com",
            "--subject", "Test",
            "--body", "inline",
            "--dosiero", "/some/file.txt",
        ])
        assert result.exit_code == 1
        assert "AŬ" in result.stdout or "OR" in result.stdout


# ── sendi priority default ────────────────────────────────────────────────────


class TestSendiPriority:
    """sendi --prioritato default is 3."""

    def test_help_shows_default(self):
        """Help text references priority 3 as default."""
        result = _run(["retposto", "sendi", "--help"])
        assert result.exit_code == 0
        # Typer shows default values in help output
        assert "3" in result.stdout

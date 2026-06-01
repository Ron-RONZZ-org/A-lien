"""CLI tests for subskribo (signature) commands.

Covers:
- subskribo aldoni with --teksto/-t (inline)
- subskribo aldoni with --dosiero/-D (file input)
- Mutual exclusion of -t and -D
- Auto-detection of HTML from file extension
- subskribo ls (list)
- subskribo forigi by UUID and by name
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from A_lien.cli import app
from A_lien.service import get_retposto_service


@pytest.fixture(autouse=True)
def isolate_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Isolate database to tmp_path to prevent leaking test data."""
    from A.core import paths
    monkeypatch.setattr(paths, "data_dir", lambda: tmp_path)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _invoke(runner, args: list[str]) -> tuple[Path | None, ...]:
    """Run a retposto subskribo command with CliRunner."""
    return runner.invoke(app, ["retposto", "subskribo"] + args)


# ── aldoni: --teksto (inline) ────────────────────────────────────────────────


class TestAldoniTeksto:
    """subskribo aldoni with --teksto/-t."""

    def test_aldoni_teksto(self, runner):
        """Create a signature with inline text."""
        result = _invoke(runner, ["aldoni", "test-sig", "-t", "Hello World"])
        assert result.exit_code == 0
        assert "kreita" in result.stdout or "created" in result.stdout

    def test_aldoni_teksto_html_flag(self, runner):
        """Create an HTML signature with inline text."""
        result = _invoke(runner, [
            "aldoni", "html-sig", "-t", "<p>Hello</p>", "--html"
        ])
        assert result.exit_code == 0

    def test_aldoni_teksto_missing(self, runner):
        """Error when neither -t nor -D is provided."""
        result = _invoke(runner, ["aldoni", "bad-sig"])
        assert result.exit_code == 1
        assert "--teksto" in result.stdout or "--dosiero" in result.stdout


# ── aldoni: --dosiero (file input) ────────────────────────────────────────────


class TestAldoniDosiero:
    """subskribo aldoni with --dosiero/-D."""

    def test_aldoni_dosiero_plain(self, runner, tmp_path):
        """Create a signature from a plain text file."""
        f = tmp_path / "sig.txt"
        f.write_text("Best regards,\nJohn")
        result = _invoke(runner, [
            "aldoni", "file-sig", "-D", str(f)
        ])
        assert result.exit_code == 0

    def test_aldoni_dosiero_html_auto_detect(self, runner, tmp_path):
        """Auto-detect HTML from .html file extension."""
        f = tmp_path / "sig.html"
        f.write_text("<p>Best regards</p>")
        result = _invoke(runner, [
            "aldoni", "html-file", "-D", str(f)
        ])
        assert result.exit_code == 0
        # Verify it was stored as HTML
        svc = get_retposto_service()
        sig = svc.find_signature_by_name("html-file")
        assert sig is not None
        assert sig["estas_html"] == 1

    def test_aldoni_dosiero_htm_extension(self, runner, tmp_path):
        """Auto-detect HTML from .htm file extension."""
        f = tmp_path / "sig.htm"
        f.write_text("<p>Test</p>")
        result = _invoke(runner, [
            "aldoni", "htm-file", "-D", str(f)
        ])
        assert result.exit_code == 0
        svc = get_retposto_service()
        sig = svc.find_signature_by_name("htm-file")
        assert sig["estas_html"] == 1

    def test_aldoni_dosiero_not_found(self, runner):
        """Error when file does not exist."""
        result = _invoke(runner, [
            "aldoni", "bad-file", "-D", "/nonexistent/file.txt"
        ])
        assert result.exit_code == 1
        assert "ne ekzistas" in result.stdout or "not found" in result.stdout

    def test_aldoni_dosiero_and_teksto_mutual_exclusion(self, runner, tmp_path):
        """Error when both -D and -t are provided."""
        f = tmp_path / "sig.txt"
        f.write_text("content")
        result = _invoke(runner, [
            "aldoni", "both", "-t", "inline", "-D", str(f)
        ])
        assert result.exit_code == 1
        assert "AŬ" in result.stdout or "OR" in result.stdout or "OU" in result.stdout


# ── aldoni: duplicate name (UNIQUE constraint) ────────────────────────────────


class TestAldoniDuplicate:
    """subskribo aldoni with duplicate name."""

    def test_aldoni_duplicate_name(self, runner):
        """Creating a signature with an existing name should fail."""
        _invoke(runner, ["aldoni", "dup", "-t", "first"])
        result = _invoke(runner, ["aldoni", "dup", "-t", "second"])
        assert result.exit_code == 1


# ── forigi: by UUID and by name ──────────────────────────────────────────────


class TestForigi:
    """subskribo forigi with UUID or name."""

    def test_forigi_by_uuid(self, runner):
        """Delete a signature by UUID."""
        _invoke(runner, ["aldoni", "to-delete", "-t", "content"])
        svc = get_retposto_service()
        sig = svc.find_signature_by_name("to-delete")
        uuid = sig["uuid"]

        result = _invoke(runner, ["forigi", uuid[:8]])
        assert result.exit_code == 0
        assert "forigita" in result.stdout or "deleted" in result.stdout

    def test_forigi_by_name(self, runner):
        """Delete a signature by name."""
        _invoke(runner, ["aldoni", "by-name", "-t", "content"])
        result = _invoke(runner, ["forigi", "by-name"])
        assert result.exit_code == 0
        assert "forigita" in result.stdout or "deleted" in result.stdout

    def test_forigi_multiple_mixed(self, runner):
        """Delete multiple signatures by mixing UUID and name."""
        _invoke(runner, ["aldoni", "sig-a", "-t", "a"])
        _invoke(runner, ["aldoni", "sig-b", "-t", "b"])
        svc = get_retposto_service()
        uuid_b = svc.find_signature_by_name("sig-b")["uuid"]

        result = _invoke(runner, ["forigi", "sig-a", uuid_b[:8]])
        assert result.exit_code == 0

    def test_forigi_not_found(self, runner):
        """Deleting a non-existent signature shows error but doesn't crash."""
        result = _invoke(runner, ["forigi", "nonexistent"])
        assert result.exit_code == 0  # forigi iterates; continues on error
        assert "ne trovita" in result.stdout or "not found" in result.stdout


# ── ls (list) ─────────────────────────────────────────────────────────────────


class TestLs:
    """subskribo ls."""

    def test_ls_empty(self, runner):
        """List shows message when no signatures."""
        result = _invoke(runner, ["ls"])
        assert result.exit_code == 0
        assert "Neniuj" in result.stdout or "No signatures" in result.stdout

    def test_ls_with_data(self, runner):
        """List shows signatures."""
        _invoke(runner, ["aldoni", "sig-one", "-t", "hello"])
        _invoke(runner, ["aldoni", "sig-two", "-t", "world"])
        result = _invoke(runner, ["ls"])
        assert result.exit_code == 0
        assert "sig-one" in result.stdout
        assert "sig-two" in result.stdout


# ── End-to-end: full workflow ─────────────────────────────────────────────────


class TestWorkflow:
    """End-to-end subskribo workflow."""

    def test_full_workflow(self, runner, tmp_path):
        """Create from file, list, delete by name."""
        # Create from file
        f = tmp_path / "signature.html"
        f.write_text("<p>Signature content</p>")
        r1 = _invoke(runner, ["aldoni", "workflow-sig", "-D", str(f)])
        assert r1.exit_code == 0

        # List
        r2 = _invoke(runner, ["ls"])
        assert r2.exit_code == 0
        assert "workflow-sig" in r2.stdout

        # Delete by name
        r3 = _invoke(runner, ["forigi", "workflow-sig"])
        assert r3.exit_code == 0

        # Verify gone
        r4 = _invoke(runner, ["ls"])
        assert "workflow-sig" not in r4.stdout

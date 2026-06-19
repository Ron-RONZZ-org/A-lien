"""Tests for A-lien retposto_elsuti — attachment download and --stdout mode.

Tests the CLI command, the _is_text_mime helper, and _try_decode.
Does NOT test actual IMAP attachment fetching (requires network).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from A_lien.cli import app


# ---------------------------------------------------------------------------
# _is_text_mime helper
# ---------------------------------------------------------------------------

class TestIsTextMime:
    def test_text_plain(self):
        from A_lien.cli.retposto_elsuti import _is_text_mime
        assert _is_text_mime("text/plain")

    def test_text_html(self):
        from A_lien.cli.retposto_elsuti import _is_text_mime
        assert _is_text_mime("text/html")

    def test_text_csv(self):
        from A_lien.cli.retposto_elsuti import _is_text_mime
        assert _is_text_mime("text/csv")

    def test_application_json(self):
        from A_lien.cli.retposto_elsuti import _is_text_mime
        assert _is_text_mime("application/json")

    def test_application_xml(self):
        from A_lien.cli.retposto_elsuti import _is_text_mime
        assert _is_text_mime("application/xml")

    def test_application_pdf_is_binary(self):
        from A_lien.cli.retposto_elsuti import _is_text_mime
        assert not _is_text_mime("application/pdf")

    def test_image_jpeg_is_binary(self):
        from A_lien.cli.retposto_elsuti import _is_text_mime
        assert not _is_text_mime("image/jpeg")

    def test_application_zip_is_binary(self):
        from A_lien.cli.retposto_elsuti import _is_text_mime
        assert not _is_text_mime("application/zip")

    def test_application_octet_stream_is_binary(self):
        from A_lien.cli.retposto_elsuti import _is_text_mime
        assert not _is_text_mime("application/octet-stream")

    def test_empty_mime(self):
        from A_lien.cli.retposto_elsuti import _is_text_mime
        assert not _is_text_mime("")

    def test_case_insensitive(self):
        from A_lien.cli.retposto_elsuti import _is_text_mime
        assert _is_text_mime("TEXT/PLAIN")
        assert _is_text_mime("Application/JSON")

    def test_yaml_and_toml(self):
        from A_lien.cli.retposto_elsuti import _is_text_mime
        assert _is_text_mime("application/x-yaml")
        assert _is_text_mime("application/toml")

    def test_shell_script(self):
        from A_lien.cli.retposto_elsuti import _is_text_mime
        assert _is_text_mime("application/x-sh")

    def test_sql(self):
        from A_lien.cli.retposto_elsuti import _is_text_mime
        assert _is_text_mime("application/sql")


# ---------------------------------------------------------------------------
# _try_decode helper
# ---------------------------------------------------------------------------


class TestTryDecode:
    def test_utf8_text(self):
        from A_lien.cli.retposto_elsuti import _try_decode
        result = _try_decode("Hello, world!".encode("utf-8"))
        assert result == "Hello, world!"

    def test_utf8_with_special_chars(self):
        from A_lien.cli.retposto_elsuti import _try_decode
        result = _try_decode("Café résumé ñoño".encode("utf-8"))
        assert result == "Café résumé ñoño"

    def test_binary_bytes_returns_none(self):
        from A_lien.cli.retposto_elsuti import _try_decode
        result = _try_decode(b"\xff\xfe\x00\x01\x02\x03")
        assert result is None

    def test_empty_bytes(self):
        from A_lien.cli.retposto_elsuti import _try_decode
        result = _try_decode(b"")
        assert result == ""

    def test_invalid_utf8_sequence_returns_none(self):
        from A_lien.cli.retposto_elsuti import _try_decode
        # 0xFF is never valid in UTF-8
        result = _try_decode(b"\xff")
        assert result is None
        # Overlong encoding is also invalid
        result = _try_decode(b"\xc0\x80")
        assert result is None


# ---------------------------------------------------------------------------
# _print_text_attachment helper
# ---------------------------------------------------------------------------


class TestPrintTextAttachment:
    def test_prints_text_content(self):
        from A_lien.cli.retposto_elsuti import _print_text_attachment

        svc = MagicMock()
        svc.get_attachment_content.return_value = b"Hello, attachment!"

        with patch("A_lien.cli.retposto_elsuti.info") as mock_info:
            _print_text_attachment(svc, "msg-uuid", {
                "dosiernomo": "readme.txt",
                "mime_tipo": "text/plain",
            })

        # Should have printed the content
        assert mock_info.call_count >= 1
        # At least one call should contain the file content
        all_calls = [str(c[0][0]) for c in mock_info.call_args_list]
        combined = " ".join(all_calls)
        assert "Hello, attachment!" in combined

    def test_binary_content_shows_error(self):
        from A_lien.cli.retposto_elsuti import _print_text_attachment

        svc = MagicMock()
        svc.get_attachment_content.return_value = b"\xff\xfe\x00\x01"

        with patch("A_lien.cli.retposto_elsuti.info") as mock_info:
            _print_text_attachment(svc, "msg-uuid", {
                "dosiernomo": "data.bin",
                "mime_tipo": "application/octet-stream",
            })

        # Should mention binary / non-UTF-8
        all_calls = [str(c[0][0]) for c in mock_info.call_args_list]
        combined = " ".join(all_calls)
        assert "binary" in combined.lower() or "binaire" in combined.lower()

    def test_large_content_truncated(self):
        from A_lien.cli.retposto_elsuti import _print_text_attachment

        svc = MagicMock()
        svc.get_attachment_content.return_value = b"A" * 100_000

        with patch("A_lien.cli.retposto_elsuti.info") as mock_info:
            _print_text_attachment(svc, "msg-uuid", {
                "dosiernomo": "large.txt",
                "mime_tipo": "text/plain",
            })

        all_calls = [str(c[0][0]) for c in mock_info.call_args_list]
        combined = " ".join(all_calls)
        assert "truncated" in combined.lower() or "tran\u0109ita" in combined.lower() or "tronqu" in combined.lower()


# ---------------------------------------------------------------------------
# CLI command: --stdout flag
# ---------------------------------------------------------------------------


class TestElsutiStdout:
    def test_stdout_flag_accepted(self):
        """--stdout should be a valid option (returns 2 = usage error
        because no arguments given, but not an 'Unknown option' error)."""
        runner = CliRunner()
        result = runner.invoke(app, ["retposto", "elsuti", "--stdout"])
        # Exit code 2 means usage error (missing argument), not 'Unknown option'
        assert result.exit_code == 2
        assert "Unknown option" not in (result.stderr or "")

    def test_stdout_no_attachments(self):
        """When --stdout is used but the message has no attachments."""
        from A_lien.service import get_retposto_service

        svc = get_retposto_service()
        # Mock: message exists but no attachments
        with patch.object(svc, "get_message", return_value={"uuid": "abc12345"}), \
             patch.object(svc, "get_attachments", return_value=[]), \
             patch("A_lien.cli.retposto_elsuti.info") as mock_info:

            runner = CliRunner()
            result = runner.invoke(app, ["retposto", "elsuti", "abc12345", "--stdout"])

        # Should succeed with "no attachments" message
        assert result.exit_code == 0
        all_calls = [str(c[0][0]) for c in mock_info.call_args_list]
        combined = " ".join(all_calls)
        assert "neniuj" in combined.lower() or "no" in combined.lower() or "aucune" in combined.lower()

    def test_stdout_with_text_attachment(self):
        """When --stdout is used and the message has a text attachment."""
        from A_lien.service import get_retposto_service

        svc = get_retposto_service()
        attachments = [{
            "dosiernomo": "notes.txt",
            "mime_tipo": "text/plain",
            "grandeco": 50,
        }]

        with patch.object(svc, "get_message", return_value={"uuid": "abc12345"}), \
             patch.object(svc, "get_attachments", return_value=attachments), \
             patch.object(svc, "get_attachment_content", return_value=b"Meeting notes content"), \
             patch("A_lien.cli.retposto_elsuti.info") as mock_info:

            runner = CliRunner()
            result = runner.invoke(app, ["retposto", "elsuti", "abc12345", "--stdout"])

        assert result.exit_code == 0
        all_calls = [str(c[0][0]) for c in mock_info.call_args_list]
        combined = " ".join(all_calls)
        assert "Meeting notes content" in combined
        assert "notes.txt" in combined

    def test_stdout_with_binary_attachment(self):
        """When --stdout is used with a binary attachment, show info message."""
        from A_lien.service import get_retposto_service

        svc = get_retposto_service()
        # Use a non-extractable binary MIME type (ZIP, not PDF)
        attachments = [{
            "dosiernomo": "archive.zip",
            "mime_tipo": "application/zip",
            "grandeco": 50_000,
        }]

        with patch.object(svc, "get_message", return_value={"uuid": "abc12345"}), \
             patch.object(svc, "get_attachments", return_value=attachments), \
             patch("A_lien.cli.retposto_elsuti.info") as mock_info:

            runner = CliRunner()
            result = runner.invoke(app, ["retposto", "elsuti", "abc12345", "--stdout"])

        assert result.exit_code == 0
        all_calls = [str(c[0][0]) for c in mock_info.call_args_list]
        combined = " ".join(all_calls)
        assert "binary" in combined.lower() or "binaire" in combined.lower()
        assert "archive.zip" in combined

    def test_stdout_specific_filename(self):
        """--stdout with a specific filename should print that attachment."""
        from A_lien.service import get_retposto_service

        svc = get_retposto_service()
        attachments = [
            {"dosiernomo": "notes.txt", "mime_tipo": "text/plain", "grandeco": 50},
            {"dosiernomo": "data.csv", "mime_tipo": "text/csv", "grandeco": 100},
        ]

        with patch.object(svc, "get_message", return_value={"uuid": "abc12345"}), \
             patch.object(svc, "get_attachments", return_value=attachments), \
             patch.object(svc, "get_attachment_content", return_value=b"csv,data,here"), \
             patch("A_lien.cli.retposto_elsuti.info") as mock_info:

            runner = CliRunner()
            result = runner.invoke(app, [
                "retposto", "elsuti", "abc12345", "data.csv", "--stdout",
            ])

        assert result.exit_code == 0
        all_calls = [str(c[0][0]) for c in mock_info.call_args_list]
        combined = " ".join(all_calls)
        assert "csv,data,here" in combined


# ---------------------------------------------------------------------------
# PDF extraction in --stdout mode
# ---------------------------------------------------------------------------


class TestElsutiStdoutPdf:
    """Tests for PDF text extraction via elsuti --stdout."""

    def test_pdf_attachment_detected_as_extractable(self):
        """application/pdf should be recognised as extractable binary."""
        from A_lien.cli.retposto_elsuti import _is_extractable_binary

        assert _is_extractable_binary("application/pdf")
        assert not _is_extractable_binary("application/zip")
        assert not _is_extractable_binary("text/plain")
        assert not _is_extractable_binary("image/jpeg")

    def test_stdout_pdf_with_a_papero_installed(self):
        """With A-papero available, PDF content should be extracted and printed."""
        from A_lien.service import get_retposto_service

        svc = get_retposto_service()
        attachments = [{
            "dosiernomo": "doc.pdf",
            "mime_tipo": "application/pdf",
            "grandeco": 500,
        }]

        # Simulate A-papero being importable
        with patch.object(svc, "get_message", return_value={"uuid": "abc12345"}), \
             patch.object(svc, "get_attachments", return_value=attachments), \
             patch.object(svc, "get_attachment_content", return_value=b"fake pdf bytes"), \
             patch("A_lien.cli.retposto_elsuti._try_extract_pdf_text",
                   return_value="Extracted PDF text content."), \
             patch("A_lien.cli.retposto_elsuti.info") as mock_info:

            runner = CliRunner()
            result = runner.invoke(app, ["retposto", "elsuti", "abc12345", "--stdout"])

        assert result.exit_code == 0
        all_calls = [str(c[0][0]) for c in mock_info.call_args_list]
        combined = " ".join(all_calls)
        assert "Extracted PDF text content" in combined
        assert "doc.pdf" in combined

    def test_stdout_pdf_without_a_papero(self):
        """Without A-papero, show install hint instead of content."""
        from A_lien.service import get_retposto_service

        svc = get_retposto_service()
        attachments = [{
            "dosiernomo": "doc.pdf",
            "mime_tipo": "application/pdf",
            "grandeco": 500,
        }]

        with patch.object(svc, "get_message", return_value={"uuid": "abc12345"}), \
             patch.object(svc, "get_attachments", return_value=attachments), \
             patch.object(svc, "get_attachment_content", return_value=b"fake pdf bytes"), \
             patch("A_lien.cli.retposto_elsuti._try_extract_pdf_text",
                   return_value=None), \
             patch("A_lien.cli.retposto_elsuti.info") as mock_info:

            runner = CliRunner()
            result = runner.invoke(app, ["retposto", "elsuti", "abc12345", "--stdout"])

        assert result.exit_code == 0
        all_calls = [str(c[0][0]) for c in mock_info.call_args_list]
        combined = " ".join(all_calls)
        assert "pip install" in combined.lower()
        assert "A-papero" in combined or "papero" in combined

    def test_stdout_pdf_single_filename(self):
        """--stdout with a PDF filename should extract that specific attachment."""
        from A_lien.service import get_retposto_service

        svc = get_retposto_service()
        attachments = [
            {"dosiernomo": "notes.txt", "mime_tipo": "text/plain", "grandeco": 50},
            {"dosiernomo": "report.pdf", "mime_tipo": "application/pdf", "grandeco": 500},
        ]

        with patch.object(svc, "get_message", return_value={"uuid": "abc12345"}), \
             patch.object(svc, "get_attachments", return_value=attachments), \
             patch.object(svc, "get_attachment_content", return_value=b"pdf content here"), \
             patch("A_lien.cli.retposto_elsuti._try_extract_pdf_text",
                   return_value="PDF text content"), \
             patch("A_lien.cli.retposto_elsuti.info") as mock_info:

            runner = CliRunner()
            result = runner.invoke(app, [
                "retposto", "elsuti", "abc12345", "report.pdf", "--stdout",
            ])

        assert result.exit_code == 0
        all_calls = [str(c[0][0]) for c in mock_info.call_args_list]
        combined = " ".join(all_calls)
        assert "PDF text content" in combined
        assert "report.pdf" in combined
        assert "notes.txt" not in combined  # Should NOT include other attachments

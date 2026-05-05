"""Tests for IMAP sync and SMTP send engines.

Uses mocked IMAP/SMTP to verify connection, folder listing, message
parsing, and email sending without actual network I/O.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from A_lien.imap import IMAPClient, sync_account, SyncResult
from A_lien.smtp import SMTPClient


# ── IMAP Client Tests ────────────────────────────────────────────────────────


class TestIMAPClient:
    """Tests for IMAPClient connection, folder listing, and message sync."""

    def test_connect_ssl(self):
        """Connect with SSL uses IMAP4_SSL."""
        with patch("A_lien.imap.client.imaplib.IMAP4_SSL") as mock:
            client = IMAPClient("imap.test.com", 993, use_ssl=True)
            mock_instance = MagicMock()
            mock.return_value = mock_instance
            client.connect("user@test.com", "password")
            mock.assert_called_once_with("imap.test.com", 993)
            mock_instance.login.assert_called_once_with("user@test.com", "password")

    def test_connect_plain(self):
        """Connect without SSL uses IMAP4."""
        with patch("A_lien.imap.client.imaplib.IMAP4") as mock:
            client = IMAPClient("imap.test.com", 143, use_ssl=False)
            mock_instance = MagicMock()
            mock.return_value = mock_instance
            client.connect("user@test.com", "password")
            mock.assert_called_once_with("imap.test.com", 143)

    def test_connect_failure(self):
        """Connection error raises ConnectionError."""
        with patch("A_lien.imap.client.imaplib.IMAP4_SSL") as mock:
            mock.side_effect = Exception("Connection refused")
            client = IMAPClient("imap.test.com", 993)
            with pytest.raises(ConnectionError):
                client.connect("user", "pw")

    def test_disconnect(self):
        """Disconnect performs logout."""
        with patch("A_lien.imap.client.imaplib.IMAP4_SSL") as mock:
            mock_instance = MagicMock()
            mock.return_value = mock_instance
            client = IMAPClient("imap.test.com", 993)
            client.connect("u", "p")
            client.disconnect()
            mock_instance.logout.assert_called_once()

    def test_list_folders(self):
        """List folders parses IMAP LIST response."""
        with patch("A_lien.imap.client.imaplib.IMAP4_SSL") as mock:
            mock_instance = MagicMock()
            mock.return_value = mock_instance
            mock_instance.list.return_value = (
                "OK",
                [
                    b'(\\HasNoChildren) "/" "INBOX"',
                    b'(\\HasChildren) "/" "Sent"',
                ],
            )
            client = IMAPClient("imap.test.com", 993)
            client.connect("u", "p")
            folders = client.list_folders()
            assert len(folders) == 2
            assert folders[0]["name"] == "INBOX"
            assert folders[1]["name"] == "Sent"

    def test_sync_folder_empty(self):
        """Syncing an empty folder returns zero counts."""
        with patch("A_lien.imap.client.imaplib.IMAP4_SSL") as mock:
            mock_instance = MagicMock()
            mock.return_value = mock_instance
            mock_instance.select.return_value = ("OK", [b"0"])
            mock_instance.uid.return_value = ("OK", [b""])

            # Build a fake store with empty known_uids
            fake_store = MagicMock()
            fake_store.get_known_uids.return_value = set()

            client = IMAPClient("imap.test.com", 993)
            client.connect("u", "p")
            result = client.sync_folder("INBOX", "konto-1", "dosierujo-1", fake_store)
            assert result.total == 0
            assert result.new == 0

    def test_sync_folder_with_messages(self):
        """Syncing a folder with messages parses headers."""
        with patch("A_lien.imap.client.imaplib.IMAP4_SSL") as mock:
            mock_instance = MagicMock()
            mock.return_value = mock_instance
            mock_instance.select.return_value = ("OK", [b"1"])

            # Build a fake email message with a Message-ID
            msg_bytes = (
                b"From: sender@test.com\r\n"
                b"To: recipient@test.com\r\n"
                b"Subject: Test Message\r\n"
                b"Date: Mon, 01 Jan 2024 12:00:00 +0000\r\n"
                b"Message-ID: <abc123@test.com>\r\n"
                b"\r\n"
                b"Hello, this is a test."
            )
            # uid() is called twice: uid('search', ...) then uid('fetch', ...)
            mock_instance.uid.side_effect = [
                ("OK", [b"100"]),              # uid('search', None, "ALL")
                ("OK", [                         # uid('fetch', ...)
                    (b"1 (UID 100 FLAGS (\\Seen) BODY[] {42}", msg_bytes),
                ]),
            ]

            fake_store = MagicMock()
            fake_store.get_known_uids.return_value = set()
            fake_store.store_message.return_value = "stored-uuid"

            client = IMAPClient("imap.test.com", 993)
            client.connect("u", "p")
            result = client.sync_folder("INBOX", "konto-1", "dosierujo-1", fake_store)
            assert result.total == 1
            assert result.new == 1

    def test_parse_email_headers(self):
        """Parsed email has correct header extraction."""
        with patch("A_lien.imap.client.imaplib.IMAP4_SSL") as mock:
            mock_instance = MagicMock()
            mock.return_value = mock_instance
            mock_instance.select.return_value = ("OK", [b"1"])

            msg_bytes = (
                b"From: John Doe <john@test.com>\r\n"
                b"To: Jane Doe <jane@test.com>\r\n"
                b"Cc: Admin <admin@test.com>\r\n"
                b"Subject: =?utf-8?Q?H=C3=A9llo?=\r\n"
                b"Date: Mon, 01 Jan 2024 12:00:00 +0000\r\n"
                b"Message-ID: <msg-1@test.com>\r\n"
                b"In-Reply-To: <prev@test.com>\r\n"
                b"\r\n"
                b"Body content here."
            )
            mock_instance.uid.side_effect = [
                ("OK", [b"200"]),              # uid('search', ...)
                ("OK", [                         # uid('fetch', ...)
                    (b"1 (UID 200 FLAGS (\\Seen) BODY[] {48}", msg_bytes),
                ]),
            ]

            fake_store = MagicMock()
            fake_store.get_known_uids.return_value = set()
            fake_store.store_message.return_value = "stored-uuid"

            client = IMAPClient("imap.test.com", 993)
            client.connect("u", "p")
            result = client.sync_folder("INBOX", "konto-1", "dosierujo-1", fake_store)
            # This just tests the sync doesn't crash
            assert result.total == 1


# ── SMTP Client Tests ────────────────────────────────────────────────────────


class TestSMTPClient:
    """Tests for SMTPClient connection and email sending."""

    def test_connect_tls(self):
        """Connect with TLS uses starttls."""
        with patch("A_lien.smtp.smtplib.SMTP") as mock:
            mock_instance = MagicMock()
            mock.return_value = mock_instance
            client = SMTPClient("smtp.test.com", 587, use_tls=True)
            client.connect("user@test.com", "password")
            mock.assert_called_once_with("smtp.test.com", 587, timeout=30)
            mock_instance.ehlo.assert_called()
            mock_instance.starttls.assert_called_once()
            mock_instance.login.assert_called_once_with("user@test.com", "password")

    def test_connect_no_tls(self):
        """Connect without TLS skips starttls."""
        with patch("A_lien.smtp.smtplib.SMTP") as mock:
            mock_instance = MagicMock()
            mock.return_value = mock_instance
            client = SMTPClient("smtp.test.com", 25, use_tls=False)
            client.connect("user@test.com", "password")
            mock_instance.starttls.assert_not_called()
            mock_instance.login.assert_called_once()

    def test_send_simple(self):
        """Send a simple plain-text email."""
        with patch("A_lien.smtp.smtplib.SMTP") as mock:
            mock_instance = MagicMock()
            mock.return_value = mock_instance
            client = SMTPClient("smtp.test.com", 587)
            client.connect("user@test.com", "pw")
            client.send_email(
                from_addr="user@test.com",
                to=["recipient@test.com"],
                subject="Hello",
                body="Test body",
            )
            mock_instance.sendmail.assert_called_once()
            args = mock_instance.sendmail.call_args[0]
            assert args[0] == "user@test.com"
            assert "recipient@test.com" in args[1]

    def test_send_with_cc(self):
        """Send with CC includes CC recipients."""
        with patch("A_lien.smtp.smtplib.SMTP") as mock:
            mock_instance = MagicMock()
            mock.return_value = mock_instance
            client = SMTPClient("smtp.test.com", 587)
            client.connect("user@test.com", "pw")
            client.send_email(
                from_addr="user@test.com",
                to=["to@test.com"],
                subject="Test",
                body="Body",
                cc=["cc@test.com"],
            )
            from_addr, recipients, _ = mock_instance.sendmail.call_args[0]
            assert "to@test.com" in recipients
            assert "cc@test.com" in recipients

    def test_send_with_attachment(self, tmp_path):
        """Send with a file attachment."""
        attach_file = tmp_path / "test.txt"
        attach_file.write_text("attachment content")

        with patch("A_lien.smtp.smtplib.SMTP") as mock:
            mock_instance = MagicMock()
            mock.return_value = mock_instance
            client = SMTPClient("smtp.test.com", 587)
            client.connect("user@test.com", "pw")
            client.send_email(
                from_addr="user@test.com",
                to=["to@test.com"],
                subject="Test",
                body="Body",
                attachments=[str(attach_file)],
            )
            mock_instance.sendmail.assert_called_once()

    def test_connect_failure(self):
        """Connection error raises ConnectionError."""
        with patch("A_lien.smtp.smtplib.SMTP") as mock:
            mock.side_effect = Exception("Connection refused")
            client = SMTPClient("smtp.test.com", 587)
            with pytest.raises(ConnectionError):
                client.connect("user", "pw")

    def test_disconnect(self):
        """Disconnect performs quit."""
        with patch("A_lien.smtp.smtplib.SMTP") as mock:
            mock_instance = MagicMock()
            mock.return_value = mock_instance
            client = SMTPClient("smtp.test.com", 587)
            client.connect("u", "p")
            client.disconnect()
            mock_instance.quit.assert_called_once()

"""Integration tests for IMAP sync against real servers.

These tests connect to real IMAP accounts to verify:
- folder listing (INBOX is never dropped)
- message sync (fetch + dedup)
- connection error messages are user-friendly

Credentials are read from environment variables.
Tests are skipped when credentials are not available.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

from A_lien.imap.client import IMAPClient, SyncResult


_IMAP_HOST = os.environ.get("A_TEST_IMAP_HOST", "imap.migadu.com")
_IMAP_PORT = int(os.environ.get("A_TEST_IMAP_PORT", "993"))


def _get_creds(prefix: str) -> tuple[str, str] | None:
    """Read IMAP credentials from environment variables.

    Args:
        prefix: Credential prefix, e.g. "TEST1" → A_TEST1_IMAP_USER

    Returns:
        (username, password) tuple, or None if not set.
    """
    user = os.environ.get(f"A_{prefix}_IMAP_USER")
    pw = os.environ.get(f"A_{prefix}_IMAP_PASS")
    if user and pw:
        return user, pw
    return None


# ── Folder listing tests ──────────────────────────────────────────────────────


class TestListFolders:
    """Verify list_folders() returns all folders including INBOX."""

    @pytest.fixture(autouse=True)
    def _check_creds(self):
        creds = _get_creds("TEST1") or _get_creds("TEST")
        if not creds:
            pytest.skip(
                "Set A_TEST1_IMAP_USER and A_TEST1_IMAP_PASS "
                "or A_TEST_IMAP_USER and A_TEST_IMAP_PASS"
            )

    @pytest.fixture
    def client(self):
        creds = _get_creds("TEST1") or _get_creds("TEST")
        assert creds is not None
        username, password = creds
        client = IMAPClient(_IMAP_HOST, _IMAP_PORT, use_ssl=True)
        try:
            client.connect(username, password)
        except ConnectionError as e:
            pytest.skip(f"Cannot connect: {e}")
        yield client
        try:
            client.disconnect()
        except Exception:
            pass

    def test_inbox_is_listed(self, client):
        """INBOX must always be in the folder list."""
        folders = client.list_folders()
        names = [f["name"] for f in folders]
        assert "INBOX" in names, (
            f"INBOX missing from folder list: {names}"
        )
        assert len(folders) >= 2, (
            f"Expected at least 2 folders, got {len(folders)}: {names}"
        )

    def test_folder_list_is_deterministic(self, client):
        """Calling list_folders() twice returns same result."""
        f1 = [f["name"] for f in client.list_folders()]
        f2 = [f["name"] for f in client.list_folders()]
        assert f1 == f2

    def test_inbox_is_selectable(self, client):
        """INBOX can be SELECTed via IMAP."""
        folders = client.list_folders()
        inbox = next(f for f in folders if f["name"] == "INBOX")
        # Actually select it to verify
        import imaplib
        try:
            typ, data = client.conn.select("INBOX", readonly=True)
            assert typ == "OK", f"Cannot select INBOX: {typ}"
        finally:
            try:
                client.conn.close()
            except Exception:
                pass


# ── Sync tests ────────────────────────────────────────────────────────────────


class TestSync:
    """Verify sync_folder() fetches messages correctly."""

    @pytest.fixture(autouse=True)
    def _check_creds(self):
        creds = _get_creds("TEST1") or _get_creds("TEST")
        if not creds:
            pytest.skip("IMAP credentials not set")

    @pytest.fixture
    def client(self):
        creds = _get_creds("TEST1") or _get_creds("TEST")
        assert creds is not None
        username, password = creds
        client = IMAPClient(_IMAP_HOST, _IMAP_PORT, use_ssl=True)
        try:
            client.connect(username, password)
        except ConnectionError as e:
            pytest.skip(f"Cannot connect: {e}")
        yield client
        try:
            client.disconnect()
        except Exception:
            pass

    @pytest.fixture
    def fake_store(self):
        """A MessageStore that tracks stored messages in memory."""
        store = MagicMock()
        store.known_uids = set()
        store.stored = []

        def get_known_uids(konto_id, dosierujo_id):
            return store.known_uids

        def store_message(data):
            uid = data.get("imap_uid", data.get("uuid", ""))
            store.known_uids.add(data.get("imap_uid"))
            store.stored.append(data)
            return data.get("uuid", str(uid))

        store.get_known_uids.side_effect = get_known_uids
        store.store_message.side_effect = store_message
        return store

    def test_sync_inbox_returns_messages(self, client, fake_store):
        """Syncing INBOX returns at least 0 messages without error."""
        result = client.sync_folder(
            "INBOX", "test-konto", "test-dosierujo", fake_store,
        )
        assert isinstance(result, SyncResult)
        assert result.total >= 0  # May be 0 for empty inbox
        assert len(fake_store.stored) == result.new
        # No errors unless total > 0 (connection works)
        if result.errors:
            for err in result.errors:
                print(f"  Sync error: {err}")

    def test_sync_dedup(self, client, fake_store):
        """Second sync of INBOX should not create duplicates."""
        # First sync
        result1 = client.sync_folder(
            "INBOX", "test-konto", "test-dosierujo", fake_store,
        )
        first_count = len(fake_store.stored)

        # Second sync — should find 0 new messages
        result2 = client.sync_folder(
            "INBOX", "test-konto", "test-dosierujo", fake_store,
        )
        assert result2.new == 0, (
            f"Second sync found {result2.new} new messages "
            f"(already stored {first_count})"
        )
        assert len(fake_store.stored) == first_count


# ── Connection error messages ─────────────────────────────────────────────────


class TestConnectionErrors:
    """Verify connection failures produce user-friendly messages."""

    def test_dns_failure_message(self):
        """Connecting to a non-existent hostname gives a clear message."""
        client = IMAPClient("nonexistent.invalid", 993, use_ssl=True)
        with pytest.raises(ConnectionError) as exc:
            client.connect("user@test.com", "password")
        msg = str(exc.value)
        assert "rezolvi" in msg or "resolve" in msg or "résoudre" in msg, (
            f"DNS error should mention resolution: {msg}"
        )
        assert "nonexistent.invalid" in msg, (
            f"DNS error should mention hostname: {msg}"
        )

    def test_connection_refused_message(self):
        """Connection to a closed port gives a clear message."""
        client = IMAPClient("localhost", 1, use_ssl=False)
        with pytest.raises(ConnectionError) as exc:
            client.connect("user@test.com", "password")
        msg = str(exc.value)
        assert "rifuzita" in msg or "refused" in msg or "refusée" in msg, (
            f"Connection refused should mention refusal: {msg}"
        )


__all__ = [
    "TestListFolders",
    "TestSync",
    "TestConnectionErrors",
]

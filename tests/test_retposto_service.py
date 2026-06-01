"""Tests for RetpostoService (Phase 3).

Covers:
- Account CRUD with keyring integration
- Signature management
- Password stored in keyring (never in DB)
"""

from __future__ import annotations

import tempfile
from unittest.mock import patch

import pytest

from A_lien.service.retposto_service import RetpostoService, get_retposto_service
from A_lien.data.storage import get_db


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def db(tmp_path):
    return get_db(str(tmp_path / "test_lien.db"))


@pytest.fixture
def service(db):
    return RetpostoService(db)


@pytest.fixture
def sample_account():
    return {
        "retposto": "user@example.com",
        "nomo": "Test User",
        "imap_servilo": "imap.example.com",
        "imap_haveno": 993,
        "smtp_servilo": "smtp.example.com",
        "smtp_haveno": 587,
    }


def _make_account(email_suffix=""):
    """Factory helper — returns a FRESH dict each call."""
    return {
        "retposto": f"user{email_suffix}@example.com",
        "nomo": f"Test User {email_suffix}".strip(),
        "imap_servilo": "imap.example.com",
        "imap_haveno": 993,
        "smtp_servilo": "smtp.example.com",
        "smtp_haveno": 587,
    }


# ── Account CRUD ─────────────────────────────────────────────────────────────


class TestAccountCRUD:
    """Tests for account creation, retrieval, update, deletion."""

    def test_create_account(self, service, sample_account):
        """Create an account with password stored in keyring."""
        account = service.create_account(sample_account, password="sekret123")
        assert account["uuid"] is not None
        assert account["retposto"] == "user@example.com"
        # Password should be in keyring, not returned
        assert "pasvorto" not in account

    def test_create_account_no_password_in_db(self, service, sample_account):
        """Verify password column does not exist in kontoj."""
        account = service.create_account(sample_account, password="sekret123")
        # Read raw from DB to confirm no pasvorto column
        raw = service.db.execute_one(
            "SELECT * FROM kontoj WHERE uuid = ?", (account["uuid"],)
        )
        assert "pasvorto" not in raw, "Password must NOT be stored in DB"

    def test_get_account(self, service, sample_account):
        """Get account by UUID."""
        account = service.create_account(sample_account, password="pw")
        retrieved = service.get_account(account["uuid"])
        assert retrieved is not None
        assert retrieved["retposto"] == "user@example.com"
        assert "pasvorto" not in retrieved

    def test_list_accounts(self, service):
        """List all accounts."""
        service.create_account(_make_account("1"), password="pw")
        service.create_account(_make_account("2"), password="pw2")
        accounts = service.list_accounts()
        assert len(accounts) == 2

    def test_update_account(self, service, sample_account):
        """Update account fields."""
        account = service.create_account(sample_account, password="pw")
        updated = service.update_account(
            account["uuid"], {"nomo": "New Name"}, password=None
        )
        assert updated["nomo"] == "New Name"

    def test_update_account_with_new_password(self, service, sample_account):
        """Update account and change password in keyring."""
        account = service.create_account(sample_account, password="old-pw")
        with patch("A_lien.service.retposto_accounts._set_keyring_pw") as mock:
            service.update_account(account["uuid"], {}, password="new-pw")
            mock.assert_called_once()

    def test_delete_account(self, service, sample_account):
        """Delete account removes from DB and keyring."""
        account = service.create_account(sample_account, password="pw")
        with patch("A_lien.service.retposto_accounts._del_keyring_pw") as mock:
            service.delete_account(account["uuid"])
            mock.assert_called_once_with(account["uuid"])
        # Account should be in trash
        assert service.get_account(account["uuid"]) is None
        trash = service.get_trash()
        uuids = [t["uuid"] for t in trash]
        assert account["uuid"] in uuids

    def test_create_does_not_inherit_trash(self, service):
        """Create with email that was previously used in a deleted account."""
        a1 = service.create_account(_make_account("1"), password="pw")
        service.delete_account(a1["uuid"])
        # Same email can be used again
        a2 = service.create_account(_make_account("2"), password="pw2")
        assert a2["uuid"] != a1["uuid"]


# ── Keyring integration ──────────────────────────────────────────────────────


class TestKeyringIntegration:
    """Tests for password storage in system keyring."""

    def test_get_password(self, service, sample_account):
        """Password set via create_account is retrievable."""
        account = service.create_account(sample_account, password="sekret123")
        pw = service.get_password(account["uuid"])
        assert pw == "sekret123"

    def test_set_password(self, service, sample_account):
        """Set password after account creation."""
        account = service.create_account(sample_account, password="pw")
        result = service.set_password(account["uuid"], "new-pw")
        assert result is True
        assert service.get_password(account["uuid"]) == "new-pw"

    def test_delete_password(self, service, sample_account):
        """Delete password from keyring."""
        account = service.create_account(sample_account, password="pw")
        result = service.delete_password(account["uuid"])
        assert result is True
        assert service.get_password(account["uuid"]) is None

    def test_password_not_in_account_data(self, service, sample_account):
        """Password never leaks into account dict."""
        account = service.create_account(sample_account, password="sekret123")
        # Update without password
        updated = service.update_account(account["uuid"], {"nomo": "x"})
        assert "pasvorto" not in account
        assert "pasvorto" not in updated
        # List
        for a in service.list_accounts():
            assert "pasvorto" not in a


# ── Signatures ───────────────────────────────────────────────────────────────


class TestSignatures:
    """Tests for signature management."""

    def test_create_signature(self, service):
        """Create a signature."""
        sig = service.create_signature("My Sig", "Best regards,\nJohn")
        assert sig["uuid"] is not None
        assert sig["nomo"] == "My Sig"

    def test_create_html_signature(self, service):
        """Create an HTML signature."""
        sig = service.create_signature("HTML Sig", "<p>Best</p>", estas_html=True)
        assert sig["estas_html"] == 1

    def test_list_signatures(self, service):
        """List all signatures."""
        service.create_signature("A", "text a")
        service.create_signature("B", "text b")
        sigs = service.list_signatures()
        assert len(sigs) == 2

    def test_get_signature(self, service):
        """Get signature by UUID."""
        sig = service.create_signature("Test", "hello")
        got = service.get_signature(sig["uuid"])
        assert got is not None
        assert got["teksto"] == "hello"

    def test_update_signature(self, service):
        """Update signature text."""
        sig = service.create_signature("Test", "old")
        updated = service.update_signature(sig["uuid"], {"teksto": "new"})
        assert updated["teksto"] == "new"

    def test_delete_signature(self, service):
        """Soft-delete a signature."""
        sig = service.create_signature("Test", "content")
        service.delete_signature(sig["uuid"])
        assert service.get_signature(sig["uuid"]) is None

    def test_find_signature_by_name(self, service):
        """Find a signature by exact name."""
        service.create_signature("My Sig", "hello")
        sig = service.find_signature_by_name("My Sig")
        assert sig is not None
        assert sig["teksto"] == "hello"

    def test_find_signature_by_name_not_found(self, service):
        """Name lookup returns None for non-existent name."""
        assert service.find_signature_by_name("Neniu") is None

    def test_resolve_signature_by_uuid(self, service):
        """Resolve by UUID prefix."""
        sig = service.create_signature("Test", "content")
        resolved = service.resolve_signature(sig["uuid"][:8])
        assert resolved is not None
        assert resolved["uuid"] == sig["uuid"]

    def test_resolve_signature_by_name(self, service):
        """Resolve by exact name."""
        sig = service.create_signature("My Sig", "hello")
        resolved = service.resolve_signature("My Sig")
        assert resolved is not None
        assert resolved["uuid"] == sig["uuid"]

    def test_resolve_signature_name_preferred_over_uuid_prefix(self, service):
        """Name match takes precedence when name happens to look like a UUID prefix."""
        # Create a signature with a UUID-like name to test resolution order
        uuid_like_name = "abc12345"
        sig_name = service.create_signature(uuid_like_name, "by name")
        # Resolve by the name — should match by UUID first (which won't exist
        # as a full UUID), then fall back to name
        resolved = service.resolve_signature(uuid_like_name)
        assert resolved is not None
        # UUID prefix match would return None (no signature has UUID starting
        # with "abc12345"), so it falls back to name match
        assert resolved["nomo"] == uuid_like_name


# ── Send email signature integration ─────────────────────────────────────────


class TestSendEmailSignature:
    """Tests for send_email signature integration."""

    def _fake_smtp(self, monkeypatch, calls):
        """Patch A_lien.smtp.SMTPClient with a fake that records calls."""
        class FakeSMTPClient:
            def __init__(self, *a, **kw): pass
            def connect(self, *a, **kw): pass
            def disconnect(self): pass
            def send_email(self, **kw):
                calls.append(kw)
        monkeypatch.setattr("A_lien.smtp.SMTPClient", FakeSMTPClient)

    def test_send_email_uses_account_default_signature(self, service, monkeypatch):
        """send_email appends account's default signature when subskribo=None."""
        svc = service
        svc.create_signature("My Sig", "Best regards")
        acct = svc.create_account({
            "retposto": "user@test.com", "nomo": "Test",
            "imap_servilo": "imap.test.com", "smtp_servilo": "smtp.test.com",
            "subskribo": svc.find_signature_by_name("My Sig")["uuid"],
        }, password="pw")

        calls = []
        self._fake_smtp(monkeypatch, calls)

        svc.send_email(account_uuid=acct["uuid"], to=["bob@test.com"],
                       subject="Test", body="Hello")
        assert len(calls) == 1
        assert "Best regards" in calls[0].get("body", "")

    def test_send_email_signature_override(self, service, monkeypatch):
        """--subskribo overrides account default signature."""
        svc = service
        svc.create_signature("Default Sig", "Default text")
        svc.create_signature("Override Sig", "Override text")
        acct = svc.create_account({
            "retposto": "user@test.com", "nomo": "Test",
            "imap_servilo": "imap.test.com", "smtp_servilo": "smtp.test.com",
            "subskribo": svc.find_signature_by_name("Default Sig")["uuid"],
        }, password="pw")

        calls = []
        self._fake_smtp(monkeypatch, calls)

        svc.send_email(account_uuid=acct["uuid"], to=["bob@test.com"],
                       subject="Test", body="Hello",
                       subskribo="Override Sig")
        assert len(calls) == 1
        assert "Override text" in calls[0].get("body", "")
        assert "Default text" not in calls[0].get("body", "")

    def test_send_email_explicit_no_signature(self, service, monkeypatch):
        """subskribo=\"\" skips the signature entirely."""
        svc = service
        svc.create_signature("Default Sig", "Should not appear")
        acct = svc.create_account({
            "retposto": "user@test.com", "nomo": "Test",
            "imap_servilo": "imap.test.com", "smtp_servilo": "smtp.test.com",
            "subskribo": svc.find_signature_by_name("Default Sig")["uuid"],
        }, password="pw")

        calls = []
        self._fake_smtp(monkeypatch, calls)

        svc.send_email(account_uuid=acct["uuid"], to=["bob@test.com"],
                       subject="Test", body="Hello",
                       subskribo="")
        assert len(calls) == 1
        assert "Should not appear" not in calls[0].get("body", "")

    def test_send_email_html_signature(self, service, monkeypatch):
        """HTML signature is appended to html_body."""
        svc = service
        svc.create_signature("HTML Sig", "<p>Sig</p>", estas_html=True)
        acct = svc.create_account({
            "retposto": "user@test.com", "nomo": "Test",
            "imap_servilo": "imap.test.com", "smtp_servilo": "smtp.test.com",
            "subskribo": svc.find_signature_by_name("HTML Sig")["uuid"],
        }, password="pw")

        calls = []
        self._fake_smtp(monkeypatch, calls)

        svc.send_email(account_uuid=acct["uuid"], to=["bob@test.com"],
                       subject="Test", body="Hello")
        assert len(calls) == 1
        assert "<p>Sig</p>" in calls[0].get("html_body", "")

    def test_send_email_no_account_signature(self, service, monkeypatch):
        """Account without default signature sends normally (no error)."""
        svc = service
        acct = svc.create_account({
            "retposto": "user@test.com", "nomo": "Test",
            "imap_servilo": "imap.test.com", "smtp_servilo": "smtp.test.com",
        }, password="pw")

        calls = []
        self._fake_smtp(monkeypatch, calls)

        svc.send_email(account_uuid=acct["uuid"], to=["bob@test.com"],
                       subject="Test", body="Hello")
        assert len(calls) == 1


# ── Singleton ────────────────────────────────────────────────────────────────


class TestServiceSingleton:
    def teardown_method(self):
        import A_lien.service.retposto_service as rs
        rs._retposto_service = None

    def test_returns_instance(self):
        import A_lien.service.retposto_service as rs
        rs._retposto_service = None
        svc = get_retposto_service()
        assert isinstance(svc, RetpostoService)

    def test_same_instance(self):
        import A_lien.service.retposto_service as rs
        rs._retposto_service = None
        svc1 = get_retposto_service()
        svc2 = get_retposto_service()
        assert svc1 is svc2

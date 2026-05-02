"""RetpostoService — email account management with keyring integration.

Extends A-core CRUDService for kontoj table.
Passwords stored in system keyring (never in SQLite).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from A.core.service import CRUDService

from A_lien.data.storage import get_db
from A_lien.keyring import get_password as _get_keyring_pw
from A_lien.keyring import set_password as _set_keyring_pw
from A_lien.keyring import delete_password as _del_keyring_pw

_retposto_service: RetpostoService | None = None


class RetpostoService(CRUDService):
    """Email account management with keyring password storage.

    Features:
    - Account CRUD (create, update, delete) with keyring password integration
    - Signature management (CRUD on subskriboj table)
    - Password never stored in database — only in OS keyring
    """

    def __init__(self, db):
        """Initialize with kontoj table, no FTS5, undo=5."""
        super().__init__(db, "kontoj", undo_size=5)

    # ── Keyring password helpers ────────────────────────────────────────────

    @staticmethod
    def _keyring_service(account_uuid: str) -> str:
        """Keyring service name for an account."""
        return f"A-lien/{account_uuid}"

    @staticmethod
    def get_password(account_uuid: str) -> str | None:
        """Retrieve account password from system keyring.

        Args:
            account_uuid: Account identifier (UUID)

        Returns:
            Stored password, or None if not found
        """
        return _get_keyring_pw(account_uuid)

    @staticmethod
    def set_password(account_uuid: str, password: str) -> bool:
        """Store account password in system keyring.

        Args:
            account_uuid: Account identifier (UUID)
            password: Password to store

        Returns:
            True if stored successfully
        """
        return _set_keyring_pw(account_uuid, password)

    @staticmethod
    def delete_password(account_uuid: str) -> bool:
        """Remove account password from system keyring.

        Args:
            account_uuid: Account identifier (UUID)

        Returns:
            True if removed (or not found)
        """
        return _del_keyring_pw(account_uuid)

    # ── Account CRUD ────────────────────────────────────────────────────────

    def create_account(self, data: dict[str, Any], password: str) -> dict[str, Any]:
        """Create a new email account with password in keyring.

        Args:
            data: Account configuration (all fields except pasvorto)
            password: Account password (stored in keyring, NOT in DB)

        Returns:
            Created account dict (without password)
        """
        # Ensure no password field leaks to DB
        data.pop("pasvorto", None)

        account = self.create(data)

        # Store password in keyring
        self.set_password(account["uuid"], password)

        return account

    def update_account(
        self, uuid: str, data: dict[str, Any], password: str | None = None
    ) -> dict[str, Any]:
        """Update account, optionally updating keyring password.

        Args:
            uuid: Account UUID
            data: Fields to update
            password: New password (None = keep existing)

        Returns:
            Updated account dict
        """
        data.pop("pasvorto", None)

        account = self.update(uuid, data)

        if password is not None:
            self.set_password(uuid, password)

        return account

    def delete_account(self, uuid: str) -> None:
        """Delete account and remove password from keyring.

        Args:
            uuid: Account UUID
        """
        self.delete(uuid, soft=True)
        self.delete_password(uuid)

    def get_account(self, uuid: str) -> dict[str, Any] | None:
        """Get account details (password never included).

        Args:
            uuid: Account UUID

        Returns:
            Account dict or None
        """
        return self.get(uuid)

    def list_accounts(self) -> list[dict[str, Any]]:
        """List all accounts (password never included).

        Returns:
            List of account dicts
        """
        return self.list(order_by="ordo", desc=False)

    # ── IMAP/SMTP sync & send ────────────────────────────────────────────────

    def get_account_with_password(self, uuid: str) -> dict[str, Any] | None:
        """Get account config with password from keyring.

        Returns:
            Account dict with password field added, or None
        """
        acct = self.get_account(uuid)
        if acct is None:
            return None
        pw = self.get_password(uuid)
        if pw:
            acct["password"] = pw
        return acct

    def sync_account(self, uuid: str) -> Any:
        """Sync messages for a single account.

        Args:
            uuid: Account UUID

        Returns:
            SyncResult from imap module
        """
        from A_lien.imap import sync_account as _sync

        acct = self.get_account_with_password(uuid)
        if not acct or "password" not in acct:
            raise ValueError(f"No password for account: {uuid}")

        return _sync(
            host=acct.get("imap_servilo", ""),
            port=acct.get("imap_haveno", 993),
            use_ssl=acct.get("imap_ssl", 1) == 1,
            username=acct.get("imap_uzantonomo", "") or acct.get("retposto", ""),
            password=acct["password"],
        )

    def sync_all(self) -> dict[str, Any]:
        """Sync messages for all accounts concurrently.

        Returns:
            Dict mapping account UUID -> SyncResult
        """
        from A_lien.imap import sync_accounts_concurrent

        accounts = self.list_accounts()
        enriched: list[dict[str, Any]] = []
        for acct in accounts:
            pw = self.get_password(acct["uuid"])
            if pw:
                acct["password"] = pw
                enriched.append(acct)

        return sync_accounts_concurrent(enriched)

    def send_email(
        self,
        account_uuid: str,
        to: list[str],
        subject: str,
        body: str = "",
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        attachments: list[str] | None = None,
    ) -> None:
        """Send an email via SMTP.

        Args:
            account_uuid: Sender account UUID
            to: Recipients
            subject: Subject line
            body: Plain text body
            cc: CC recipients
            bcc: BCC recipients
            attachments: File paths

        Raises:
            ConnectionError, ValueError
        """
        from A_lien.smtp import SMTPClient

        acct = self.get_account_with_password(account_uuid)
        if not acct or "password" not in acct:
            raise ValueError(f"No password for account: {account_uuid}")

        client = SMTPClient(
            host=acct.get("smtp_servilo", ""),
            port=acct.get("smtp_haveno", 587),
            use_tls=acct.get("smtp_tls", 1) == 1,
        )
        try:
            client.connect(
                username=acct.get("smtp_uzantonomo", "") or acct.get("retposto", ""),
                password=acct["password"],
            )
            client.send_email(
                from_addr=acct.get("retposto", ""),
                to=to,
                subject=subject,
                body=body,
                cc=cc,
                bcc=bcc,
                attachments=attachments or [],
            )
        finally:
            client.disconnect()

    # ── Signature management (subskriboj via CRUDService) ───────────────────

    @property
    def _signatures(self) -> CRUDService:
        """Get CRUDService for subskriboj table (instance-level)."""
        return CRUDService(self.db, "subskriboj")

    def list_signatures(self) -> list[dict[str, Any]]:
        """List all signatures."""
        return self._signatures.list(order_by="nomo", desc=False)

    def create_signature(
        self, nomo: str, teksto: str, estas_html: bool = False
    ) -> dict[str, Any]:
        """Create a new signature.

        Args:
            nomo: Display name
            teksto: Signature text (plain text or HTML)
            estas_html: Whether text is HTML

        Returns:
            Created signature dict
        """
        return self._signatures.create({
            "nomo": nomo,
            "teksto": teksto,
            "estas_html": 1 if estas_html else 0,
        })

    def get_signature(self, uuid: str) -> dict[str, Any] | None:
        """Get a signature by UUID."""
        return self._signatures.get(uuid)

    def update_signature(self, uuid: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update a signature."""
        return self._signatures.update(uuid, data)

    def delete_signature(self, uuid: str) -> None:
        """Delete a signature."""
        self._signatures.delete(uuid, soft=True)


def get_retposto_service() -> RetpostoService:
    """Get the singleton RetpostoService."""
    global _retposto_service
    if _retposto_service is None:
        _retposto_service = RetpostoService(get_db())
    return _retposto_service


__all__ = ["RetpostoService", "get_retposto_service"]

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

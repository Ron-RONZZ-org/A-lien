"""Account CRUD mixin — RetpostoAccountsMixin.

Keyring password helpers + account create/update/delete/list.
"""

from __future__ import annotations

from typing import Any

from A_lien.keyring import get_password as _get_keyring_pw
from A_lien.keyring import set_password as _set_keyring_pw
from A_lien.keyring import delete_password as _del_keyring_pw


class RetpostoAccountsMixin:
    """Account CRUD with keyring password storage."""

    @staticmethod
    def _keyring_service(account_uuid: str) -> str:
        return f"A-lien/{account_uuid}"

    @staticmethod
    def get_password(account_uuid: str) -> str | None:
        """Retrieve account password from system keyring."""
        return _get_keyring_pw(account_uuid)

    @staticmethod
    def set_password(account_uuid: str, password: str) -> bool:
        """Store account password in system keyring."""
        return _set_keyring_pw(account_uuid, password)

    @staticmethod
    def delete_password(account_uuid: str) -> bool:
        """Remove account password from system keyring."""
        return _del_keyring_pw(account_uuid)

    def create_account(self, data: dict[str, Any], password: str) -> dict[str, Any]:
        """Create a new email account with password in keyring."""
        data.pop("pasvorto", None)
        account = self.create(data)
        self.set_password(account["uuid"], password)
        return account

    def update_account(
        self, uuid: str, data: dict[str, Any], password: str | None = None
    ) -> dict[str, Any]:
        """Update account, optionally updating keyring password."""
        data.pop("pasvorto", None)
        account = self.update(uuid, data)
        if password is not None:
            self.set_password(uuid, password)
        return account

    def delete_account(self, uuid: str) -> None:
        """Delete account and remove password from keyring."""
        self.delete(uuid, soft=True)
        self.delete_password(uuid)

    def delete_accounts(self, uuids: list[str]) -> list[dict[str, object | str]]:
        """Bulk-delete accounts, returning per-UUID results."""
        results: list[dict[str, object | str]] = []
        for uid in uuids:
            try:
                account = self.get_account(uid)
                if not account:
                    matches = self.find_by_uuid_prefix(uid)
                    if len(matches) == 1:
                        account = matches[0]
                    elif len(matches) > 1:
                        results.append({
                            "uuid": uid,
                            "success": False,
                            "error": f"UUID '{uid[:8]}' matches multiple accounts",
                        })
                        continue
                    else:
                        results.append({
                            "uuid": uid,
                            "success": False,
                            "error": f"Account not found: {uid[:8]}",
                        })
                        continue
                full_uuid = account["uuid"]
                self.delete(full_uuid, soft=True)
                self.delete_password(full_uuid)
                results.append({"uuid": uid, "success": True, "error": None})
            except Exception as e:
                results.append({"uuid": uid, "success": False, "error": str(e)})
        return results

    def get_account(self, uuid: str) -> dict[str, Any] | None:
        """Get account details (password never included)."""
        return self.get(uuid)

    def find_by_uuid_prefix(self, prefix: str, limit: int = 10) -> list[dict[str, Any]]:
        """Find accounts by UUID prefix."""
        return super().find_by_uuid_prefix(prefix, limit=limit)

    def list_accounts(self) -> list[dict[str, Any]]:
        """List all accounts (password never included)."""
        return self.list(order_by="ordo", desc=False)

    def get_account_with_password(self, uuid: str) -> dict[str, Any] | None:
        """Get account config with password from keyring."""
        acct = self.get_account(uuid)
        if acct is None:
            return None
        pw = self.get_password(uuid)
        if pw:
            acct["password"] = pw
        return acct

    def find_by_email(self, email: str) -> dict[str, Any] | None:
        """Find an account by its email address (exact match)."""
        return self.db.execute_one(
            "SELECT * FROM kontoj WHERE retposto = ?", (email,)
        )

    def resolve_account(self, identifier: str) -> dict[str, Any] | None:
        """Resolve an account identifier to an account dict.

        Tries in order:
        1. Exact UUID match
        2. UUID prefix match (unique)
        3. Exact email match

        Args:
            identifier: UUID, UUID prefix, or email address.

        Returns:
            Account dict, or ``None`` if not found.

        Raises:
            typer.Exit: If multiple accounts match the identifier.
        """
        # 1. Exact UUID
        acct = self.get_account(identifier)
        if acct:
            return acct

        # 2. UUID prefix
        matches = self.find_by_uuid_prefix(identifier)
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            from A import error as _error, tr_multi
            _error(tr_multi(
                f"UUID '{identifier}' kongruas kun pluraj kontoj: "
                + ", ".join(m["retposto"] for m in matches),
                f"UUID '{identifier}' matches multiple accounts: "
                + ", ".join(m["retposto"] for m in matches),
                f"L'UUID '{identifier}' correspond à plusieurs comptes: "
                + ", ".join(m["retposto"] for m in matches),
            ))
            import typer
            raise typer.Exit(1)

        # 3. Email match
        if "@" in identifier:
            acct = self.find_by_email(identifier)
            if acct:
                return acct

        return None

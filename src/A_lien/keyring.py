"""Keyring abstraction for A-lien.

Delegates to ``A.core.keyring`` (see A-core issue #24).

Usage::

    from A_lien.keyring import get_password, set_password, delete_password

    set_password("account-uuid", "my-secret")
    pw = get_password("account-uuid")
    delete_password("account-uuid")

Keyring service pattern:
    service = f"A-lien/{account_uuid}"
    key = "password"
"""

from __future__ import annotations

from A.core.keyring import get_password as _core_get
from A.core.keyring import set_password as _core_set
from A.core.keyring import delete_password as _core_del

_SERVICE_PREFIX = "A-lien"


def get_password(account_uuid: str) -> str | None:
    """Retrieve password from system keyring.

    Args:
        account_uuid: The account identifier (UUID)

    Returns:
        The stored password, or None if not found or keyring unavailable
    """
    return _core_get(f"{_SERVICE_PREFIX}/{account_uuid}", "password")


def set_password(account_uuid: str, password: str) -> bool:
    """Store a password in the system keyring.

    Args:
        account_uuid: The account identifier (UUID)
        password: The password to store

    Returns:
        True if stored successfully, False if keyring unavailable
    """
    return _core_set(f"{_SERVICE_PREFIX}/{account_uuid}", "password", password)


def delete_password(account_uuid: str) -> bool:
    """Remove a password from the system keyring.

    Args:
        account_uuid: The account identifier (UUID)

    Returns:
        True if deleted (or not found), False if keyring unavailable
    """
    return _core_del(f"{_SERVICE_PREFIX}/{account_uuid}", "password")


__all__ = [
    "get_password",
    "set_password",
    "delete_password",
]

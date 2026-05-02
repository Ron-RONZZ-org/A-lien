"""Keyring abstraction for A-lien.

Wraps the ``keyring`` library with graceful fallback when unavailable.
Will be replaced by ``A.core.keyring`` when that exists (see A-core issue #24).

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

_SERVICE_PREFIX = "A-lien"


def _keyring_available() -> bool:
    """Check if the keyring library is available.

    Checked at call time so that tests can mock ``keyring``.
    """
    try:
        import keyring  # noqa: F401
        return True
    except ImportError:
        return False


def get_password(account_uuid: str) -> str | None:
    """Retrieve password from system keyring.

    Args:
        account_uuid: The account identifier (UUID)

    Returns:
        The stored password, or None if not found or keyring unavailable
    """
    if not _keyring_available():
        return None
    try:
        import keyring
        return keyring.get_password(f"{_SERVICE_PREFIX}/{account_uuid}", "password")
    except Exception:  # pragma: no cover
        return None


def set_password(account_uuid: str, password: str) -> bool:
    """Store a password in the system keyring.

    Args:
        account_uuid: The account identifier (UUID)
        password: The password to store

    Returns:
        True if stored successfully, False if keyring unavailable
    """
    if not _keyring_available():
        return False
    try:
        import keyring
        keyring.set_password(f"{_SERVICE_PREFIX}/{account_uuid}", "password", password)
        return True
    except Exception:  # pragma: no cover
        return False


def delete_password(account_uuid: str) -> bool:
    """Remove a password from the system keyring.

    Args:
        account_uuid: The account identifier (UUID)

    Returns:
        True if deleted (or not found), False if keyring unavailable
    """
    if not _keyring_available():
        return False
    try:
        import keyring
        keyring.delete_password(f"{_SERVICE_PREFIX}/{account_uuid}", "password")
        return True
    except keyring.errors.PasswordDeleteError:
        return True  # Already gone — idempotent
    except Exception:  # pragma: no cover
        return False


__all__ = [
    "get_password",
    "set_password",
    "delete_password",
]

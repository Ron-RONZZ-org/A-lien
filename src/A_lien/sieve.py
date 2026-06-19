"""Sieve filter management for A-lien.

Provides:
- Local Sieve syntax validation via sievelib
- Remote script management via managesieve (RFC 5804)
"""

from __future__ import annotations

import socket
import ssl
from typing import Any

from A import tr_multi
from A.core.network import format_connection_error
from A_lien.service import get_retposto_service


# ── Syntax validation ────────────────────────────────────────────────────────


def validate_sieve(content: str) -> tuple[bool, str]:
    """Validate Sieve script syntax locally using sievelib.

    Args:
        content: Sieve script source

    Returns:
        (is_valid, error_message) tuple
    """
    try:
        from sievelib.parser import Parser
    except ImportError:
        # sievelib not installed — skip validation
        return True, ""

    p = Parser()
    if p.parse(content):
        return True, ""
    return False, p.error


# ── Remote management ────────────────────────────────────────────────────────


class SieveManager:
    """Thin wrapper around managesieve protocol (RFC 5804).

    Connects to a ManageSieve server to list, upload, download,
    delete, and activate Sieve scripts.
    """

    def __init__(self, host: str, port: int = 4190, use_tls: bool = True):
        self.host = host
        self.port = port
        self.use_tls = use_tls
        self._client: Any = None

    def connect(self, username: str, password: str) -> None:
        """Connect and authenticate to ManageSieve server.

        Args:
            username: Authentication username
            password: Authentication password

        Raises:
            ConnectionError: If connection or login fails
        """
        try:
            from managesieve import MANAGESIEVE as SieveClient
            self._client = SieveClient(self.host, self.port, use_tls=self.use_tls)
            login_ok = self._client.login(username, password)
            if login_ok != "OK":
                reason = self._client.response_text or login_ok
                raise ConnectionError(
                    tr_multi(
                        f"Sieve-ensaluto malsukcesis por {username}: {reason}",
                        f"Sieve login failed for {username}: {reason}",
                        f"Échec de connexion Sieve pour {username}: {reason}",
                    )
                )
        except (socket.gaierror, ConnectionRefusedError,
                TimeoutError, socket.timeout, ssl.SSLError, OSError) as e:
            raise ConnectionError(
                format_connection_error(e, self.host, self.port, "Sieve")
            ) from e
        except ConnectionError:
            raise
        except Exception as e:
            raise ConnectionError(
                tr_multi(
                    f"Sieve-konekto malsukcesis al {username}@{self.host}:{self.port} — {e}",
                    f"Sieve connection failed to {username}@{self.host}:{self.port} — {e}",
                    f"Échec de connexion Sieve vers {username}@{self.host}:{self.port} — {e}",
                )
            ) from e

    @property
    def client(self) -> Any:
        if self._client is None:
            raise RuntimeError("Not connected. Call connect() first.")
        return self._client

    def disconnect(self) -> None:
        """Close the managesieve connection."""
        if self._client:
            try:
                self._client.logout()
            except Exception:  # noqa: S110 — cleanup, ignore errors
                pass
            self._client = None

    def list_scripts(self) -> list[dict[str, Any]]:
        """List all Sieve scripts on the server.

        Returns:
            List of dicts with keys: name, active
        """
        try:
            scripts = self.client.listscripts()
            return [
                {"name": name, "active": active}
                for name, active in scripts
            ]
        except Exception as e:
            raise RuntimeError(f"Failed to list scripts: {e}") from e

    def get_script(self, name: str) -> str:
        """Download a Sieve script from the server.

        Args:
            name: Script name

        Returns:
            Script content as string
        """
        try:
            content = self.client.getscript(name)
            return content
        except Exception as e:
            raise RuntimeError(f"Failed to get script '{name}': {e}") from e

    def put_script(self, name: str, content: str) -> None:
        """Upload a Sieve script to the server.

        The script is validated locally FIRST using sievelib.

        Args:
            name: Script name
            content: Sieve script source

        Raises:
            ValueError: If syntax validation fails
            RuntimeError: If upload fails
        """
        # Local validation first
        valid, error = validate_sieve(content)
        if not valid:
            raise ValueError(
                f"Sieve syntax error in '{name}': {error}"
            )

        try:
            self.client.putscript(name, content)
        except Exception as e:
            raise RuntimeError(f"Failed to upload script '{name}': {e}") from e

    def delete_script(self, name: str) -> None:
        """Delete a Sieve script from the server.

        Args:
            name: Script name
        """
        try:
            self.client.deletescript(name)
        except Exception as e:
            raise RuntimeError(f"Failed to delete script '{name}': {e}") from e

    def activate_script(self, name: str) -> None:
        """Set a script as the active Sieve script.

        Args:
            name: Script name
        """
        try:
            self.client.setactive(name)
        except Exception as e:
            raise RuntimeError(f"Failed to activate script '{name}': {e}") from e


# ── Convenience: connect from account ────────────────────────────────────────


def get_sieve_manager(identifier: str) -> SieveManager:
    """Create a SieveManager connected using an account's Sieve settings.

    Accepts an account UUID, UUID prefix, or email address. Resolves
    to the account record before connecting.

    Falls back to IMAP credentials if Sieve-specific credentials are
    not configured.

    Args:
        identifier: Account UUID, UUID prefix, or email address

    Returns:
        Connected SieveManager

    Raises:
        ValueError: If account not found or no password
        ConnectionError: If connection fails
    """
    svc = get_retposto_service()
    acct = svc.resolve_account(identifier)
    if not acct:
        raise ValueError(f"Account not found: {identifier}")
    acct_with_pw = svc.get_account_with_password(acct["uuid"])
    if not acct_with_pw:
        raise ValueError(
            f"No password configured for account {identifier}"
        )

    manager = SieveManager(
        host=acct.get("sieve_servilo", "") or acct.get("imap_servilo", ""),
        port=int(acct.get("sieve_haveno", 4190)),
        use_tls=acct.get("sieve_starttls", 1) == 1,
    )
    manager.connect(
        username=acct.get("sieve_uzantonomo", "") or acct.get("retposto", ""),
        password=acct["password"],
    )
    return manager


__all__ = [
    "SieveManager",
    "get_sieve_manager",
    "validate_sieve",
]

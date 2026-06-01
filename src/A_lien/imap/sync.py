"""Account-level IMAP sync functions."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
import uuid

from A_lien.data.storage import get_db
from A_lien.imap._sync_types import SyncResult
from A_lien.imap.client import IMAPClient
from A_lien.service.retposto_sync import get_known_uids, store_message


class _ThreadLocalStore:
    """MessageStore with a per-instance SQLiteDB connection.

    Each instance creates its own SQLiteDB, avoiding the
    "SQLite objects created in a thread can only be used in that same thread"
    error when sync_accounts_concurrent runs sync tasks in a ThreadPoolExecutor.

    Implements the MessageStore protocol and exposes ``.db`` for code that
    accesses it directly (e.g. ``IMAPClient._ensure_folder``).
    """

    def __init__(self) -> None:
        self.db = get_db()

    def get_known_uids(self, konto_id: str, dosierujo_id: str) -> set[int]:
        """Get set of already-synced IMAP UIDs (delegates to module helper)."""
        return get_known_uids(self.db, konto_id, dosierujo_id)

    def store_message(self, data: dict[str, Any], force: bool = False) -> str:
        """Insert or update a message (delegates to module helper)."""
        return store_message(self.db, data, force=force)


def sync_account(
    host: str, port: int, use_ssl: bool,
    username: str, password: str,
    konto_id: str,
    db_store: Any,
    folders: list[str] | None = None,
    force: bool = False,
) -> SyncResult:
    """Sync all messages from an IMAP account.

    Args:
        host: IMAP server
        port: IMAP port
        use_ssl: Use SSL
        username: Login username
        password: Login password
        konto_id: Account UUID for DB lookups
        db_store: Object with get_known_uids() and store_message()
        folders: Specific folders to sync (None = all)
        force: If True, re-download all messages even if already synced

    Returns:
        Aggregated SyncResult
    """
    client = IMAPClient(host, port, use_ssl)
    try:
        client.connect(username, password)
        result = SyncResult()

        available = client.list_folders()
        target_folders = folders or [f["name"] for f in available]

        for folder_name in target_folders:
            dosierujo_id = str(uuid.uuid5(
                uuid.NAMESPACE_DNS, f"{konto_id}/{folder_name}",
            ))
            try:
                client._ensure_folder(konto_id, folder_name, db_store)
            except Exception:  # noqa: S110 — folder already exists, non-fatal
                pass
            fr = client.sync_folder(
                folder_name, konto_id, dosierujo_id, db_store,
                force=force,
            )
            result.total += fr.total
            result.new += fr.new
            result.updated += fr.updated
            result.errors.extend(fr.errors)

        return result
    finally:
        client.disconnect()


def sync_accounts_concurrent(
    accounts: list[dict[str, Any]],
    max_workers: int = 4,
) -> dict[str, SyncResult]:
    """Sync multiple accounts concurrently using ThreadPoolExecutor.

    Each worker thread creates its own ``_ThreadLocalStore`` (with a private
    ``SQLiteDB`` connection) to avoid the
    "SQLite objects created in a thread can only be used in that same thread"
    error that occurs when a single ``sqlite3.Connection`` is shared across threads.

    Args:
        accounts: List of account dicts with connection info.
                  Each must include: host, port, use_ssl, username, password,
                  uuid.  ``db_store`` is **not** passed from the caller;
                  each thread creates its own.
        max_workers: Max concurrent connections

    Returns:
        Dict mapping account UUID -> SyncResult
    """
    results: dict[str, SyncResult] = {}

    def _sync_one(acct: dict[str, Any]) -> tuple[str, SyncResult]:
        uid = acct.get("uuid", "?")
        email = acct.get("retposto", uid[:8])
        pw = acct.get("password", "")
        # Per-thread SQLiteDB — each thread gets its own connection
        db_store = _ThreadLocalStore()
        try:
            sr = sync_account(
                host=acct.get("imap_servilo", ""),
                port=acct.get("imap_haveno", 993),
                use_ssl=acct.get("imap_ssl", 1) == 1,
                username=acct.get("imap_uzantonomo", "") or acct.get("retposto", ""),
                password=pw,
                konto_id=uid,
                db_store=db_store,
                force=acct.get("force", False),
            )
            return uid, sr
        except Exception as e:
            sr = SyncResult()
            sr.errors.append(f"[{email}] {e}")
            return uid, sr

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_sync_one, a): a for a in accounts}
        for future in as_completed(futures):
            uid, sr = future.result()
            results[uid] = sr

    return results


__all__ = [
    "sync_account",
    "sync_accounts_concurrent",
]

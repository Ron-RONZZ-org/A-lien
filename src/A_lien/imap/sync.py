"""Account-level IMAP sync functions."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
import uuid

from A_lien.imap.client import IMAPClient, SyncResult


def sync_account(
    host: str, port: int, use_ssl: bool,
    username: str, password: str,
    konto_id: str,
    db_store: Any,
    folders: list[str] | None = None,
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

    Args:
        accounts: List of account dicts with connection info.
                  Each must include: host, port, use_ssl, username, password,
                  uuid, db_store (MessageStore)
        max_workers: Max concurrent connections

    Returns:
        Dict mapping account UUID -> SyncResult
    """
    results: dict[str, SyncResult] = {}

    def _sync_one(acct: dict[str, Any]) -> tuple[str, SyncResult]:
        uid = acct.get("uuid", "?")
        email = acct.get("retposto", uid[:8])
        pw = acct.get("password", "")
        db_store_m = acct.get("db_store")
        try:
            sr = sync_account(
                host=acct.get("imap_servilo", ""),
                port=acct.get("imap_haveno", 993),
                use_ssl=acct.get("imap_ssl", 1) == 1,
                username=acct.get("imap_uzantonomo", "") or acct.get("retposto", ""),
                password=pw,
                konto_id=uid,
                db_store=db_store_m,
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

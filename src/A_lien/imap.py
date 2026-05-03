"""IMAP sync engine for A-lien.

Provides async-free, concurrent IMAP folder and message synchronization
using stdlib imaplib and concurrent.futures.ThreadPoolExecutor.
"""

from __future__ import annotations

import imaplib
import email as email_lib
from email.header import decode_header
from email.utils import parsedate_to_datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Callable, Protocol
import uuid
import json


# ── Helpers ──────────────────────────────────────────────────────────────────


def _decode_mime_header(value: str) -> str:
    """Decode a MIME encoded header value to plain text."""
    if not value:
        return ""
    parts = decode_header(value)
    result: list[str] = []
    for part, encoding in parts:
        if isinstance(part, bytes):
            result.append(part.decode(encoding or "utf-8", errors="replace"))
        else:
            result.append(str(part))
    return " ".join(result)


def _parse_email_address(value: str) -> str:
    """Extract email address from 'Name <addr@dom.ain>' form."""
    if not value:
        return ""
    if "<" in value and ">" in value:
        return value.split("<")[1].split(">")[0].strip()
    return value.strip()


def _extract_sender_name(from_header: str) -> str:
    """Extract display name from 'Name <addr@dom.ain>' form."""
    if not from_header:
        return ""
    if "<" in from_header and ">" in from_header:
        return from_header.split("<")[0].strip().strip("\"'")
    return ""


_NO_REPLY_PATTERNS: tuple[str, ...] = (
    "no-reply", "noreply", "no_reply", "noreplay",
    "noresponder", "donotreply", "do-not-reply",
    "mailer-daemon", "mailer_daemon",
    "notifications", "notification",
    "nepagesu", "nepagas",
)


def _is_likely_temporary_local_part(local: str) -> bool:
    """Check if local part looks like a temporary/throwaway address."""
    if len(local) > 30:
        return True
    digits = sum(1 for c in local if c.isdigit())
    if len(local) > 0 and digits / len(local) > 0.6:
        return True
    return False


def should_autosave_contact(email_addr: str) -> bool:
    """Check if an email address should be auto-saved as a contact.

    Skips: no-reply, noreply, mailer-daemon, long random local-parts, etc.
    """
    addr = _parse_email_address(email_addr)
    if "@" not in addr:
        return False
    local, _domain = addr.split("@", 1)
    local_low = local.lower()
    if any(pat in local_low for pat in _NO_REPLY_PATTERNS):
        return False
    if _is_likely_temporary_local_part(local_low):
        return False
    return True


def _parse_address_list(value: str) -> list[str]:
    """Parse a list of email addresses from a header value."""
    if not value:
        return []
    results = []
    for part in value.split(","):
        addr = _parse_email_address(part.strip())
        if addr:
            results.append(addr)
    return results


# ── Storage protocol ─────────────────────────────────────────────────────────


class MessageStore(Protocol):
    """Interface for message persistence during IMAP sync."""

    def get_known_uids(self, konto_id: str, dosierujo_id: str) -> set[str]:
        """Return set of known IMAP UIDs for an account+folder combination."""
        ...

    def store_message(self, data: dict[str, Any]) -> str:
        """Persist a parsed message dict. Return the stored message UUID."""
        ...


# ── Sync result ──────────────────────────────────────────────────────────────


class SyncResult:
    """Result of a folder/account sync operation."""

    def __init__(self) -> None:
        self.total = 0
        self.new = 0
        self.updated = 0
        self.errors: list[str] = []

    def __repr__(self) -> str:
        return (
            f"SyncResult(total={self.total}, new={self.new}, "
            f"updated={self.updated}, errors={len(self.errors)})"
        )


# ── IMAP Client ──────────────────────────────────────────────────────────────


class IMAPClient:
    """Low-level IMAP operations for a single connection."""

    def __init__(self, host: str, port: int = 993, use_ssl: bool = True):
        self.host = host
        self.port = port
        self.use_ssl = use_ssl
        self._conn: imaplib.IMAP4 | None = None

    def connect(self, username: str, password: str) -> None:
        """Connect and login to IMAP server.

        Args:
            username: IMAP username (usually email)
            password: IMAP password

        Raises:
            ConnectionError: If connection or login fails
        """
        try:
            if self.use_ssl:
                self._conn = imaplib.IMAP4_SSL(self.host, self.port)
            else:
                self._conn = imaplib.IMAP4(self.host, self.port)
            self._conn.login(username, password)
        except Exception as e:
            raise ConnectionError(f"IMAP connection failed: {e}") from e

    @property
    def conn(self) -> imaplib.IMAP4:
        """Get the underlying IMAP connection (must be connected first)."""
        if self._conn is None:
            raise RuntimeError("Not connected. Call connect() first.")
        return self._conn

    def disconnect(self) -> None:
        """Close IMAP connection."""
        if self._conn:
            try:
                self._conn.logout()
            except Exception:
                pass
            self._conn = None

    def list_folders(self) -> list[dict[str, Any]]:
        """List all IMAP folders/mailboxes.

        Returns:
            List of dicts with keys: name, delimiter, flags
        """
        result: list[dict[str, Any]] = []
        try:
            typ, data = self.conn.list()
            if typ != "OK":
                return result
            for line in data:
                if not line:
                    continue
                decoded = line.decode("utf-8", errors="replace")
                parts = decoded.split('"')
                if len(parts) >= 3:
                    flags_str = parts[0].strip("() ")
                    name = parts[-2].strip()
                    result.append({
                        "name": name,
                        "delimiter": "/",
                        "flags": flags_str.split() if flags_str else [],
                    })
        except Exception:
            pass
        return result

    def _ensure_folder(
        self, konto_id: str, folder_name: str, db_store: MessageStore,
    ) -> str:
        """Ensure folder exists in local DB, return its UUID."""
        # This should be handled by the service layer
        # For now, generate a stable UUID from konto_id + folder_name
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{konto_id}/{folder_name}"))

    def sync_folder(
        self,
        folder: str,
        konto_id: str,
        dosierujo_id: str,
        db_store: MessageStore,
    ) -> SyncResult:
        """Sync messages in a single folder, storing new ones.

        Args:
            folder: IMAP folder name (e.g., 'INBOX')
            konto_id: Account UUID
            dosierujo_id: Folder UUID in local DB
            db_store: Object with get_known_uids() and store_message()

        Returns:
            SyncResult with counts
        """
        result = SyncResult()

        try:
            typ, data = self.conn.select(folder, readonly=True)
            if typ != "OK":
                result.errors.append(f"Cannot select folder: {folder}")
                return result

            # Get known UIDs to skip already-synced messages
            known_uids = db_store.get_known_uids(konto_id, dosierujo_id)

            # Fetch all message UIDs
            typ, msg_ids = self.conn.search(None, "ALL")
            if typ != "OK":
                return result

            ids = msg_ids[0].split() if msg_ids[0] else []
            result.total = len(ids)

            if not ids:
                return result

            # Fetch FLAGS and full BODY for ALL messages (we need the body)
            # Use BODY.PEEK to avoid marking messages as read
            typ, fetch_data = self.conn.fetch(
                b",".join(ids), "(FLAGS BODY.PEEK[])",
            )
            if typ != "OK":
                return result

            for i in range(0, len(fetch_data), 2):
                if not isinstance(fetch_data[i], tuple):
                    continue
                try:
                    raw_data = fetch_data[i][1]
                    msg = email_lib.message_from_bytes(raw_data)

                    imap_uid = _decode_mime_header(msg.get("Message-ID", ""))
                    if not imap_uid:
                        # Fallback: use a hash of the raw message
                        imap_uid = str(uuid.uuid5(
                            uuid.NAMESPACE_DNS, str(hash(raw_data)),
                        ))

                    # Only store new messages
                    if imap_uid in known_uids:
                        result.total -= 1  # counted but not new
                        continue

                    self._store_message(
                        folder, msg, konto_id, dosierujo_id,
                        imap_uid, db_store,
                    )
                    result.new += 1

                except Exception as e:
                    result.errors.append(f"Parse/store error: {e}")

            self.conn.close()
        except Exception as e:
            result.errors.append(f"Sync error: {e}")

        return result

    def _store_message(
        self,
        folder: str,
        msg: Any,
        konto_id: str,
        dosierujo_id: str,
        imap_uid: str,
        db_store: MessageStore,
    ) -> str | None:
        """Parse a single email and store it via db_store.

        Returns:
            Stored message UUID, or None if skipped.
        """
        now = datetime.now(timezone.utc).isoformat()
        message_id = _decode_mime_header(msg.get("Message-ID", ""))
        in_reply_to = _decode_mime_header(msg.get("In-Reply-To", ""))
        references = _decode_mime_header(msg.get("References", ""))

        subject = _decode_mime_header(msg.get("Subject", ""))
        from_header = _decode_mime_header(msg.get("From", ""))
        to_raw = _decode_mime_header(msg.get("To", ""))
        cc_raw = _decode_mime_header(msg.get("Cc", ""))
        date_str = msg.get("Date", "")

        # Parse date
        ricevita_je = now
        if date_str:
            try:
                dt = parsedate_to_datetime(date_str)
                ricevita_je = dt.isoformat()
            except Exception:
                pass

        # Extract plain text and HTML body
        body = ""
        html_body = ""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == "text/plain" and not body:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        body = payload.decode(charset, errors="replace")
                elif content_type == "text/html" and not html_body:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        html_body = payload.decode(charset, errors="replace")
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                body = payload.decode(charset, errors="replace")

        data: dict[str, Any] = {
            "uuid": str(uuid.uuid4()),
            "konto_id": konto_id,
            "dosierujo_id": dosierujo_id,
            "message_id": message_id,
            "in_reply_to": in_reply_to,
            "references_hdr": references,
            "uid": imap_uid,
            "de": from_header,
            "al": json.dumps(_parse_address_list(to_raw), ensure_ascii=False),
            "kc": json.dumps(_parse_address_list(cc_raw), ensure_ascii=False),
            "bkc": "[]",
            "subjekto": subject,
            "korpo": body,
            "html_korpo": html_body,
            "prioritato": 5,
            "legita": 0,
            "stelo": 0,
            "spamo": 0,
            "forigita": 0,
            "aldonajxoj": "[]",
            "etikedoj": "[]",
            "ricevita_je": ricevita_je,
            "kreita_je": now,
            "modifita_je": now,
        }

        stored_uuid = db_store.store_message(data)
        return stored_uuid


# ── Account-level sync ───────────────────────────────────────────────────────


def sync_account(
    host: str, port: int, use_ssl: bool,
    username: str, password: str,
    konto_id: str,
    db_store: MessageStore,
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
            # Generate a stable folder UUID (service layer should manage this)
            dosierujo_id = str(uuid.uuid5(
                uuid.NAMESPACE_DNS, f"{konto_id}/{folder_name}",
            ))
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
        pw = acct.get("password", "")
        db_store = acct.get("db_store")
        try:
            sr = sync_account(
                host=acct.get("imap_servilo", ""),
                port=acct.get("imap_haveno", 993),
                use_ssl=acct.get("imap_ssl", 1) == 1,
                username=acct.get("imap_uzantonomo", "") or acct.get("retposto", ""),
                password=pw,
                konto_id=uid,
                db_store=db_store,
            )
            return uid, sr
        except Exception as e:
            sr = SyncResult()
            sr.errors.append(str(e))
            return uid, sr

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_sync_one, a): a for a in accounts}
        for future in as_completed(futures):
            uid, sr = future.result()
            results[uid] = sr

    return results


__all__ = [
    "IMAPClient",
    "SyncResult",
    "MessageStore",
    "sync_account",
    "sync_accounts_concurrent",
    "should_autosave_contact",
    "_parse_email_address",
    "_extract_sender_name",
    "_NO_REPLY_PATTERNS",
]

"""IMAP client wrapper and protocol definitions."""

from __future__ import annotations

import imaplib
import email as email_lib
import re
import socket
import ssl
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from typing import Any, Protocol
import uuid
import json

from A import tr_multi
from A.core.network import format_connection_error
from A_lien.imap.helpers import (
    _decode_mime_header,
    _parse_address_list,
)


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


class MessageStore(Protocol):
    """Interface for message persistence during IMAP sync."""

    def get_known_uids(self, konto_id: str, dosierujo_id: str) -> set[int]:
        """Return set of known IMAP UIDs (integers) for dedup."""
        ...

    def store_message(self, data: dict[str, Any]) -> str:
        """Persist a parsed message dict. Return the stored message UUID."""
        ...


class IMAPClient:
    """Low-level IMAP operations for a single connection."""

    def __init__(self, host: str, port: int = 993, use_ssl: bool = True,
                 debug: int = 0):
        self.host = host
        self.port = port
        self.use_ssl = use_ssl
        self._debug = debug
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
            if self._debug:
                self._conn.debug = self._debug
            self._conn.login(username, password)
        except imaplib.IMAP4.error as e:
            raise ConnectionError(
                tr_multi(
                    f"IMAP-aŭtentigo malsukcesis por {username}@{self.host}:{self.port} — {e}",
                    f"IMAP authentication failed for {username}@{self.host}:{self.port} — {e}",
                    f"Échec d'authentification IMAP pour {username}@{self.host}:{self.port} — {e}",
                )
            ) from e
        except (socket.gaierror, ConnectionRefusedError,
                TimeoutError, socket.timeout, ssl.SSLError, OSError) as e:
            raise ConnectionError(
                format_connection_error(e, self.host, self.port, "IMAP")
            ) from e
        except Exception as e:
            raise ConnectionError(
                tr_multi(
                    f"IMAP-konekto malsukcesis al {username}@{self.host}:{self.port} — {e}",
                    f"IMAP connection failed to {username}@{self.host}:{self.port} — {e}",
                    f"Échec de connexion IMAP vers {username}@{self.host}:{self.port} — {e}",
                )
            ) from e

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
            except Exception:  # noqa: S110 — cleanup, ignore errors
                pass
            self._conn = None

    def list_folders(self) -> list[dict[str, Any]]:
        """List all IMAP folders/mailboxes.

        Returns:
            List of dicts with keys: name, delimiter, flags
        """
        result: list[dict[str, Any]] = []
        typ, data = self.conn.list()
        if typ != "OK":
            return result
        # Regex to extract folder name from LIST response:
        #   (\Flags) "/" "QuotedName"  or  (\Flags) "/" UnquotedName
        _folder_re = re.compile(rb'"/" "?([^"]+)"?\s*$')
        for line in data:
            if not line:
                continue
            m = _folder_re.search(line)
            if m:
                name = m.group(1).decode("utf-8", errors="replace").strip()
            else:
                # Fallback for unusual formats: split by quotes
                decoded = line.decode("utf-8", errors="replace")
                parts = decoded.split('"')
                if len(parts) >= 3:
                    name = parts[-2].strip() if len(parts) == 3 else parts[2].strip()
                else:
                    continue
            if not name or name == "/":
                # Bare separator — use flags to identify special folders
                decoded = line.decode("utf-8", errors="replace")
                flags_str = decoded.split('"')[0].strip("() ")
                if "\\Sent" in flags_str:
                    name = "Sent"
                elif "\\Drafts" in flags_str:
                    name = "Drafts"
                elif "\\Trash" in flags_str:
                    name = "Trash"
                elif "\\Junk" in flags_str:
                    name = "Junk"
                elif "\\Archive" in flags_str:
                    name = "Archive"
                elif "\\Inbox" in flags_str:
                    name = "INBOX"
                else:
                    continue
            result.append({
                "name": name,
                "delimiter": "/",
                "flags": [],
            })
        return result

    def _ensure_folder(
        self, konto_id: str, folder_name: str, db_store: MessageStore,
    ) -> str:
        """Ensure folder exists in local DB, return its UUID."""
        dosierujo_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{konto_id}/{folder_name}"))
        try:
            now = datetime.now(timezone.utc).isoformat()
            db_store.db.execute(
                "INSERT OR IGNORE INTO dosierujoj "
                "(uuid, konto_id, nomo, patro_id, kreita_je, modifita_je) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (dosierujo_id, konto_id, folder_name, None, now, now),
            )
        except Exception:  # noqa: S110 — INSERT OR IGNORE, non-fatal
            pass
        return dosierujo_id

    def sync_folder(
        self,
        folder: str,
        konto_id: str,
        dosierujo_id: str,
        db_store: MessageStore,
        force: bool = False,
    ) -> SyncResult:
        """Sync messages in a single folder, storing new ones.

        Uses IMAP UID SEARCH/FETCH (RFC 3501) for stable dedup.
        Fetches newest UIDs first, paginated in chunks of 100.

        Args:
            folder: IMAP folder name (e.g., 'INBOX')
            konto_id: Account UUID
            dosierujo_id: Folder UUID in local DB
            db_store: Object with get_known_uids() and store_message()
            force: If True, re-download all messages even if already synced

        Returns:
            SyncResult with counts
        """
        result = SyncResult()

        try:
            typ, data = self.conn.select(folder, readonly=True)
            if typ != "OK":
                result.errors.append(f"Cannot select folder: {folder}")
                return result

            # Get mailbox message count from SELECT response
            mailbox_count = int(data[0]) if data and data[0] else 0

            # Fetch all IMAP UIDs from server (stable per-folder identifiers).
            # Some servers cap SEARCH at ~5000 results — paginate if needed.
            use_uid_fetch = True
            all_uids: list[int] = []
            search_uid_from: int | None = None  # None = "ALL"
            while True:
                if search_uid_from is not None:
                    typ, uid_data = self.conn.uid(
                        "search", None, f"UID {search_uid_from}:*",
                    )
                else:
                    typ, uid_data = self.conn.uid("search", None, "ALL")

                if typ != "OK":
                    result.errors.append(
                        f"UID SEARCH failed for {folder}"
                    )
                    return result
                if not uid_data or not uid_data[0]:
                    break

                chunk = [int(x) for x in uid_data[0].split()]
                if not chunk:
                    break
                all_uids.extend(chunk)

                # If result count is suspiciously round, try fetching more
                if len(chunk) in (5000, 10000, 20000):
                    search_uid_from = chunk[-1] + 1
                else:
                    break

            # If UID SEARCH returned far fewer than mailbox contains,
            # the server might not support UID SEARCH properly.
            # Fall back to regular SEARCH (returns sequence numbers).
            if mailbox_count > 0 and len(all_uids) < mailbox_count // 2:
                result.errors.append(
                    f"UID SEARCH returned {len(all_uids)} of {mailbox_count} "
                    f"messages for {folder} — falling back to SEARCH"
                )
                use_uid_fetch = False
                typ, seq_data = self.conn.search(None, "ALL")
                if typ == "OK" and seq_data and seq_data[0]:
                    all_uids = [int(x) for x in seq_data[0].split()]

            result.total = len(all_uids)

            # Filter out already-synced UIDs (unless force refresh)
            known_uids: set[int] = set()
            if not force:
                known_uids = db_store.get_known_uids(konto_id, dosierujo_id)
            new_uids = [uid for uid in all_uids if uid not in known_uids]

            if not new_uids:
                self.conn.close()
                return result

            # Fetch newest UIDs first (UIDs are monotonically increasing)
            new_uids.sort(reverse=True)

            # Paginate in chunks of 100 to avoid command-line overflow
            chunk_size = 100
            _IMAP_UID_RE = re.compile(rb"UID (\d+)")

            for start in range(0, len(new_uids), chunk_size):
                chunk = new_uids[start : start + chunk_size]
                uid_list = b",".join(str(u).encode() for u in chunk)

                if use_uid_fetch:
                    typ, fetch_data = self.conn.uid(
                        "fetch", uid_list, "(FLAGS BODY.PEEK[] UID)",
                    )
                else:
                    typ, fetch_data = self.conn.fetch(
                        uid_list, "(FLAGS BODY.PEEK[] UID)",
                    )
                if typ != "OK":
                    result.errors.append(
                        f"FETCH error at IDs {chunk[0]}..{chunk[-1]}"
                    )
                    continue

                for item in fetch_data:
                    if not isinstance(item, tuple):
                        continue
                    raw_flags = item[0] if item[0] else b""
                    raw_data = item[1]
                    imap_uid = -1  # placeholder for error messages
                    try:
                        # Extract IMAP UID from FETCH response
                        uid_match = _IMAP_UID_RE.search(raw_flags)
                        if not uid_match:
                            result.errors.append(
                                f"UID regex failed on: {raw_flags[:200]!r}"
                            )
                            continue
                        imap_uid = int(uid_match.group(1))

                        if not force and imap_uid in known_uids:
                            continue

                        msg = email_lib.message_from_bytes(raw_data)

                        self._store_message(
                            folder, msg, konto_id, dosierujo_id,
                            imap_uid, db_store, force=force,
                        )
                        result.new += 1

                    except Exception as e:
                        result.errors.append(
                            f"Parse/store error at UID {imap_uid}: {e}"
                        )

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
        imap_uid: int,
        db_store: MessageStore,
        force: bool = False,
    ) -> str | None:
        """Parse a single email and store it via db_store."""
        now = datetime.now(timezone.utc).isoformat()
        message_id = _decode_mime_header(msg.get("Message-ID", ""))
        in_reply_to = _decode_mime_header(msg.get("In-Reply-To", ""))
        references = _decode_mime_header(msg.get("References", ""))

        subject = _decode_mime_header(msg.get("Subject", ""))
        from_header = _decode_mime_header(msg.get("From", ""))
        to_raw = _decode_mime_header(msg.get("To", ""))
        cc_raw = _decode_mime_header(msg.get("Cc", ""))
        date_str = msg.get("Date", "")

        ricevita_je = now
        if date_str:
            try:
                dt = parsedate_to_datetime(date_str)
                ricevita_je = dt.isoformat()
            except (TypeError, ValueError):  # noqa: S110 — invalid date, use current time
                pass

        body = ""
        html_body = ""
        attachments: list[dict[str, Any]] = []
        if msg.is_multipart():
            for part in msg.walk():
                ct = part.get_content_type()
                disp = str(part.get("Content-Disposition") or "")
                filename = part.get_filename()
                # Detect attachments via Content-Disposition header (matching autish-legacy)
                if "attachment" in disp or filename:
                    fname = filename or "attachment"
                    payload = part.get_payload(decode=True)
                    attachments.append({
                        "dosiernomo": fname,
                        "mime_tipo": ct,
                        "grandeco": len(payload) if payload else 0,
                    })
                # Calendar invites and other non-text MIME parts
                elif ct not in ("text/plain", "text/html") and not part.is_multipart():
                    name = part.get_param("name", None, "Content-Type") or ""
                    if name:
                        payload = part.get_payload(decode=True)
                        attachments.append({
                            "dosiernomo": name,
                            "mime_tipo": ct,
                            "grandeco": len(payload) if payload else 0,
                        })
                elif ct == "text/plain" and not body and not filename:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        body = payload.decode(charset, errors="replace")
                elif ct == "text/html" and not html_body and not filename:
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
            "imap_uid": imap_uid,
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
            "aldonajxoj": json.dumps(attachments, ensure_ascii=False),
            "etikedoj": "[]",
            "ricevita_je": ricevita_je,
            "kreita_je": now,
            "modifita_je": now,
        }

        stored_uuid = db_store.store_message(data, force=force)
        return stored_uuid

    # ── Message operations (move, delete, append) ────────────────────────────

    def move_message(
        self, source_folder: str, uid: int, target_folder: str
    ) -> bool:
        """Move a message via IMAP MOVE (RFC 6851) or COPY+DELETE fallback.

        Args:
            source_folder: Source folder name
            uid: IMAP UID of the message
            target_folder: Target folder name

        Returns:
            True if the move succeeded, False otherwise
        """
        self.conn.select(source_folder)
        try:
            typ, _ = self.conn.uid("MOVE", str(uid), target_folder)
            if typ == "OK":
                return True
        except imaplib.IMAP4.error:
            pass
        # Fallback: COPY + STORE +FLAGS.SILENT \Deleted
        typ, _ = self.conn.uid("COPY", str(uid), target_folder)
        if typ != "OK":
            return False
        self.conn.uid("STORE", str(uid), "+FLAGS.SILENT", "(\\Deleted)")
        self.conn.expunge()
        return True

    def delete_message(self, folder: str, uid: int) -> None:
        """Mark a message as ``\\Deleted`` in an IMAP folder.

        Args:
            folder: Folder name
            uid: IMAP UID of the message
        """
        self.conn.select(folder)
        self.conn.uid("STORE", str(uid), "+FLAGS.SILENT", "(\\Deleted)")

    def set_flags(
        self, folder: str, uid: int,
        add: list[str] | None = None,
        remove: list[str] | None = None,
    ) -> None:
        """Add or remove IMAP flags on a message.

        Args:
            folder: Folder name
            uid: IMAP UID of the message
            add: Flags to add (e.g. ``["\\Seen", "\\Flagged"]``)
            remove: Flags to remove (e.g. ``["\\Deleted"]``)
        """
        self.conn.select(folder)
        if add:
            flag_str = " ".join(add)
            self.conn.uid("STORE", str(uid), "+FLAGS.SILENT", f"({flag_str})")
        if remove:
            flag_str = " ".join(remove)
            self.conn.uid("STORE", str(uid), "-FLAGS.SILENT", f"({flag_str})")

    def append_message(
        self, folder: str, raw_message: bytes, flags: list[str] | None = None
    ) -> bool:
        """Append a raw message to an IMAP folder.

        Args:
            folder: Target folder name
            raw_message: Raw RFC 5322 message bytes
            flags: Optional IMAP flags (e.g. ``["\\Seen"]``)

        Returns:
            True if the append succeeded
        """
        flag_str = " ".join(flags) if flags else ""
        try:
            typ, _ = self.conn.append(folder, flag_str, None, raw_message)
            return typ == "OK"
        except imaplib.IMAP4.error:
            return False

    def fetch_raw_message(self, folder: str, uid: int) -> bytes | None:
        """Fetch raw RFC 5322 message bytes by UID.

        Args:
            folder: Folder name
            uid: IMAP UID of the message

        Returns:
            Raw message bytes or ``None`` if not found
        """
        self.conn.select(folder, readonly=True)
        try:
            typ, data = self.conn.uid(
                "FETCH", str(uid), "(BODY[] UID)"
            )
            if typ != "OK" or not data or not isinstance(data[0], tuple):
                return None
            return data[0][1]
        except imaplib.IMAP4.error:
            return None


__all__ = [
    "IMAPClient",
    "SyncResult",
    "MessageStore",
]

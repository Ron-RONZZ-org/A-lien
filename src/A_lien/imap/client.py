"""IMAP client wrapper — connection, folder listing, sync."""

from __future__ import annotations

import email as email_lib
import imaplib
import re
import socket
import ssl
import uuid
from datetime import datetime, timezone
from typing import Any

from A import tr_multi
from A.core.network import format_connection_error
from A_lien.imap._message_parser import parse_email_message
from A_lien.imap._sync_types import MessageStore, SyncResult


class IMAPClient:
    """Low-level IMAP operations for a single connection."""

    def __init__(self, host: str, port: int = 993, use_ssl: bool = True,
                 debug: int = 0, timeout: float | None = None):
        self.host = host
        self.port = port
        self.use_ssl = use_ssl
        self._debug = debug
        self._timeout = timeout
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
                self._conn = imaplib.IMAP4_SSL(
                    self.host, self.port, timeout=self._timeout,
                )
            else:
                self._conn = imaplib.IMAP4(
                    self.host, self.port, timeout=self._timeout,
                )
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
            except Exception:
                pass
            self._conn = None

    def list_folders(self) -> list[dict[str, Any]]:
        """List all IMAP folders/mailboxes.

        Returns:
            List of dicts with keys: name, delimiter, flags
        """
        result: list[dict[str, Any]] = []
        typ, data = self.conn.list()
        if typ != "OK" or not data:
            return result
        _folder_re = re.compile(rb'"/" "?([^"]+)"?\s*$')
        for line in data:
            if not line:
                continue
            m = _folder_re.search(line)
            if m:
                name = m.group(1).decode("utf-8", errors="replace").strip()
            else:
                decoded = line.decode("utf-8", errors="replace")
                parts = decoded.split('"')
                if len(parts) >= 3:
                    name = parts[-2].strip() if len(parts) == 3 else parts[2].strip()
                else:
                    continue
            if not name or name == "/":
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
        except Exception:
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

            mailbox_count = int(data[0]) if data and data[0] else 0

            use_uid_fetch = True
            all_uids: list[int] = []
            search_uid_from: int | None = None
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

                if len(chunk) in (5000, 10000, 20000):
                    search_uid_from = chunk[-1] + 1
                else:
                    break

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

            known_uids: set[int] = set()
            if not force:
                known_uids = db_store.get_known_uids(konto_id, dosierujo_id)
            if known_uids is None:
                known_uids = set()
            new_uids = [uid for uid in all_uids if uid not in known_uids]

            if not new_uids:
                self.conn.close()
                return result

            new_uids.sort(reverse=True)

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
                if typ != "OK" or not fetch_data:
                    result.errors.append(
                        f"FETCH error at IDs {chunk[0]}..{chunk[-1]}"
                    )
                    continue

                for item in fetch_data:
                    if not isinstance(item, tuple):
                        continue
                    raw_flags = item[0] if item[0] else b""
                    raw_data = item[1]
                    imap_uid = -1
                    try:
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
                        data = parse_email_message(
                            msg, konto_id, dosierujo_id, imap_uid,
                        )
                        db_store.store_message(data, force=force)
                        result.new += 1

                    except Exception as e:
                        result.errors.append(
                            f"Parse/store error at UID {imap_uid}: {e}"
                        )

            self.conn.close()
        except TypeError as e:
            result.errors.append(f"Sync type-error [{folder}]: {e}")
        except Exception as e:
            result.errors.append(f"Sync error: {e}")

        return result


__all__ = [
    "IMAPClient",
    "SyncResult",
    "MessageStore",
]

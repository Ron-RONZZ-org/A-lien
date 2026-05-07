"""Message operations mixin — RetpostoMessageOpsMixin.

Message mutation: mark_read, trash, move, extract, IMAP flag sync.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class RetpostoMessageOpsMixin:
    """Message mutation and IMAP operations."""

    def mark_read(self, msg_uuid: str, legita: bool = True) -> None:
        """Mark a message as read or unread locally and on IMAP server."""
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            "UPDATE mesagoj SET legita = ?, modifita_je = ? WHERE uuid = ?",
            (1 if legita else 0, now, msg_uuid),
        )
        self._imap_sync_flags(msg_uuid)

    def _imap_sync_flags(self, msg_uuid: str) -> None:
        """Sync local message flags to the IMAP server, queuing on failure."""
        msg = self.get_message(msg_uuid)
        if not msg:
            return
        konto_id = msg.get("konto_id", "")
        if not konto_id:
            return
        acct = self.get_account_with_password(konto_id)
        if not acct or "password" not in acct:
            self._enqueue_sync(msg)
            return
        imap_uid = msg.get("imap_uid")
        if imap_uid is None:
            self._enqueue_sync(msg)
            return
        folder_row = self.db.execute_one(
            "SELECT nomo FROM dosierujoj WHERE uuid = ?",
            (msg.get("dosierujo_id", ""),),
        )
        folder = folder_row["nomo"] if folder_row else "INBOX"
        legita = bool(msg.get("legita", 0))
        forigita = bool(msg.get("forigita", 0))
        from A_lien.imap.client import IMAPClient
        client = IMAPClient(
            host=acct.get("imap_servilo", ""),
            port=acct.get("imap_haveno", 993),
            use_ssl=acct.get("imap_ssl", 1) == 1,
        )
        try:
            client.connect(
                username=acct.get("imap_uzantonomo", "") or acct.get("retposto", ""),
                password=acct["password"],
            )
            add: list[str] = []
            remove: list[str] = []
            if legita:
                add.append("\\Seen")
            else:
                remove.append("\\Seen")
            if forigita:
                add.append("\\Deleted")
            else:
                remove.append("\\Deleted")
            client.set_flags(folder, int(imap_uid), add=add or None, remove=remove or None)
        except Exception:
            self._enqueue_sync(msg)
        finally:
            client.disconnect()

    def _enqueue_sync(self, msg: dict) -> None:
        """Queue a message flag sync request for later processing."""
        now = datetime.now(timezone.utc).isoformat()
        msg_uuid = msg["uuid"]
        self.db.execute(
            "INSERT OR REPLACE INTO _sync_backlog "
            "(id, msg_uuid, konto_id, dosierujo_id, imap_uid, "
            " legita, forigita, stelo, spamo, kreita_je, last_attempt, provis) "
            "VALUES ("
            "  COALESCE((SELECT id FROM _sync_backlog WHERE msg_uuid = ?), NULL),"
            "  ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0"
            ")",
            (msg_uuid, msg_uuid, msg.get("konto_id", ""), msg.get("dosierujo_id", ""),
             msg.get("imap_uid"), int(msg.get("legita", 0)), int(msg.get("forigita", 0)),
             int(msg.get("stelo", 0)), int(msg.get("spamo", 0)), now, None),
        )

    def process_sync_backlog(self) -> int:
        """Process all pending flag sync requests."""
        entries = list(self.db.execute(
            "SELECT * FROM _sync_backlog ORDER BY kreita_je ASC LIMIT 500"
        ))
        if not entries:
            return 0
        from collections import defaultdict
        by_account: dict[str, list[dict]] = defaultdict(list)
        for e in entries:
            by_account[e["konto_id"]].append(e)
        synced = 0
        for konto_id, items in by_account.items():
            acct = self.get_account_with_password(konto_id)
            if not acct or "password" not in acct:
                continue
            from A_lien.imap.client import IMAPClient
            client = IMAPClient(
                host=acct.get("imap_servilo", ""),
                port=acct.get("imap_haveno", 993),
                use_ssl=acct.get("imap_ssl", 1) == 1,
            )
            try:
                client.connect(
                    username=acct.get("imap_uzantonomo", "") or acct.get("retposto", ""),
                    password=acct["password"],
                )
                for item in items:
                    try:
                        imap_uid = item["imap_uid"]
                        if imap_uid is None:
                            continue
                        row = self.db.execute_one(
                            "SELECT nomo FROM dosierujoj WHERE uuid = ?",
                            (item.get("dosierujo_id", ""),),
                        )
                        folder = row["nomo"] if row else "INBOX"
                        add = []
                        remove = []
                        if item.get("legita"):
                            add.append("\\Seen")
                        else:
                            remove.append("\\Seen")
                        if item.get("forigita"):
                            add.append("\\Deleted")
                        else:
                            remove.append("\\Deleted")
                        client.set_flags(folder, int(imap_uid), add=add or None, remove=remove or None)
                        self.db.execute("DELETE FROM _sync_backlog WHERE id = ?", (item["id"],))
                        synced += 1
                    except Exception:
                        self.db.execute(
                            "UPDATE _sync_backlog SET provis = provis + 1, last_attempt = ? WHERE id = ?",
                            (datetime.now(timezone.utc).isoformat(), item["id"]),
                        )
            except Exception:
                pass
            finally:
                client.disconnect()
        return synced

    def trash_message(self, msg_uuid: str, permanent: bool = False) -> None:
        """Soft-delete or hard-delete a message."""
        if permanent:
            self.db.execute("DELETE FROM mesagoj WHERE uuid = ?", (msg_uuid,))
        else:
            now = datetime.now(timezone.utc).isoformat()
            self.db.execute(
                "UPDATE mesagoj SET forigita = 1, modifita_je = ? WHERE uuid = ?",
                (now, msg_uuid),
            )
            self._imap_sync_flags(msg_uuid)

    def move_message(self, msg: dict, dest_account_uuid: str, dest_folder: str) -> None:
        """Move a message to a different account/folder."""
        src_account_uuid = msg.get("konto_id", "")
        src_account = self.get_account_with_password(src_account_uuid)
        dest_account = self.get_account_with_password(dest_account_uuid)
        if not src_account or "password" not in src_account:
            raise ValueError(f"Source account {src_account_uuid[:8]} has no password")
        if not dest_account or "password" not in dest_account:
            raise ValueError(f"Destination account {dest_account_uuid[:8]} has no password")
        from A_lien.imap.client import IMAPClient
        imap = IMAPClient(
            host=src_account.get("imap_servilo", ""),
            port=src_account.get("imap_haveno", 993),
            use_ssl=src_account.get("imap_ssl", 1) == 1,
        )
        try:
            imap.connect(
                username=src_account.get("imap_uzantonomo", "") or src_account.get("retposto", ""),
                password=src_account["password"],
            )
            src_folder_row = self.db.execute_one(
                "SELECT nomo FROM dosierujoj WHERE uuid = ?",
                (msg.get("dosierujo_id", ""),),
            )
            src_folder = src_folder_row["nomo"] if src_folder_row else "INBOX"
            uid = int(msg.get("uid", 0))
            same_account = src_account_uuid == dest_account_uuid
            if same_account:
                imap.move_message(src_folder, uid, dest_folder)
                dest_folder_id = self._ensure_folder_exists(dest_account_uuid, dest_folder)
                now = datetime.now(timezone.utc).isoformat()
                self.db.execute(
                    "UPDATE mesagoj SET dosierujo_id = ?, modifita_je = ? WHERE uuid = ?",
                    (dest_folder_id, now, msg["uuid"]),
                )
            else:
                raw = imap.fetch_raw_message(src_folder, uid)
                if not raw:
                    raise ValueError(f"Could not fetch raw message (UID {uid})")
                dest_imap = IMAPClient(
                    host=dest_account.get("imap_servilo", ""),
                    port=dest_account.get("imap_haveno", 993),
                    use_ssl=dest_account.get("imap_ssl", 1) == 1,
                )
                try:
                    dest_imap.connect(
                        username=dest_account.get("imap_uzantonomo", "") or dest_account.get("retposto", ""),
                        password=dest_account["password"],
                    )
                    dest_imap.append_message(dest_folder, raw)
                finally:
                    dest_imap.disconnect()
                imap.delete_message(src_folder, uid)
                dest_folder_id = self._ensure_folder_exists(dest_account_uuid, dest_folder)
                now = datetime.now(timezone.utc).isoformat()
                self.db.execute(
                    "UPDATE mesagoj SET konto_id = ?, dosierujo_id = ?, modifita_je = ? WHERE uuid = ?",
                    (dest_account_uuid, dest_folder_id, now, msg["uuid"]),
                )
        finally:
            imap.disconnect()

    def _ensure_folder_exists(self, konto_id: str, folder_name: str) -> str:
        """Ensure an IMAP folder exists in local DB, return its UUID."""
        import uuid as uuid_mod
        row = self.db.execute_one(
            "SELECT uuid FROM dosierujoj WHERE konto_id = ? AND nomo = ?",
            (konto_id, folder_name),
        )
        if row:
            return row["uuid"]
        folder_uuid = str(uuid_mod.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            "INSERT INTO dosierujoj (uuid, konto_id, nomo, kreita_je, modifita_je) "
            "VALUES (?, ?, ?, ?, ?)",
            (folder_uuid, konto_id, folder_name, now, now),
        )
        return folder_uuid

    def extract_attachment(
        self, msg_uuid: str, filename: str, output_dir: str | None = None,
    ) -> str:
        """Extract an attachment from a message and save it to disk."""
        from pathlib import Path
        msg = self.get_message(msg_uuid)
        if not msg:
            raise ValueError(f"Message not found: {msg_uuid[:8]}")
        konto_id = msg.get("konto_id", "")
        imap_uid = msg.get("imap_uid")
        if not imap_uid:
            raise ValueError(f"Message {msg_uuid[:8]} has no IMAP UID")
        acct = self.get_account_with_password(konto_id)
        if not acct or "password" not in acct:
            raise ValueError(f"Account {konto_id[:8]} has no password")
        folder_row = self.db.execute_one(
            "SELECT nomo FROM dosierujoj WHERE uuid = ?",
            (msg.get("dosierujo_id", ""),),
        )
        folder = folder_row["nomo"] if folder_row else "INBOX"
        from A_lien.imap.client import IMAPClient
        client = IMAPClient(
            host=acct.get("imap_servilo", ""),
            port=acct.get("imap_haveno", 993),
            use_ssl=acct.get("imap_ssl", 1) == 1,
        )
        try:
            client.connect(
                username=acct.get("imap_uzantonomo", "") or acct.get("retposto", ""),
                password=acct["password"],
            )
            raw = client.fetch_raw_message(folder, int(imap_uid))
            if not raw:
                raise ValueError(f"Could not fetch message from IMAP")
        finally:
            client.disconnect()
        import email as email_lib
        parsed = email_lib.message_from_bytes(raw)
        payload: bytes | None = None
        if parsed.is_multipart():
            for part in parsed.walk():
                disp = str(part.get("Content-Disposition") or "")
                fn = part.get_filename()
                if "attachment" in disp or fn:
                    match_fn = fn or "attachment"
                    if match_fn == filename:
                        payload = part.get_payload(decode=True)
                        break
        else:
            payload = parsed.get_payload(decode=True)
        if not payload:
            raise ValueError(f"Attachment '{filename}' not found in message")
        out_dir = Path(output_dir or ".")
        out_dir.mkdir(parents=True, exist_ok=True)
        safe_name = Path(filename).name
        out_path = out_dir / safe_name
        out_path.write_bytes(payload)
        return str(out_path.resolve())

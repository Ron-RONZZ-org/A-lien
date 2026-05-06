"""RetpostoService — email account management with keyring integration.

Extends A-core CRUDService for kontoj table.
Passwords stored in system keyring (never in SQLite).
"""

from __future__ import annotations

import json
import uuid as uuid_mod
from datetime import datetime, timezone
from typing import Any

from A.core.service import CRUDService

from A_lien.data.storage import get_db
from A_lien.imap import (
    MessageStore,
    SyncResult,
    should_autosave_contact,
    _parse_email_address,
    _extract_sender_name,
)
from A_lien.keyring import get_password as _get_keyring_pw
from A_lien.keyring import set_password as _set_keyring_pw
from A_lien.keyring import delete_password as _del_keyring_pw
from A_lien.service.kontakto_service import get_kontakto_service
from A_lien.service.retposto_contact_mixin import RetpostoContactMixin
from A_lien.service.retposto_signature import RetpostoSignatureMixin
from A_lien.service.retposto_spamo import RetpostoSpamoMixin

_retposto_service: RetpostoService | None = None


class RetpostoService(CRUDService, MessageStore, RetpostoSignatureMixin, RetpostoContactMixin, RetpostoSpamoMixin):
    """Email account management with keyring password storage.

    Features:
    - Account CRUD (create, update, delete) with keyring password integration
    - Message sync (IMAP) with dedup and auto-contact creation
    - Email send (SMTP) with sent-message storage and auto-contact creation
    - Signature management (CRUD on subskriboj table)
    - Password never stored in database — only in OS keyring
    """

    def __init__(self, db):
        """Initialize with kontoj table, no FTS5, undo=5."""
        super().__init__(db, "kontoj", undo_size=5)

    # ── MessageStore protocol implementation ──────────────────────────────────

    def get_known_uids(self, konto_id: str, dosierujo_id: str) -> set[int]:
        """Get set of already-synced IMAP UIDs for an account+folder.

        Args:
            konto_id: Account UUID
            dosierujo_id: Folder UUID

        Returns:
            Set of integer IMAP UIDs
        """
        rows = self.db.execute(
            "SELECT imap_uid FROM mesagoj WHERE konto_id = ? AND dosierujo_id = ? AND imap_uid IS NOT NULL",
            (konto_id, dosierujo_id),
        )
        return {r["imap_uid"] for r in rows}

    def store_message(self, data: dict[str, Any], force: bool = False) -> str:
        """Insert or update a message in mesagoj table.

        When ``force=True`` and the message already exists (matched by IMAP UID),
        the existing row is replaced with new data, preserving the original UUID.

        Args:
            data: Parsed message dict
            force: If True, replace existing message with same IMAP UID

        Returns:
            Stored message UUID
        """
        msg_uuid = data.get("uuid") or str(uuid_mod.uuid4())

        # When force-refreshing, delete the existing row first so INSERT works
        if force:
            imap_uid = data.get("imap_uid")
            if imap_uid is not None:
                existing = self.db.execute_one(
                    "SELECT uuid FROM mesagoj WHERE konto_id = ? AND dosierujo_id = ? AND imap_uid = ?",
                    (data["konto_id"], data["dosierujo_id"], imap_uid),
                )
                if existing:
                    msg_uuid = existing["uuid"]
                    self.db.execute("DELETE FROM mesagoj WHERE uuid = ?", (msg_uuid,))
        self.db.execute(
            """INSERT OR IGNORE INTO mesagoj
               (uuid, konto_id, dosierujo_id, message_id, in_reply_to,
                references_hdr, imap_uid, de, al, kc, bkc,
                subjekto, korpo, html_korpo,
                prioritato, legita, stelo, spamo, forigita,
                aldonajxoj, etikedoj, ricevita_je,
                kreita_je, modifita_je)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                msg_uuid,
                data.get("konto_id", ""),
                data.get("dosierujo_id", ""),
                data.get("message_id", ""),
                data.get("in_reply_to", ""),
                data.get("references_hdr", ""),
                data.get("imap_uid"),
                data.get("de", ""),
                data.get("al", "[]"),
                data.get("kc", "[]"),
                data.get("bkc", "[]"),
                data.get("subjekto", ""),
                data.get("korpo", ""),
                data.get("html_korpo", ""),
                data.get("prioritato", 5),
                int(data.get("legita", 0)),
                int(data.get("stelo", 0)),
                int(data.get("spamo", 0)),
                int(data.get("forigita", 0)),
                data.get("aldonajxoj", "[]"),
                data.get("etikedoj", "[]"),
                data.get("ricevita_je", ""),
                data.get("kreita_je", ""),
                data.get("modifita_je", ""),
            ),
        )
        return msg_uuid

    # ── Auto-contact helpers — provided by RetpostoContactMixin ─────────────

    # ── Keyring password helpers ────────────────────────────────────────────

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

    # ── Account CRUD ────────────────────────────────────────────────────────

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
        """Bulk-delete accounts, returning per-UUID results.

        Resolves short UUID prefixes to full UUIDs before deletion.
        Each result dict has:
        - ``uuid``: the original UUID input (truncated to 8 chars)
        - ``success``: whether deletion succeeded
        - ``error``: error message if failed, else ``None``

        Args:
            uuids: List of account UUIDs (full or short prefix) to delete

        Returns:
            List of result dicts, one per UUID
        """
        results: list[dict[str, object | str]] = []
        for uid in uuids:
            try:
                # Resolve short UUID to full UUID
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
                results.append({
                    "uuid": uid,
                    "success": False,
                    "error": str(e),
                })
        return results

    def get_account(self, uuid: str) -> dict[str, Any] | None:
        """Get account details (password never included)."""
        return self.get(uuid)

    def find_by_uuid_prefix(self, prefix: str, limit: int = 10) -> list[dict[str, Any]]:
        """Find accounts by UUID prefix (uses core CRUD method)."""
        return super().find_by_uuid_prefix(prefix, limit=limit)

    def list_accounts(self) -> list[dict[str, Any]]:
        """List all accounts (password never included)."""
        return self.list(order_by="ordo", desc=False)

    # ── IMAP/SMTP sync & send ────────────────────────────────────────────────

    def get_account_with_password(self, uuid: str) -> dict[str, Any] | None:
        """Get account config with password from keyring."""
        acct = self.get_account(uuid)
        if acct is None:
            return None
        pw = self.get_password(uuid)
        if pw:
            acct["password"] = pw
        return acct

    def sync_account(self, uuid: str, force: bool = False) -> Any:
        """Sync messages for a single account, auto-creating contacts from senders.

        Args:
            uuid: Account UUID
            force: If True, re-download all messages even if already synced

        Returns:
            SyncResult from imap module
        """
        from A_lien.imap import sync_account as _sync

        acct = self.get_account_with_password(uuid)
        if not acct or "password" not in acct:
            raise ValueError(f"No password for account: {uuid}")

        result = _sync(
            host=acct.get("imap_servilo", ""),
            port=acct.get("imap_haveno", 993),
            use_ssl=acct.get("imap_ssl", 1) == 1,
            username=acct.get("imap_uzantonomo", "") or acct.get("retposto", ""),
            password=acct["password"],
            konto_id=uuid,
            db_store=self,
            force=force,
        )

        # Auto-create contacts from senders of new, unseen messages
        if result.new > 0:
            self._autosave_sync_contacts(uuid)

        return result

    def sync_all(self, force: bool = False) -> dict[str, Any]:
        """Sync messages for all accounts concurrently, auto-creating contacts.

        Args:
            force: If True, re-download all messages even if already synced

        Returns:
            Dict mapping account UUID -> SyncResult
        """
        from A_lien.imap import sync_accounts_concurrent

        accounts = self.list_accounts()
        enriched: list[dict[str, Any]] = []
        for acct in accounts:
            pw = self.get_password(acct["uuid"])
            if pw:
                acct["password"] = pw
                acct["db_store"] = self
                acct["force"] = force
                enriched.append(acct)

        results = sync_accounts_concurrent(enriched)
        return results

    def send_email(
        self,
        account_uuid: str,
        to: list[str],
        subject: str,
        body: str = "",
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        attachments: list[str] | None = None,
        priority: int = 5,
        in_reply_to: str = "",
        references: str = "",
    ) -> None:
        """Send an email via SMTP, save a copy, and auto-create contacts.

        Args:
            account_uuid: Sender account UUID
            to: Recipients
            subject: Subject line
            body: Plain text body
            cc: CC recipients
            bcc: BCC recipients
            attachments: File paths
            priority: Priority level (1=highest, 5=lowest)
            in_reply_to: Message-ID being replied to
            references: References header for threading

        Raises:
            ConnectionError, ValueError
        """
        from A_lien.smtp import SMTPClient

        acct = self.get_account_with_password(account_uuid)
        if not acct or "password" not in acct:
            raise ValueError(f"No password for account: {account_uuid}")

        sender_email = acct.get("retposto", "")
        cc = cc or []
        bcc = bcc or []

        client = SMTPClient(
            host=acct.get("smtp_servilo", ""),
            port=acct.get("smtp_haveno", 587),
            use_tls=acct.get("smtp_tls", 1) == 1,
        )
        try:
            client.connect(
                username=acct.get("smtp_uzantonomo", "") or sender_email,
                password=acct["password"],
            )
            client.send_email(
                from_addr=sender_email,
                to=to,
                subject=subject,
                body=body,
                cc=cc,
                bcc=bcc,
                attachments=attachments or [],
                priority=priority,
            )
        finally:
            client.disconnect()

        # Auto-create contacts from recipients
        all_recipients = to + cc + bcc
        for addr in all_recipients:
            if should_autosave_contact(addr):
                self._upsert_contact_from_email(addr)

        # Save a copy of sent message
        now = datetime.now(timezone.utc).isoformat()
        self.store_message({
            "konto_id": account_uuid,
            "dosierujo_id": "",
            "message_id": f"sent-{uuid_mod.uuid4()}",
            "in_reply_to": in_reply_to,
            "references_hdr": references,
            "de": sender_email,
            "al": json.dumps(to, ensure_ascii=False),
            "kc": json.dumps(cc, ensure_ascii=False),
            "bkc": json.dumps(bcc, ensure_ascii=False),
            "subjekto": subject,
            "korpo": body,
            "html_korpo": "",
            "prioritato": priority,
            "legita": 1,
            "stelo": 0,
            "spamo": 0,
            "forigita": 0,
            "aldonajxoj": "[]",
            "etikedoj": "[]",
            "ricevita_je": now,
            "kreita_je": now,
            "modifita_je": now,
        })

    # ── Signature management — provided by RetpostoSignatureMixin ──────────
    # ── Message search ─────────────────────────────────────────────────────────

    def get_message(self, uuid: str) -> dict[str, Any] | None:
        """Get a non-deleted message by UUID (queries mesagoj table directly)."""
        return self.db.execute_one(
            "SELECT * FROM mesagoj WHERE uuid = ? AND forigita = 0", (uuid,)
        )

    def get_attachments(self, msg_uuid: str) -> list[dict[str, Any]]:
        """Get attachments for a message.

        Checks both the ``aldonajxoj`` table (for IMAP-stored attachments)
        and the inline JSON ``aldonajxoj`` column on the message itself.

        Args:
            msg_uuid: Message UUID

        Returns:
            List of attachment dicts with keys: dosiernomo, mime_tipo, grandeco, vojo
        """
        # First try the aldonajxoj table
        table_rows = list(self.db.execute(
            "SELECT uuid, dosiernomo, mime_tipo, grandeco, vojo "
            "FROM aldonajxoj WHERE mesagxo_id = ? ORDER BY dosiernomo",
            (msg_uuid,),
        ))
        if table_rows:
            return table_rows

        # Fallback: parse inline JSON column on the message
        msg = self.get_message(msg_uuid)
        if not msg:
            return []
        raw = msg.get("aldonajxoj", "[]")
        if isinstance(raw, str):
            try:
                raw = json.loads(raw) if raw.strip() else []
            except (json.JSONDecodeError, TypeError):
                raw = []
        if not isinstance(raw, list):
            return []
        result = []
        for item in raw:
            if isinstance(item, dict):
                result.append({
                    "uuid": item.get("uuid", ""),
                    "dosiernomo": item.get("dosiernomo", item.get("filename", "")),
                    "mime_tipo": item.get("mime_tipo", item.get("mime", "")),
                    "grandeco": item.get("grandeco", item.get("size", 0)),
                    "vojo": item.get("vojo", ""),
                })
            elif isinstance(item, str):
                result.append({
                    "uuid": "",
                    "dosiernomo": item,
                    "mime_tipo": "",
                    "grandeco": 0,
                    "vojo": "",
                })
        return result

    def find_message_by_uuid_prefix(self, prefix: str) -> list[dict[str, Any]]:
        """Find non-deleted messages by UUID prefix (e.g. first 8 characters).

        Args:
            prefix: First N characters of a message UUID

        Returns:
            List of matching messages (empty if none)
        """
        if not prefix:
            return []
        return list(
            self.db.execute(
                "SELECT * FROM mesagoj WHERE uuid LIKE ? AND forigita = 0",
                (f"{prefix}%",),
            )
        )

    def mark_read(self, msg_uuid: str, legita: bool = True) -> None:
        """Mark a message as read or unread.

        Args:
            msg_uuid: Message UUID
            legita: True for read, False for unread
        """
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            "UPDATE mesagoj SET legita = ?, modifita_je = ? WHERE uuid = ?",
            (1 if legita else 0, now, msg_uuid),
        )

    def search_messages(
        self, filters: dict[str, Any], limit: int = 50
    ) -> list[dict[str, Any]]:
        """Search messages with filters.

        Args:
            filters: Dict with search criteria:
                - query: Full-text search in subject/body
                - from: From address
                - to: To address
                - cc: CC address
                - bcc: BCC address
                - subject: Subject search
                - body: Body search
                - after: Date after (YYYYMMDD)
                - before: Date before (YYYYMMDD)
                - read: Boolean read status
                - priority: Priority level
                - account: Account UUID
            limit: Max results

        Returns:
            List of matching messages
        """
        # Build SQL query
        conditions = []
        params = []

        if filters.get("query"):
            conditions.append("(subjekto LIKE ? OR korpo LIKE ?)")
            q = f"%{filters['query']}%"
            params.extend([q, q])

        if filters.get("from"):
            conditions.append("de LIKE ?")
            params.append(f"%{filters['from']}%")

        if filters.get("to"):
            conditions.append("al LIKE ?")
            params.append(f"%{filters['to']}%")

        if filters.get("cc"):
            conditions.append("kc LIKE ?")
            params.append(f"%{filters['cc']}%")

        if filters.get("bcc"):
            conditions.append("bkc LIKE ?")
            params.append(f"%{filters['bcc']}%")

        if filters.get("subject"):
            conditions.append("subjekto LIKE ?")
            params.append(f"%{filters['subject']}%")

        if filters.get("body"):
            conditions.append("korpo LIKE ?")
            params.append(f"%{filters['body']}%")

        if filters.get("after"):
            conditions.append("ricevita_je >= ?")
            params.append(filters["after"])

        if filters.get("before"):
            conditions.append("ricevita_je <= ?")
            params.append(filters["before"])

        if filters.get("read") is not None:
            conditions.append("legita = ?")
            params.append(1 if filters["read"] else 0)

        if filters.get("priority"):
            conditions.append("prioritato = ?")
            params.append(filters["priority"])

        if filters.get("account"):
            conditions.append("konto_id = ?")
            params.append(filters["account"])

        # Build query
        if conditions:
            where = " AND ".join(conditions)
            sql = f"SELECT * FROM mesagoj WHERE {where} AND forigita = 0 ORDER BY ricevita_je DESC LIMIT ?"
        else:
            sql = "SELECT * FROM mesagoj WHERE forigita = 0 ORDER BY ricevita_je DESC LIMIT ?"

        params.append(limit)

        try:
            rows = self.db.execute(sql, tuple(params))
        except Exception:
            # Fallback to simple query
            sql = "SELECT * FROM mesagoj WHERE forigita = 0 ORDER BY ricevita_je DESC LIMIT ?"
            rows = self.db.execute(sql, (limit,))

        return list(rows)

    # ── Message operations (trash, move) ─────────────────────────────────────

    def trash_message(self, msg_uuid: str, permanent: bool = False) -> None:
        """Soft-delete or hard-delete a message.

        Args:
            msg_uuid: Message UUID
            permanent: If True, delete permanently instead of marking as trash
        """
        if permanent:
            self.db.execute("DELETE FROM mesagoj WHERE uuid = ?", (msg_uuid,))
        else:
            now = datetime.now(timezone.utc).isoformat()
            self.db.execute(
                "UPDATE mesagoj SET forigita = 1, modifita_je = ? WHERE uuid = ?",
                (now, msg_uuid),
            )

    def move_message(
        self,
        msg: dict,
        dest_account_uuid: str,
        dest_folder: str,
    ) -> None:
        """Move a message to a different account/folder.

        If same server: uses IMAP MOVE or COPY+DELETE.
        If different server: downloads raw message, appends, deletes original.

        Args:
            msg: The message dict (must include konto_id, dosierujo_id, uid)
            dest_account_uuid: Destination account UUID
            dest_folder: Destination folder name (e.g. 'INBOX', 'Archive')
        """
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
                username=src_account.get("imap_uzantonomo", "")
                          or src_account.get("retposto", ""),
                password=src_account["password"],
            )

            # Determine source folder name from dosierujo_id
            src_folder_row = self.db.execute_one(
                "SELECT nomo FROM dosierujoj WHERE uuid = ?",
                (msg.get("dosierujo_id", ""),),
            )
            src_folder = src_folder_row["nomo"] if src_folder_row else "INBOX"
            uid = int(msg.get("uid", 0))

            same_account = src_account_uuid == dest_account_uuid

            if same_account:
                # Same-account folder move
                imap.move_message(src_folder, uid, dest_folder)
                # Update local DB
                dest_folder_id = self._ensure_folder_exists(
                    dest_account_uuid, dest_folder
                )
                now = datetime.now(timezone.utc).isoformat()
                self.db.execute(
                    "UPDATE mesagoj SET dosierujo_id = ?, modifita_je = ? WHERE uuid = ?",
                    (dest_folder_id, now, msg["uuid"]),
                )
            else:
                # Cross-account: fetch raw, append, delete original
                raw = imap.fetch_raw_message(src_folder, uid)
                if not raw:
                    raise ValueError(
                        f"Could not fetch raw message (UID {uid})"
                    )

                # Connect to destination IMAP
                dest_imap = IMAPClient(
                    host=dest_account.get("imap_servilo", ""),
                    port=dest_account.get("imap_haveno", 993),
                    use_ssl=dest_account.get("imap_ssl", 1) == 1,
                )
                try:
                    dest_imap.connect(
                        username=dest_account.get("imap_uzantonomo", "")
                                  or dest_account.get("retposto", ""),
                        password=dest_account["password"],
                    )
                    dest_imap.append_message(dest_folder, raw)
                finally:
                    dest_imap.disconnect()

                # Delete original
                imap.delete_message(src_folder, uid)

                # Update local DB
                dest_folder_id = self._ensure_folder_exists(
                    dest_account_uuid, dest_folder
                )
                now = datetime.now(timezone.utc).isoformat()
                self.db.execute(
                    "UPDATE mesagoj SET konto_id = ?, dosierujo_id = ?, "
                    "modifita_je = ? WHERE uuid = ?",
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


def get_retposto_service() -> RetpostoService:
    """Get the singleton RetpostoService."""
    global _retposto_service
    if _retposto_service is None:
        _retposto_service = RetpostoService(get_db())
    return _retposto_service



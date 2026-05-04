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

_retposto_service: RetpostoService | None = None


class RetpostoService(CRUDService, MessageStore):
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

    def get_known_uids(self, konto_id: str, dosierujo_id: str) -> set[str]:
        """Get set of already-synced IMAP UIDs for an account+folder.

        Args:
            konto_id: Account UUID
            dosierujo_id: Folder UUID

        Returns:
            Set of UID strings (message_id / IMAP UID)
        """
        rows = self.db.execute(
            "SELECT uid FROM mesagxoj WHERE konto_id = ? AND dosierujo_id = ?",
            (konto_id, dosierujo_id),
        )
        return {r["uid"] for r in rows if r.get("uid")}

    def store_message(self, data: dict[str, Any]) -> str:
        """Insert a parsed message into mesagxoj table.

        Args:
            data: Parsed message dict

        Returns:
            Stored message UUID
        """
        msg_uuid = data.get("uuid") or str(uuid_mod.uuid4())
        self.db.execute(
            """INSERT OR IGNORE INTO mesagxoj
               (uuid, konto_id, dosierujo_id, message_id, in_reply_to,
                references_hdr, uid, de, al, kc, bkc,
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
                data.get("uid", ""),
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

    # ── Auto-contact helpers ──────────────────────────────────────────────────

    def _upsert_contact_from_email(
        self, email_addr: str, display_name: str = "",
    ) -> None:
        """Create or update a contact from an email address.

        Skips no-reply / temporary addresses.
        If a contact with this email already exists, updates the name.
        Otherwise creates a new contact.

        Args:
            email_addr: Raw From header (e.g. 'Name <addr@dom.ain>')
            display_name: Optional display name
        """
        addr = _parse_email_address(email_addr)
        if not addr or not should_autosave_contact(email_addr):
            return

        kontakto = get_kontakto_service()
        name = display_name or _extract_sender_name(email_addr) or addr.split("@")[0]

        existing = kontakto.find_by_email(addr)
        if existing:
            # Update name if we have one and contact doesn't have a full name
            if name and not existing.get("plena_nomo"):
                kontakto.update(existing["uuid"], {"plena_nomo": name})
        else:
            kontakto.create({
                "plena_nomo": name,
                "retposhtadresoj": json.dumps(
                    [{"valoro": addr}],
                    ensure_ascii=False,
                ),
            })

    def _autosave_sync_contacts(self, konto_id: str) -> None:
        """Auto-create contacts from senders of newly synced, unseen messages.

        Args:
            konto_id: Account UUID whose messages to scan
        """
        rows = self.db.execute(
            """SELECT de FROM mesagxoj
               WHERE konto_id = ? AND legita = 0
               ORDER BY ricevita_je DESC LIMIT 100""",
            (konto_id,),
        )
        seen = set()
        for row in rows:
            sender = (row.get("de") or "").strip()
            if sender and sender not in seen:
                seen.add(sender)
                self._upsert_contact_from_email(sender)

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

    def get_account(self, uuid: str) -> dict[str, Any] | None:
        """Get account details (password never included)."""
        return self.get(uuid)

    def find_by_uuid_prefix(self, prefix: str) -> list[dict[str, Any]]:
        """Find accounts by UUID prefix (for short UUIDs like '11a31fb9').
        
        Returns all accounts where uuid starts with prefix.
        """
        if not prefix:
            return []
        results = self.db.execute(
            "SELECT * FROM kontoj WHERE uuid LIKE ?",
            (f"{prefix}%",),
        )
        return [r for r in results]

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

    def sync_account(self, uuid: str) -> Any:
        """Sync messages for a single account, auto-creating contacts from senders.

        Args:
            uuid: Account UUID

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
        )

        # Auto-create contacts from senders of new, unseen messages
        if result.new > 0:
            self._autosave_sync_contacts(uuid)

        return result

    def sync_all(self) -> dict[str, Any]:
        """Sync messages for all accounts concurrently, auto-creating contacts.

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
                enriched.append(acct)

        results = sync_accounts_concurrent(enriched)

        # Auto-create contacts for each account
        for acct_uuid in results:
            if results[acct_uuid].new > 0:
                self._autosave_sync_contacts(acct_uuid)

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
            "in_reply_to": "",
            "references_hdr": "",
            "uid": f"sent-{uuid_mod.uuid4()}",
            "de": sender_email,
            "al": json.dumps(to, ensure_ascii=False),
            "kc": json.dumps(cc, ensure_ascii=False),
            "bkc": json.dumps(bcc, ensure_ascii=False),
            "subjekto": subject,
            "korpo": body,
            "html_korpo": "",
            "prioritato": 5,
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

    # ── Signature management (subskriboj via CRUDService) ───────────────────

    @property
    def _signatures(self) -> CRUDService:
        return CRUDService(self.db, "subskriboj")

    def list_signatures(self) -> list[dict[str, Any]]:
        return self._signatures.list(order_by="nomo", desc=False)

    def create_signature(
        self, nomo: str, teksto: str, estas_html: bool = False
    ) -> dict[str, Any]:
        return self._signatures.create({
            "nomo": nomo,
            "teksto": teksto,
            "estas_html": 1 if estas_html else 0,
        })

    def get_signature(self, uuid: str) -> dict[str, Any] | None:
        return self._signatures.get(uuid)

    def update_signature(self, uuid: str, data: dict[str, Any]) -> dict[str, Any]:
        return self._signatures.update(uuid, data)

    def delete_signature(self, uuid: str) -> None:
        self._signatures.delete(uuid, soft=True)

    # ── Message search ─────────────────────────────────────────────────────────

    def get_message(self, uuid: str) -> dict[str, Any] | None:
        """Get a message by UUID."""
        return self.get(uuid)  # Uses inherited CRUDService.get

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
            sql = f"SELECT * FROM mesagxoj WHERE {where} ORDER BY ricevita_je DESC LIMIT ?"
        else:
            sql = "SELECT * FROM mesagxoj ORDER BY ricevita_je DESC LIMIT ?"

        params.append(limit)

        try:
            rows = self.db.execute(sql, tuple(params))
        except Exception:
            # Fallback to simple query
            sql = "SELECT * FROM mesagxoj ORDER BY ricevita_je DESC LIMIT ?"
            rows = self.db.execute(sql, (limit,))

        return list(rows)


def get_retposto_service() -> RetpostoService:
    """Get the singleton RetpostoService."""
    global _retposto_service
    if _retposto_service is None:
        _retposto_service = RetpostoService(get_db())
    return _retposto_service


__all__ = ["RetpostoService", "get_retposto_service"]

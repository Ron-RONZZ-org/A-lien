"""IMAP sync and SMTP send mixin — RetpostoSyncMixin.

MessageStore protocol, IMAP sync, SMTP send.
"""

from __future__ import annotations

import json
import uuid as uuid_mod
from datetime import datetime, timezone
from typing import Any

__all__ = [
    "get_known_uids",
    "store_message",
    "RetpostoSyncMixin",
]


# ── Module-level helpers (used by RetpostoSyncMixin and _ThreadLocalStore) ──


def get_known_uids(db: Any, konto_id: str, dosierujo_id: str) -> set[int]:
    """Get set of already-synced IMAP UIDs for an account+folder.

    Args:
        db: SQLiteDB instance
        konto_id: Account UUID
        dosierujo_id: Folder UUID
    """
    rows = db.execute(
        "SELECT imap_uid FROM mesagoj WHERE konto_id = ? AND dosierujo_id = ? AND imap_uid IS NOT NULL",
        (konto_id, dosierujo_id),
    )
    return {r["imap_uid"] for r in rows}


def store_message(db: Any, data: dict[str, Any], force: bool = False) -> str:
    """Insert or update a message in mesagoj table.

    Args:
        db: SQLiteDB instance
        data: Message data dict
        force: If True, re-download existing messages (preserving local flags)

    Returns:
        Message UUID
    """
    msg_uuid = data.get("uuid") or str(uuid_mod.uuid4())
    local_legita = None
    local_stelo = None
    local_spamo = None
    local_forigita = None
    if force:
        imap_uid = data.get("imap_uid")
        if imap_uid is not None:
            existing = db.execute_one(
                "SELECT uuid, legita, stelo, spamo, forigita FROM mesagoj "
                "WHERE konto_id = ? AND dosierujo_id = ? AND imap_uid = ?",
                (data["konto_id"], data["dosierujo_id"], imap_uid),
            )
            if existing:
                msg_uuid = existing["uuid"]
                local_legita = existing["legita"]
                local_stelo = existing["stelo"]
                local_spamo = existing["spamo"]
                local_forigita = existing["forigita"]
                db.execute("DELETE FROM mesagoj WHERE uuid = ?", (msg_uuid,))
    db.execute(
        """INSERT OR IGNORE INTO mesagoj
           (uuid, konto_id, dosierujo_id, message_id, in_reply_to,
            references_hdr, imap_uid, de, al, kc, bkc,
            subjekto, korpo, html_korpo,
            prioritato, legita, stelo, spamo, forigita,
            aldonajxoj, etikedoj, ricevita_je,
            kreita_je, modifita_je)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (msg_uuid, data.get("konto_id", ""), data.get("dosierujo_id", "") or None,
         data.get("message_id", ""), data.get("in_reply_to", ""),
         data.get("references_hdr", ""), data.get("imap_uid"),
         data.get("de", ""), data.get("al", "[]"), data.get("kc", "[]"),
         data.get("bkc", "[]"), data.get("subjekto", ""), data.get("korpo", ""),
         data.get("html_korpo", ""), data.get("prioritato", 5),
         int(data.get("legita", 0)), int(data.get("stelo", 0)),
         int(data.get("spamo", 0)), int(data.get("forigita", 0)),
         data.get("aldonajxoj", "[]"), data.get("etikedoj", "[]"),
         data.get("ricevita_je", ""), data.get("kreita_je", ""),
         data.get("modifita_je", "")),
    )
    if force and local_legita is not None:
        db.execute(
            "UPDATE mesagoj SET legita = ?, stelo = ?, spamo = ?, forigita = ? WHERE uuid = ?",
            (local_legita, local_stelo, local_spamo, local_forigita, msg_uuid),
        )
    return msg_uuid


class RetpostoSyncMixin:
    """IMAP sync, SMTP send, and MessageStore protocol."""

    def get_known_uids(self, konto_id: str, dosierujo_id: str) -> set[int]:
        """Get set of already-synced IMAP UIDs for an account+folder."""
        return get_known_uids(self.db, konto_id, dosierujo_id)

    def store_message(self, data: dict[str, Any], force: bool = False) -> str:
        """Insert or update a message in mesagoj table."""
        return store_message(self.db, data, force=force)

    def sync_account(self, uuid: str, force: bool = False) -> Any:
        """Sync messages for a single account."""
        from A_lien.imap import sync_account as _sync
        acct = self.get_account_with_password(uuid)
        if not acct or "password" not in acct:
            raise ValueError(f"No password for account: {uuid}")
        result = _sync(
            host=acct.get("imap_servilo", ""), port=acct.get("imap_haveno", 993),
            use_ssl=acct.get("imap_ssl", 1) == 1,
            username=acct.get("imap_uzantonomo", "") or acct.get("retposto", ""),
            password=acct["password"], konto_id=uuid, db_store=self, force=force,
        )
        backlog_count = self.process_sync_backlog()
        if backlog_count > 0:
            from A import info as _info
            _info(f"  Sinkronigitaj {backlog_count} flagoj al servilo")
        if result.new > 0:
            self._autosave_sync_contacts(uuid)
        return result

    def sync_all(self, force: bool = False) -> dict[str, Any]:
        """Sync messages for all accounts concurrently."""
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
        return sync_accounts_concurrent(enriched)

    def send_email(
        self, account_uuid: str, to: list[str], subject: str, body: str = "",
        cc: list[str] | None = None, bcc: list[str] | None = None,
        attachments: list[str] | None = None, priority: int = 3,
        in_reply_to: str = "", references: str = "",
        html_body: str = "",
        subskribo: str | None = None,
    ) -> None:
        """Send an email via SMTP.

        Args:
            account_uuid: Account to send from
            to: Primary recipients
            subject: Email subject
            body: Plain text body
            cc: Carbon copy recipients
            bcc: Blind carbon copy recipients
            attachments: File paths to attach
            priority: Priority level (1=highest, 5=lowest, 3=normal)
            in_reply_to: Message-ID being replied to
            references: References header for threading
            html_body: Optional HTML body (alternative to plain text)
            subskribo: Signature override.
                None = use account default (kontoj.subskribo)
                ""  = explicit "no signature"
                otherwise = name or UUID to resolve
        """
        from A_lien.smtp import SMTPClient
        from A_lien.imap import should_autosave_contact

        acct = self.get_account_with_password(account_uuid)
        if not acct or "password" not in acct:
            raise ValueError(f"No password for account: {account_uuid}")
        sender_email = acct.get("retposto", "")
        cc = cc or []
        bcc = bcc or []

        # ── Resolve signature ──────────────────────────────────────────────
        if subskribo is None:
            sig_uuid = acct.get("subskribo") or ""
        elif subskribo == "":
            sig_uuid = ""  # explicit skip
        else:
            sig_uuid = subskribo  # CLI override

        if sig_uuid:
            sig = self.resolve_signature(sig_uuid)
            if sig:
                sig_text = sig.get("teksto", "")
                if sig.get("estas_html"):
                    html_body = (html_body or "") + "<br>" + sig_text
                else:
                    body = (body + "\n\n-- \n" + sig_text) if body else sig_text
        # ───────────────────────────────────────────────────────────────────

        client = SMTPClient(
            host=acct.get("smtp_servilo", ""), port=acct.get("smtp_haveno", 587),
            use_tls=acct.get("smtp_tls", 1) == 1,
        )
        try:
            client.connect(
                username=acct.get("smtp_uzantonomo", "") or sender_email,
                password=acct["password"],
            )
            client.send_email(
                from_addr=sender_email, to=to, subject=subject, body=body,
                cc=cc, bcc=bcc, attachments=attachments or [],
                html_body=html_body, priority=priority,
            )
        finally:
            client.disconnect()

        all_recipients = to + cc + bcc
        for addr in all_recipients:
            if should_autosave_contact(addr):
                self._upsert_contact_from_email(addr)
        now = datetime.now(timezone.utc).isoformat()
        self.store_message({
            "konto_id": account_uuid, "dosierujo_id": "",
            "message_id": f"sent-{uuid_mod.uuid4()}",
            "in_reply_to": in_reply_to, "references_hdr": references,
            "de": sender_email, "al": json.dumps(to, ensure_ascii=False),
            "kc": json.dumps(cc, ensure_ascii=False),
            "bkc": json.dumps(bcc, ensure_ascii=False),
            "subjekto": subject, "korpo": body, "html_korpo": html_body,
            "prioritato": priority, "legita": 1, "stelo": 0, "spamo": 0, "forigita": 0,
            "aldonajxoj": "[]", "etikedoj": "[]",
            "ricevita_je": now, "kreita_je": now, "modifita_je": now,
        })

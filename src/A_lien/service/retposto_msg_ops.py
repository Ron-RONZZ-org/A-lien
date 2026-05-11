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

    def _imap_sync_flags(self, msg_uuid: str, msg: dict[str, Any] | None = None) -> None:
        """Sync local message flags to the IMAP server, queuing on failure.

        Args:
            msg_uuid: Message UUID
            msg: Pre-fetched message dict (optional). If provided, bypasses
                 the ``get_message()`` call so trashed messages (forigita=1)
                 can still sync ``\\Deleted`` to the server.
        """
        if msg is None:
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
            timeout=timeout,
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

    def get_attachment_content(
        self, msg_uuid: str, filename: str,
        timeout: float | None = None,
    ) -> bytes:
        """Get attachment content as bytes, without saving to disk.

        Tries BLOB cache first; falls back to IMAP fetch if needed.

        Args:
            msg_uuid: Message UUID.
            filename: Attachment filename to retrieve.
            timeout: IMAP connection timeout in seconds (default: no timeout).

        Returns:
            Attachment content as bytes.

        Raises:
            ValueError: If message or attachment not found.
        """
        # ── Try BLOB cache first ──────────────────────────────────────────
        row = self.db.execute_one(
            "SELECT enhavo FROM aldonajxoj "
            "WHERE mesagxo_id = ? AND dosiernomo = ?",
            (msg_uuid, filename),
        )
        if row and row["enhavo"] is not None:
            return row["enhavo"]

        # ── Fallback: fetch from IMAP ─────────────────────────────────────
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
        if parsed.is_multipart():
            for part in parsed.walk():
                disp = str(part.get("Content-Disposition") or "")
                fn = part.get_filename()
                if "attachment" in disp or fn:
                    match_fn = fn or "attachment"
                    if match_fn == filename:
                        payload = part.get_payload(decode=True)
                        if payload:
                            return payload
                        break
        else:
            payload = parsed.get_payload(decode=True)
            if payload:
                return payload

        raise ValueError(f"Attachment '{filename}' not found in message")

"""Message query mixin — RetpostoMessagingMixin.

Read-only message queries: get, search, attachment metadata.
"""

from __future__ import annotations

import json
from typing import Any


class RetpostoMessagingMixin:
    """Read-only message queries."""

    def get_message(self, uuid: str) -> dict[str, Any] | None:
        """Get a non-deleted message by UUID."""
        return self.db.execute_one(
            "SELECT * FROM mesagoj WHERE uuid = ? AND forigita = 0", (uuid,)
        )

    def get_attachments(self, msg_uuid: str) -> list[dict[str, Any]]:
        """Get attachments for a message.

        Checks both the aldonajxoj table and inline JSON column.
        """
        table_rows = list(self.db.execute(
            "SELECT uuid, dosiernomo, mime_tipo, grandeco, vojo "
            "FROM aldonajxoj WHERE mesagxo_id = ? ORDER BY dosiernomo",
            (msg_uuid,),
        ))
        if table_rows:
            return table_rows
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
                result.append({"uuid": "", "dosiernomo": item, "mime_tipo": "", "grandeco": 0, "vojo": ""})
        return result

    def find_message_by_uuid_prefix(self, prefix: str) -> list[dict[str, Any]]:
        """Find non-deleted messages by UUID prefix."""
        if not prefix:
            return []
        return list(
            self.db.execute(
                "SELECT * FROM mesagoj WHERE uuid LIKE ? AND forigita = 0",
                (f"{prefix}%",),
            )
        )

    def search_messages(
        self, filters: dict[str, Any], limit: int = 50
    ) -> list[dict[str, Any]]:
        """Search messages with filters."""
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
        if conditions:
            where = " AND ".join(conditions)
            sql = f"SELECT * FROM mesagoj WHERE {where} AND forigita = 0 ORDER BY ricevita_je DESC LIMIT ?"
        else:
            sql = "SELECT * FROM mesagoj WHERE forigita = 0 ORDER BY ricevita_je DESC LIMIT ?"
        params.append(limit)
        try:
            rows = self.db.execute(sql, tuple(params))
        except Exception:
            sql = "SELECT * FROM mesagoj WHERE forigita = 0 ORDER BY ricevita_je DESC LIMIT ?"
            rows = self.db.execute(sql, (limit,))
        return list(rows)

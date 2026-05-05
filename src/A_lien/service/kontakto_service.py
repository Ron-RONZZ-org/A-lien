"""KontaktoService — contacts CRUD with FTS5, search, and serialization.

Extends A-core CRUDService. VCF and category features are in mixins:
- KontaktoVCFMixin (kontakto_vcf.py)
- KontaktoCategoryMixin (kontakto_category.py)
"""

from __future__ import annotations

import json
from typing import Any

from A.core.service import CRUDService

from A_lien.data.storage import get_db, KONTAKTOJ_FTS_CONFIG
from A_lien.service.kontakto_category import KontaktoCategoryMixin
from A_lien.service.kontakto_vcf import KontaktoVCFMixin

_kontakto_service: KontaktoService | None = None


class KontaktoService(CRUDService, KontaktoVCFMixin, KontaktoCategoryMixin):
    """Contacts CRUD with FTS5 search, categories, and VCF import/export.

    Features:
    - JSON serialization for multi-value fields (phones, emails, languages)
    - Core FTS5 full-text search (inherited from CRUDService)
    - Category management (via KontaktoCategoryMixin)
    - Duplicate detection via fuzzy matching (inherited search_fuzzy)
    - VCF import/export (via KontaktoVCFMixin)
    """

    # JSON columns that are arrays
    _JSON_LIST_FIELDS: tuple[str, ...] = (
        "lingvoj", "telefonnumeroj", "retposhtadresoj", "kategorioj",
    )
    # JSON columns that are objects
    _JSON_DICT_FIELDS: tuple[str, ...] = ("kampoj",)

    def __init__(self, db):
        """Initialize with FTS5 for contact search and undo support."""
        super().__init__(db, "kontaktoj", fts_config=KONTAKTOJ_FTS_CONFIG, undo_size=10)

    # ── JSON serialization for trash ────────────────────────────────────────

    def undo(self) -> dict[str, Any] | None:
        """Undo last operation with JSON field serialization."""
        if self._undo_manager is None:
            return None

        operation = self._undo_manager.undo()
        if not operation:
            return None

        # Serialize any JSON fields in old_data before restoring
        if operation.operation_type == "delete" and operation.old_data:
            operation.old_data.update(
                self._serialize(operation.old_data)
            )

        # Let parent handle the actual undo logic
        # (we push back because parent.undo() will pop again)
        self._undo_manager.push(operation)
        op = self._undo_manager.undo()

        if op is None:
            return None

        # perform the undo manually
        if op.operation_type == "add":
            sql = f"DELETE FROM {self.table} WHERE uuid = ?"
            with self.db.transaction() as conn:
                conn.execute(sql, (op.record_uuid,))
            if self._fts_config:
                self._rebuild_fts()
        elif op.operation_type == "delete" and op.old_data:
            restored = {k: v for k, v in op.old_data.items() if k != "forigita_je"}
            from datetime import datetime, timezone
            restored["modifita_je"] = datetime.now(timezone.utc).isoformat()
            restored = self._serialize(restored)
            columns = list(restored.keys())
            values = list(restored.values())
            placeholders = ", ".join(["?"] * len(columns))
            sql = f"INSERT INTO {self.table} ({', '.join(columns)}) VALUES ({placeholders})"
            with self.db.transaction() as conn:
                conn.execute(sql, values)
            if self._fts_config:
                self._rebuild_fts()
        elif op.operation_type == "modify" and op.old_data:
            old_data = {k: v for k, v in op.old_data.items() if k not in ("uuid", "kreita_je")}
            old_data = self._serialize(old_data)
            from datetime import datetime, timezone
            old_data["modifita_je"] = datetime.now(timezone.utc).isoformat()
            set_clauses = [f"{k} = ?" for k in old_data.keys()]
            values = list(old_data.values()) + [op.record_uuid]
            sql = f"UPDATE {self.table} SET {', '.join(set_clauses)} WHERE uuid = ?"
            with self.db.transaction() as conn:
                conn.execute(sql, values)
            if self._fts_config:
                self._rebuild_fts()

        return op.to_dict()

    def _ensure_fts(self) -> None:
        """Create FTS5 schema. Content sync is handled by *rebuild*."""
        from A.data.search import build_fts_schema
        for stmt in build_fts_schema(self._fts_config):
            self.db.execute(stmt)

    def _rebuild_fts(self) -> None:
        """Rebuild the entire FTS index from kontaktoj table."""
        with self.db.transaction() as conn:
            conn.execute(
                f"INSERT INTO {self._fts_config.fts_table}"
                f"({self._fts_config.fts_table}) VALUES('rebuild')"
            )

    def _index_fts(self, uuid: str) -> None:
        """Index new contact by rebuilding the FTS index."""
        self._rebuild_fts()

    def _remove_from_fts(self, uuid: str) -> None:
        """Remove from FTS index by rebuilding."""
        self._rebuild_fts()

    def _move_to_trash(self, uuid: str) -> None:
        """Move entry to trash table with JSON fields serialized."""
        entry = self.get(uuid)
        if not entry:
            return

        # Serialize JSON fields before storing in trash
        entry = self._serialize(entry)

        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        entry["forigita_je"] = now
        entry["modifita_je"] = now  # Keep constraint satisfied

        columns = list(entry.keys())
        values = list(entry.values())
        placeholders = ", ".join(["?"] * len(columns))
        sql = f"INSERT INTO {self._trash_table} ({', '.join(columns)}) VALUES ({placeholders})"

        with self.db.transaction() as conn:
            conn.execute(sql, values)
            # Delete from main table inside the same transaction
            conn.execute(f"DELETE FROM {self.table} WHERE uuid = ?", (uuid,))

    # ── JSON serialization ──────────────────────────────────────────────────

    def _serialize(self, data: dict[str, Any]) -> dict[str, Any]:
        """JSON-serialize complex fields before DB insert."""
        result = dict(data)
        for field in self._JSON_LIST_FIELDS:
            if field in result and isinstance(result[field], (list, dict)):
                result[field] = json.dumps(result[field], ensure_ascii=False)
        for field in self._JSON_DICT_FIELDS:
            if field in result and isinstance(result[field], (list, dict, set)):
                result[field] = json.dumps(result[field], ensure_ascii=False)
        return result

    def _deserialize_row(self, row: dict[str, Any]) -> dict[str, Any]:
        """Parse JSON columns back to Python objects."""
        if not row:
            return row
        result = dict(row)
        for field in self._JSON_LIST_FIELDS:
            if field in result and isinstance(result[field], str):
                try:
                    result[field] = json.loads(result[field])
                except (json.JSONDecodeError, TypeError):
                    pass
        for field in self._JSON_DICT_FIELDS:
            if field in result and isinstance(result[field], str):
                try:
                    result[field] = json.loads(result[field])
                except (json.JSONDecodeError, TypeError):
                    pass
        return result

    # ── CRUD overrides ──────────────────────────────────────────────────────

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create contact with JSON serialization."""
        data = self._serialize(data)
        result = super().create(data)
        return self._deserialize_row(result)

    def update(self, uuid: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update contact with JSON serialization."""
        data = self._serialize(data)
        result = super().update(uuid, data)
        return self._deserialize_row(result)

    def get(self, uuid: str) -> dict[str, Any] | None:
        """Get contact with JSON deserialization."""
        row = super().get(uuid)
        return self._deserialize_row(row)

    def list(
        self,
        order_by: str = "plena_nomo",
        desc: bool = False,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """List contacts with JSON deserialization."""
        rows = super().list(order_by=order_by, desc=desc, limit=limit)
        return [self._deserialize_row(row) for row in rows]

    # ── Domain: contact lookups ─────────────────────────────────────────────

    def find_by_email(self, email: str) -> dict[str, Any] | None:
        """Find contact by primary email address (case-insensitive)."""
        row = self.db.execute_one(
            "SELECT * FROM kontaktoj WHERE LOWER(retposto) = LOWER(?)",
            (email,),
        )
        return self._deserialize_row(row)

    def find_by_uuid_prefix(self, prefix: str, limit: int = 10) -> list[dict[str, Any]]:
        """Find contacts whose UUID starts with prefix (uses core CRUD method)."""
        rows = super().find_by_uuid_prefix(prefix, limit=limit)
        return [self._deserialize_row(row) for row in rows]

    def find_duplicates(
        self, contact: dict[str, Any], threshold: float = 0.85
    ) -> list[dict[str, Any]]:
        """Find potential duplicates using fuzzy name matching.

        Args:
            contact: Contact data to check against
            threshold: Minimum similarity score (0.0-1.0)

        Returns:
            List of potential duplicate contacts
        """
        name = contact.get("plena_nomo") or contact.get("nomo", "")
        if not name:
            return []

        email = contact.get("retposto", "")
        candidates: list[dict[str, Any]] = []

        # Exact email match is always a duplicate
        if email:
            row = self.find_by_email(email)
            if row and row["uuid"] != contact.get("uuid"):
                candidates.append(row)

        # Fuzzy name search
        if name:
            fuzzy_results = self.search_fuzzy(name, field="plena_nomo", threshold=threshold)
            for r in fuzzy_results:
                if r["uuid"] != contact.get("uuid") and r not in candidates:
                    candidates.append(r)

        return candidates

    def search_contacts(
        self,
        query: str = "",
        fuzzy: bool = False,
        filters: dict[str, str] | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Search contacts using FTS5 with optional fuzzy re-ranking.

        Args:
            query: Search text
            fuzzy: Enable fuzzy re-ranking via rapidfuzz
            filters: Exact match filters (e.g. {"konfirmita": "1"})
            limit: Max results

        Returns:
            List of matching contacts
        """
        if not query and not filters:
            return self.list(limit=limit)

        rows = super().search_advanced(
            query=query, filters=filters, fuzzy=fuzzy, limit=limit
        )
        return [self._deserialize_row(row) for row in rows]

    def count(self) -> int:
        """Return total contact count."""
        row = self.db.execute_one("SELECT COUNT(*) AS cnt FROM kontaktoj")
        return row["cnt"] if row else 0

    # ── Domain: category management — provided by KontaktoCategoryMixin ────
    # ── Domain: VCF import/export — provided by KontaktoVCFMixin ───────────


def get_kontakto_service() -> KontaktoService:
    """Get the singleton KontaktoService."""
    global _kontakto_service
    if _kontakto_service is None:
        _kontakto_service = KontaktoService(get_db())
    return _kontakto_service


__all__ = ["KontaktoService", "get_kontakto_service"]

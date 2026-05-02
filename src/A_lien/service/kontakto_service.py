"""KontaktoService — contacts CRUD with FTS5, categories, VCF import/export.

Extends A-core CRUDService following the A-encik EncikService pattern.
"""

from __future__ import annotations

import json
from typing import Any

from A.core.service import CRUDService

from A_lien.data.storage import get_db, KONTAKTOJ_FTS_CONFIG

_kontakto_service: KontaktoService | None = None


class KontaktoService(CRUDService):
    """Contacts CRUD with FTS5 search, categories, and VCF import/export.

    Features:
    - JSON serialization for multi-value fields (phones, emails, languages)
    - Core FTS5 full-text search (inherited from CRUDService)
    - Category management (CRUD for kategorioj table)
    - Duplicate detection via fuzzy matching (inherited search_fuzzy)
    - VCF import/export
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

    def find_by_uuid_prefix(self, prefix: str) -> list[dict[str, Any]]:
        """Find contacts whose UUID starts with prefix."""
        rows = self.db.execute(
            "SELECT * FROM kontaktoj WHERE uuid LIKE ?", (f"{prefix}%",)
        )
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

    # ── Domain: category management ─────────────────────────────────────────

    def list_categories(self) -> list[dict[str, Any]]:
        """List all categories."""
        return self.db.execute(
            "SELECT * FROM kategorioj ORDER BY nomo ASC"
        )

    def create_category(self, nomo: str, koloro: str = "") -> dict[str, Any]:
        """Create a new category.

        Args:
            nomo: Category name (unique)
            koloro: Optional color code

        Returns:
            Created category dict
        """
        from datetime import datetime, timezone
        import uuid

        now = datetime.now(timezone.utc).isoformat()
        data = {
            "uuid": str(uuid.uuid4()),
            "nomo": nomo,
            "koloro": koloro,
            "kreita_je": now,
            "modifita_je": now,
        }
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO kategorioj (uuid, nomo, koloro, kreita_je, modifita_je) "
                "VALUES (?, ?, ?, ?, ?)",
                (data["uuid"], nomo, koloro, now, now),
            )
        return data

    def update_category(self, uuid: str, data: dict[str, Any]) -> dict[str, Any] | None:
        """Update a category."""
        from datetime import datetime, timezone

        data["modifita_je"] = datetime.now(timezone.utc).isoformat()
        set_clauses = [f"{k} = ?" for k in data.keys()]
        values = list(data.values()) + [uuid]
        with self.db.transaction() as conn:
            conn.execute(
                f"UPDATE kategorioj SET {', '.join(set_clauses)} WHERE uuid = ?",
                values,
            )
        row = self.db.execute_one("SELECT * FROM kategorioj WHERE uuid = ?", (uuid,))
        return row

    def delete_category(self, uuid: str) -> bool:
        """Delete a category.

        Args:
            uuid: Category UUID

        Returns:
            True if deleted, False if not found
        """
        cursor = self.db.execute_one(
            "SELECT COUNT(*) AS cnt FROM kategorioj WHERE uuid = ?", (uuid,)
        )
        if not cursor or cursor["cnt"] == 0:
            return False
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM kategorioj WHERE uuid = ?", (uuid,))
        return True
        return True

    # ── Domain: VCF import/export ───────────────────────────────────────────

    def import_vcf(self, path: str) -> int:
        """Import contacts from a VCF file.

        Args:
            path: Path to .vcf file

        Returns:
            Number of contacts imported

        Raises:
            ImportError: If vobject library is not installed
            FileNotFoundError: If VCF file not found
        """
        try:
            import vobject
        except ImportError:
            raise ImportError(
                "vobject library required for VCF import. "
                "Install: pip install vobject"
            )

        from pathlib import Path

        path_obj = Path(path)
        if not path_obj.exists():
            raise FileNotFoundError(f"VCF file not found: {path}")

        with path_obj.open("r", encoding="utf-8") as f:
            content = f.read()

        count = 0
        for vcard in vobject.readComponents(content):
            contact = self._vcard_to_contact(vcard)
            if contact and contact.get("plena_nomo"):
                self.create(contact)
                count += 1

        return count

    def export_vcf(self, uuid: str | None = None, path: str | None = None) -> str:
        """Export contact(s) to VCF format.

        Args:
            uuid: Single contact UUID (None = export all)
            path: Optional output file path (None = return string)

        Returns:
            VCF string (if path is None)

        Raises:
            ImportError: If vobject library is not installed
        """
        try:
            import vobject
        except ImportError:
            raise ImportError(
                "vobject library required for VCF export. "
                "Install: pip install vobject"
            )

        contacts = [self.get(uuid)] if uuid else self.list()

        lines: list[str] = []
        for contact in contacts:
            if not contact:
                continue
            lines.append(self._contact_to_vcard(contact))

        vcf_text = "\n".join(lines)

        if path:
            from pathlib import Path

            Path(path).write_text(vcf_text, encoding="utf-8")

        return vcf_text

    # ── VCF conversion helpers ──────────────────────────────────────────────

    @staticmethod
    def _vcard_to_contact(vcard: Any) -> dict[str, Any]:
        """Convert a vobject vCard to a contact dict."""
        from datetime import datetime, timezone
        import uuid

        now = datetime.now(timezone.utc).isoformat()
        contact: dict[str, Any] = {
            "uuid": str(uuid.uuid4()),
            "kreita_je": now,
            "modifita_je": now,
            "lingvoj": [],
            "telefonnumeroj": [],
            "retposhtadresoj": [],
            "kampoj": {},
            "kategorioj": [],
            "konfirmita": 0,
        }

        # Name
        if hasattr(vcard, "n"):
            given = str(vcard.n.value.given) if vcard.n.value.given else ""
            family = str(vcard.n.value.family) if vcard.n.value.family else ""
            contact["nomo"] = given
            contact["familia_nomo"] = family
            contact["plena_nomo"] = f"{given} {family}".strip()

        if hasattr(vcard, "fn"):
            fn_val = str(vcard.fn.value) if vcard.fn.value else ""
            if not contact.get("plena_nomo"):
                contact["plena_nomo"] = fn_val
            if not contact.get("nomo") and not contact.get("familia_nomo"):
                contact["nomo"] = fn_val

        # Email
        if hasattr(vcard, "email"):
            for email in vcard.contents.get("email", []):
                addr = str(email.value) if email.value else ""
                if addr:
                    if not contact.get("retposto"):
                        contact["retposto"] = addr
                    contact["retposhtadresoj"].append({
                        "valoro": addr,
                        "etikedo": email.params.get("TYPE", [""])[0] if hasattr(email, "params") else "",
                        "cxefa": not bool(contact.get("retposto")),
                    })

        # Phone
        if hasattr(vcard, "tel"):
            for tel in vcard.contents.get("tel", []):
                num = str(tel.value) if tel.value else ""
                if num:
                    contact["telefonnumeroj"].append({
                        "valoro": num,
                        "etikedo": tel.params.get("TYPE", [""])[0] if hasattr(tel, "params") else "",
                        "cxefa": len(contact["telefonnumeroj"]) == 0,
                    })

        # Organization
        if hasattr(vcard, "org"):
            org_val = str(vcard.org.value) if vcard.org.value else ""
            if org_val:
                contact["organizo"] = org_val

        # Categories
        if hasattr(vcard, "categories"):
            cats = str(vcard.categories.value) if vcard.categories.value else ""
            if cats:
                contact["kategorioj"] = [c.strip() for c in cats.split(",")]

        # Note
        if hasattr(vcard, "note"):
            note_val = str(vcard.note.value) if vcard.note.value else ""
            if note_val:
                contact["noto"] = note_val

        return contact

    @staticmethod
    def _contact_to_vcard(contact: dict[str, Any]) -> str:
        """Convert a contact dict to vCard 3.0 string."""
        try:
            import vobject
        except ImportError:
            raise ImportError("vobject library required for VCF export")

        card = vobject.vCard()

        # Name (N)
        card.add("n")
        family = contact.get("familia_nomo", "")
        given = contact.get("nomo", "")
        card.n.value = vobject.vcard.Name(family=family, given=given)

        # Full name (FN)
        card.add("fn")
        card.fn.value = contact.get("plena_nomo", "") or (
            f"{given} {family}".strip()
        )

        # Email
        email = contact.get("retposto", "")
        if email:
            card.add("email")
            card.email.value = email
            card.email.type_param = "INTERNET"

        # Additional emails from JSON array
        retposhtadresoj = contact.get("retposhtadresoj", [])
        if isinstance(retposhtadresoj, str):
            try:
                retposhtadresoj = json.loads(retposhtadresoj)
            except (json.JSONDecodeError, TypeError):
                retposhtadresoj = []
        for addr in retposhtadresoj:
            val = addr.get("valoro", "")
            if val and val != email:
                card.add("email")
                card.email.value = val
                card.email.type_param = "INTERNET"

        # Phone
        telefonnumeroj = contact.get("telefonnumeroj", [])
        if isinstance(telefonnumeroj, str):
            try:
                telefonnumeroj = json.loads(telefonnumeroj)
            except (json.JSONDecodeError, TypeError):
                telefonnumeroj = []
        for tel in telefonnumeroj:
            val = tel.get("valoro", "")
            if val:
                card.add("tel")
                card.tel.value = val
                card.tel.type_param = tel.get("etikedo", "VOICE")

        # Organization
        org = contact.get("organizo", "")
        if org:
            card.add("org")
            card.org.value = [org]

        # Categories
        kategorioj = contact.get("kategorioj", [])
        if isinstance(kategorioj, str):
            try:
                kategorioj = json.loads(kategorioj)
            except (json.JSONDecodeError, TypeError):
                kategorioj = []
        if kategorioj:
            card.add("categories")
            card.categories.value = ",".join(kategorioj)

        # Note
        note = contact.get("noto", "")
        if note:
            card.add("note")
            card.note.value = note

        return card.serialize()


def get_kontakto_service() -> KontaktoService:
    """Get the singleton KontaktoService."""
    global _kontakto_service
    if _kontakto_service is None:
        _kontakto_service = KontaktoService(get_db())
    return _kontakto_service


__all__ = ["KontaktoService", "get_kontakto_service"]

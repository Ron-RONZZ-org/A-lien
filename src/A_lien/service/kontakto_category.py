"""Category management mixin for KontaktoService."""

from __future__ import annotations

from typing import Any


class KontaktoCategoryMixin:
    """Mixin providing category CRUD for KontaktoService.

    Requires self.db from the host class.
    """

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


__all__ = ["KontaktoCategoryMixin"]

"""Signature management mixin for RetpostoService."""

from __future__ import annotations

from typing import Any

from A.core.service import CRUDService


class RetpostoSignatureMixin:
    """Mixin providing signature CRUD for RetpostoService.

    Requires self.db, self.table to create a CRUDService on subskriboj table.
    """

    @property
    def _signatures(self) -> CRUDService:
        return CRUDService(self.db, "subskriboj")

    def list_signatures(self) -> list[dict[str, Any]]:
        """List all signatures ordered by name."""
        return self._signatures.list(order_by="nomo", desc=False)

    def create_signature(
        self, nomo: str, teksto: str, estas_html: bool = False
    ) -> dict[str, Any]:
        """Create a new signature."""
        return self._signatures.create({
            "nomo": nomo,
            "teksto": teksto,
            "estas_html": 1 if estas_html else 0,
        })

    def get_signature(self, uuid: str) -> dict[str, Any] | None:
        """Get a single signature by UUID."""
        return self._signatures.get(uuid)

    def find_signature_by_name(self, nomo: str) -> dict[str, Any] | None:
        """Find a signature by exact name.

        Args:
            nomo: Signature name (exact match, case-sensitive per SQLite default).

        Returns:
            Signature dict or None if not found.
        """
        return self._signatures.get_by_field("nomo", nomo)

    def resolve_signature(self, ident: str) -> dict[str, Any] | None:
        """Resolve a signature by UUID (prefix) or name.

        Tries UUID prefix match first, then exact name match.
        Useful for CLI commands that accept either format.

        Args:
            ident: UUID prefix (8+ chars) or exact signature name.

        Returns:
            Signature dict or None if not found.
        """
        sig = self._signatures.get(ident)
        if sig:
            return sig
        return self.find_signature_by_name(ident)

    def update_signature(self, uuid: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update a signature."""
        return self._signatures.update(uuid, data)

    def delete_signature(self, uuid: str) -> None:
        """Soft-delete a signature."""
        self._signatures.delete(uuid, soft=True)


__all__ = ["RetpostoSignatureMixin"]

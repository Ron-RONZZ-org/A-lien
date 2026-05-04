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

    def update_signature(self, uuid: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update a signature."""
        return self._signatures.update(uuid, data)

    def delete_signature(self, uuid: str) -> None:
        """Soft-delete a signature."""
        self._signatures.delete(uuid, soft=True)


__all__ = ["RetpostoSignatureMixin"]

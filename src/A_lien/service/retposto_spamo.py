"""Spam block management mixin for RetpostoService.

Provides CRUD for local spam blocks plus Sieve server sync.
"""

from __future__ import annotations

from typing import Any

from A.core.service import CRUDService


class RetpostoSpamoMixin:
    """Mixin providing spam block CRUD and Sieve server sync.

    Requires self.db from the host class (RetpostoService).
    """

    @property
    def _spamo(self) -> CRUDService:
        """CRUD service on spamo_blokoj table with undo."""
        return CRUDService(self.db, "spamo_blokoj", undo_size=5)

    def list_spam_blocks(self) -> list[dict[str, Any]]:
        """List all spam block rules, newest first."""
        return self._spamo.list(order_by="kreita_je", desc=True)

    def add_spam_block(self, rule: str, kreas: str | None = None) -> dict[str, Any]:
        """Add a new spam block rule (stored lowercase).

        Args:
            rule: Substring pattern (email or domain)
            kreas: Optional creator identifier

        Returns:
            Created record dict
        """
        return self._spamo.create({
            "regulo": rule.strip().lower(),
            "kreas": kreas or "",
        })

    def get_spam_block_by_rule(self, rule: str) -> dict[str, Any] | None:
        """Find a spam block by its rule text (case-insensitive)."""
        rows = self.db.execute(
            "SELECT * FROM spamo_blokoj WHERE regulo = ?",
            (rule.strip().lower(),),
        )
        for r in rows:
            return r
        return None

    def remove_spam_block(self, uuid: str) -> None:
        """Delete a spam block by UUID."""
        self._spamo.delete(uuid, soft=False)

    def is_spam(self, sender: str) -> bool:
        """Check if a sender address matches any spam block rule.

        Args:
            sender: Full email address or From header

        Returns:
            True if sender matches any block rule (substring match)
        """
        rules = self._spamo.list()
        sender_lower = sender.lower()
        for r in rules:
            if r.get("regulo", "") in sender_lower:
                return True
        return False

    def sync_spam_blocks_to_sieve(self, account_uuid: str) -> None:
        """Push ALL local spam blocks to an account's ManageSieve server.

        Uses wrapped merge strategy: maintains an A-lien-managed section
        within the active Sieve script via marker comments.

        Args:
            account_uuid: Target account UUID

        Raises:
            ValueError: If account not found or Sieve not configured
            ConnectionError: If Sieve server unreachable
            RuntimeError: If upload fails
        """
        from A_lien.sieve import get_sieve_manager
        from A_lien.sieve_spamo import (
            BEGIN_MARKER,
            END_MARKER,
            generate_spam_sieve,
            merge_spam_sieve,
        )

        # 1. Collect active rules (exclude soft-deleted)
        rules = [r["regulo"] for r in self.list_spam_blocks()]
        spam_section = generate_spam_sieve(rules)

        # 2. Connect to ManageSieve server
        manager = get_sieve_manager(account_uuid)

        try:
            scripts = manager.list_scripts()
            active = [s for s in scripts if s.get("active")]

            if active:
                # Merge into existing active script
                existing = manager.get_script(active[0]["name"])
                merged = merge_spam_sieve(existing, spam_section)
                manager.put_script(active[0]["name"], merged)
                manager.activate_script(active[0]["name"])
            else:
                # No active script — create a dedicated one
                script_name = "A-lien-spamo"
                full_script = (
                    f"require [\"fileinto\"];\n"
                    f"{spam_section}"
                )
                manager.put_script(script_name, full_script)
                manager.activate_script(script_name)
        finally:
            manager.disconnect()


__all__ = ["RetpostoSpamoMixin"]

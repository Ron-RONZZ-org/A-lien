"""Contact auto-creation mixin for RetpostoService.

Handles automatic contact creation from email senders and recipients
during IMAP sync and SMTP send operations.
"""

from __future__ import annotations

import json
from typing import Any

from A_lien.imap import (
    should_autosave_contact,
    _parse_email_address,
    _extract_sender_name,
)
from A_lien.service.kontakto_service import get_kontakto_service


class RetpostoContactMixin:
    """Mixin providing auto-contact creation for RetpostoService.

    Requires self.db and the ability to call get_kontakto_service().
    """

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
            """SELECT de FROM mesagoj
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


__all__ = ["RetpostoContactMixin"]

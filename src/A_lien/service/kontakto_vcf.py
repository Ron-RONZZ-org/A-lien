"""VCF import/export mixin for KontaktoService."""

from __future__ import annotations

import json
from typing import Any


class KontaktoVCFMixin:
    """Mixin providing VCF import/export for KontaktoService.

    Requires self.db, self.get(), self.list(), self.create() from the host class.
    """

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

        if hasattr(vcard, "tel"):
            for tel in vcard.contents.get("tel", []):
                num = str(tel.value) if tel.value else ""
                if num:
                    contact["telefonnumeroj"].append({
                        "valoro": num,
                        "etikedo": tel.params.get("TYPE", [""])[0] if hasattr(tel, "params") else "",
                        "cxefa": len(contact["telefonnumeroj"]) == 0,
                    })

        if hasattr(vcard, "org"):
            org_val = str(vcard.org.value) if vcard.org.value else ""
            if org_val:
                contact["organizo"] = org_val

        if hasattr(vcard, "categories"):
            cats = str(vcard.categories.value) if vcard.categories.value else ""
            if cats:
                contact["kategorioj"] = [c.strip() for c in cats.split(",")]

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

        card.add("n")
        family = contact.get("familia_nomo", "")
        given = contact.get("nomo", "")
        card.n.value = vobject.vcard.Name(family=family, given=given)

        card.add("fn")
        card.fn.value = contact.get("plena_nomo", "") or (
            f"{given} {family}".strip()
        )

        email = contact.get("retposto", "")
        if email:
            card.add("email")
            card.email.value = email
            card.email.type_param = "INTERNET"

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

        org = contact.get("organizo", "")
        if org:
            card.add("org")
            card.org.value = [org]

        kategorioj = contact.get("kategorioj", [])
        if isinstance(kategorioj, str):
            try:
                kategorioj = json.loads(kategorioj)
            except (json.JSONDecodeError, TypeError):
                kategorioj = []
        if kategorioj:
            card.add("categories")
            card.categories.value = ",".join(kategorioj)

        note = contact.get("noto", "")
        if note:
            card.add("note")
            card.note.value = note

        return card.serialize()


__all__ = ["KontaktoVCFMixin"]

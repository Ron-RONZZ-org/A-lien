"""Retposto forward command — plusendi.

Extracted from retposto_message_ops.py to keep files under 500 lines.
"""

from __future__ import annotations

import os
import re
import tempfile

import typer

from A import error, info, tr_multi
from A_lien.cli.retposto_message_ops import _resolve_message
from A_lien.service import get_retposto_service


def _forward_subject(original: str) -> str:
    """Prepend or ensure ``Fwd:`` prefix on a subject."""
    if re.match(r"^Fwd:\s*", original, re.IGNORECASE):
        return original
    return f"Fwd: {original}"


def retposto_plusendi(
    uuid: str = typer.Argument(
        ..., help=tr_multi(
            "Mesa\u011do UUID (plusendota)",
            "Message UUID (to forward)",
            "UUID du message (\u00e0 transf\u00e9rer)",
        ),
    ),
    to: str = typer.Option(
        ..., "--to", "-t",
        help=tr_multi(
            "Ricevinto (punktokomo-separita)",
            "Recipient (comma-separated)",
            "Destinataire (s\u00e9par\u00e9 par;)",
        ),
    ),
    subject: str = typer.Option(
        "", "--subject", "-s",
        help=tr_multi(
            "Temeto (defaultingas: Fwd: <originala>)",
            "Subject (defaults: Fwd: <original>)",
            "Sujet (par d\u00e9faut: Fwd: <original>)",
        ),
    ),
    cc: str = typer.Option(
        "", "--cc",
        help=tr_multi(
            "KK (punktokomo-separita)",
            "CC (comma-separated)",
            "CC (s\u00e9par\u00e9 par;)",
        ),
    ),
    bcc: str = typer.Option(
        "", "--bcc",
        help=tr_multi(
            "SKK (punktokomo-separita)",
            "BCC (comma-separated)",
            "BCC (s\u00e9par\u00e9 par;)",
        ),
    ),
    priority: int = typer.Option(
        5, "--prioritato", "-p",
        help=tr_multi(
            "Prioritato (1-5, 1=plej alta)",
            "Priority (1-5, 1=highest)",
            "Priorit\u00e9 (1-5, 1=la plus haute)",
        ),
    ),
    account: str = typer.Option(
        "", "--konto", "-k",
        help=tr_multi("Konto UUID", "Account UUID", "UUID compte"),
    ),
    attach: list[str] = typer.Option(
        [], "--alglui", "-a",
        help=tr_multi(
            "Dosiero algluenda (ripetebla)",
            "File to attach (repeatable)",
            "Fichier \u00e0 joindre (r\u00e9p\u00e9table)",
        ),
    ),
) -> None:
    """Forward an email to new recipients."""
    svc = get_retposto_service()
    msg = _resolve_message(svc, uuid)
    if not msg:
        error(tr_multi(
            f"Mesa\u011do ne trovita: {uuid}",
            f"Message not found: {uuid}",
            f"Message non trouv\u00e9: {uuid}",
        ))
        raise typer.Exit(1)

    effective_subject = subject or _forward_subject(msg.get("subjekto", ""))
    effective_account = account or msg.get("konto_id", "")

    # Build forwarded message text
    forwarded = (
        f"\n\n-------- Originala Mesa\u011do --------\n"
        f"From: {msg.get('de', '')}\n"
        f"Date: {msg.get('ricevita_je', '')}\n"
        f"Subject: {msg.get('subjekto', '')}\n"
        f"To: {msg.get('al', '')}\n"
        f"\n{msg.get('korpo', '')}\n"
    )

    # Open editor or use body directly
    body_text = forwarded.strip()
    editor = os.environ.get("EDITOR", "").strip()
    if editor:
        import sys

        template = (
            f"To: {to}\n"
            f"Subject: {effective_subject}\n"
            f"\n"
            f"{forwarded}\n"
        )
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8",
        ) as f:
            f.write(template)
            temp_path = f.name
        try:
            os.system(f"{editor} {temp_path}")
            with open(temp_path, encoding="utf-8") as f:
                edited = f.read()
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

        marker = "-------- Originala Mesa\u011do --------"
        if marker in edited:
            body = edited.split(marker)[0].strip()
        else:
            body = edited.strip()
        lines = body.splitlines()
        body_lines = []
        in_body = False
        for line in lines:
            if not in_body and re.match(r"^(To|Subject|Cc):\s*", line):
                continue
            if line.strip() == "" and not in_body:
                continue
            in_body = True
            body_lines.append(line)
        body_text = "\n".join(body_lines).strip()

    recipients = [r.strip() for r in to.split(",") if r.strip()]
    cc_list = [r.strip() for r in cc.split(",") if r.strip()] if cc else None
    bcc_list = [r.strip() for r in bcc.split(",") if r.strip()] if bcc else None

    try:
        svc.send_email(
            account_uuid=effective_account,
            to=recipients,
            subject=effective_subject,
            body=body_text,
            cc=cc_list,
            bcc=bcc_list,
            attachments=attach or None,
            priority=priority,
        )
        info(tr_multi(
            f"Mesa\u011do plusendita al {to}",
            f"Message forwarded to {to}",
            f"Message transf\u00e9r\u00e9 \u00e0 {to}",
        ))
    except Exception as e:
        error(tr_multi(
            f"Sendado malsukcesis: {e}",
            f"Send failed: {e}",
            f"\u00c9chec d'envoi: {e}",
        ))
        raise typer.Exit(1)

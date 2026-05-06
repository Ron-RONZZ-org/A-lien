"""Retposto message operations — respondi, forigi, movi.

Extracted from retposto.py to keep files under 500 lines.
These functions are registered on the retposto typer from retposto.py.
"""

from __future__ import annotations

import os
import re
import tempfile
from typing import Annotated, Optional

import typer

from A import error, info, tr_multi
from A_lien.service import get_retposto_service


def _resolve_message(svc, uuid: str) -> dict | None:
    """Resolve a message by UUID or prefix."""
    msg = svc.get_message(uuid)
    if msg:
        return msg
    matches = svc.find_message_by_uuid_prefix(uuid)
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        error(tr_multi(
            f"UUID '{uuid[:8]}' kongruas kun pluraj mesaĝoj",
            f"UUID '{uuid[:8]}' matches multiple messages",
            f"L'UUID '{uuid[:8]}' correspond à plusieurs messages",
        ))
        raise typer.Exit(1)
    return None


def _build_references(msg: dict) -> str:
    """Build References header from an existing message's headers."""
    refs = (msg.get("references_hdr") or "").strip()
    mid = (msg.get("message_id") or "").strip()
    if refs and mid:
        return f"{refs} {mid}"
    return refs or mid


# ── respondi — reply to an email ──────────────────────────────────────────────


def retposto_respondi(
    uuid: str = typer.Argument(
        ..., help=tr_multi(
            "Mesaĝo UUID (respondota)",
            "Message UUID (to reply to)",
            "UUID du message (auquel répondre)",
        ),
    ),
    to: str = typer.Option(
        "", "--to", "-t",
        help=tr_multi(
            "Ricevinto (defaultingas al originala sendinto)",
            "Recipient (defaults to original sender)",
            "Destinataire (par défaut l'expéditeur original)",
        ),
    ),
    subject: str = typer.Option(
        "", "--subject", "-s",
        help=tr_multi(
            "Temeto (defaultingas: Re: <originala>)",
            "Subject (defaults: Re: <original>)",
            "Sujet (par défaut: Re: <original>)",
        ),
    ),
    cc: str = typer.Option(
        "", "--cc",
        help=tr_multi(
            "KK (punktokomo-separita)",
            "CC (comma-separated)",
            "CC (séparé par;)",
        ),
    ),
    bcc: str = typer.Option(
        "", "--bcc",
        help=tr_multi(
            "SKK (punktokomo-separita)",
            "BCC (comma-separated)",
            "BCC (séparé par;)",
        ),
    ),
    priority: int = typer.Option(
        5, "--prioritato", "-p",
        help=tr_multi(
            "Prioritato (1-5, 1=plej alta)",
            "Priority (1-5, 1=highest)",
            "Priorité (1-5, 1=la plus haute)",
        ),
    ),
    account: str = typer.Option(
        "", "--konto", "-k",
        help=tr_multi(
            "Konto UUID (defaultingas al mesaĝa konto)",
            "Account UUID (defaults to message's account)",
            "UUID compte (par défaut celui du message)",
        ),
    ),
    attach: list[str] = typer.Option(
        [], "--alglui", "-a",
        help=tr_multi(
            "Dosiero algluenda",
            "File to attach",
            "Fichier à joindre",
        ),
    ),
) -> None:
    """Reply to an email."""
    svc = get_retposto_service()
    msg = _resolve_message(svc, uuid)
    if not msg:
        error(tr_multi(
            f"Mesaĝo ne trovita: {uuid}",
            f"Message not found: {uuid}",
            f"Message non trouvé: {uuid}",
        ))
        raise typer.Exit(1)

    # Defaults from original message
    effective_to = to or msg.get("de", "")
    effective_subject = subject or _reply_subject(msg.get("subjekto", ""))
    effective_account = account or msg.get("konto_id", "")

    # Build quoted original text
    original_body = msg.get("korpo") or ""
    quoted = "".join(f"> {line}\n" for line in original_body.splitlines(True))
    original_hdr = (
        f"---- Originala Mesaĝo ----\n"
        f"From: {msg.get('de', '')}\n"
        f"Date: {msg.get('ricevita_je', '')}\n"
        f"Subject: {msg.get('subjekto', '')}\n"
        f"\n{quoted}"
    )

    # Open editor or use body if non-interactive
    body_text = _edit_or_body(
        effective_to, effective_subject,
        msg.get("kc") or "[]", original_hdr,
    )

    recipients = [r.strip() for r in effective_to.split(",") if r.strip()]
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
            in_reply_to=msg.get("message_id", ""),
            references=_build_references(msg),
        )
        info(tr_multi(
            f"Respondo sendita al {effective_to}",
            f"Reply sent to {effective_to}",
            f"Réponse envoyée à {effective_to}",
        ))
    except Exception as e:
        error(tr_multi(
            f"Sendado malsukcesis: {e}",
            f"Send failed: {e}",
            f"Échec d'envoi: {e}",
        ))
        raise typer.Exit(1)


def _reply_subject(original: str) -> str:
    """Prepend or ensure ``Re:`` prefix on a subject."""
    if re.match(r"^Re(\[\d+\])?:\s*", original, re.IGNORECASE):
        return original
    return f"Re: {original}"


def _edit_or_body(
    to: str, subject: str, cc_json: str, original_hdr: str,
) -> str:
    """Open editor or read body from stdin for reply composition."""
    import json
    import sys

    cc_text = ""
    try:
        cc_list = json.loads(cc_json) if cc_json else []
        if isinstance(cc_list, list):
            cc_text = ", ".join(cc_list)
    except (json.JSONDecodeError, TypeError):
        cc_text = cc_json

    template = (
        f"To: {to}\n"
        f"Subject: {subject}\n"
        f"Cc: {cc_text}\n"
        f"\n"
        f"\n{original_hdr}\n"
    )

    editor = os.environ.get("EDITOR", "").strip()
    if not editor or not sys.stdin.isatty():
        # Non-interactive — require body via --body equivalent
        # (In CLI context, body is already provided as an arg)
        return ""

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

    # Extract body: everything before "---- Originala Mesaĝo ----"
    marker = "---- Originala Mesaĝo ----"
    if marker in edited:
        body = edited.split(marker)[0].strip()
    else:
        body = edited.strip()

    # Strip the header lines (To:, Subject:, Cc:)
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

    return "\n".join(body_lines).strip()


# ── forigi — delete/trash a message ───────────────────────────────────────────


def retposto_forigi(
    uuids: Annotated[list[str], typer.Argument(
        ..., help=tr_multi(
            "Mesaĝo UUID (pluraj)",
            "Message UUIDs (multiple)",
            "UUIDs des messages (plusieurs)",
        ),
    )],
    permanente: bool = typer.Option(
        False, "--permanente",
        help=tr_multi(
            "Permanente forigi (ne nur rubujon)",
            "Permanently delete (not just trash)",
            "Supprimer définitivement (pas seulement la corbeille)",
        ),
    ),
) -> None:
    """Delete/move messages to trash."""
    svc = get_retposto_service()
    successes = 0
    errors = 0
    for uid in uuids:
        msg = _resolve_message(svc, uid)
        if not msg:
            error(tr_multi(
                f"Mesaĝo ne trovita: {uid[:8]}",
                f"Message not found: {uid[:8]}",
                f"Message non trouvé: {uid[:8]}",
            ))
            errors += 1
            continue
        try:
            svc.trash_message(msg["uuid"], permanent=permanente)
            successes += 1
        except Exception as e:
            error(tr_multi(
                f"Eraro: {uid[:8]} — {e}",
                f"Error: {uid[:8]} — {e}",
                f"Erreur: {uid[:8]} — {e}",
            ))
            errors += 1
    if successes:
        label = tr_multi("forigitaj", "deleted", "supprimés")
        info(f"{successes} mesaĝo(j) {label}")
    if errors:
        raise typer.Exit(1)


# ── movi — move message to another account/folder ────────────────────────────


def retposto_movi(
    uuid: str = typer.Argument(
        ..., help=tr_multi(
            "Mesaĝo UUID",
            "Message UUID",
            "UUID du message",
        ),
    ),
    destination: str = typer.Argument(
        ..., help=tr_multi(
            "Celo-formato: {konto_uuid}:{dosierujo_nomo}",
            "Destination format: {account_uuid}:{folder_name}",
            "Format destination: {uuid_compte}:{nom_dossier}",
        ),
    ),
) -> None:
    """Move message to another account/folder."""
    svc = get_retposto_service()
    msg = _resolve_message(svc, uuid)
    if not msg:
        error(tr_multi(
            f"Mesaĝo ne trovita: {uuid}",
            f"Message not found: {uuid}",
            f"Message non trouvé: {uuid}",
        ))
        raise typer.Exit(1)

    # Parse destination
    if ":" not in destination:
        error(tr_multi(
            "Celo-formato devas esti {konto_uuid}:{dosierujo_nomo}",
            "Destination format must be {account_uuid}:{folder_name}",
            "Le format de destination doit être {uuid_compte}:{nom_dossier}",
        ))
        raise typer.Exit(1)

    dest_account, dest_folder = destination.split(":", 1)

    try:
        svc.move_message(msg, dest_account, dest_folder)
        info(tr_multi(
            f"Mesaĝo movita al {dest_account[:8]}:{dest_folder}",
            f"Message moved to {dest_account[:8]}:{dest_folder}",
            f"Message déplacé vers {dest_account[:8]}:{dest_folder}",
        ))
    except Exception as e:
        error(tr_multi(
            f"Movado malsukcesis: {e}",
            f"Move failed: {e}",
            f"Échec du déplacement: {e}",
        ))
        raise typer.Exit(1)


__all__ = [
    "retposto_respondi",
    "retposto_forigi",
    "retposto_movi",
]

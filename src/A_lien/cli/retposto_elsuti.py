"""Retposto attachment download — elsuti.

Download/extract attachment from an email via IMAP.
"""

from __future__ import annotations

from typing import Optional

import typer

from A import error, info, tr_multi
from A_lien.cli.retposto_message_ops import _resolve_message
from A_lien.service import get_retposto_service


def retposto_elsuti(
    uuid: str = typer.Argument(
        ..., help=tr_multi(
            "Mesa\u011do UUID",
            "Message UUID",
            "UUID du message",
        ),
    ),
    filename: Optional[str] = typer.Argument(
        None, help=tr_multi(
            "Dosiernomo \u015dan\u0109i\u0115enda (preterlasu por listo)",
            "Filename to download (omit for list)",
            "Nom du fichier \u00e0 t\u00e9l\u00e9charger (omettre pour lister)",
        ),
    ),
    output_dir: Optional[str] = typer.Option(
        None, "--output", "-o",
        help=tr_multi(
            "Konserva dosierujo (default: nuna dosierujo)",
            "Output directory (default: current dir)",
            "Dossier de sortie (d\u00e9faut: dossier courant)",
        ),
    ),
) -> None:
    """Download attachment from a message via IMAP.

    If no filename is given, lists available attachments.
    Otherwise extracts and saves the named attachment.
    """
    svc = get_retposto_service()
    msg = _resolve_message(svc, uuid)
    if not msg:
        error(tr_multi(
            f"Mesa\u011do ne trovita: {uuid}",
            f"Message not found: {uuid}",
            f"Message non trouv\u00e9: {uuid}",
        ))
        raise typer.Exit(1)

    attachments = svc.get_attachments(msg["uuid"])

    if not filename:
        # List mode
        if not attachments:
            info(tr_multi(
                "Neniuj aldona\u0135oj en \u0109i tiu mesa\u011do.",
                "No attachments in this message.",
                "Aucune pi\u00e8ce jointe dans ce message.",
            ))
            return
        info(tr_multi(
            "Aldona\u0135oj haveblaj:",
            "Available attachments:",
            "Pi\u00e8ces jointes disponibles:",
        ))
        for att in attachments:
            size = att.get("grandeco", 0)
            size_str = (
                f"{size / (1024 * 1024):.1f} MB" if size > 1024 * 1024
                else f"{size / 1024:.1f} KB" if size > 1024
                else f"{size} B"
            )
            info(f"  {att['dosiernomo']} ({size_str})")
        return

    # Download mode
    if not any(a.get("dosiernomo") == filename for a in attachments):
        error(tr_multi(
            f"Aldona\u0135o '{filename}' ne trovita en \u0109i tiu mesa\u011do.",
            f"Attachment '{filename}' not found in this message.",
            f"Pi\u00e8ce jointe '{filename}' non trouv\u00e9e.",
        ))
        raise typer.Exit(1)

    try:
        path = svc.extract_attachment(msg["uuid"], filename, output_dir)
        info(tr_multi(
            f"Konservita: {path}",
            f"Saved: {path}",
            f"Enregistr\u00e9: {path}",
        ))
    except Exception as e:
        error(str(e))
        raise typer.Exit(1)

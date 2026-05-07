"""Retposto attachment download — elsuti.

Download/extract attachment(s) from an email via IMAP.
"""

from __future__ import annotations

from typing import Optional

import typer

from A import error, info, tr_multi
from A_lien.cli.retposto_message_ops import _resolve_message
from A_lien.service import get_retposto_service


def _fmt_size(size: int) -> str:
    """Format byte count to human-readable string."""
    if size > 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    if size > 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} B"


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
            "Dosiernomo \u015dan\u0109i\u0115enda (preterlasu por \u0109iuj)",
            "Filename to download (omit for all)",
            "Nom du fichier \u00e0 t\u00e9l\u00e9charger (omettre pour tout)",
        ),
    ),
    output_dir: Optional[str] = typer.Option(
        None, "--output", "-o",
        help=tr_multi(
            "Konserva dosierujo (default: /tmp/)",
            "Output directory (default: /tmp/)",
            "Dossier de sortie (d\u00e9faut: /tmp/)",
        ),
    ),
) -> None:
    """Download attachment(s) from a message via IMAP.

    If no filename is given, downloads ALL attachments
    (with confirmation if >3 files or >10 MB total).
    """
    import os

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
    if not attachments:
        info(tr_multi(
            "Neniuj aldona\u0135oj en \u0109i tiu mesa\u011do.",
            "No attachments in this message.",
            "Aucune pi\u00e8ce jointe dans ce message.",
        ))
        return

    out = output_dir or "/tmp"

    if filename:
        # ── Single attachment ─────────────────────────────────────────────
        if not any(a.get("dosiernomo") == filename for a in attachments):
            error(tr_multi(
                f"Aldona\u0135o '{filename}' ne trovita.",
                f"Attachment '{filename}' not found.",
                f"Pi\u00e8ce jointe '{filename}' non trouv\u00e9e.",
            ))
            raise typer.Exit(1)
        try:
            path = svc.extract_attachment(msg["uuid"], filename, out)
            info(tr_multi(f"Konservita: {path}", f"Saved: {path}", f"Enregistr\u00e9: {path}"))
        except Exception as e:
            error(str(e))
            raise typer.Exit(1)
        return

    # ── Download all ──────────────────────────────────────────────────────
    total_size = sum(a.get("grandeco", 0) for a in attachments)
    total_mb = total_size / (1024 * 1024)

    info(tr_multi(
        f"El\u015dutota {len(attachments)} aldona\u0135o(j) ({_fmt_size(total_size)})",
        f"Downloading {len(attachments)} attachment(s) ({_fmt_size(total_size)})",
        f"T\u00e9l\u00e9chargement de {len(attachments)} pi\u00e8ce(s) jointe(s) ({_fmt_size(total_size)})",
    ))

    # Confirmation gate for large/many downloads
    if len(attachments) > 3 or total_mb > 10:
        confirmed = typer.confirm(
            tr_multi(
                "\u0108u da\u016drigi?",
                "Continue?",
                "Continuer?",
            ),
            default=True,
        )
        if not confirmed:
            info(tr_multi("Nuligita.", "Cancelled.", "Annul\u00e9."))
            raise typer.Exit(0)

    saved = 0
    for att in attachments:
        fname = att["dosiernomo"]
        try:
            path = svc.extract_attachment(msg["uuid"], fname, out)
            info(f"  [{'OK' if len(attachments) > 1 else ''}] {os.path.basename(path)}")
            saved += 1
        except Exception as e:
            error(tr_multi(
                f"  Eraro: {fname} — {e}",
                f"  Error: {fname} — {e}",
                f"  Erreur: {fname} — {e}",
            ))

    if saved:
        info(tr_multi(
            f"{saved} aldona\u0135o(j) konservita(j) al {out}",
            f"{saved} attachment(s) saved to {out}",
            f"{saved} pi\u00e8ce(s) jointe(s) enregistr\u00e9e(s) dans {out}",
        ))

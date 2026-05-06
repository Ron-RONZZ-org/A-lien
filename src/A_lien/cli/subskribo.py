"""Subskribo sub-typer — signature management.

Commands: ls, aldoni, forigi
"""

from __future__ import annotations

from typing import Annotated

import typer

from A import error, info, tr_multi
from A_lien.service import get_retposto_service

subskribo_app = typer.Typer(
    name="subskribo",
    help=tr_multi(
        "Administri subskribojn.",
        "Manage signatures.",
        "Gérer les signatures.",
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help", "--helpo"]},
)


@subskribo_app.command("ls")
def subskribo_ls() -> None:
    """List signatures."""
    service = get_retposto_service()
    sigs = service.list_signatures()

    if not sigs:
        info(tr_multi(
            "Neniuj subskriboj.",
            "No signatures.",
            "Aucune signature.",
        ))
        return

    for s in sigs:
        preview = s.get("teksto", "")[:60].replace("\n", " ")
        html_tag = " [HTML]" if s.get("estas_html") else ""
        default_tag = (
            tr_multi(" [apriora]", " [default]", " [défaut]")
            if s.get("apriora")
            else ""
        )
        info(f"  {s['uuid'][:8]}  {s['nomo']}{html_tag}{default_tag}")
        if preview:
            info(f"         {preview}...")


@subskribo_app.command("aldoni")
def subskribo_aldoni(
    nomo: str = typer.Argument(
        ..., help=tr_multi("Subskribo nomo", "Signature name", "Nom de signature")
    ),
    teksto: str = typer.Option(
        ..., "--teksto", "-t",
        help=tr_multi("Subskribo teksto", "Signature text", "Texte de signature"),
    ),
    estas_html: bool = typer.Option(
        False, "--html",
        help=tr_multi("Teksto estas HTML", "Text is HTML", "Texte est HTML"),
    ),
) -> None:
    """Add a new signature."""
    service = get_retposto_service()
    try:
        sig = service.create_signature(nomo, teksto, estas_html)
        info(tr_multi(
            f"Subskribo kreita: {sig['uuid'][:8]} {nomo}",
            f"Signature created: {sig['uuid'][:8]} {nomo}",
            f"Signature créée: {sig['uuid'][:8]} {nomo}",
        ))
    except Exception as e:
        error(tr_multi(
            f"Eraro: {e}",
            f"Error: {e}",
            f"Erreur: {e}",
        ))
        raise typer.Exit(1)


@subskribo_app.command("forigi")
def subskribo_forigi(
    uuids: Annotated[list[str], typer.Argument(
        ..., help=tr_multi("Subskribo UUID (pluraj)", "Signature UUIDs (multiple)", "UUIDs signature (plusieurs)")
    )],
) -> None:
    """Delete signatures."""
    service = get_retposto_service()
    for uid in uuids:
        try:
            service.delete_signature(uid)
            info(tr_multi(
                f"Subskribo forigita: {uid[:8]}",
                f"Signature deleted: {uid[:8]}",
                f"Signature supprimée: {uid[:8]}",
            ))
        except Exception as e:
            error(tr_multi(
                f"Eraro: {uid[:8]} — {e}",
                f"Error: {uid[:8]} — {e}",
                f"Erreur: {uid[:8]} — {e}",
            ))


__all__ = [
    "subskribo_app",
    "subskribo_ls",
    "subskribo_aldoni",
    "subskribo_forigi",
]

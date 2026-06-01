"""Subskribo sub-typer — signature management.

Commands: ls, aldoni, forigi
"""

from __future__ import annotations

from pathlib import Path
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
    teksto: str | None = typer.Option(
        None, "--teksto", "-t",
        help=tr_multi("Subskriba teksto (enlinie)", "Signature text (inline)", "Texte de signature (en ligne)"),
    ),
    dosiero: str | None = typer.Option(
        None, "--dosiero", "-D",
        help=tr_multi(
            "Subskriba dosiero (anstataŭas --teksto)",
            "Signature file (replaces --teksto)",
            "Fichier de signature (remplace --teksto)",
        ),
    ),
    estas_html: bool = typer.Option(
        False, "--html",
        help=tr_multi("Marki kiel HTML", "Mark as HTML", "Marquer comme HTML"),
    ),
) -> None:
    """Add a new signature.

    Provide the signature text either inline (--teksto/-t)
    or from a file (--dosiero/-D), but not both.
    """
    if dosiero and teksto:
        error(tr_multi(
            "Donu --teksto AŬ --dosiero, ne ambaŭ.",
            "Provide --teksto OR --dosiero, not both.",
            "Fournissez --teksto OU --dosiero, pas les deux.",
        ))
        raise typer.Exit(1)

    if dosiero:
        path = Path(dosiero)
        if not path.exists():
            error(tr_multi(
                f"Dosiero ne ekzistas: {dosiero}",
                f"File not found: {dosiero}",
                f"Fichier introuvable: {dosiero}",
            ))
            raise typer.Exit(1)
        teksto = path.read_text(encoding="utf-8")
        # Auto-detect HTML from file extension unless --html was explicitly passed
        if not estas_html and path.suffix.lower() in (".html", ".htm"):
            estas_html = True
    elif not teksto:
        error(tr_multi(
            "Donu --teksto/-t aŭ --dosiero/-D.",
            "Provide --teksto/-t or --dosiero/-D.",
            "Fournissez --teksto/-t ou --dosiero/-D.",
        ))
        raise typer.Exit(1)

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
    identifiers: Annotated[list[str], typer.Argument(
        ..., help=tr_multi(
            "Subskribo nomo aŭ UUID (pluraj)",
            "Signature name or UUID (multiple)",
            "Nom ou UUID de signature (plusieurs)",
        )
    )],
) -> None:
    """Delete signatures.

    Accepts signature names or UUIDs (or a mix). Names are matched
    exactly; UUIDs support 8+ char prefix matching.
    """
    service = get_retposto_service()
    for ident in identifiers:
        sig = service.resolve_signature(ident)
        if not sig:
            error(tr_multi(
                f"Subskribo ne trovita: {ident}",
                f"Signature not found: {ident}",
                f"Signature introuvable: {ident}",
            ))
            continue
        try:
            service.delete_signature(sig["uuid"])
            info(tr_multi(
                f"Subskribo forigita: {sig['nomo']} ({sig['uuid'][:8]})",
                f"Signature deleted: {sig['nomo']} ({sig['uuid'][:8]})",
                f"Signature supprimée: {sig['nomo']} ({sig['uuid'][:8]})",
            ))
        except Exception as e:
            error(tr_multi(
                f"Eraro: {ident} — {e}",
                f"Error: {ident} — {e}",
                f"Erreur: {ident} — {e}",
            ))


__all__ = [
    "subskribo_app",
    "subskribo_ls",
    "subskribo_aldoni",
    "subskribo_forigi",
]

"""Kategorio sub-typer — category management.

Commands: ls, aldoni, forigi
Registered on kontakto typer from kontakto.py.
"""

from __future__ import annotations

from typing import Annotated

import typer

from A import error, info, tr_multi
from A_lien.service import get_kontakto_service

kategorio_app = typer.Typer(
    name="kategorio",
    help=tr_multi(
        "Administri kategoriojn.",
        "Manage categories.",
        "Gérer les catégories.",
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help", "--helpo"]},
)


@kategorio_app.command("ls")
def kategorio_ls() -> None:
    """List categories."""
    service = get_kontakto_service()
    cats = service.list_categories()
    if not cats:
        info(tr_multi(
            "Neniuj kategorioj.",
            "No categories.",
            "Aucune catégorie.",
        ))
        return
    for c in cats:
        color = f" ({c['koloro']})" if c.get("koloro") else ""
        info(f"  {c['uuid'][:8]}  {c['nomo']}{color}")


@kategorio_app.command("aldoni")
def kategorio_aldoni(
    nomo: str = typer.Argument(
        ...,
        help=tr_multi("Kategorinomo", "Category name", "Nom de catégorie"),
    ),
    koloro: str = typer.Option(
        "", "--koloro", "-k",
        help=tr_multi("Kolorkodo", "Color code", "Code couleur"),
    ),
) -> None:
    """Add a new category."""
    service = get_kontakto_service()
    try:
        cat = service.create_category(nomo, koloro)
        info(tr_multi(
            f"Kategorio kreita: {cat['uuid'][:8]} {nomo}",
            f"Category created: {cat['uuid'][:8]} {nomo}",
            f"Catégorie créée: {cat['uuid'][:8]} {nomo}",
        ))
    except Exception as e:
        error(tr_multi(
            f"Eraro: {e}",
            f"Error: {e}",
            f"Erreur: {e}",
        ))
        raise typer.Exit(1)


@kategorio_app.command("forigi")
def kategorio_forigi(
    uuids: Annotated[list[str], typer.Argument(
        ...,
        help=tr_multi("Kategorio UUID (pluraj)", "Category UUIDs (multiple)", "UUIDs catégorie (plusieurs)"),
    )],
) -> None:
    """Delete categories."""
    service = get_kontakto_service()
    for uid in uuids:
        if service.delete_category(uid):
            info(tr_multi(
                f"Kategorio forigita: {uid[:8]}",
                f"Category deleted: {uid[:8]}",
                f"Catégorie supprimée: {uid[:8]}",
            ))
        else:
            error(tr_multi(
                f"Kategorio ne trovita: {uid[:8]}",
                f"Category not found: {uid[:8]}",
                f"Catégorie non trouvée: {uid[:8]}",
            ))


__all__ = [
    "kategorio_app",
    "kategorio_ls",
    "kategorio_aldoni",
    "kategorio_forigi",
]

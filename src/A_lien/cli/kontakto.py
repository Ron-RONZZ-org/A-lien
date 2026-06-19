"""Kontakto sub-typer — contact management.

Commands: ls, serci, vidi, malfari, purigi
Write commands in kontakto_edit.py, categories in kategorio.py
"""

from __future__ import annotations

import json
from typing import Any

import typer

from A import error, info, tr_multi
from A_lien.service import get_kontakto_service

kontakto = typer.Typer(
    name="kontakto",
    help=tr_multi(
        "Administri kontaktojn.",
        "Manage contacts.",
        "Gérer les contacts.",
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help", "--helpo"]},
)

_kontakto_fields_doc = """
Valid contact fields (JSON):
  nomo, familia_nomo, plena_nomo, retposto, organizo,
  noto, naskigx_dato, naskigx_loko, konfirmita,
  lingvoj, telefonnumeroj, retposhtadresoj, kampoj, kategorioj
"""


# ── Import and register write commands from sibling modules ──────────────────

from A_lien.cli.kontakto_edit import (  # noqa: E402
    kontakto_aldoni,
    kontakto_eksporti,
    kontakto_forigi,
    kontakto_importi,
    kontakto_modifi,
)
from A_lien.cli.kategorio import kategorio_app  # noqa: E402

kontakto.command(name="aldoni")(kontakto_aldoni)
kontakto.command(name="modifi")(kontakto_modifi)
kontakto.command(name="forigi")(kontakto_forigi)
kontakto.command(name="importi")(kontakto_importi)
kontakto.command(name="eksporti")(kontakto_eksporti)
kontakto.add_typer(kategorio_app, name="kategorio")


# ── Read-only commands ───────────────────────────────────────────────────────


@kontakto.command("ls")
def kontakto_ls(
    limit: int = typer.Option(
        50, "--limo", "-l",
        help=tr_multi("Maksimumaj rezultoj", "Max results", "Résultats max"),
    ),
    order_by: str = typer.Option(
        "plena_nomo", "--order", "-o",
        help=tr_multi("Ordiga kolumno", "Sort column", "Colonne de tri"),
    ),
    desc: bool = typer.Option(
        False, "--desc", "-d",
        help=tr_multi("Malkreska ordo", "Descending order", "Ordre décroissant"),
    ),
) -> None:
    """List all contacts."""
    from A.utils.output import print_table

    service = get_kontakto_service()
    contacts = service.list(order_by=order_by, desc=desc, limit=limit)

    if not contacts:
        info(tr_multi("Neniuj kontaktoj.", "No contacts.", "Aucun contact."))
        return

    rows = []
    for c in contacts:
        emails = c.get("retposhtadresoj", [])
        primary_email = (
            emails[0].get("valoro", "")
            if emails and isinstance(emails, list)
            else ""
        )
        rows.append({
            "uuid": c["uuid"][:8],
            "nomo": c.get("plena_nomo") or c.get("nomo") or "",
            "retposto": primary_email,
            "organizo": c.get("organizo", ""),
            "kategorioj": c.get("kategorioj", []),
        })

    columns = [
        {"header": "UUID", "key": "uuid", "style": "dim", "width": 10},
        {"header": tr_multi("Nomo", "Name", "Nom"), "key": "nomo"},
        {"header": tr_multi("Retpoŝto", "Email", "Email"), "key": "retposto"},
        {"header": tr_multi("Organizo", "Organization", "Organisation"), "key": "organizo"},
        {"header": tr_multi("Kategorioj", "Categories", "Catégories"), "key": "kategorioj"},
    ]

    print_table(
        columns,
        rows,
        title=tr_multi("Kontaktoj", "Contacts", "Contacts"),
    )


@kontakto.command("serci")
def kontakto_serci(
    query: str = typer.Argument(
        ...,
        help=tr_multi("Serĉa teksto", "Search text", "Texte de recherche"),
    ),
    fuzzy: bool = typer.Option(
        False, "--fuzzy", "-f",
        help=tr_multi("Ŝalti fuzzy kongruigon", "Enable fuzzy matching", "Activer correspondance floue"),
    ),
    limit: int = typer.Option(
        50, "--limo", "-l",
        help=tr_multi("Maksimumaj rezultoj", "Max results", "Résultats max"),
    ),
) -> None:
    """Search contacts using full-text search."""
    service = get_kontakto_service()
    contacts = service.search_contacts(query=query, fuzzy=fuzzy, limit=limit)

    if not contacts:
        info(tr_multi(
            f"Neniuj rezultoj por '{query}'.",
            f"No results for '{query}'.",
            f"Aucun résultat pour '{query}'.",
        ))
        return

    info(tr_multi(
        f"Trovitaj {len(contacts)} kontakto(j) por '{query}':",
        f"Found {len(contacts)} contact(s) for '{query}':",
        f"{len(contacts)} contact(s) trouvé(s) pour '{query}':",
    ))
    for c in contacts:
        name = c.get("plena_nomo") or c.get("nomo") or "(sen nomo)"
        email = c.get("retposto", "")
        extra = f" — {email}" if email else ""
        info(f"  {c['uuid'][:8]}  {name}{extra}")


@kontakto.command("vidi")
def kontakto_vidi(
    uuid: str = typer.Argument(
        ...,
        help=tr_multi(
            "Kontakto UUID (aŭ prefikso)",
            "Contact UUID (or prefix)",
            "UUID contact (ou préfixe)",
        ),
    ),
) -> None:
    """View a contact's full details."""
    service = get_kontakto_service()
    contact = service.get(uuid)

    if not contact:
        candidates = service.find_by_uuid_prefix(uuid)
        if len(candidates) == 1:
            contact = candidates[0]
        elif len(candidates) > 1:
            error(tr_multi(
                f"Pluraj kontaktoj kongruas kun '{uuid}':",
                f"Multiple contacts match '{uuid}':",
                f"Plusieurs contacts correspondent à '{uuid}':",
            ))
            for c in candidates:
                name = c.get("plena_nomo") or c.get("nomo") or "(sen nomo)"
                info(f"  {c['uuid'][:8]}  {name}")
            return
        else:
            error(tr_multi(
                f"Kontakto ne trovita: {uuid}",
                f"Contact not found: {uuid}",
                f"Contact non trouvé: {uuid}",
            ))
            raise typer.Exit(1)

    name = contact.get("plena_nomo") or contact.get("nomo") or "(sen nomo)"
    info(f"  UUID: {contact['uuid']}")
    info(f"  Nomo: {name}")
    familia_nomo = contact.get("familia_nomo") or ""
    if familia_nomo and familia_nomo.lower() != "none":
        info(f"  Familia nomo: {familia_nomo}")
    if contact.get("retposto"):
        info(f"  Retpoŝto: {contact['retposto']}")
    if contact.get("organizo"):
        info(f"  Organizo: {contact['organizo']}")
    if contact.get("telefonnumeroj"):
        tels = contact["telefonnumeroj"]
        if isinstance(tels, str):
            try:
                tels = json.loads(tels)
            except (json.JSONDecodeError, TypeError):
                tels = []
        for t in tels:
            label = t.get("etikedo", "") or ""
            label = f" ({label})" if label else ""
            info(f"  Telefono{label}: {t.get('valoro', '')}")
    if contact.get("kategorioj"):
        cats = contact["kategorioj"]
        if isinstance(cats, str):
            try:
                cats = json.loads(cats)
            except (json.JSONDecodeError, TypeError):
                cats = []
        info(f"  Kategorioj: {', '.join(cats)}")
    if contact.get("noto"):
        info(f"  Noto: {contact['noto']}")
    if contact.get("konfirmita"):
        info("  Konfirmita: jes")
    info(f"  Kreita: {contact.get('kreita_je', '?')}")
    info(f"  Modifita: {contact.get('modifita_je', '?')}")


@kontakto.command("malfari")
def kontakto_malfari() -> None:
    """Undo the last contact operation."""
    service = get_kontakto_service()
    result = service.undo()
    if result:
        info(tr_multi(
            f"Malfarita: {result.get('operation_type', '?')}",
            f"Undone: {result.get('operation_type', '?')}",
            f"Annulé: {result.get('operation_type', '?')}",
        ))
    else:
        info(tr_multi(
            "Nenio por malfari.",
            "Nothing to undo.",
            "Rien à annuler.",
        ))


@kontakto.command("purigi")
def kontakto_purigi() -> None:
    """Find and suggest duplicate contact cleanup."""
    service = get_kontakto_service()
    contacts = service.list()

    duplicates: list[tuple[dict, list[dict]]] = []
    seen: set[str] = set()

    for c in contacts:
        cid = c["uuid"]
        if cid in seen:
            continue
        dups = service.find_duplicates(c, threshold=0.85)
        if dups:
            duplicates.append((c, dups))
            for d in dups:
                seen.add(d["uuid"])

    if not duplicates:
        info(tr_multi(
            "Neniuj duplikatoj trovitaj.",
            "No duplicates found.",
            "Aucun doublon trouvé.",
        ))
        return

    info(tr_multi(
        f"Trovitaj {len(duplicates)} grupo(j) da duplikatoj:",
        f"Found {len(duplicates)} duplicate group(s):",
        f"{len(duplicates)} groupe(s) de doublons trouvé(s):",
    ))
    for master, dups in duplicates:
        master_name = master.get("plena_nomo") or master.get("nomo") or "?"
        info(f"  Grupo: {master_name} ({master['uuid'][:8]})")
        for d in dups:
            name = d.get("plena_nomo") or d.get("nomo") or "?"
            info(f"    → {name} ({d['uuid'][:8]})")


__all__ = [
    "kontakto",
    "kontakto_ls",
    "kontakto_serci",
    "kontakto_vidi",
    "kontakto_malfari",
    "kontakto_purigi",
]

"""CLI for lien command (retposto, kontakto)."""

from __future__ import annotations

import json
from typing import Optional

import typer

from A import error, info, tr_multi, warning

from A_lien.service import get_kontakto_service

app = typer.Typer(
    name="lien",
    help=tr_multi(
        "Lien — retpoŝto kaj kontaktoj.",
        "Lien — email and contacts.",
        "Lien — email et contacts.",
    ),
    no_args_is_help=False,
    invoke_without_command=True,
    context_settings={"help_option_names": ["-h", "--help", "--helpo"]},
)

retposto = typer.Typer(
    name="retposto",
    help=tr_multi(
        "Retpoŝto — retpoŝta mikroapo.",
        "Retpoŝto — email microapp.",
        "Retpoŝto — microapp email.",
    ),
    no_args_is_help=False,
    invoke_without_command=True,
    context_settings={"help_option_names": ["-h", "--help", "--helpo"]},
)
app.add_typer(retposto, name="retposto")

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
app.add_typer(kontakto, name="kontakto")


# ══════════════════════════════════════════════════════════════════════════════
# retposto subcommands (TODO — Phase 3/4)
# ══════════════════════════════════════════════════════════════════════════════


@retposto.command("ls")
def retposto_ls() -> None:
    """List email accounts."""
    info("[dim]TODO: implement retposto ls[/dim]")


@retposto.command("preni")
def retposto_preni() -> None:
    """Fetch mail from all accounts."""
    info("[dim]TODO: implement retposto preni[/dim]")


@retposto.command("sendi")
def retposto_sendi(to: str, subject: str) -> None:
    """Send an email."""
    info(f"[dim]TODO: implement retposto sendi to={to} subject={subject}[/dim]")


# ══════════════════════════════════════════════════════════════════════════════
# kontakto subcommands
# ══════════════════════════════════════════════════════════════════════════════

_kontakto_fields_doc = """
Valid contact fields (JSON):
  nomo, familia_nomo, plena_nomo, retposto, organizo,
  noto, naskigx_dato, naskigx_loko, konfirmita,
  lingvoj, telefonnumeroj, retposhtadresoj, kampoj, kategorioj
"""


@kontakto.command("ls")
def kontakto_ls(
    limit: int = typer.Option(50, "--limit", "-l", help="Max results"),
    order_by: str = typer.Option(
        "plena_nomo", "--order", "-o", help="Sort column"
    ),
    desc: bool = typer.Option(False, "--desc", "-d", help="Descending order"),
) -> None:
    """List all contacts."""
    service = get_kontakto_service()
    contacts = service.list(order_by=order_by, desc=desc, limit=limit)

    if not contacts:
        info(tr_multi("Neniuj kontaktoj.", "No contacts.", "Aucun contact."))
        return

    info(tr_multi(
        f"Trovitaj {len(contacts)} kontakto(j):",
        f"Found {len(contacts)} contact(s):",
        f"{len(contacts)} contact(s) trouvé(s):",
    ))
    for c in contacts:
        name = c.get("plena_nomo") or c.get("nomo") or "(sen nomo)"
        email = c.get("retposto", "")
        org = c.get("organizo", "")
        extra = f" — {email}" if email else ""
        extra += f" ({org})" if org else ""
        info(f"  {c['uuid'][:8]}  {name}{extra}")


@kontakto.command("serci")
def kontakto_serci(
    query: str = typer.Argument(..., help="Search text"),
    fuzzy: bool = typer.Option(False, "--fuzzy", "-f", help="Enable fuzzy matching"),
    limit: int = typer.Option(50, "--limit", "-l", help="Max results"),
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
    uuid: str = typer.Argument(..., help="Contact UUID (or prefix)"),
) -> None:
    """View a contact's full details."""
    service = get_kontakto_service()
    contact = service.get(uuid)

    if not contact:
        # Try prefix match
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
    if contact.get("familia_nomo"):
        info(f"  Familia nomo: {contact['familia_nomo']}")
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


@kontakto.command("aldoni")
def kontakto_aldoni(
    nomo: str = typer.Option("", "--nomo", "-n", help="Given name"),
    familia_nomo: str = typer.Option("", "--familia-nomo", "--fn", help="Family name"),
    plena_nomo: str = typer.Option("", "--plena-nomo", "--pn", help="Full name"),
    retposto_opt: str = typer.Option("", "--retposto", "-r", help="Primary email"),
    organizo: str = typer.Option("", "--organizo", "-o", help="Organization"),
    telefono: str = typer.Option("", "--telefono", "-t", help="Phone number"),
    noto: str = typer.Option("", "--noto", "-N", help="Notes"),
    kategorio: str = typer.Option("", "--kategorio", "-k", help="Category"),
) -> None:
    """Add a new contact."""
    from A_lien.utils import split_full_name

    service = get_kontakto_service()

    if not plena_nomo and nomo:
        plena_nomo = nomo
    if not plena_nomo:
        error(tr_multi(
            "Bezonata nomo aŭ plena nomo.",
            "Name or full name required.",
            "Nom ou nom complet requis.",
        ))
        raise typer.Exit(1)

    if not nomo and not familia_nomo:
        nomo, familia_nomo = split_full_name(plena_nomo)

    data: dict = {
        "nomo": nomo,
        "familia_nomo": familia_nomo,
        "plena_nomo": plena_nomo,
        "retposto": retposto_opt,
        "organizo": organizo,
        "noto": noto,
    }

    if telefono:
        data["telefonnumeroj"] = [{"valoro": telefono, "etikedo": "VOICE", "cxefa": True}]

    if kategorio:
        data["kategorioj"] = [kategorio]

    # Remove empty values
    data = {k: v for k, v in data.items() if v}

    try:
        contact = service.create(data)
        info(tr_multi(
            f"Kontakto kreita: {contact['uuid'][:8]} {contact.get('plena_nomo', '')}",
            f"Contact created: {contact['uuid'][:8]} {contact.get('plena_nomo', '')}",
            f"Contact créé: {contact['uuid'][:8]} {contact.get('plena_nomo', '')}",
        ))
    except Exception as e:
        error(tr_multi(
            f"Eraro dum kreado de kontakto: {e}",
            f"Error creating contact: {e}",
            f"Erreur lors de la création du contact: {e}",
        ))
        raise typer.Exit(1)


@kontakto.command("modifi")
def kontakto_modifi(
    uuid: str = typer.Argument(..., help="Contact UUID"),
    nomo: str = typer.Option("", "--nomo", "-n", help="Given name"),
    familia_nomo: str = typer.Option("", "--familia-nomo", "--fn", help="Family name"),
    plena_nomo: str = typer.Option("", "--plena-nomo", "--pn", help="Full name"),
    retposto_opt: str = typer.Option("", "--retposto", "-r", help="Primary email"),
    organizo: str = typer.Option("", "--organizo", "-o", help="Organization"),
    telefono: str = typer.Option("", "--telefono", "-t", help="Phone number"),
    noto: str = typer.Option("", "--noto", "-N", help="Notes"),
    kategorio: str = typer.Option("", "--kategorio", "-k", help="Category"),
) -> None:
    """Modify an existing contact."""
    service = get_kontakto_service()
    existing = service.get(uuid)

    if not existing:
        error(tr_multi(
            f"Kontakto ne trovita: {uuid}",
            f"Contact not found: {uuid}",
            f"Contact non trouvé: {uuid}",
        ))
        raise typer.Exit(1)

    updates: dict = {}
    if nomo:
        updates["nomo"] = nomo
    if familia_nomo:
        updates["familia_nomo"] = familia_nomo
    if plena_nomo:
        updates["plena_nomo"] = plena_nomo
    if retposto_opt:
        updates["retposto"] = retposto_opt
    if organizo:
        updates["organizo"] = organizo
    if telefono:
        updates["telefonnumeroj"] = [{"valoro": telefono, "etikedo": "VOICE", "cxefa": True}]
    if noto:
        updates["noto"] = noto
    if kategorio:
        updates["kategorioj"] = [kategorio]

    if not updates:
        warning(tr_multi(
            "Neniu ŝanĝo provizita.",
            "No changes provided.",
            "Aucun changement fourni.",
        ))
        return

    try:
        updated = service.update(uuid, updates)
        info(tr_multi(
            f"Kontakto ĝisdatigita: {updated['uuid'][:8]}",
            f"Contact updated: {updated['uuid'][:8]}",
            f"Contact mis à jour: {updated['uuid'][:8]}",
        ))
    except Exception as e:
        error(tr_multi(
            f"Eraro dum ĝisdatigo: {e}",
            f"Error updating: {e}",
            f"Erreur lors de la mise à jour: {e}",
        ))
        raise typer.Exit(1)


@kontakto.command("forigi")
def kontakto_forigi(
    uuid: str = typer.Argument(..., help="Contact UUID"),
    permanent: bool = typer.Option(False, "--permanent", "-P", help="Permanent delete"),
) -> None:
    """Delete a contact (soft-delete by default)."""
    service = get_kontakto_service()

    try:
        service.delete(uuid, soft=not permanent)
        info(tr_multi(
            f"Kontakto forigita: {uuid[:8]}",
            f"Contact deleted: {uuid[:8]}",
            f"Contact supprimé: {uuid[:8]}",
        ))
    except Exception as e:
        error(tr_multi(
            f"Eraro dum forigo: {e}",
            f"Error deleting: {e}",
            f"Erreur lors de la suppression: {e}",
        ))
        raise typer.Exit(1)


@kontakto.command("importi")
def kontakto_importi(
    path: str = typer.Argument(..., help="Path to .vcf file"),
) -> None:
    """Import contacts from a VCF file."""
    service = get_kontakto_service()

    try:
        count = service.import_vcf(path)
        info(tr_multi(
            f"Importitaj {count} kontakto(j).",
            f"Imported {count} contact(s).",
            f"{count} contact(s) importé(s).",
        ))
    except ImportError as e:
        error(str(e))
        raise typer.Exit(1)
    except FileNotFoundError:
        error(tr_multi(
            f"Dosiero ne trovita: {path}",
            f"File not found: {path}",
            f"Fichier non trouvé: {path}",
        ))
        raise typer.Exit(1)
    except Exception as e:
        error(tr_multi(
            f"Eraro dum importo: {e}",
            f"Error during import: {e}",
            f"Erreur lors de l'import: {e}",
        ))
        raise typer.Exit(1)


@kontakto.command("eksporti")
def kontakto_eksporti(
    uuid: str = typer.Option("", "--uuid", "-u", help="Export single contact"),
    output: str = typer.Option("", "--output", "-o", help="Output file path"),
) -> None:
    """Export contacts to VCF format."""
    service = get_kontakto_service()

    try:
        uuid_val = uuid if uuid else None
        result = service.export_vcf(uuid=uuid_val, path=output if output else None)

        if not output:
            # Print to stdout
            from rich.markup import escape
            info(escape(result))
        else:
            info(tr_multi(
                f"Eksportita al {output}",
                f"Exported to {output}",
                f"Exporté vers {output}",
            ))
    except ImportError as e:
        error(str(e))
        raise typer.Exit(1)
    except Exception as e:
        error(tr_multi(
            f"Eraro dum eksporto: {e}",
            f"Error during export: {e}",
            f"Erreur lors de l'export: {e}",
        ))
        raise typer.Exit(1)


@kontakto.command("malfermi")
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
        for d in dups:
            if d["uuid"] not in seen:
                duplicates.append((c, dups))
                seen.add(d["uuid"])
        seen.add(cid)

    if not duplicates:
        info(tr_multi(
            "Neniuj duplikatoj trovitaj.",
            "No duplicates found.",
            "Aucun doublon trouvé.",
        ))
        return

    for original, dups in duplicates:
        info(tr_multi(
            f"Ebla duplikato: {original.get('plena_nomo', '?')}",
            f"Possible duplicate: {original.get('plena_nomo', '?')}",
            f"Doublon possible: {original.get('plena_nomo', '?')}",
        ))
        for d in dups:
            info(f"  → {d['uuid'][:8]} {d.get('plena_nomo', '?')}")


# ── Category sub-typer ───────────────────────────────────────────────────────

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
kontakto.add_typer(kategorio_app, name="kategorio")


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
    nomo: str = typer.Argument(..., help="Category name"),
    koloro: str = typer.Option("", "--koloro", "-k", help="Color code"),
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
    uuid: str = typer.Argument(..., help="Category UUID"),
) -> None:
    """Delete a category."""
    service = get_kontakto_service()
    if service.delete_category(uuid):
        info(tr_multi(
            f"Kategorio forigita: {uuid[:8]}",
            f"Category deleted: {uuid[:8]}",
            f"Catégorie supprimée: {uuid[:8]}",
        ))
    else:
        error(tr_multi(
            f"Kategorio ne trovita: {uuid}",
            f"Category not found: {uuid}",
            f"Catégorie non trouvée: {uuid}",
        ))
        raise typer.Exit(1)


__all__ = [
    "app",
    "retposto",
    "kontakto",
    "kategorio_app",
]

"""Kontakto write commands — contact CRUD operations.

Commands registered on kontakto typer: aldoni, modifi, forigi, importi, eksporti
"""

from __future__ import annotations

from typing import Annotated, Any

import typer

from A import error, info, tr_multi, warning
from A_lien.service import get_kontakto_service
from A_lien.utils import normalize_multi_field


def _parse_telefonnumeroj(
    telefonnumeroj: list[str],
) -> list[dict[str, Any]]:
    """Parse phone number strings like 'NUMBER:label[:primary]'."""
    return normalize_multi_field(telefonnumeroj, "telefono")


def _parse_retposhtadresoj(
    retposhtadresoj: list[str],
) -> list[dict[str, Any]]:
    """Parse email strings like 'ADDRESS:label[:primary]'."""
    return normalize_multi_field(retposhtadresoj, "retposhto")


def _parse_kampoj(kampo: list[str]) -> dict[str, str]:
    """Parse custom field strings like 'KEY:VALUE'."""
    kampoj: dict[str, str] = {}
    for kv in kampo:
        if ":" in kv:
            key, _, val = kv.partition(":")
            kampoj[key.strip()] = val.strip()
    return kampoj


def kontakto_aldoni(
    persona_nomo: str = typer.Option(
        "", "--persona-nomo", "-pn",
        help=tr_multi("Persona nomo", "Given name", "Prénom"),
    ),
    nomo: str = typer.Option(
        "", "--nomo", "-n",
        help=tr_multi("Familia nomo", "Family name", "Nom de famille"),
    ),
    organizo: str = typer.Option(
        "", "--organizo", "-o",
        help=tr_multi("Organizo", "Organization", "Organisation"),
    ),
    naskig_dato: str = typer.Option(
        "", "--naskig-dato", "-d",
        help=tr_multi("Naskiĝdato (YYYYMMDD)", "Birthdate (YYYYMMDD)", "Date de naissance (YYYYMMDD)"),
    ),
    naskig_loko: str = typer.Option(
        "", "--naskig-loko", "-L",
        help=tr_multi("Naskiĝloko", "Birthplace", "Lieu de naissance"),
    ),
    lingvoj: str = typer.Option(
        "", "--lingvoj", "-l",
        help=tr_multi("Lingvoj (ekz. en,fr)", "Languages (e.g. en,fr)", "Langues (ex: en,fr)"),
    ),
    organiza_identiga_numero: str = typer.Option(
        "", "--organiza-identiga-numero", "-I",
        help=tr_multi(
            "Organiza identiga numero",
            "Organization ID number",
            "Numéro d'identification de l'organisation",
        ),
    ),
    telefonnumeroj: list[str] = typer.Option(
        [], "--telefonnumero", "-t",
        help=tr_multi(
            "Ripeti telefonnumeron: NOMO:etikedo[:prima]",
            "Repeat phone: NUMBER:label[:primary]",
            "Répéter téléphone: NUMÉRO:étiquette[:principal]",
        ),
    ),
    retposhtadresoj: list[str] = typer.Option(
        [], "--retposhtadreso",
        help=tr_multi(
            "Ripeti retpoŝton: ADRESO:etikedo[:prima]",
            "Repeat email: ADDRESS:label[:primary]",
            "Répéter email: ADRESSE:étiquette[:principal]",
        ),
    ),
    postadreso: str = typer.Option(
        "", "--postadreso", "-p",
        help=tr_multi("Poŝtadreso", "Postal address", "Adresse postale"),
    ),
    postkodo: str = typer.Option(
        "", "--poŝtkodo", "-pk",
        help=tr_multi("Poŝtkodo", "Postcode", "Code postal"),
    ),
    kampo: list[str] = typer.Option(
        [], "--kampo", "-c",
        help=tr_multi(
            "Propra kampo KEY:VALUE (ripetebla)",
            "Custom field KEY:value (repeatable)",
            "Champ personnalisé KEY:VALUE (répétable)",
        ),
    ),
    noto: str = typer.Option(
        "", "--noto", "-N",
        help=tr_multi("Notoj", "Notes", "Notes"),
    ),
    kategorio: list[str] = typer.Option(
        [], "--kategorio", "-k",
        help=tr_multi("Kategorio (ripetebla)", "Category (repeatable)", "Catégorie (répétable)"),
    ),
    konfirmita: int = typer.Option(
        1, "--konfirmita", "-K",
        help=tr_multi("Ĉu konfirmita (0/1)", "Whether confirmed (0/1)", "Confirmé ou non (0/1)"),
    ),
) -> None:
    """Add a new contact."""
    service = get_kontakto_service()

    if not persona_nomo and not nomo:
        error(tr_multi(
            "Bezonata persona nomo aŭ familia nomo.",
            "Given name or family name required.",
            "Prénom ou nom requis.",
        ))
        raise typer.Exit(1)

    # Auto-construct full name from given + family name
    parts = [p for p in (persona_nomo, nomo) if p]
    plena_nomo = " ".join(parts)

    data: dict[str, Any] = {
        "nomo": persona_nomo,
        "familia_nomo": nomo,
        "plena_nomo": plena_nomo,
        "organizo": organizo,
        "noto": noto,
    }

    if naskig_dato:
        data["naskigx_dato"] = naskig_dato
    if naskig_loko:
        data["naskigx_loko"] = naskig_loko
    if lingvoj:
        data["lingvoj"] = [l.strip() for l in lingvoj.split(",") if l.strip()]
    if organiza_identiga_numero:
        data["organiza_identiga_numero"] = organiza_identiga_numero
    if postadreso:
        data["postadreso"] = postadreso
    if postkodo:
        data["postkodo"] = postkodo
    if telefonnumeroj:
        data["telefonnumeroj"] = _parse_telefonnumeroj(telefonnumeroj)
    if retposhtadresoj:
        parsed = _parse_retposhtadresoj(retposhtadresoj)
        data["retposhtadresoj"] = parsed
        # Extract primary email for retposto column
        primary = next((a["valoro"] for a in parsed if a.get("cxefa")), parsed[0]["valoro"])
        data["retposto"] = primary
    if kampo:
        parsed = _parse_kampoj(kampo)
        if parsed:
            data["kampoj"] = parsed
    if kategorio:
        data["kategorioj"] = kategorio
    if konfirmita is not None:
        data["konfirmita"] = konfirmita

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


def kontakto_modifi(
    uuid: str = typer.Argument(
        ..., help=tr_multi("Kontakto UUID", "Contact UUID", "UUID contact")
    ),
    persona_nomo: str = typer.Option(
        "", "--persona-nomo", "-pn",
        help=tr_multi("Persona nomo", "Given name", "Prénom"),
    ),
    nomo: str = typer.Option(
        "", "--nomo", "-n",
        help=tr_multi("Familia nomo", "Family name", "Nom de famille"),
    ),
    organizo: str = typer.Option(
        "", "--organizo", "-o",
        help=tr_multi("Organizo", "Organization", "Organisation"),
    ),
    telefonnumeroj: list[str] = typer.Option(
        [], "--telefonnumero", "-t",
        help=tr_multi(
            "Ripeti telefonnumeron: NOMO:etikedo[:prima]",
            "Repeat phone: NUMBER:label[:primary]",
            "Répéter téléphone: NUMÉRO:étiquette[:principal]",
        ),
    ),
    retposhtadresoj: list[str] = typer.Option(
        [], "--retposhtadreso",
        help=tr_multi(
            "Ripeti retpoŝton: ADRESO:etikedo[:prima]",
            "Repeat email: ADDRESS:label[:primary]",
            "Répéter email: ADRESSE:étiquette[:principal]",
        ),
    ),
    postadreso: str = typer.Option(
        "", "--postadreso", "-p",
        help=tr_multi("Poŝtadreso", "Postal address", "Adresse postale"),
    ),
    postkodo: str = typer.Option(
        "", "--poŝtkodo", "-pk",
        help=tr_multi("Poŝtkodo", "Postcode", "Code postal"),
    ),
    noto: str = typer.Option(
        "", "--noto", "-N",
        help=tr_multi("Notoj", "Notes", "Notes"),
    ),
    kategorio: list[str] = typer.Option(
        [], "--kategorio", "-k",
        help=tr_multi("Kategorio (ripetebla)", "Category (repeatable)", "Catégorie (répétable)"),
    ),
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

    updates: dict[str, Any] = {}
    if persona_nomo:
        updates["nomo"] = persona_nomo
        # Rebuild plena_nomo if given name changes
        current_family = existing.get("familia_nomo", "")
        updates["plena_nomo"] = f"{persona_nomo} {current_family}".strip()
    if nomo:
        updates["familia_nomo"] = nomo
        # Rebuild plena_nomo if family name changes
        current_given = updates.get("nomo") or existing.get("nomo", "")
        updates["plena_nomo"] = f"{current_given} {nomo}".strip()
    if organizo:
        updates["organizo"] = organizo
    if telefonnumeroj:
        updates["telefonnumeroj"] = _parse_telefonnumeroj(telefonnumeroj)
    if retposhtadresoj:
        parsed = _parse_retposhtadresoj(retposhtadresoj)
        updates["retposhtadresoj"] = parsed
        primary = next((a["valoro"] for a in parsed if a.get("cxefa")), parsed[0]["valoro"])
        updates["retposto"] = primary
    if postadreso:
        updates["postadreso"] = postadreso
    if postkodo:
        updates["postkodo"] = postkodo
    if noto:
        updates["noto"] = noto
    if kategorio:
        updates["kategorioj"] = kategorio

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


def kontakto_forigi(
    uuids: Annotated[list[str], typer.Argument(
        ..., help=tr_multi(
            "Kontakto UUID (pluraj)",
            "Contact UUIDs (multiple)",
            "UUIDs des contacts (plusieurs)",
        ),
    )],
    permanent: bool = typer.Option(
        False, "--permanenta", "-P",
        help=tr_multi("Definitiva forigo", "Permanent delete", "Suppression permanente"),
    ),
) -> None:
    """Delete contacts (soft-delete by default)."""
    service = get_kontakto_service()
    successes = 0
    for uid in uuids:
        try:
            service.delete(uid, soft=not permanent)
            successes += 1
        except Exception as e:
            error(tr_multi(
                f"Eraro dum forigo de {uid[:8]}: {e}",
                f"Error deleting {uid[:8]}: {e}",
                f"Erreur lors de la suppression de {uid[:8]}: {e}",
            ))
    if successes:
        info(tr_multi(
            f"{successes} kontakto(j) forigitaj",
            f"{successes} contact(s) deleted",
            f"{successes} contact(s) supprimé(s)",
        ))
    else:
        raise typer.Exit(1)


def kontakto_importi(
    path: str = typer.Argument(
        ...,
        help=tr_multi("Vojo al .vcf dosiero", "Path to .vcf file", "Chemin vers fichier .vcf"),
    ),
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


def kontakto_eksporti(
    uuid: str = typer.Option(
        "", "--uuid", "-u",
        help=tr_multi("Eksporti unu kontakton", "Export single contact", "Exporter un contact"),
    ),
    output: str = typer.Option(
        "", "--eligo", "-o",
        help=tr_multi("Eliga dosiera vojo", "Output file path", "Chemin de sortie"),
    ),
) -> None:
    """Export contacts to VCF format."""
    service = get_kontakto_service()

    try:
        uuid_val = uuid if uuid else None
        result = service.export_vcf(uuid=uuid_val, path=output if output else None)

        if not output:
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


__all__ = [
    "kontakto_aldoni",
    "kontakto_modifi",
    "kontakto_forigi",
    "kontakto_importi",
    "kontakto_eksporti",
]

"""Kontakto write commands — contact CRUD operations.

Commands registered on kontakto typer: aldoni, modifi, forigi, importi, eksporti
"""

from __future__ import annotations

from typing import Annotated, Any

import typer

from A import error, info, tr_multi, warning
from A_lien.service import get_kontakto_service
from A_lien.utils import normalize_multi_field, split_full_name


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
    nomo: str = typer.Option(
        "", "--nomo", "-n",
        help=tr_multi("Persona nomo", "Given name", "Prénom"),
    ),
    familia_nomo: str = typer.Option(
        "", "--familia-nomo", "--fn",
        help=tr_multi("Familia nomo", "Family name", "Nom de famille"),
    ),
    plena_nomo: str = typer.Option(
        "", "--plena-nomo", "--pn",
        help=tr_multi("Plena nomo", "Full name", "Nom complet"),
    ),
    retposto_opt: str = typer.Option(
        "", "--retposto", "-r",
        help=tr_multi("Ĉefa retpoŝto", "Primary email", "Email principal"),
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

    data: dict[str, Any] = {
        "nomo": nomo,
        "familia_nomo": familia_nomo,
        "plena_nomo": plena_nomo,
        "retposto": retposto_opt,
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
    if telefonnumeroj:
        data["telefonnumeroj"] = _parse_telefonnumeroj(telefonnumeroj)
    if retposhtadresoj:
        data["retposhtadresoj"] = _parse_retposhtadresoj(retposhtadresoj)
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
    nomo: str = typer.Option(
        "", "--nomo", "-n",
        help=tr_multi("Persona nomo", "Given name", "Prénom"),
    ),
    familia_nomo: str = typer.Option(
        "", "--familia-nomo", "--fn",
        help=tr_multi("Familia nomo", "Family name", "Nom de famille"),
    ),
    plena_nomo: str = typer.Option(
        "", "--plena-nomo", "--pn",
        help=tr_multi("Plena nomo", "Full name", "Nom complet"),
    ),
    retposto_opt: str = typer.Option(
        "", "--retposto", "-r",
        help=tr_multi("Ĉefa retpoŝto", "Primary email", "Email principal"),
    ),
    organizo: str = typer.Option(
        "", "--organizo", "-o",
        help=tr_multi("Organizo", "Organization", "Organisation"),
    ),
    telefono: str = typer.Option(
        "", "--telefono", "-t",
        help=tr_multi("Telefonnumero", "Phone number", "Téléphone"),
    ),
    noto: str = typer.Option(
        "", "--noto", "-N",
        help=tr_multi("Notoj", "Notes", "Notes"),
    ),
    kategorio: str = typer.Option(
        "", "--kategorio", "-k",
        help=tr_multi("Kategorio", "Category", "Catégorie"),
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
        updates["telefonnumeroj"] = [{
            "valoro": telefono, "etikedo": "VOICE", "cxefa": True,
        }]
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


def kontakto_forigi(
    uuids: Annotated[list[str], typer.Argument(
        ..., help=tr_multi(
            "Kontakto UUID (pluraj)",
            "Contact UUIDs (multiple)",
            "UUIDs des contacts (plusieurs)",
        ),
    )],
    permanent: bool = typer.Option(
        False, "--permanent", "-P",
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
        "", "--output", "-o",
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

from __future__ import annotations
"""Konton sub-typer — email account management.

Commands: ls, vidi, aldoni, forigi, modifi
"""


from typing import Annotated, Any

import typer

from A import confirm_action, error, info, tr_multi, warning
from A_lien.service import get_retposto_service

konton = typer.Typer(
    name="konton",
    help=tr_multi(
        "Administri retpoŝtajn kontojn.",
        "Manage email accounts.",
        "Gérer les comptes email.",
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help", "--helpo"]},
)


def _resolve_account(svc: Any, uuid: str) -> dict[str, Any] | None:
    """Resolve an account by exact UUID or prefix. Returns None if not found."""
    account = svc.get_account(uuid)
    if account:
        return account
    matches = svc.find_by_uuid_prefix(uuid)
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        error(tr_multi(
            f"UUID '{uuid}' kongruas kun pluraj kontoj: "
            + ", ".join(m["retposto"] for m in matches),
            f"UUID '{uuid}' matches multiple accounts: "
            + ", ".join(m["retposto"] for m in matches),
            f"L'UUID '{uuid}' correspond à plusieurs comptes: "
            + ", ".join(m["retposto"] for m in matches),
        ))
        raise typer.Exit(1)
    error(tr_multi(
        f"Konto ne trovita: {uuid}",
        f"Account not found: {uuid}",
        f"Compte non trouvé: {uuid}",
    ))
    raise typer.Exit(1)


@konton.command("ls")
def konton_ls() -> None:
    """List email accounts."""
    service = get_retposto_service()
    accounts = service.list_accounts()

    if not accounts:
        info(tr_multi(
            "Neniuj kontoj.",
            "No accounts.",
            "Aucun compte.",
        ))
        return

    for a in accounts:
        name = a.get("nomo", "") or a.get("retposto", "")
        email = a.get("retposto", "")
        has_pw = (
            tr_multi("(jes)", "(yes)", "(oui)")
            if service.get_password(a["uuid"])
            else tr_multi("(ne)", "(no)", "(non)")
        )
        info(f"  {a['uuid'][:8]}  {name} — {email}  ŝlosilo:{has_pw}")


@konton.command("vidi")
def konton_vidi(
    uuid: str = typer.Argument(
        ..., help=tr_multi("Konto UUID", "Account UUID", "UUID compte")
    ),
) -> None:
    """View account details (password not shown)."""
    service = get_retposto_service()
    account = _resolve_account(service, uuid)

    info(f"  UUID: {account['uuid']}")
    info(f"  Nomo: {account.get('nomo', '')}")
    info(f"  Retpoŝto: {account.get('retposto', '')}")
    info(f"  IMAP: {account.get('imap_servilo', '')}:{account.get('imap_haveno', '993')}")
    info(f"  SMTP: {account.get('smtp_servilo', '')}:{account.get('smtp_haveno', '587')}")
    has_pw = service.get_password(account["uuid"]) is not None
    info(tr_multi(
        f"  Pasvorto: {'konservita' if has_pw else 'mankas'}",
        f"  Password: {'stored' if has_pw else 'missing'}",
        f"  Mot de passe: {'stocké' if has_pw else 'manquant'}",
    ))
    if account.get("subskribo"):
        info(f"  Subskribo: {account['subskribo']}")


@konton.command("aldoni")
def konton_aldoni(
    retposto: str = typer.Option(
        ..., "--retposto", "-r",
        help=tr_multi("Retpoŝta adreso", "Email address", "Adresse email"),
    ),
    nomo: str = typer.Option(
        "", "--nomo", "-n",
        help=tr_multi("Vidiga nomo", "Display name", "Nom d'affichage"),
    ),
    imap_servilo: str = typer.Option(
        "", "--imap-server",
        help=tr_multi("IMAP servilo", "IMAP server", "Serveur IMAP"),
    ),
    imap_haveno: int = typer.Option(
        993, "--imap-port",
        help=tr_multi("IMAP haveno", "IMAP port", "Port IMAP"),
    ),
    smtp_servilo: str = typer.Option(
        "", "--smtp-server",
        help=tr_multi("SMTP servilo", "SMTP server", "Serveur SMTP"),
    ),
    smtp_haveno: int = typer.Option(
        587, "--smtp-port",
        help=tr_multi("SMTP haveno", "SMTP port", "Port SMTP"),
    ),
    password: str = typer.Option(
        ..., "--password", "-p", prompt=True, hide_input=True,
        help=tr_multi("Konto pasvorto", "Account password", "Mot de passe"),
    ),
) -> None:
    """Add a new email account (password stored in system keyring)."""
    service = get_retposto_service()

    # Auto-fill common server patterns if not specified
    domain = retposto.split("@")[-1] if "@" in retposto else ""
    if not imap_servilo:
        imap_servilo = f"imap.{domain}" if domain else ""
    if not smtp_servilo:
        smtp_servilo = f"smtp.{domain}" if domain else ""

    if not imap_servilo or not smtp_servilo:
        error(tr_multi(
            "Ne eble aŭtomate detekti servilojn. Bonvolu specifii ilin.",
            "Cannot auto-detect servers. Please specify them.",
            "Impossible de détecter les serveurs. Veuillez les spécifier.",
        ))
        raise typer.Exit(1)

    data = {
        "retposto": retposto,
        "nomo": nomo or retposto,
        "imap_servilo": imap_servilo,
        "imap_haveno": imap_haveno,
        "smtp_servilo": smtp_servilo,
        "smtp_haveno": smtp_haveno,
        "ordo": len(service.list_accounts()),
    }

    try:
        account = service.create_account(data, password)
        info(tr_multi(
            f"Konto kreita: {account['uuid'][:8]} {retposto}",
            f"Account created: {account['uuid'][:8]} {retposto}",
            f"Compte créé: {account['uuid'][:8]} {retposto}",
        ))
    except Exception as e:
        error(tr_multi(
            f"Eraro dum kreado de konto: {e}",
            f"Error creating account: {e}",
            f"Erreur lors de la création du compte: {e}",
        ))
        raise typer.Exit(1)


@konton.command("forigi")
def konton_forigi(
    uuids: Annotated[list[str], typer.Argument(
        ...,
        help=tr_multi(
            "Kontoj UUID (pluraj)",
            "Account UUIDs (multiple)",
            "UUIDs des comptes (plusieurs)",
        ),
    )],
    force: bool = typer.Option(
        False,
        "--force", "-f",
        help=tr_multi(
            "Forigi sen konfirmo",
            "Delete without confirmation",
            "Supprimer sans confirmation",
        ),
    ),
) -> None:
    """Delete one or more email accounts and remove passwords from keyring."""
    service = get_retposto_service()

    # Confirmation prompt (unless --force)
    if not force:
        if not confirm_action(tr_multi(
            f"Ĉu vi certas ke vi volas forigi {len(uuids)} konton(j)?",
            f"Are you sure you want to delete {len(uuids)} account(s)?",
            f"Êtes-vous sûr de vouloir supprimer {len(uuids)} compte(s)?",
        )):
            info(tr_multi("Nuligita.", "Cancelled.", "Annulé."))
            raise typer.Exit(0)

    # Execute bulk delete
    results = service.delete_accounts(uuids)
    failures = []

    for r in results:
        if r["success"]:
            info(tr_multi(
                f"Konto forigita: {r['uuid'][:8]}",
                f"Account deleted: {r['uuid'][:8]}",
                f"Compte supprimé: {r['uuid'][:8]}",
            ))
        else:
            failures.append(r)
            error(tr_multi(
                f"Eraro dum forigo de {r['uuid'][:8]}: {r.get('error', '')}",
                f"Error deleting {r['uuid'][:8]}: {r.get('error', '')}",
                f"Erreur lors de la suppression de {r['uuid'][:8]}: {r.get('error', '')}",
            ))

    # Exit with error if any deletions failed
    if failures:
        raise typer.Exit(1)


@konton.command("modifi")
def konton_modifi(
    uuid: str = typer.Argument(
        ..., help=tr_multi("Konto UUID", "Account UUID", "UUID compte")
    ),
    retposto: str = typer.Option(
        "", "--retposto", "-r",
        help=tr_multi("Retpoŝta adreso", "Email address", "Adresse email"),
    ),
    nomo: str = typer.Option(
        "", "--nomo", "-n",
        help=tr_multi("Vidiga nomo", "Display name", "Nom d'affichage"),
    ),
    imap_servilo: str = typer.Option(
        "", "--imap-server",
        help=tr_multi("IMAP servilo", "IMAP server", "Serveur IMAP"),
    ),
    imap_haveno: int = typer.Option(
        0, "--imap-port",
        help=tr_multi("IMAP haveno", "IMAP port", "Port IMAP"),
    ),
    smtp_servilo: str = typer.Option(
        "", "--smtp-server",
        help=tr_multi("SMTP servilo", "SMTP server", "Serveur SMTP"),
    ),
    smtp_haveno: int = typer.Option(
        0, "--smtp-port",
        help=tr_multi("SMTP haveno", "SMTP port", "Port SMTP"),
    ),
    password: str = typer.Option(
        "", "--password", "-p",
        help=tr_multi("Nova pasvorto", "New password", "Nouveau mot de passe"),
    ),
) -> None:
    """Modify an existing email account."""
    service = get_retposto_service()
    existing = _resolve_account(service, uuid)

    # Build updates dict (only non-empty values)
    updates: dict[str, Any] = {}
    if retposto:
        updates["retposto"] = retposto
    if nomo:
        updates["nomo"] = nomo
    if imap_servilo:
        updates["imap_servilo"] = imap_servilo
    if imap_haveno:
        updates["imap_haveno"] = imap_haveno
    if smtp_servilo:
        updates["smtp_servilo"] = smtp_servilo
    if smtp_haveno:
        updates["smtp_haveno"] = smtp_haveno

    # Password needs special handling (keyring)
    pw = password if password else None

    if not updates and pw is None:
        warning(tr_multi(
            "Neniu ŝanĝo provizita.",
            "No changes provided.",
            "Aucun changement fourni.",
        ))
        return

    # Use the actual UUID (not the input prefix)
    actual_uuid = existing["uuid"]

    try:
        account = service.update_account(actual_uuid, updates, pw)
        info(tr_multi(
            f"Konto ĝisdatigita: {uuid[:8]}",
            f"Account updated: {uuid[:8]}",
            f"Compte mis à jour: {uuid[:8]}",
        ))
    except Exception as e:
        error(tr_multi(
            f"Eraro dum ĝisdatigo: {e}",
            f"Error updating: {e}",
            f"Erreur lors de la mise à jour: {e}",
        ))
        raise typer.Exit(1)


__all__ = [
    "konton",
    "konton_ls",
    "konton_vidi",
    "konton_aldoni",
    "konton_forigi",
    "konton_modifi",
    "_resolve_account",
]

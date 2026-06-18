"""CLI for lien command (retposto, kontakto)."""

from __future__ import annotations

import json
from typing import Any, Optional, Annotated

import typer

from A import error, info, tr_multi, warning

from A_lien.service import get_kontakto_service, get_retposto_service
from A_lien.sieve import get_sieve_manager, validate_sieve

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

# Account management subcommand
konton = typer.Typer(
    name="konton",
    help=tr_multi(
        "Administri retpoŝtajn kontojn.",
        "Manage email accounts.",
        "Gérer les comptes email.",
    ),
    no_args_is_help=False,
    context_settings={"help_option_names": ["-h", "--help", "--helpo"]},
)
retposto.add_typer(konton, name="konton")

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
# konton subcommands — account management
# ══════════════════════════════════════════════════════════════════════════════════════


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
        has_pw = tr_multi("(jes)", "(yes)", "(oui)") if service.get_password(a["uuid"]) else tr_multi("(ne)", "(no)", "(non)")
        info(f"  {a['uuid'][:8]}  {name} — {email}  ŝlosilo:{has_pw}")


@konton.command("vidi")
def konton_vidi(
    uuid: str = typer.Argument(..., help=tr_multi("Konto UUID", "Account UUID", "UUID compte")),
) -> None:
    """View account details (password not shown)."""
    service = get_retposto_service()
    
    # Try exact match first, then prefix match
    account = service.get_account(uuid)
    if not account:
        matches = service.find_by_uuid_prefix(uuid)
        if len(matches) == 1:
            account = matches[0]
        elif len(matches) > 0:
            error(tr_multi(
                f"UUID '{uuid}' kongruas kun pluraj kontoj: " + ", ".join(m["uuid"] for m in matches),
                f"UUID '{uuid}' matches multiple accounts: " + ", ".join(m["uuid"] for m in matches),
                f"L'UUID '{uuid}' correspond à plusieurs comptes: " + ", ".join(m["uuid"] for m in matches),
            ))
            raise typer.Exit(1)
        else:
            error(tr_multi(
                f"Konto ne trovita: {uuid}",
                f"Account not found: {uuid}",
                f"Compte non trouvé: {uuid}",
            ))
            raise typer.Exit(1)

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
    retposto: str = typer.Option(..., "--retposto", "-r", help=tr_multi("Retpoŝta adreso", "Email address", "Adresse email")),
    nomo: str = typer.Option("", "--nomo", "-n", help=tr_multi("Vidiga nomo", "Display name", "Nom d'affichage")),
    imap_servilo: str = typer.Option("", "--imap-server", help=tr_multi("IMAP servilo", "IMAP server", "Serveur IMAP")),
    imap_haveno: int = typer.Option(993, "--imap-port", help=tr_multi("IMAP haveno", "IMAP port", "Port IMAP")),
    smtp_servilo: str = typer.Option("", "--smtp-server", help=tr_multi("SMTP servilo", "SMTP server", "Serveur SMTP")),
    smtp_haveno: int = typer.Option(587, "--smtp-port", help=tr_multi("SMTP haveno", "SMTP port", "Port SMTP")),
    password: str = typer.Option(..., "--password", "-p", prompt=True, hide_input=True, help=tr_multi("Konto pasvorto", "Account password", "Mot de passe")),
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
        "--force",
        "-f",
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
        typer.confirm(tr_multi(
            f"Ĉu vi certas ke vi volas forigi {len(uuids)} konton(j)?",
            f"Are you sure you want to delete {len(uuids)} account(s)?",
            f"Êtes-vous sûr de vouloir supprimer {len(uuids)} compte(s)?",
        ), abort=True)

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
    uuid: str = typer.Argument(..., help=tr_multi("Konto UUID", "Account UUID", "UUID compte")),
    retposto: str = typer.Option("", "--retposto", "-r", help=tr_multi("Retpoŝta adreso", "Email address", "Adresse email")),
    nomo: str = typer.Option("", "--nomo", "-n", help=tr_multi("Vidiga nomo", "Display name", "Nom d'affichage")),
    imap_servilo: str = typer.Option("", "--imap-server", help=tr_multi("IMAP servilo", "IMAP server", "Serveur IMAP")),
    imap_haveno: int = typer.Option(0, "--imap-port", help=tr_multi("IMAP haveno", "IMAP port", "Port IMAP")),
    smtp_servilo: str = typer.Option("", "--smtp-server", help=tr_multi("SMTP servilo", "SMTP server", "Serveur SMTP")),
    smtp_haveno: int = typer.Option(0, "--smtp-port", help=tr_multi("SMTP haveno", "SMTP port", "Port SMTP")),
    password: str = typer.Option("", "--password", "-p", help=tr_multi("Nova pasvorto", "New password", "Nouveau mot de passe")),
) -> None:
    """Modify an existing email account."""
    service = get_retposto_service()

    # Try exact match first, then prefix match
    existing = service.get_account(uuid)
    if not existing:
        matches = service.find_by_uuid_prefix(uuid)
        if len(matches) == 1:
            existing = matches[0]
        elif len(matches) > 0:
            error(tr_multi(
                f"UUID '{uuid}' kongruas kun pluraj kontoj: " + ", ".join(m["uuid"] for m in matches),
                f"UUID '{uuid}' matches multiple accounts: " + ", ".join(m["uuid"] for m in matches),
                f"L'UUID '{uuid}' correspond à plusieurs comptes: " + ", ".join(m["uuid"] for m in matches),
            ))
            raise typer.Exit(1)
        else:
            error(tr_multi(
                f"Konto ne trovita: {uuid}",
                f"Account not found: {uuid}",
                f"Compte non trouvé: {uuid}",
            ))
            raise typer.Exit(1)

    # Build updates dict (only non-empty values)
    updates: dict = {}
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


# Legacy aliases (deprecated) for backward compatibility
@retposto.command("ls", hidden=True)
def retposto_ls() -> None:
    """[DEPRECATED] Use 'A lien retposto konton ls' instead."""
    konton_ls()


@retposto.command("vidi", hidden=True)
def retposto_vidi(uuid: str = typer.Argument(..., help="Account UUID")) -> None:
    """[DEPRECATED] Use 'A lien retposto konton vidi' instead."""
    konton_vidi(uuid)


@retposto.command("aldoni-konton", hidden=True)
def retposto_aldoni_konton(
    retposto: str = typer.Option(..., "--retposto", "-r", help="Email address"),
    nomo: str = typer.Option("", "--nomo", "-n", help="Display name"),
    imap_servilo: str = typer.Option("", "--imap-server", help="IMAP server"),
    imap_haveno: int = typer.Option(993, "--imap-port", help="IMAP port"),
    smtp_servilo: str = typer.Option("", "--smtp-server", help="SMTP server"),
    smtp_haveno: int = typer.Option(587, "--smtp-port", help="SMTP port"),
    password: str = typer.Option(..., "--password", "-p", prompt=True, hide_input=True, help="Account password"),
) -> None:
    """[DEPRECATED] Use 'A lien retposto konton aldoni' instead."""
    konton_aldoni(retposto, nomo, imap_servilo, imap_haveno, smtp_servilo, smtp_haveno, password)


@retposto.command("forigi-konton", hidden=True)
def retposto_forigi_konton(
    uuids: Annotated[list[str], typer.Argument(..., help="Account UUIDs")],
) -> None:
    """[DEPRECATED] Use 'A lien retposto konton forigi' instead."""
    konton_forigi(uuids=uuids)


@retposto.command("preni")
def retposto_preni(
    account: str = typer.Option("", "--account", "-a", help=tr_multi("Specifa konto UUID", "Specific account UUID", "UUID compte spécifique")),
    all_accounts: bool = typer.Option(False, "--all", help=tr_multi("Sinkronigi ĉiujn kontojn", "Sync all accounts", "Synchroniser tous les comptes")),
) -> None:
    """Fetch mail from accounts."""
    svc = get_retposto_service()

    if account:
        uuids = [account]
    else:
        uuids = [a["uuid"] for a in svc.list_accounts()]
        if not uuids:
            info(tr_multi(
                "Neniuj kontoj. Aldonu unue per 'aldoni-konton'.",
                "No accounts. Add one with 'aldoni-konton'.",
                "Aucun compte. Ajoutez-en un avec 'aldoni-konton'.",
            ))
            return

    if len(uuids) == 1:
        info(tr_multi("Prenas mesaĝojn...", "Fetching messages...", "Récupération..."))
        try:
            result = svc.sync_account(uuids[0])
            _report_sync(result)
        except Exception as e:
            error(str(e))
            raise typer.Exit(1)
    else:
        info(tr_multi(
            f"Prenas mesaĝojn el {len(uuids)} kontoj...",
            f"Fetching from {len(uuids)} accounts...",
            f"Récupération de {len(uuids)} comptes...",
        ))
        results = svc.sync_all()
        for uid, result in results.items():
            info(f"  {uid[:8]}: ", nl=False)
            _report_sync(result)


def _report_sync(result: Any) -> None:
    """Print sync result summary."""
    parts = [tr_multi(f"{result.total} entute", f"{result.total} total", f"{result.total} total")]
    if result.new:
        parts.append(tr_multi(f"{result.new} novaj", f"{result.new} new", f"{result.new} nouveaux"))
    if result.errors:
        parts.append(tr_multi(f"{len(result.errors)} eraroj", f"{len(result.errors)} errors", f"{len(result.errors)} erreurs"))
    info(", ".join(parts))
    for err in result.errors[:3]:
        warning(f"  {err}")


@retposto.command("sendi")
def retposto_sendi(
    to: str = typer.Option(..., "--to", "-t", help=tr_multi("Ricevinto (punktokomo-separita)", "Recipient (comma-separated)", "Destinataire (séparé par;)")),
    subject: str = typer.Option("", "--subject", "-s", help=tr_multi("Temeto", "Subject", "Sujet")),
    body: str = typer.Option("", "--body", "-b", help=tr_multi("Teksto de la mesaĝo", "Body text", "Corps du texte")),
    cc: str = typer.Option("", "--cc", help=tr_multi("KK (punktokomo-separita)", "CC (comma-separated)", "CC (séparé par;)")),
    account: str = typer.Option("", "--account", "-a", help=tr_multi("Konto UUID", "Account UUID", "UUID compte")),
    attach: list[str] = typer.Option([], "--attach", help=tr_multi("Dosiero algluenda", "File to attach", "Fichier à joindre")),
) -> None:
    """Send an email."""
    svc = get_retposto_service()

    if not account:
        accounts = svc.list_accounts()
        if not accounts:
            error(tr_multi(
                "Neniuj kontoj. Aldonu unue.",
                "No accounts. Add one first.",
                "Aucun compte. Ajoutez-en un d'abord.",
            ))
            raise typer.Exit(1)
        account = accounts[0]["uuid"]

    recipients = [r.strip() for r in to.split(",") if r.strip()]
    cc_list = [r.strip() for r in cc.split(",") if r.strip()] if cc else None

    try:
        svc.send_email(
            account_uuid=account,
            to=recipients,
            subject=subject,
            body=body,
            cc=cc_list,
            attachments=attach or None,
        )
        info(tr_multi(
            f"Mesaĝo sendita al {to}",
            f"Message sent to {to}",
            f"Message envoyé à {to}",
        ))
    except Exception as e:
        error(tr_multi(
            f"Sendado malsukcesis: {e}",
            f"Send failed: {e}",
            f"Échec d'envoi: {e}",
        ))
        raise typer.Exit(1)


@retposto.command("vidi")
def retposto_vidi_mesago(
    uuid: str = typer.Argument(..., help=tr_multi("Mesaĝo UUID", "Message UUID", "UUID message")),
    html: bool = typer.Option(False, "--html", help=tr_multi("Montri HTML", "Show HTML", "Afficher HTML")),
) -> None:
    """View a email by UUID (opens in editor by default)."""
    import os
    import tempfile

    svc = get_retposto_service()
    msg = svc.get_message(uuid)

    if not msg:
        error(tr_multi(
            f"Mesaĝo ne trovita: {uuid}",
            f"Message not found: {uuid}",
            f"Message non trouvé: {uuid}",
        ))
        raise typer.Exit(1)

    # Build email text
    lines = [
        f"From: {msg.get('de', '')}",
        f"To: {msg.get('al', '')}",
        f"Subject: {msg.get('subjekto', '')}",
        f"Date: {msg.get('ricevita_je', '')}",
        f"Priority: {msg.get('prioritato', 5)}",
        f"Read: {'Yes' if msg.get('legita') else 'No'}",
        "-" * 40,
        "",
    ]

    body = msg.get("html_korpo", "") if html else msg.get("korpo", "")
    if not body:
        body = msg.get("korpo", "")
    lines.append(body)

    email_text = "\n".join(lines)

    # Open in editor or print
    editor = os.environ.get("EDITOR", "less")
    if editor in ("less", "more") or "-" in editor:
        info(email_text)
    else:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write(email_text)
            temp_path = f.name
        try:
            os.system(f"{editor} {temp_path}")
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)


@retposto.command("serci")
def retposto_serci(
    query: str = typer.Argument("", help=tr_multi("Serĉa teksto", "Search text", "Texte de recherche")),
    from_addr: str = typer.Option("", "--from", "-f", help=tr_multi("Sendanto", "From sender", "Expéditeur")),
    to: str = typer.Option("", "--to", "-t", help=tr_multi("Ricevinto", "Recipient", "Destinataire")),
    cc: str = typer.Option("", "--cc", help=tr_multi("KK", "CC", "CC")),
    bcc: str = typer.Option("", "--bcc", help=tr_multi("SKK", "BCC", "BCC")),
    subject: str = typer.Option("", "--subject", "-s", help=tr_multi("Temeto", "Subject", "Sujet")),
    body: str = typer.Option("", "--body", "-b", help=tr_multi("Korpo", "Body", "Corps")),
    after: str = typer.Option("", "--after", help=tr_multi("Post dato (YYYYMMDD)", "After date (YYYYMMDD)", "Après date (YYYYMMDD)")),
    before: str = typer.Option("", "--before", help=tr_multi("Antaŭ dato (YYYYMMDD)", "Before date (YYYYMMDD)", "Avant date (YYYYMMDD)")),
    read: bool = typer.Option(False, "--read", help=tr_multi("Legita", "Read", "Lu")),
    unread: bool = typer.Option(False, "--unread", help=tr_multi("Nelegita", "Unread", "Non lu")),
    priority: int = typer.Option(0, "--priority", "-p", help=tr_multi("Prioritato (1-5)", "Priority (1-5)", "Priorité (1-5)")),
    limit: int = typer.Option(50, "--limit", "-l", help=tr_multi("Maksimumaj rezultoj", "Max results", "Résultats max")),
    account: str = typer.Option("", "--account", "-a", help=tr_multi("Konto UUID", "Account UUID", "UUID compte")),
) -> None:
    """Search emails with filters."""
    import json

    svc = get_retposto_service()

    # Build filters
    filters: dict = {}
    if query:
        filters["query"] = query
    if from_addr:
        filters["from"] = from_addr
    if to:
        filters["to"] = to
    if cc:
        filters["cc"] = cc
    if bcc:
        filters["bcc"] = bcc
    if subject:
        filters["subject"] = subject
    if body:
        filters["body"] = body
    if after:
        filters["after"] = after
    if before:
        filters["before"] = before
    if read:
        filters["read"] = True
    if unread:
        filters["read"] = False
    if priority > 0:
        filters["priority"] = priority
    if account:
        filters["account"] = account

    results = svc.search_messages(filters, limit=limit)

    if not results:
        info(tr_multi(
            "Neniuj rezultoj.",
            "No results.",
            "Aucun résultat.",
        ))
        return

    info(tr_multi(
        f"Trovitaj {len(results)} mesaĝo(j):",
        f"Found {len(results)} message(s):",
        f"{len(results)} message(s) trouvé(s):",
    ))

    for m in results:
        read_indicator = tr_multi("legita", "read", "lu") if m.get("legita") else tr_multi("nelegita", "unread", "non lu")
        preview = (m.get("subjekto", "") or "(sen temo)")[:50]
        info(f"  {m['uuid'][:8]}  {read_indicator}: {preview}")


@retposto.command("dosierujoj")
def retposto_dosierujoj(
    account: str = typer.Option(..., "--account", "-a", help=tr_multi("Konto UUID", "Account UUID", "UUID compte")),
) -> None:
    """List IMAP folders for an account."""
    svc = get_retposto_service()
    acct = svc.get_account_with_password(account)
    if not acct or "password" not in acct:
        error(tr_multi(
            "Konto ne trovita aŭ mankas pasvorto.",
            "Account not found or missing password.",
            "Compte non trouvé ou mot de passe manquant.",
        ))
        raise typer.Exit(1)

    from A_lien.imap import IMAPClient
    client = IMAPClient(
        host=acct.get("imap_servilo", ""),
        port=acct.get("imap_haveno", 993),
        use_ssl=acct.get("imap_ssl", 1) == 1,
    )
    try:
        client.connect(
            username=acct.get("imap_uzantonomo", "") or acct.get("retposto", ""),
            password=acct["password"],
        )
        folders = client.list_folders()
        for f in folders:
            info(f"  {f['name']}")
    except Exception as e:
        error(str(e))
        raise typer.Exit(1)
    finally:
        client.disconnect()


@retposto.command("mesagxoj", hidden=True)
def retposto_mesagxoj(
    account: str = typer.Option(..., "--account", "-a", help=tr_multi("Konto UUID", "Account UUID", "UUID compte")),
    folder: str = typer.Option("INBOX", "--folder", "-f", help=tr_multi("Dosieruja nomo", "Folder name", "Nom du dossier")),
    limit: int = typer.Option(20, "--limit", "-l", help=tr_multi("Maksimumaj mesaĝoj", "Max messages", "Messages max")),
) -> None:
    """[DEPRECATED] Use 'A lien retposto serci' instead."""
    warning(tr_multi(
        "Ĉi tiu komando estas eksvalidigita. Uzu 'serci' anstataŭe.",
        "This command is deprecated. Use 'serci' instead.",
        "Cette commande est obsolète. Utilisez 'serci' à la place.",
    ))
    # Still work for compatibility
    svc = get_retposto_service()
    try:
        result = svc.sync_account(account)
        info(tr_multi(
            f"Trovitaj {result.total} mesaĝoj (prenitaj: {result.new} novaj)",
            f"Found {result.total} messages (fetched: {result.new} new)",
            f"Trouvé {result.total} messages (récupérés: {result.new} nouveaux)",
        ))
    except Exception as e:
        error(str(e))
        raise typer.Exit(1)
    svc = get_retposto_service()
    # Fetch from IMAP
    try:
        result = svc.sync_account(account)
        info(tr_multi(
            f"Trovitaj {result.total} mesaĝoj (prenitaj: {result.new} novaj)",
            f"Found {result.total} messages (fetched: {result.new} new)",
            f"Trouvé {result.total} messages (récupérés: {result.new} nouveaux)",
        ))
    except Exception as e:
        error(str(e))
        raise typer.Exit(1)


# ── Signature sub-typer ──────────────────────────────────────────────────────

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
retposto.add_typer(subskribo_app, name="subskribo")


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
        default_tag = tr_multi(" [apriora]", " [default]", " [défaut]") if s.get("apriora") else ""
        info(f"  {s['uuid'][:8]}  {s['nomo']}{html_tag}{default_tag}")
        if preview:
            info(f"         {preview}...")


@subskribo_app.command("aldoni")
def subskribo_aldoni(
    nomo: str = typer.Argument(..., help=tr_multi("Subskribo nomo", "Signature name", "Nom de signature")),
    teksto: str = typer.Option(..., "--teksto", "-t", help=tr_multi("Subskribo teksto", "Signature text", "Texte de signature")),
    estas_html: bool = typer.Option(False, "--html", help=tr_multi("Teksto estas HTML", "Text is HTML", "Texte est HTML")),
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
    uuid: str = typer.Argument(..., help=tr_multi("Subskribo UUID", "Signature UUID", "UUID signature")),
) -> None:
    """Delete a signature."""
    service = get_retposto_service()
    try:
        service.delete_signature(uuid)
        info(tr_multi(
            f"Subskribo forigita: {uuid[:8]}",
            f"Signature deleted: {uuid[:8]}",
            f"Signature supprimée: {uuid[:8]}",
        ))
    except Exception as e:
        error(tr_multi(
            f"Eraro: {e}",
            f"Error: {e}",
            f"Erreur: {e}",
        ))
        raise typer.Exit(1)


# ── Sieve filter sub-typer ───────────────────────────────────────────────────

filtraj_app = typer.Typer(
    name="filtraj",
    help=tr_multi(
        "Administri Sieve-filtrilojn.",
        "Manage Sieve filters.",
        "Gérer les filtres Sieve.",
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help", "--helpo"]},
)
retposto.add_typer(filtraj_app, name="filtraj")


@filtraj_app.command("ls")
def filtraj_ls(
    account: str = typer.Option(..., "--account", "-a", help=tr_multi("Konto UUID", "Account UUID", "UUID compte")),
) -> None:
    """List Sieve scripts on the server."""
    try:
        sieve = get_sieve_manager(account)
        scripts = sieve.list_scripts()
        sieve.disconnect()
    except Exception as e:
        error(str(e))
        raise typer.Exit(1)

    if not scripts:
        info(tr_multi(
            "Neniuj filtriloj sur la servilo.",
            "No filters on the server.",
            "Aucun filtre sur le serveur.",
        ))
        return

    for s in scripts:
        active = tr_multi(" (aktiva)", " (active)", " (actif)") if s["active"] else ""
        info(f"  {s['name']}{active}")


@filtraj_app.command("vidi")
def filtraj_vidi(
    account: str = typer.Option(..., "--account", "-a", help=tr_multi("Konto UUID", "Account UUID", "UUID compte")),
    name: str = typer.Argument(..., help=tr_multi("Skripta nomo", "Script name", "Nom du script")),
) -> None:
    """View a Sieve script from the server."""
    try:
        sieve = get_sieve_manager(account)
        content = sieve.get_script(name)
        sieve.disconnect()
    except Exception as e:
        error(str(e))
        raise typer.Exit(1)

    info(f"--- {name} ---")
    for line in content.splitlines():
        info(f"  {line}")


@filtraj_app.command("aldoni")
def filtraj_aldoni(
    account: str = typer.Option(..., "--account", "-a", help=tr_multi("Konto UUID", "Account UUID", "UUID compte")),
    path: str = typer.Argument(..., help=tr_multi("Vojo al .sieve dosiero", "Path to .sieve file", "Chemin vers fichier .sieve")),
    name: str = typer.Option("", "--name", "-n", help=tr_multi("Skripta nomo (defaŭlte: dosiernomo)", "Script name (default: filename)", "Nom du script (défaut: nom de fichier)")),
    activate: bool = typer.Option(False, "--activate", help=tr_multi("Agordi kiel aktiva post alŝuto", "Set as active after upload", "Définir comme actif après téléchargement")),
) -> None:
    """Upload a Sieve script (validates syntax locally first)."""
    from pathlib import Path as _Path
    sieve_path = _Path(path)

    if not sieve_path.exists():
        error(tr_multi(
            f"Dosiero ne trovita: {path}",
            f"File not found: {path}",
            f"Fichier non trouvé: {path}",
        ))
        raise typer.Exit(1)

    content = sieve_path.read_text(encoding="utf-8")
    script_name = name or sieve_path.name

    # Local syntax validation
    valid, err_msg = validate_sieve(content)
    if not valid:
        error(tr_multi(
            f"Sintaksa eraro en '{script_name}': {err_msg}",
            f"Syntax error in '{script_name}': {err_msg}",
            f"Erreur de syntaxe dans '{script_name}': {err_msg}",
        ))
        raise typer.Exit(1)

    info(tr_multi(
        f"Sintakso validigita por '{script_name}'.",
        f"Syntax validated for '{script_name}'.",
        f"Syntaxe validée pour '{script_name}'.",
    ))

    # Upload to server
    try:
        sieve = get_sieve_manager(account)
        sieve.put_script(script_name, content)
        if activate:
            sieve.activate_script(script_name)
        sieve.disconnect()
    except Exception as e:
        error(str(e))
        raise typer.Exit(1)

    info(tr_multi(
        f"Filtrilo alŝutita: {script_name}",
        f"Filter uploaded: {script_name}",
        f"Filtre téléchargé: {script_name}",
    ))


@filtraj_app.command("forigi")
def filtraj_forigi(
    account: str = typer.Option(..., "--account", "-a", help=tr_multi("Konto UUID", "Account UUID", "UUID compte")),
    name: str = typer.Argument(..., help=tr_multi("Skripta nomo", "Script name", "Nom du script")),
) -> None:
    """Delete a Sieve script from the server."""
    try:
        sieve = get_sieve_manager(account)
        sieve.delete_script(name)
        sieve.disconnect()
    except Exception as e:
        error(str(e))
        raise typer.Exit(1)

    info(tr_multi(
        f"Filtrilo forigita: {name}",
        f"Filter deleted: {name}",
        f"Filtre supprimé: {name}",
    ))


@filtraj_app.command("aktivi")
def filtraj_aktivi(
    account: str = typer.Option(..., "--account", "-a", help=tr_multi("Konto UUID", "Account UUID", "UUID compte")),
    name: str = typer.Argument(..., help=tr_multi("Skripta nomo", "Script name", "Nom du script")),
) -> None:
    """Set a Sieve script as active."""
    try:
        sieve = get_sieve_manager(account)
        sieve.activate_script(name)
        sieve.disconnect()
    except Exception as e:
        error(str(e))
        raise typer.Exit(1)

    info(tr_multi(
        f"Filtrilo aktivigita: {name}",
        f"Filter activated: {name}",
        f"Filtre activé: {name}",
    ))
# ══════════════════════════════════════════════════════════════════════════════

_kontakto_fields_doc = """
Valid contact fields (JSON):
  nomo, familia_nomo, plena_nomo, retposto, organizo,
  noto, naskigx_dato, naskigx_loko, konfirmita,
  lingvoj, telefonnumeroj, retposhtadresoj, kampoj, kategorioj
"""


@kontakto.command("ls")
def kontakto_ls(
    limit: int = typer.Option(50, "--limit", "-l", help=tr_multi("Maksimumaj rezultoj", "Max results", "Résultats max")),
    order_by: str = typer.Option(
        "plena_nomo", "--order", "-o", help=tr_multi("Ordiga kolumno", "Sort column", "Colonne de tri")
    ),
    desc: bool = typer.Option(False, "--desc", "-d", help=tr_multi("Malkreska ordo", "Descending order", "Ordre décroissant")),
) -> None:
    """List all contacts."""
    from A.utils.output import print_table

    service = get_kontakto_service()
    contacts = service.list(order_by=order_by, desc=desc, limit=limit)

    if not contacts:
        info(tr_multi("Neniuj kontaktoj.", "No contacts.", "Aucun contact."))
        return

    # Pre-process: extract primary email (print_table handles other JSON arrays)
    rows = []
    for c in contacts:
        emails = c.get("retposhtadresoj", [])
        primary_email = emails[0].get("valoro", "") if emails and isinstance(emails, list) else ""
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

    print_table(columns, rows, title=tr_multi("Kontaktoj", "Contacts", "Contacts"))


@kontakto.command("serci")
def kontakto_serci(
    query: str = typer.Argument(..., help=tr_multi("Serĉa teksto", "Search text", "Texte de recherche")),
    fuzzy: bool = typer.Option(False, "--fuzzy", "-f", help=tr_multi("Ŝalti fuzzy kongruigon", "Enable fuzzy matching", "Activer correspondance floue")),
    limit: int = typer.Option(50, "--limit", "-l", help=tr_multi("Maksimumaj rezultoj", "Max results", "Résultats max")),
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
    uuid: str = typer.Argument(..., help=tr_multi("Kontakto UUID (aŭ prefikso)", "Contact UUID (or prefix)", "UUID contact (ou préfixe)")),
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


@kontakto.command("aldoni")
def kontakto_aldoni(
    nomo: str = typer.Option("", "--nomo", "-n", help=tr_multi("Persona nomo", "Given name", "Prénom")),
    familia_nomo: str = typer.Option("", "--familia-nomo", "--fn", help=tr_multi("Familia nomo", "Family name", "Nom de famille")),
    plena_nomo: str = typer.Option("", "--plena-nomo", "--pn", help=tr_multi("Plena nomo", "Full name", "Nom complet")),
    retposto_opt: str = typer.Option("", "--retposto", "-r", help=tr_multi("Ĉefa retpoŝto", "Primary email", "Email principal")),
    organizo: str = typer.Option("", "--organizo", "-o", help=tr_multi("Organizo", "Organization", "Organisation")),
    naskig_dato: str = typer.Option("", "--naskig-dato", "-d", help=tr_multi("Naskiĝdato (YYYYMMDD)", "Birthdate (YYYYMMDD)", "Date de naissance (YYYYMMDD)")),
    naskig_loko: str = typer.Option("", "--naskig-loko", "-L", help=tr_multi("Naskiĝloko", "Birthplace", "Lieu de naissance")),
    lingvoj: str = typer.Option("", "--lingvoj", "-l", help=tr_multi("Lingvoj (ekz. en,fr)", "Languages (e.g. en,fr)", "Langues (ex: en,fr)")),
    organiza_identiga_numero: str = typer.Option("", "--organiza-identiga-numero", "-I", help=tr_multi("Organiza identiga numero", "Organization ID number", "Numéro d'identification de l'organisation")),
    telefonnumeroj: list[str] = typer.Option([], "--telefonnumero", "-t", help=tr_multi("Ripeti telefonnumeron: NOMO:etikedo[:prima]", "Repeat phone: NUMBER:label[:primary]", "Répéter téléphone: NUMÉRO:étiquette[:principal]")),
    retposhtadresoj: list[str] = typer.Option([], "--retposhtadreso", help=tr_multi("Ripeti retpoŝton: ADRESO:etikedo[:prima]", "Repeat email: ADDRESS:label[:primary]", "Répéter email: ADRESSE:étiquette[:principal]")),
    postadreso: str = typer.Option("", "--postadreso", "-p", help=tr_multi("Poŝtadreso", "Postal address", "Adresse postale")),
    kampo: list[str] = typer.Option([], "--kampo", "-c", help=tr_multi("Propra kampo KEY:VALUE (ripetebla)", "Custom field KEY:value (repeatable)", "Champ personnalisé KEY:VALUE (répétable)")),
    noto: str = typer.Option("", "--noto", "-N", help=tr_multi("Notoj", "Notes", "Notes")),
    kategorio: list[str] = typer.Option([], "--kategorio", "-k", help=tr_multi("Kategorio (ripetebla)", "Category (repeatable)", "Catégorie (répétable)")),
    konfirmita: int = typer.Option(1, "--konfirmita", "-K", help=tr_multi("Ĉu konfirmita (0/1)", "Whether confirmed (0/1)", "Confirmé ou non (0/1)")),
) -> None:
    """Add a new contact."""
    from A_lien.utils import split_full_name, normalize_multi_field

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

    # Handle optional fields
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

    # Handle repeatable phone numbers: numero:etikedo[:prima]
    if telefonnumeroj:
        data["telefonnumeroj"] = normalize_multi_field(telefonnumeroj, "telefono")

    # Handle repeatable email addresses: adreso:etikedo[:prima]
    if retposhtadresoj:
        data["retposhtadresoj"] = normalize_multi_field(retposhtadresoj, "retposhto")

    # Handle custom fields: KEY:VALUE
    if kampo:
        kampoj = {}
        for kv in kampo:
            if ":" in kv:
                key, _, val = kv.partition(":")
                kampoj[key.strip()] = val.strip()
        if kampoj:
            data["kampoj"] = kampoj

    # Handle categories
    if kategorio:
        data["kategorioj"] = kategorio

    # Handle confirmed flag
    if konfirmita is not None:
        data["konfirmita"] = konfirmita

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
    uuid: str = typer.Argument(..., help=tr_multi("Kontakto UUID", "Contact UUID", "UUID contact")),
    nomo: str = typer.Option("", "--nomo", "-n", help=tr_multi("Persona nomo", "Given name", "Prénom")),
    familia_nomo: str = typer.Option("", "--familia-nomo", "--fn", help=tr_multi("Familia nomo", "Family name", "Nom de famille")),
    plena_nomo: str = typer.Option("", "--plena-nomo", "--pn", help=tr_multi("Plena nomo", "Full name", "Nom complet")),
    retposto_opt: str = typer.Option("", "--retposto", "-r", help=tr_multi("Ĉefa retpoŝto", "Primary email", "Email principal")),
    organizo: str = typer.Option("", "--organizo", "-o", help=tr_multi("Organizo", "Organization", "Organisation")),
    telefono: str = typer.Option("", "--telefono", "-t", help=tr_multi("Telefonnumero", "Phone number", "Téléphone")),
    noto: str = typer.Option("", "--noto", "-N", help=tr_multi("Notoj", "Notes", "Notes")),
    kategorio: str = typer.Option("", "--kategorio", "-k", help=tr_multi("Kategorio", "Category", "Catégorie")),
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
    uuid: str = typer.Argument(..., help=tr_multi("Kontakto UUID", "Contact UUID", "UUID contact")),
    permanent: bool = typer.Option(False, "--permanent", "-P", help=tr_multi("Definitiva forigo", "Permanent delete", "Suppression permanente")),
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
    path: str = typer.Argument(..., help=tr_multi("Vojo al .vcf dosiero", "Path to .vcf file", "Chemin vers fichier .vcf")),
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
    uuid: str = typer.Option("", "--uuid", "-u", help=tr_multi("Eksporti unu kontakton", "Export single contact", "Exporter un contact")),
    output: str = typer.Option("", "--output", "-o", help=tr_multi("Eliga dosiera vojo", "Output file path", "Chemin de sortie")),
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
    nomo: str = typer.Argument(..., help=tr_multi("Kategorinomo", "Category name", "Nom de catégorie")),
    koloro: str = typer.Option("", "--koloro", "-k", help=tr_multi("Kolorkodo", "Color code", "Code couleur")),
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
    uuid: str = typer.Argument(..., help=tr_multi("Kategorio UUID", "Category UUID", "UUID catégorie")),
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

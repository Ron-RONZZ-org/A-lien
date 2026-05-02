"""CLI for lien command (retposto, kontakto)."""

from __future__ import annotations

import json
from typing import Optional

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
# retposto subcommands — account management (Phase 3)
# ══════════════════════════════════════════════════════════════════════════════


@retposto.command("ls")
def retposto_ls() -> None:
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


@retposto.command("vidi")
def retposto_vidi(
    uuid: str = typer.Argument(..., help="Account UUID"),
) -> None:
    """View account details (password not shown)."""
    service = get_retposto_service()
    account = service.get_account(uuid)

    if not account:
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
    has_pw = service.get_password(uuid) is not None
    info(tr_multi(
        f"  Pasvorto: {'konservita' if has_pw else 'mankas'}",
        f"  Password: {'stored' if has_pw else 'missing'}",
        f"  Mot de passe: {'stocké' if has_pw else 'manquant'}",
    ))
    if account.get("subskribo"):
        info(f"  Subskribo: {account['subskribo']}")


@retposto.command("aldoni-konton")
def retposto_aldoni_konton(
    retposto: str = typer.Option(..., "--retposto", "-r", help="Email address"),
    nomo: str = typer.Option("", "--nomo", "-n", help="Display name"),
    imap_servilo: str = typer.Option("", "--imap-server", help="IMAP server"),
    imap_haveno: int = typer.Option(993, "--imap-port", help="IMAP port"),
    smtp_servilo: str = typer.Option("", "--smtp-server", help="SMTP server"),
    smtp_haveno: int = typer.Option(587, "--smtp-port", help="SMTP port"),
    password: str = typer.Option(..., "--password", "-p", prompt=True, hide_input=True, help="Account password"),
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


@retposto.command("forigi-konton")
def retposto_forigi_konton(
    uuid: str = typer.Argument(..., help="Account UUID"),
) -> None:
    """Delete an email account and its password from keyring."""
    service = get_retposto_service()
    try:
        service.delete_account(uuid)
        info(tr_multi(
            f"Konto forigita: {uuid[:8]}",
            f"Account deleted: {uuid[:8]}",
            f"Compte supprimé: {uuid[:8]}",
        ))
    except Exception as e:
        error(tr_multi(
            f"Eraro dum forigo: {e}",
            f"Error deleting: {e}",
            f"Erreur lors de la suppression: {e}",
        ))
        raise typer.Exit(1)


@retposto.command("preni")
def retposto_preni(
    account: str = typer.Option("", "--account", "-a", help="Specific account UUID"),
    all_accounts: bool = typer.Option(False, "--all", help="Sync all accounts"),
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
    to: str = typer.Option(..., "--to", "-t", help="Recipient (comma-separated)"),
    subject: str = typer.Option("", "--subject", "-s", help="Subject"),
    body: str = typer.Option("", "--body", "-b", help="Body text"),
    cc: str = typer.Option("", "--cc", help="CC (comma-separated)"),
    account: str = typer.Option("", "--account", "-a", help="Account UUID"),
    attach: list[str] = typer.Option([], "--attach", help="File to attach"),
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


@retposto.command("dosierujoj")
def retposto_dosierujoj(
    account: str = typer.Option(..., "--account", "-a", help="Account UUID"),
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


@retposto.command("mesagxoj")
def retposto_mesagxoj(
    account: str = typer.Option(..., "--account", "-a", help="Account UUID"),
    folder: str = typer.Option("INBOX", "--folder", "-f", help="Folder name"),
    limit: int = typer.Option(20, "--limit", "-l", help="Max messages"),
) -> None:
    """List recent messages in a folder."""
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
    nomo: str = typer.Argument(..., help="Signature name"),
    teksto: str = typer.Option(..., "--teksto", "-t", help="Signature text"),
    estas_html: bool = typer.Option(False, "--html", help="Text is HTML"),
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
    uuid: str = typer.Argument(..., help="Signature UUID"),
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
    account: str = typer.Option(..., "--account", "-a", help="Account UUID"),
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
    account: str = typer.Option(..., "--account", "-a", help="Account UUID"),
    name: str = typer.Argument(..., help="Script name"),
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
    account: str = typer.Option(..., "--account", "-a", help="Account UUID"),
    path: str = typer.Argument(..., help="Path to .sieve file"),
    name: str = typer.Option("", "--name", "-n", help="Script name (default: filename)"),
    activate: bool = typer.Option(False, "--activate", help="Set as active after upload"),
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
    account: str = typer.Option(..., "--account", "-a", help="Account UUID"),
    name: str = typer.Argument(..., help="Script name"),
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
    account: str = typer.Option(..., "--account", "-a", help="Account UUID"),
    name: str = typer.Argument(..., help="Script name"),
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

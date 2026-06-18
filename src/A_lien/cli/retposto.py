"""Retposto commands — email operations.

Commands: preni, sendi, respondi, plusendi, vidi, forigi, movi, serci, dosierujoj, mesagoj, elsuti
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

import typer

from A import error, info, tr_multi, warning
from A_lien.imap import IMAPClient
from A_lien.service import get_retposto_service


def _resolve_message(svc: Any, prefix: str) -> dict[str, Any]:
    """Resolve a message by exact UUID or unique prefix.

    Tries exact match first, then prefix lookup.
    Handles 0 matches (not found) and multiple (ambiguous).

    Args:
        svc: RetpostoService instance
        prefix: UUID or UUID prefix

    Returns:
        Message dict

    Raises:
        typer.Exit(1) if not found or ambiguous
    """
    # Exact match first
    msg = svc.get_message(prefix)
    if msg:
        return msg

    # Prefix fallback
    matches = svc.find_message_by_uuid_prefix(prefix)

    if len(matches) == 1:
        return matches[0]

    if len(matches) > 1:
        error(tr_multi(
            f"Pluraj mesaĝoj kongruas kun '{prefix}':",
            f"Multiple messages match '{prefix}':",
            f"Plusieurs messages correspondent à '{prefix}':",
        ))
        for m in matches:
            subj = (m.get("subjekto", "") or "(sen temo)")[:50]
            info(f"  {m['uuid'][:8]}  {subj}")
        raise typer.Exit(1)

    error(tr_multi(
        f"Mesaĝo ne trovita: {prefix}",
        f"Message not found: {prefix}",
        f"Message non trouvé: {prefix}",
    ))
    raise typer.Exit(1)

retposto = typer.Typer(
    name="retposto",
    help=tr_multi(
        "Retpoŝto — retpoŝta mikroapo.",
        "Retpoŝto — email microapp.",
        "Retpoŝto — microapp email.",
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help", "--helpo"]},
)


def _report_sync(result: Any, account_label: str = "") -> None:
    """Print sync result summary with optional account context.

    Args:
        result: SyncResult with total, new, errors attributes
        account_label: Account email or label for error context
    """
    prefix = f"[{account_label}] " if account_label else ""
    parts = [
        tr_multi(
            f"{result.total} entute",
            f"{result.total} total",
            f"{result.total} total",
        )
    ]
    if result.new:
        parts.append(tr_multi(
            f"{result.new} novaj",
            f"{result.new} new",
            f"{result.new} nouveaux",
        ))
    if result.errors:
        parts.append(tr_multi(
            f"{len(result.errors)} eraroj",
            f"{len(result.errors)} errors",
            f"{len(result.errors)} erreurs",
        ))
    info(f"{prefix}{', '.join(parts)}")
    for err in result.errors[:3]:
        error(f"  {prefix}{err}")


# ── Mail operations ──────────────────────────────────────────────────────────


@retposto.command("preni")
def retposto_preni(
    account: str = typer.Option(
        "", "--konto", "-k",
        help=tr_multi(
            "Specifa konto UUID, prefikso aŭ retpoŝto",
            "Specific account UUID, prefix or email",
            "UUID, préfixe ou email de compte spécifique",
        ),
    ),
    folder: str = typer.Option(
        "", "--dosierujo", "-f",
        help=tr_multi(
            "Dosieruja nomo (ekz. INBOX; postulas --konto)",
            "Folder name (e.g. INBOX; requires --konto)",
            "Nom du dossier (p. ex. INBOX; nécessite --konto)",
        ),
    ),
    force: bool = typer.Option(
        False, "--deviga", "-d",
        help=tr_multi(
            "Deviga resinkronigo (re- elŝuti ĉiujn mesaĝojn)",
            "Force re-sync (re-download all messages)",
            "Resynchronisation forcée (retélécharger tous les messages)",
        ),
    ),
    debug_imap: bool = typer.Option(
        False, "--debug-imap",
        help=tr_multi(
            "Montri krudajn IMAP-komandojn kaj respondojn",
            "Show raw IMAP commands and responses",
            "Afficher les commandes et réponses IMAP brutes",
        ),
    ),
) -> None:
    """Fetch mail from accounts.

    By default syncs all accounts with passwords.
    Use --konto to sync a single account (by UUID or prefix).
    Use --dosierujo with --konto to sync only a specific folder.
    Use --deviga to re-download all messages (not just new ones).
    """
    # Enable IMAP debug logging globally
    if debug_imap:
        import imaplib
        imaplib.IMAP4.debug = 4  # Max verbosity

    svc = get_retposto_service()

    # --dosierujo without --konto is invalid
    if folder and not account:
        error(tr_multi(
            "--dosierujo postulas --konto",
            "--dosierujo requires --konto",
            "--dosierujo nécessite --konto",
        ))
        raise typer.Exit(1)

    if account:
        # Single account — resolve identifier (UUID, prefix, or email)
        acct = svc.resolve_account(account)
        if not acct:
            error(tr_multi(
                f"Konto ne trovita: {account}",
                f"Account not found: {account}",
                f"Compte non trouvé: {account}",
            ))
            raise typer.Exit(1)
        email = acct.get("retposto", account[:8])
        folder_label = f" [{folder}]" if folder else ""
        info(tr_multi(
            f"Prenas mesaĝojn el {email}{folder_label}...",
            f"Fetching messages from {email}{folder_label}...",
            f"Récupération depuis {email}{folder_label}...",
        ))
        try:
            folders_arg = [folder] if folder else None
            result = svc.sync_account(acct["uuid"], force=force,
                                      folders=folders_arg)
            _report_sync(result, account_label=email)
        except ConnectionError as e:
            error(str(e))
            raise typer.Exit(1)
        except Exception as e:
            error(f"[{email}] {e}")
            raise typer.Exit(1)

        return

    # Default: sync all accounts with passwords
    all_accts = svc.list_accounts()
    sync_accts = [
        a for a in all_accts if svc.get_password(a["uuid"])
    ]

    if not sync_accts:
        info(tr_multi(
            "Neniuj kontoj kun pasvorto. Aldonu unue per 'konton aldoni'.",
            "No accounts with passwords. Add one via 'konton aldoni'.",
            "Aucun compte avec mot de passe. Ajoutez-en un via 'konton aldoni'.",
        ))
        return

    email_map = {a["uuid"]: a["retposto"] for a in all_accts}
    info(tr_multi(
        f"Prenas mesaĝojn el {len(sync_accts)} kontoj...",
        f"Fetching from {len(sync_accts)} accounts...",
        f"Récupération de {len(sync_accts)} comptes...",
    ))
    results = svc.sync_all(force=force)
    for uid, result in results.items():
        email = email_map.get(uid, uid[:8])
        info(f"  {email}: ", nl=False)
        _report_sync(result, account_label=email)


@retposto.command("sendi")
def retposto_sendi(
    to: str = typer.Option(
        ..., "--to", "-t",
        help=tr_multi(
            "Ricevinto (punktokomo-separita)",
            "Recipient (comma-separated)",
            "Destinataire (séparé par;)",
        ),
    ),
    subject: str = typer.Option(
        "", "--subject", "-s",
        help=tr_multi("Temeto", "Subject", "Sujet"),
    ),
    body: str = typer.Option(
        "", "--body", "-b",
        help=tr_multi("Teksto de la mesaĝo", "Body text", "Corps du texte"),
    ),
    dosiero: str | None = typer.Option(
        None, "--dosiero", "-D",
        help=tr_multi(
            "Mesaĝa korpo el dosiero (.txt, .html, .md)",
            "Message body from file (.txt, .html, .md)",
            "Corps du message depuis un fichier (.txt, .html, .md)",
        ),
    ),
    cc: str = typer.Option(
        "", "--cc",
        help=tr_multi(
            "KK (punktokomo-separita)",
            "CC (comma-separated)",
            "CC (séparé par;)",
        ),
    ),
    bcc: str = typer.Option(
        "", "--bcc",
        help=tr_multi(
            "SKK (punktokomo-separita)",
            "BCC (comma-separated)",
            "BCC (séparé par;)",
        ),
    ),
    priority: int = typer.Option(
        3, "--prioritato", "-p",
        help=tr_multi(
            "Prioritato (1-5, 3=neŭtrala)",
            "Priority (1-5, 3=normal)",
            "Priorité (1-5, 3=normale)",
        ),
    ),
    subskribo_opt: str = typer.Option(
        "", "--subskribo",
        help=tr_multi(
            "Subskribo (nomo aŭ UUID; malplena = uzu kontan aprioran)",
            "Signature (name or UUID; empty = use account default)",
            "Signature (nom ou UUID; vide = utiliser celle du compte)",
        ),
    ),
    account: str = typer.Option(
        "", "--konto", "-k",
        help=tr_multi("Konto UUID", "Account UUID", "UUID compte"),
    ),
    attach: list[str] = typer.Option(
        [], "--alglui", "-a",
        help=tr_multi(
            "Dosiero algluenda (ripetebla)",
            "File to attach (repeatable)",
            "Fichier à joindre (répétable)",
        ),
    ),
) -> None:
    """Send an email.

    Provide the message body either inline (--body/-b) or from a
    file (--dosiero/-D), but not both. Supported file formats:
    .txt (plain text), .html (HTML body), .md (Markdown → HTML).
    """
    svc = get_retposto_service()

    # Parse recipients early — needed both for account matching and sending
    recipients = [r.strip() for r in to.split(",") if r.strip()]
    cc_list = [r.strip() for r in cc.split(",") if r.strip()] if cc else None
    bcc_list = [r.strip() for r in bcc.split(",") if r.strip()] if bcc else None

    if account:
        # Resolve by UUID, prefix, or email
        acct = svc.resolve_account(account)
        if not acct:
            error(tr_multi(
                f"Konto ne trovita: {account}",
                f"Account not found: {account}",
                f"Compte non trouvé: {account}",
            ))
            raise typer.Exit(1)
        account = acct["uuid"]
    else:
        accounts = svc.list_accounts()
        if not accounts:
            error(tr_multi(
                "Neniuj kontoj. Aldonu unue.",
                "No accounts. Add one first.",
                "Aucun compte. Ajoutez-en un d'abord.",
            ))
            raise typer.Exit(1)

        # Prefer account that matches recipient domain
        recipient_domains = {r.split("@")[-1].lower() for r in recipients if "@" in r}
        matched = None
        for acct in accounts:
            acct_email = acct.get("retposto", "").lower()
            acct_domain = acct_email.split("@")[-1] if "@" in acct_email else ""
            if acct_domain in recipient_domains:
                matched = acct
                break
        account = (matched or accounts[0])["uuid"]

    # Resolve sender email for success message
    acct_obj = svc.get_account(account)
    _sender_email = acct_obj.get("retposto", account[:8]) if acct_obj else account[:8]

    # ── Resolve body from --dosiero/-D ──────────────────────────────────────
    html_body = ""
    if dosiero and body:
        error(tr_multi(
            "Donu --body AŬ --dosiero, ne ambaŭ.",
            "Provide --body OR --dosiero, not both.",
            "Fournissez --body OU --dosiero, pas les deux.",
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
        content = path.read_text(encoding="utf-8")
        ext = path.suffix.lower()
        if ext == ".html":
            html_body = content
        elif ext == ".md":
            try:
                from A.core.markdown_parser import render_markdown
                html_body = render_markdown(content)
            except ImportError:
                warning(tr_multi(
                    "Markdown analizilo ne havebla. Uzante simplan tekston.",
                    "Markdown parser not available. Falling back to plain text.",
                    "Analyseur Markdown indisponible. Texte brut utilisé.",
                ))
                body = content
        else:
            body = content

    # ── Resolve signature override ─────────────────────────────────────────
    # subskribo_opt: "" (default) → use account default (None sentinel)
    # subskribo_opt: "name" → CLI override
    # User can pass --subskribo " " (single space) to explicitly skip
    subskribo: str | None = None
    if subskribo_opt.strip() == "":
        subskribo = None  # use account default
    elif subskribo_opt.strip() == " ":
        subskribo = ""    # explicit "no signature"
    else:
        subskribo = subskribo_opt  # CLI override

    try:
        svc.send_email(
            account_uuid=account,
            to=recipients,
            subject=subject,
            body=body,
            html_body=html_body,
            cc=cc_list,
            bcc=bcc_list,
            attachments=attach or None,
            priority=priority,
            subskribo=subskribo,
        )
        info(tr_multi(
            f"Mesaĝo sendita al {to} (de: {_sender_email})",
            f"Message sent to {to} (from: {_sender_email})",
            f"Message envoyé à {to} (de: {_sender_email})",
        ))
    except ConnectionError as e:
        error(str(e))
        raise typer.Exit(1)
    except Exception as e:
        error(tr_multi(
            f"Sendado malsukcesis: {e}",
            f"Send failed: {e}",
            f"Échec d'envoi: {e}",
        ))
        raise typer.Exit(1)


# Import and register serci from retposto_search.py
from A_lien.cli.retposto_search import retposto_serci  # noqa: E402
from A_lien.cli.retposto_message_ops import (  # noqa: E402
    retposto_respondi,
    retposto_forigi,
    retposto_movi,
)
from A_lien.cli.retposto_plusendi import retposto_plusendi  # noqa: E402
from A_lien.cli.retposto_vidi import retposto_vidi_mesago  # noqa: E402
from A_lien.cli.retposto_elsuti import retposto_elsuti  # noqa: E402

retposto.command(name="serci")(retposto_serci)
retposto.command(name="respondi")(retposto_respondi)
retposto.command(name="forigi")(retposto_forigi)
retposto.command(name="movi")(retposto_movi)
retposto.command(name="plusendi")(retposto_plusendi)
retposto.command(name="vidi")(retposto_vidi_mesago)
retposto.command(name="elsuti")(retposto_elsuti)


@retposto.command("sinkronigi")
def retposto_sinkronigi() -> None:
    """Sinkronigi flagojn al servilo (legita, forigita).

    Processes the sync backlog — local read/delete flag changes
    that have not yet been synced to the IMAP server are sent now.
    """
    svc = get_retposto_service()
    count = svc.process_sync_backlog()
    if count:
        info(tr_multi(
            f"{count} flago(j) sinkronigitaj al servilo",
            f"{count} flag(s) synced to server",
            f"{count} flag(s) synchronisé(s) au serveur",
        ))
    else:
        info(tr_multi(
            "Neniuj flagoj por sinkronigi",
            "No flags to sync",
            "Aucun flag à synchroniser",
        ))


@retposto.command("dosierujoj")
def retposto_dosierujoj(
    account: str = typer.Option(
        ..., "--konto", "-k",
        help=tr_multi(
            "Konto UUID, prefikso aŭ retpoŝto",
            "Account UUID, prefix or email",
            "UUID, préfixe ou email du compte",
        ),
    ),
) -> None:
    """List IMAP folders for an account."""
    svc = get_retposto_service()
    # Resolve identifier (UUID, prefix, or email) → account dict
    acct = svc.resolve_account(account)
    if not acct:
        error(tr_multi(
            f"Konto ne trovita: {account}",
            f"Account not found: {account}",
            f"Compte non trouvé: {account}",
        ))
        raise typer.Exit(1)
    # Fetch password for IMAP connection
    pw = svc.get_password(acct["uuid"])
    if not pw:
        error(tr_multi(
            f"Pasvorto mankas por konto: {acct.get('retposto', account)}",
            f"Password missing for account: {acct.get('retposto', account)}",
            f"Mot de passe manquant pour le compte: {acct.get('retposto', account)}",
        ))
        raise typer.Exit(1)
    acct["password"] = pw

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
    except ConnectionError as e:
        error(str(e))
        raise typer.Exit(1)
    except Exception as e:
        error(str(e))
        raise typer.Exit(1)
    finally:
        client.disconnect()


@retposto.command("mesagoj", hidden=True)
def retposto_mesagoj(
    account: str = typer.Option(
        ..., "--konto", "-k",
        help=tr_multi(
            "Konto UUID, prefikso aŭ retpoŝto",
            "Account UUID, prefix or email",
            "UUID, préfixe ou email du compte",
        ),
    ),
    folder: str = typer.Option(
        "INBOX", "--dosierujo", "-f",
        help=tr_multi("Dosieruja nomo", "Folder name", "Nom du dossier"),
    ),
    limit: int = typer.Option(
        20, "--limo", "-l",
        help=tr_multi("Maksimumaj mesaĝoj", "Max messages", "Messages max"),
    ),
) -> None:
    """[DEPRECATED] Use 'A lien retposto serci' instead."""
    warning(tr_multi(
        "Ĉi tiu komando estas eksvalidigita. Uzu 'serci' anstataŭe.",
        "This command is deprecated. Use 'serci' instead.",
        "Cette commande est obsolète. Utilisez 'serci' à la place.",
    ))
    svc = get_retposto_service()
    try:
        result = svc.sync_account(account)
        info(tr_multi(
            f"Trovitaj {result.total} mesaĝoj (prenitaj: {result.new} novaj)",
            f"Found {result.total} messages (fetched: {result.new} new)",
            f"Trouvé {result.total} messages (récupérés: {result.new} nouveaux)",
        ))
    except ConnectionError as e:
        error(str(e))
        raise typer.Exit(1)
    except Exception as e:
        error(str(e))
        raise typer.Exit(1)



__all__ = [
    "retposto",
    "_report_sync",
    "retposto_preni",
    "retposto_sendi",
    "retposto_vidi_mesago",
    "retposto_serci",
    "retposto_dosierujoj",
    "retposto_mesagoj",
]

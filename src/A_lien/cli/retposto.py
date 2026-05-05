"""Retposto commands — email operations.

Commands: preni, sendi, vidi, serci, dosierujoj, mesagoj
"""

from __future__ import annotations

import json
import os
import tempfile
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
        warning(f"  {prefix}{err}")


# ── Mail operations ──────────────────────────────────────────────────────────


@retposto.command("preni")
def retposto_preni(
    account: str = typer.Option(
        "", "--konto", "-a",
        help=tr_multi(
            "Specifa konto UUID aŭ prefikso",
            "Specific account UUID or prefix",
            "UUID ou préfixe de compte spécifique",
        ),
    ),
) -> None:
    """Fetch mail from accounts.

    By default syncs all accounts with passwords.
    Use --konto to sync a single account (by UUID or prefix).
    """
    svc = get_retposto_service()

    if account:
        # Single account — resolve UUID prefix
        acct = svc.get_account(account)
        if not acct:
            from A_lien.cli.konton import _resolve_account

            acct = _resolve_account(svc, account)
        email = acct.get("retposto", account[:8])
        info(tr_multi(
            f"Prenas mesaĝojn el {email}...",
            f"Fetching messages from {email}...",
            f"Récupération depuis {email}...",
        ))
        try:
            result = svc.sync_account(acct["uuid"])
            _report_sync(result, account_label=email)
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
    results = svc.sync_all()
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
    cc: str = typer.Option(
        "", "--cc",
        help=tr_multi(
            "KK (punktokomo-separita)",
            "CC (comma-separated)",
            "CC (séparé par;)",
        ),
    ),
    account: str = typer.Option(
        "", "--konto", "-a",
        help=tr_multi("Konto UUID", "Account UUID", "UUID compte"),
    ),
    attach: list[str] = typer.Option(
        [], "--alglui",
        help=tr_multi(
            "Dosiero algluenda",
            "File to attach",
            "Fichier à joindre",
        ),
    ),
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
    uuid: str = typer.Argument(
        ..., help=tr_multi("Mesaĝo UUID", "Message UUID", "UUID message")
    ),
    html: bool = typer.Option(
        False, "--html",
        help=tr_multi("Montri HTML", "Show HTML", "Afficher HTML"),
    ),
) -> None:
    """View a email by UUID or prefix (opens in editor by default)."""
    svc = get_retposto_service()
    msg = _resolve_message(svc, uuid)

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


# Import and register serci from retposto_search.py
from A_lien.cli.retposto_search import retposto_serci  # noqa: E402
retposto.command(name="serci")(retposto_serci)


@retposto.command("dosierujoj")
def retposto_dosierujoj(
    account: str = typer.Option(
        ..., "--konto", "-a",
        help=tr_multi("Konto UUID", "Account UUID", "UUID compte"),
    ),
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


@retposto.command("mesagoj", hidden=True)
def retposto_mesagoj(
    account: str = typer.Option(
        ..., "--konto", "-a",
        help=tr_multi("Konto UUID", "Account UUID", "UUID compte"),
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

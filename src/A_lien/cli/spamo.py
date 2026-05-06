"""Spamo sub-typer — spam block management.

Commands: ls, aldoni, forigi, sinkronigi
"""

from __future__ import annotations

from typing import Annotated

import typer

from A import error, info, warning, tr_multi
from A_lien.service import get_retposto_service

spamo_app = typer.Typer(
    name="spamo",
    help=tr_multi(
        "Administri spamajn blokojn.",
        "Manage spam blocks.",
        "Gérer les blocs de spam.",
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help", "--helpo"]},
)


def _sync_and_report(svc, account_uuid: str) -> None:
    """Attempt Sieve sync with user-facing messages. Non-fatal on failure."""
    # Check account has Sieve configured (try prefix match if needed)
    acct = svc.get_account(account_uuid)
    if not acct:
        from A_lien.cli.konton import _resolve_account
        try:
            acct = _resolve_account(svc, account_uuid)
        except typer.Exit:
            return

    if not acct.get("sieve_servilo"):
        warning(tr_multi(
            "Sinkronigo ne ebla: konto ne havas Sieve-servilon. "
            "Agordi per 'konton modifi --sieve-server'.",
            "Sync not possible: account has no Sieve server. "
            "Configure via 'konton modifi --sieve-server'.",
            "Sync impossible: le compte n'a pas de serveur Sieve. "
            "Configurez via 'konton modifi --sieve-server'.",
        ))
        return

    try:
        svc.sync_spam_blocks_to_sieve(acct["uuid"])
        info(tr_multi(
            "Spamaj blokoj sinkronigitaj al Sieve-servilo.",
            "Spam blocks synced to Sieve server.",
            "Blocs de spam synchronisés au serveur Sieve.",
        ))
    except Exception as e:
        error(tr_multi(
            f"Sinkronigo malsukcesis: {e}. Reprovu per 'spamo sinkronigi -a ...'",
            f"Sync failed: {e}. Retry with 'spamo sinkronigi -a ...'",
            f"Sync échoué: {e}. Réessayez avec 'spamo sinkronigi -a ...'",
        ))
        raise typer.Exit(1)


@spamo_app.command("ls")
def spamo_ls() -> None:
    """List all spam block rules."""
    svc = get_retposto_service()
    blocks = svc.list_spam_blocks()

    if not blocks:
        info(tr_multi(
            "Neniuj spamaj blokoj.",
            "No spam blocks.",
            "Aucun bloc de spam.",
        ))
        return

    for b in blocks:
        info(f"  {b['uuid'][:8]}  {b['regulo']}")


@spamo_app.command("aldoni")
def spamo_aldoni(
    rule: str = typer.Argument(
        ...,
        help=tr_multi(
            "Regula esprimo (retadreso aŭ domajno)",
            "Rule pattern (email or domain)",
            "Motif de règle (email ou domaine)",
        ),
    ),
    account: str = typer.Option(
        "", "--account", "-a",
        help=tr_multi(
            "Konto UUID por Sieve-sinkronigo",
            "Account UUID for Sieve sync",
            "UUID du compte pour synchro Sieve",
        ),
    ),
) -> None:
    """Add a spam block rule (stored lowercase).

    Use --account to also sync the updated ruleset to the account's
    ManageSieve server as a Sieve script.
    """
    svc = get_retposto_service()
    try:
        block = svc.add_spam_block(rule)
    except Exception as e:
        if "UNIQUE" in str(e):
            error(tr_multi(
                f"Regulo jam ekzistas: {rule}",
                f"Rule already exists: {rule}",
                f"Règle existe déjà: {rule}",
            ))
        else:
            error(str(e))
        raise typer.Exit(1)

    info(tr_multi(
        f"Spama bloko aldonita: {block['uuid'][:8]}",
        f"Spam block added: {block['uuid'][:8]}",
        f"Bloc de spam ajouté: {block['uuid'][:8]}",
    ))

    if account:
        _sync_and_report(svc, account)


@spamo_app.command("forigi")
def spamo_forigi(
    uuids: Annotated[list[str], typer.Argument(
        ...,
        help=tr_multi(
            "Bloka UUID (pluraj)",
            "Block UUIDs (multiple)",
            "UUIDs du bloc (plusieurs)",
        ),
    )],
    account: str = typer.Option(
        "", "--account", "-a",
        help=tr_multi(
            "Konto UUID por Sieve-sinkronigo",
            "Account UUID for Sieve sync",
            "UUID du compte pour synchro Sieve",
        ),
    ),
) -> None:
    """Remove spam block rules by UUID.
    Use --account to also sync the updated ruleset to the account's
    ManageSieve server.
    """
    svc = get_retposto_service()
    successes = 0
    for uid in uuids:
        try:
            svc.remove_spam_block(uid)
            successes += 1
        except Exception as e:
            error(tr_multi(
                f"Eraro: {uid[:8]} — {e}",
                f"Error: {uid[:8]} — {e}",
                f"Erreur: {uid[:8]} — {e}",
            ))
    if successes:
        info(tr_multi(
            f"{successes} bloko(j) forigitaj",
            f"{successes} block(s) removed",
            f"{successes} bloc(s) supprimé(s)",
        ))
    if not successes:
        raise typer.Exit(1)

    if account:
        _sync_and_report(svc, account)


@spamo_app.command("sinkronigi")
def spamo_sinkronigi(
    account: str = typer.Option(
        ..., "--account", "-a",
        help=tr_multi(
            "Konto UUID por Sieve-sinkronigo",
            "Account UUID for Sieve sync",
            "UUID du compte pour synchro Sieve",
        ),
    ),
) -> None:
    """Push all spam blocks to account's ManageSieve server (explicit sync)."""
    svc = get_retposto_service()
    _sync_and_report(svc, account)


__all__ = [
    "spamo_app",
    "spamo_ls",
    "spamo_aldoni",
    "spamo_forigi",
    "spamo_sinkronigi",
]

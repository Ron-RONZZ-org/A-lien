"""Filtraj sub-typer — Sieve filter management.

Commands: ls, vidi, aldoni, forigi, aktivi
"""

from __future__ import annotations

from pathlib import Path as _Path

import typer

from A import error, info, tr_multi
from A_lien.sieve import get_sieve_manager, validate_sieve

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


@filtraj_app.command("ls")
def filtraj_ls(
    account: str = typer.Option(
        ..., "--account", "-a",
        help=tr_multi("Konto UUID", "Account UUID", "UUID compte"),
    ),
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
        active = (
            tr_multi(" (aktiva)", " (active)", " (actif)")
            if s["active"]
            else ""
        )
        info(f"  {s['name']}{active}")


@filtraj_app.command("vidi")
def filtraj_vidi(
    account: str = typer.Option(
        ..., "--account", "-a",
        help=tr_multi("Konto UUID", "Account UUID", "UUID compte"),
    ),
    name: str = typer.Argument(
        ..., help=tr_multi("Skripta nomo", "Script name", "Nom du script")
    ),
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
    account: str = typer.Option(
        ..., "--account", "-a",
        help=tr_multi("Konto UUID", "Account UUID", "UUID compte"),
    ),
    path: str = typer.Argument(
        ..., help=tr_multi(
            "Vojo al .sieve dosiero",
            "Path to .sieve file",
            "Chemin vers fichier .sieve",
        ),
    ),
    name: str = typer.Option(
        "", "--name", "-n",
        help=tr_multi(
            "Skripta nomo (defaŭlte: dosiernomo)",
            "Script name (default: filename)",
            "Nom du script (défaut: nom de fichier)",
        ),
    ),
    activate: bool = typer.Option(
        False, "--activate",
        help=tr_multi(
            "Agordi kiel aktiva post alŝuto",
            "Set as active after upload",
            "Définir comme actif après téléchargement",
        ),
    ),
) -> None:
    """Upload a Sieve script (validates syntax locally first)."""
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
    account: str = typer.Option(
        ..., "--account", "-a",
        help=tr_multi("Konto UUID", "Account UUID", "UUID compte"),
    ),
    name: str = typer.Argument(
        ..., help=tr_multi("Skripta nomo", "Script name", "Nom du script")
    ),
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
    account: str = typer.Option(
        ..., "--account", "-a",
        help=tr_multi("Konto UUID", "Account UUID", "UUID compte"),
    ),
    name: str = typer.Argument(
        ..., help=tr_multi("Skripta nomo", "Script name", "Nom du script")
    ),
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


__all__ = [
    "filtraj_app",
    "filtraj_ls",
    "filtraj_vidi",
    "filtraj_aldoni",
    "filtraj_forigi",
    "filtraj_aktivi",
]

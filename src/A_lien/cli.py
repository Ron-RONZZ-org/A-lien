"""CLI for lien command (retposto, kontakto)."""

from __future__ import annotations

import typer

from A import info, tr

app = typer.Typer(
    name="lien",
    help=tr(
        "Lien — email and contacts microapp.",
        "Lien — email and contacts microapp.",
        "Lien — email et contacts microapp.",
    ),
    no_args_is_help=False,
    invoke_without_command=True,
    context_settings={"help_option_names": ["-h", "--help", "--helpo"]},
)

retposto = typer.Typer(
    name="retposto",
    help=tr(
        "Retpoŝto — TUI retpoŝta mikroapo.",
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
    help=tr(
        "Administri kontaktojn.",
        "Manage contacts.",
        "Gérer les contacts.",
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help", "--helpo"]},
)
app.add_typer(kontakto, name="kontakto")


# ──────────────────────────────────────────────────────────────────────────────
# retposto subcommands
# ──────────────────────────────────────────────────────────────────────────────


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


# ──────────────────────────────────────────────────────────────────────────────
# kontakto subcommands
# ──────────────────────────────────────────────────────────────────────────────


@kontakto.command("ls")
def kontakto_ls() -> None:
    """List contacts."""
    info("[dim]TODO: implement kontakto ls[/dim]")


@kontakto.command("serci")
def kontakto_serci(query: str) -> None:
    """Search contacts."""
    info(f"[dim]TODO: implement kontakto serci {query}[/dim]")


@kontakto.command("vidi")
def kontakto_vidi(uuid: str) -> None:
    """View a contact."""
    info(f"[dim]TODO: implement kontakto vidi {uuid}[/dim]")


__all__ = ["app", "retposto", "kontakto"]
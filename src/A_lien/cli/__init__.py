"""CLI for lien command (retposto, kontakto)."""

from __future__ import annotations

import typer

from A import tr_multi

from A_lien.cli.filtraj import filtraj_app
from A_lien.cli.kontakto import kontakto
from A_lien.cli.konton import konton
from A_lien.cli.retposto import retposto
from A_lien.cli.spamo import spamo_app
from A_lien.cli.subskribo import subskribo_app

# Wire up sub-typers under retposto
retposto.add_typer(konton, name="konton")
retposto.add_typer(subskribo_app, name="subskribo")
retposto.add_typer(filtraj_app, name="filtraj")
retposto.add_typer(spamo_app, name="spamo")

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

app.add_typer(retposto, name="retposto")
app.add_typer(kontakto, name="kontakto")

__all__ = ["app"]

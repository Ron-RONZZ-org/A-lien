"""Separate entry points for retposto and kontakto."""

from __future__ import annotations

from A_lien.cli.filtraj import filtraj_app
from A_lien.cli.kontakto import kontakto
from A_lien.cli.konton import konton
from A_lien.cli.retposto import retposto
from A_lien.cli.spamo import spamo_app
from A_lien.cli.subskribo import subskribo_app

# Wire sub-typers under retposto (same as cli/__init__.py)
retposto.add_typer(konton, name="konton")
retposto.add_typer(subskribo_app, name="subskribo")
retposto.add_typer(filtraj_app, name="filtraj")
retposto.add_typer(spamo_app, name="spamo")

__all__ = ["retposto", "kontakto"]

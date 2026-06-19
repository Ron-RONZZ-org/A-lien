"""Separate entry points for retposto and kontakto (top-level commands).

Avoids importing individual submodules directly to prevent duplicate
sub-typer wiring (cli/__init__.py already wires konton, subskribo,
filtraj, spamo under retposto).
"""

from __future__ import annotations

from A_lien.cli import kontakto, retposto  # noqa: F811

__all__ = ["retposto", "kontakto"]

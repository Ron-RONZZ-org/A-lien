"""Retposto email search command (serci).

Extracted from retposto.py to keep files under 500 lines.
This function is registered on the retposto typer from retposto.py.
"""

from __future__ import annotations

from typing import Any, Optional

import typer

from A import error, info, tr_multi
from A_lien.service import get_retposto_service


def _format_results(results: list[dict]) -> list[str]:
    """Format search results as a list of text lines."""
    lines: list[str] = [
        tr_multi(
            f"Trovitaj {len(results)} mesaĝo(j):",
            f"Found {len(results)} message(s):",
            f"{len(results)} message(s) trouvé(s):",
        ),
    ]
    for m in results:
        read_indicator = (
            tr_multi("legita", "read", "lu")
            if m.get("legita")
            else tr_multi("nelegita", "unread", "non lu")
        )
        preview = (m.get("subjekto", "") or "(sen temo)")[:50]
        lines.append(f"  {m['uuid'][:8]}  {read_indicator}: {preview}")
    return lines


def retposto_serci(
    query: list[str] = typer.Argument(
        [], help=tr_multi(
            "Serĉa teksto (pluraj vortoj aŭtomate kunigitaj)",
            "Search text (multiple words joined automatically)",
            "Texte de recherche (plusieurs mots joints automatiquement)",
        ),
    ),
    from_addr: str = typer.Option(
        "", "--from", "-f",
        help=tr_multi("Sendanto", "From sender", "Expéditeur"),
    ),
    to: str = typer.Option(
        "", "--to", "-t",
        help=tr_multi("Ricevinto", "Recipient", "Destinataire"),
    ),
    cc: str = typer.Option(
        "", "--cc",
        help=tr_multi("KK", "CC", "CC"),
    ),
    bcc: str = typer.Option(
        "", "--bcc",
        help=tr_multi("SKK", "BCC", "BCC"),
    ),
    subject: str = typer.Option(
        "", "--subject", "-s",
        help=tr_multi("Temeto", "Subject", "Sujet"),
    ),
    body: str = typer.Option(
        "", "--body", "-b",
        help=tr_multi("Korpo", "Body", "Corps"),
    ),
    after: str = typer.Option(
        "", "--post",
        help=tr_multi(
            "Post dato (YYYYMMDD)", "After date (YYYYMMDD)", "Après date (YYYYMMDD)"
        ),
    ),
    before: str = typer.Option(
        "", "--antaux",
        help=tr_multi(
            "Antaŭ dato (YYYYMMDD)", "Before date (YYYYMMDD)", "Avant date (YYYYMMDD)"
        ),
    ),
    read: bool = typer.Option(
        False, "--legita",
        help=tr_multi("Legita", "Read", "Lu"),
    ),
    unread: bool = typer.Option(
        False, "--nelegita",
        help=tr_multi("Nelegita", "Unread", "Non lu"),
    ),
    priority: int = typer.Option(
        0, "--prioritato", "-p",
        help=tr_multi("Prioritato (1-5)", "Priority (1-5)", "Priorité (1-5)"),
    ),
    limit: int = typer.Option(
        50, "--limo", "-l",
        help=tr_multi("Maksimumaj rezultoj", "Max results", "Résultats max"),
    ),
    account: str = typer.Option(
        "", "--konto", "-a",
        help=tr_multi("Konto UUID", "Account UUID", "UUID compte"),
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o",
        help=tr_multi(
            "Eliga dosiero (anstataŭ stdout)",
            "Output file (instead of stdout)",
            "Fichier de sortie (au lieu de stdout)",
        ),
    ),
) -> None:
    """Search emails with filters."""
    svc = get_retposto_service()

    filters: dict[str, Any] = {}
    query_str = " ".join(query) if query else ""
    if query_str:
        filters["query"] = query_str
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

    # Warn if query looks like it contains shell redirect operators
    if query_str and any(op in query_str for op in (">", "<")):
        info(tr_multi(
            "Noto: la serĉa teksto enhavas '>' aŭ '<'. "
            "Se vi volis redirekti eligon, uzu --output.",
            "Note: search text contains '>' or '<'. "
            "If you wanted to redirect output, use --output.",
            "Remarque: le texte de recherche contient '>' ou '<'. "
            "Pour rediriger la sortie, utilisez --output.",
        ))

    results = svc.search_messages(filters, limit=limit)

    if not results:
        info(tr_multi(
            "Neniuj rezultoj.",
            "No results.",
            "Aucun résultat.",
        ))
        return

    lines = _format_results(results)

    if output:
        from pathlib import Path
        Path(output).write_text("\n".join(lines) + "\n", encoding="utf-8")
        info(tr_multi(
            f"Rezultoj skribitaj al {output}",
            f"Results written to {output}",
            f"Résultats écrits dans {output}",
        ))
    else:
        for line in lines:
            info(line)


__all__ = ["retposto_serci", "_format_results"]

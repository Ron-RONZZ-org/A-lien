"""Retposto message view — vidi (CLI and HTML).

Extracted from retposto.py to keep files under 500 lines.
"""

from __future__ import annotations

import html
import os
import tempfile
from typing import Any

import typer

from A import error, info, tr_multi
from A_lien.cli.retposto_message_ops import _resolve_message
from A_lien.service import get_retposto_service


def _format_size(size: int) -> str:
    """Format byte count to human-readable string."""
    if size > 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    if size > 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} B"


def _build_attachments_html(attachments: list[dict[str, Any]]) -> str:
    """Build an HTML attachment block for appending to email body HTML.

    Args:
        attachments: List of attachment dicts (dosiernomo, mime_tipo, grandeco, vojo)

    Returns:
        HTML string or empty string if no attachments
    """
    if not attachments:
        return ""
    rows: list[str] = []
    for att in attachments:
        size = att.get("grandeco", 0)
        size_str = _format_size(size)
        mime = att.get("mime_tipo", "")
        fname = html.escape(att.get("dosiernomo", ""))
        vojo = att.get("vojo", "")
        if vojo:
            rows.append(
                f'<li><a href="file://{vojo}">{fname}</a>'
                f" ({size_str}) <code>{html.escape(mime)}</code></li>"
            )
        else:
            rows.append(
                f"<li>{fname} ({size_str}) <code>{html.escape(mime)}</code></li>"
            )
    return (
        '<div class="attachments">\n'
        f"<h3>{tr_multi('Aldona\u0135oj:', 'Attachments:', 'Pi\u00e8ces jointes:')}</h3>\n"
        f"<ul>\n{chr(10).join(rows)}\n</ul>\n"
        "</div>\n"
    )


# ── vidi — view a message ────────────────────────────────────────────────────


def retposto_vidi_mesago(
    uuid: str = typer.Argument(
        ..., help=tr_multi("Mesa\u011do UUID", "Message UUID", "UUID message")
    ),
    html: bool = typer.Option(
        False, "--html", "-H",
        help=tr_multi("Montri HTML en retumilo", "Show HTML in browser", "Afficher HTML dans le navigateur"),
    ),
) -> None:
    """View an email by UUID or prefix (opens in editor by default)."""
    svc = get_retposto_service()
    msg = _resolve_message(svc, uuid)

    # Mark as read
    svc.mark_read(msg["uuid"])

    if html:
        html_body = msg.get("html_korpo", "") or msg.get("korpo", "")
        if html_body:
            attachments = svc.get_attachments(msg["uuid"])
            if attachments:
                html_body += _build_attachments_html(attachments)
            from A.core.markdown_html_view import preview_html

            preview_html(
                html_body,
                open_browser=True,
                title=msg.get("subjekto", "Mesa\u011do"),
            )
        else:
            error(tr_multi(
                "Neniu HTML-enhavo por \u0109i tiu mesa\u011do.",
                "No HTML content for this message.",
                "Aucun contenu HTML pour ce message.",
            ))
        return

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

    # Append attachments info
    attachments = svc.get_attachments(msg["uuid"])
    if attachments:
        lines.append("")
        lines.append("-" * 40)
        lines.append(tr_multi("Aldona\u0135oj:", "Attachments:", "Pi\u00e8ces jointes:"))
        for idx, att in enumerate(attachments, 1):
            size = att.get("grandeco", 0)
            size_str = _format_size(size)
            mime = att.get("mime_tipo", "?")
            fname = att.get("dosiernomo", "?")
            lines.append(f"  [{idx}] {fname} ({size_str}) [{mime}]")

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

"""Retposto attachment download — elsuti.

Download/extract attachment(s) from an email via IMAP,
or print text-type attachment content to stdout.
"""

from __future__ import annotations

from typing import Optional

import typer

from A import confirm_action, error, info, tr_multi
from A_lien.cli.retposto_message_ops import _resolve_message
from A_lien.service import get_retposto_service

# MIME types whose content can safely be printed as text.
_TEXT_MIME_PREFIXES: frozenset[str] = frozenset({
    "text/",
})

_TEXT_MIME_EXACT: frozenset[str] = frozenset({
    "application/json",
    "application/xml",
    "application/xhtml+xml",
    "application/atom+xml",
    "application/rss+xml",
    "application/javascript",
    "application/ecmascript",
    "application/x-yaml",
    "application/toml",
    "application/csv",
    "application/x-csv",
    "application/x-httpd-php",
    "application/x-sh",
    "application/sql",
})


def _is_text_mime(mime: str) -> bool:
    """Check whether a MIME type is text-like and safe to print inline.

    Args:
        mime: The MIME type string (e.g. ``"text/plain"``, ``"application/pdf"``).

    Returns:
        True if the content can be decoded as readable text.
    """
    mime_lower = mime.strip().lower()
    if mime_lower in _TEXT_MIME_EXACT:
        return True
    for prefix in _TEXT_MIME_PREFIXES:
        if mime_lower.startswith(prefix):
            return True
    return False


# Binary MIME types that we can extract text from (via optional A-papero).
_EXTRACTABLE_BINARY_MIMES: frozenset[str] = frozenset({
    "application/pdf",
})


def _is_extractable_binary(mime: str) -> bool:
    """Check whether a binary MIME type supports text extraction.

    Currently supported: PDF (requires ``A-papero[pdf]`` installed).

    Args:
        mime: The MIME type string.

    Returns:
        True if text extraction is possible with optional dependencies.
    """
    return mime.strip().lower() in _EXTRACTABLE_BINARY_MIMES


def _try_extract_pdf_text(data: bytes) -> str | None:
    """Try to extract text from PDF bytes using A-papero (optional dependency).

    Attempts a runtime import from ``A_papero.formats.pdf``.  If A-papero
    is not installed, returns ``None`` — the caller should suggest installing it.

    Args:
        data: Raw PDF bytes.

    Returns:
        Extracted text, or ``None`` if A-papero is unavailable.
    """
    try:
        from A_papero.formats.pdf import read_pdf_bytes
    except ImportError:
        return None
    return read_pdf_bytes(data)


def _fmt_size(size: int) -> str:
    """Format byte count to human-readable string."""
    if size > 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    if size > 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} B"


# ── stdout-mode helpers ──────────────────────────────────────────────────────


def _try_decode(data: bytes) -> str | None:
    """Try to decode bytes as UTF-8 text.

    Args:
        data: Raw bytes.

    Returns:
        Decoded string, or None if the data is not valid UTF-8.
    """
    try:
        return data.decode("utf-8")
    except (UnicodeDecodeError, UnicodeError):
        return None


def _print_text_attachment(svc: object, msg_uuid: str, att: dict) -> None:
    """Fetch a text attachment and print its content to stdout.

    Args:
        svc: RetpostoService instance.
        msg_uuid: Message UUID.
        att: Attachment metadata dict (must contain ``dosiernomo`` and ``mime_tipo``).
    """
    fname = att.get("dosiernomo", "?")
    mime = att.get("mime_tipo", "") or "application/octet-stream"

    try:
        raw: bytes = svc.get_attachment_content(msg_uuid, fname)  # type: ignore[arg-type]
    except Exception as e:
        info(tr_multi(
            f"  [eraro] {fname}: {e}",
            f"  [error] {fname}: {e}",
            f"  [erreur] {fname} : {e}",
        ))
        return

    text = _try_decode(raw)
    if text is None:
        info(tr_multi(
            f"  [binary] {fname} ({mime}) — enhavo ne estas valida UTF-8; uzu --output por konservi",
            f"  [binary] {fname} ({mime}) — content is not valid UTF-8; use --output to save",
            f"  [binaire] {fname} ({mime}) — le contenu n'est pas en UTF-8 valide; utilisez --output",
        ))
        return

    # Truncation guard: if content is huge, print first and last N chars
    _print_content_block(fname, raw, text)


def _print_content_block(fname: str, raw: bytes, text: str) -> None:
    """Print a content block with header and optional truncation.

    Args:
        fname: Attachment filename for the header.
        raw: Raw bytes (for size calculation).
        text: Decoded text content.
    """
    MAX_STDOUT_CHARS = 50_000
    if len(text) > MAX_STDOUT_CHARS:
        info(f"--- {fname} ({_fmt_size(len(raw))}) — {tr_multi('montras unuajn', 'showing first', 'affiche les premiers')} {MAX_STDOUT_CHARS} {tr_multi('signojn', 'chars', 'caractères')} ---")
        info(text[:MAX_STDOUT_CHARS])
        info("... " + tr_multi("(tranĉita)", "(truncated)", "(tronqué)"))
    else:
        info(f"--- {fname} ({_fmt_size(len(raw))}) ---")
        info(text)


def _print_extracted_attachment(svc: object, msg_uuid: str, att: dict) -> None:
    """Fetch an extractable-binary attachment (e.g. PDF) and print its text.

    Requires ``A-papero[pdf]`` at runtime.  If unavailable, prints an
    installation hint instead.

    Args:
        svc: RetpostoService instance.
        msg_uuid: Message UUID.
        att: Attachment metadata dict.
    """
    fname = att.get("dosiernomo", "?")
    mime = att.get("mime_tipo", "") or "application/octet-stream"

    try:
        raw: bytes = svc.get_attachment_content(msg_uuid, fname)  # type: ignore[arg-type]
    except Exception as e:
        info(tr_multi(
            f"  [eraro] {fname}: {e}",
            f"  [error] {fname}: {e}",
            f"  [erreur] {fname} : {e}",
        ))
        return

    text = _try_extract_pdf_text(raw)
    if text is None:
        # A-papero not installed
        info(tr_multi(
            f"--- {fname} ({mime}) ---",
            f"--- {fname} ({mime}) ---",
            f"--- {fname} ({mime}) ---",
        ))
        info(tr_multi(
            "Por eltiri tekston el PDF, instalu: pip install A-papero[pdf]",
            "To extract text from PDF, install: pip install A-papero[pdf]",
            "Pour extraire le texte du PDF, installez : pip install A-papero[pdf]",
        ))
        return

    _print_content_block(fname, raw, text)


# ── Main command ─────────────────────────────────────────────────────────────


def retposto_elsuti(
    uuid: str = typer.Argument(
        ..., help=tr_multi(
            "Mesa\u011do UUID",
            "Message UUID",
            "UUID du message",
        ),
    ),
    filename: Optional[str] = typer.Argument(
        None, help=tr_multi(
            "Dosiernomo \u015dan\u0109i\u0115enda (preterlasu por \u0109iuj)",
            "Filename to download (omit for all)",
            "Nom du fichier \u00e0 t\u00e9l\u00e9charger (omettre pour tout)",
        ),
    ),
    output_dir: Optional[str] = typer.Option(
        None, "--eligo", "-o",
        help=tr_multi(
            "Konserva dosierujo (default: /tmp/)",
            "Output directory (default: /tmp/)",
            "Dossier de sortie (d\u00e9faut: /tmp/)",
        ),
    ),
    stdout: bool = typer.Option(
        False, "--stdout",
        help=tr_multi(
            "Presi tekstan enhavon al stdout (anstata\u016d konservi)",
            "Print text content to stdout (instead of saving to disk)",
            "Imprimer le contenu texte sur stdout (au lieu de sauvegarder)",
        ),
    ),
) -> None:
    """Download attachment(s) from a message via IMAP.

    If no filename is given, downloads ALL attachments
    (with confirmation if >3 files or >10 MB total).

    Use --stdout to print text-type attachment content directly
    to stdout instead of saving to disk.
    """
    svc = get_retposto_service()
    msg = _resolve_message(svc, uuid)
    if not msg:
        error(tr_multi(
            f"Mesa\u011do ne trovita: {uuid}",
            f"Message not found: {uuid}",
            f"Message non trouv\u00e9: {uuid}",
        ))
        raise typer.Exit(1)

    attachments = svc.get_attachments(msg["uuid"])
    if not attachments:
        info(tr_multi(
            "Neniuj aldona\u0135oj en \u0109i tiu mesa\u011do.",
            "No attachments in this message.",
            "Aucune pi\u00e8ce jointe dans ce message.",
        ))
        return

    # ── stdout mode: print text content inline ────────────────────────────
    if stdout:
        if filename:
            # Single attachment
            matching = [a for a in attachments if a.get("dosiernomo") == filename]
            if not matching:
                error(tr_multi(
                    f"Aldona\u0135o '{filename}' ne trovita.",
                    f"Attachment '{filename}' not found.",
                    f"Pi\u00e8ce jointe '{filename}' non trouv\u00e9e.",
                ))
                raise typer.Exit(1)
            att = matching[0]
            mime = att.get("mime_tipo", "") or "application/octet-stream"
            if _is_text_mime(mime):
                _print_text_attachment(svc, msg["uuid"], att)
            elif _is_extractable_binary(mime):
                _print_extracted_attachment(svc, msg["uuid"], att)
            else:
                info(tr_multi(
                    f"[binary] {filename} ({mime}) — ne eblas montri kiel teksto; uzu --output por konservi",
                    f"[binary] {filename} ({mime}) — cannot display as text; use --output to save",
                    f"[binaire] {filename} ({mime}) — ne peut pas \u00eatre affich\u00e9 comme texte; utilisez --output",
                ))
            return

        # All attachments in stdout mode
        text_count = 0
        extracted_count = 0
        binary_count = 0
        for att in attachments:
            fname = att.get("dosiernomo", "?")
            mime = att.get("mime_tipo", "") or "application/octet-stream"
            if _is_text_mime(mime):
                _print_text_attachment(svc, msg["uuid"], att)
                text_count += 1
            elif _is_extractable_binary(mime):
                _print_extracted_attachment(svc, msg["uuid"], att)
                extracted_count += 1
            else:
                info(tr_multi(
                    f"--- {fname} ({mime}) — [binary] ne montrebla kiel teksto ---",
                    f"--- {fname} ({mime}) — [binary] not displayable as text ---",
                    f"--- {fname} ({mime}) — [binaire] non affichable comme texte ---",
                ))
                binary_count += 1

        if text_count:
            info(tr_multi(
                f"Montris {text_count} tekstan(j)n aldona\u0135o(j)n.",
                f"Displayed {text_count} text attachment(s).",
                f"{text_count} pi\u00e8ce(s) jointe(s) texte affich\u00e9e(s).",
            ))
        if extracted_count:
            info(tr_multi(
                f"Elsutis tekston el {extracted_count} aldona\u0135o(j) (PDF).",
                f"Extracted text from {extracted_count} attachment(s) (PDF).",
                f"Texte extrait de {extracted_count} pi\u00e8ce(s) jointe(s) (PDF).",
            ))
        if binary_count:
            info(tr_multi(
                f"{binary_count} aldona\u0135o(j) estas en ne-teksta formato; uzu --output por konservi.",
                f"{binary_count} attachment(s) are in non-text format; use --output to save.",
                f"{binary_count} pi\u00e8ce(s) jointe(s) sont en format non-texte; utilisez --output.",
            ))
        return

    # ── Save-to-disk mode (original behaviour) ────────────────────────────
    import os

    out = output_dir or "/tmp"

    if filename:
        # Single attachment download
        if not any(a.get("dosiernomo") == filename for a in attachments):
            error(tr_multi(
                f"Aldona\u0135o '{filename}' ne trovita.",
                f"Attachment '{filename}' not found.",
                f"Pi\u00e8ce jointe '{filename}' non trouv\u00e9e.",
            ))
            raise typer.Exit(1)
        try:
            path = svc.extract_attachment(msg["uuid"], filename, out)
            info(tr_multi(f"Konservita: {path}", f"Saved: {path}", f"Enregistr\u00e9: {path}"))
        except Exception as e:
            error(str(e))
            raise typer.Exit(1)
        return

    # Download all attachments
    total_size = sum(a.get("grandeco", 0) for a in attachments)
    total_mb = total_size / (1024 * 1024)

    info(tr_multi(
        f"El\u015dutota {len(attachments)} aldona\u0135o(j) ({_fmt_size(total_size)})",
        f"Downloading {len(attachments)} attachment(s) ({_fmt_size(total_size)})",
        f"T\u00e9l\u00e9chargement de {len(attachments)} pi\u00e8ce(s) jointe(s) ({_fmt_size(total_size)})",
    ))

    # Confirmation gate for large/many downloads
    if len(attachments) > 3 or total_mb > 10:
        confirmed = confirm_action(
            tr_multi(
                "\u0108u da\u016drigi?",
                "Continue?",
                "Continuer?",
            ),
            default=True,
        )
        if not confirmed:
            info(tr_multi("Nuligita.", "Cancelled.", "Annul\u00e9."))
            raise typer.Exit(0)

    saved = 0
    for att in attachments:
        fname = att["dosiernomo"]
        try:
            path = svc.extract_attachment(msg["uuid"], fname, out)
            info(f"  [{'OK' if len(attachments) > 1 else ''}] {os.path.basename(path)}")
            saved += 1
        except Exception as e:
            error(tr_multi(
                f"  Eraro: {fname} — {e}",
                f"  Error: {fname} — {e}",
                f"  Erreur: {fname} — {e}",
            ))

    if saved:
        info(tr_multi(
            f"{saved} aldona\u0135o(j) konservita(j) al {out}",
            f"{saved} attachment(s) saved to {out}",
            f"{saved} pi\u00e8ce(s) jointe(s) enregistr\u00e9e(s) dans {out}",
        ))

"""IMAP helper functions: header decoding, email parsing, auto-contact filtering."""

from __future__ import annotations

from email.header import decode_header


def _decode_mime_header(value: str) -> str:
    """Decode a MIME encoded header value to plain text."""
    if not value:
        return ""
    parts = decode_header(value)
    result: list[str] = []
    for part, encoding in parts:
        if isinstance(part, bytes):
            result.append(part.decode(encoding or "utf-8", errors="replace"))
        else:
            result.append(str(part))
    return " ".join(result)


def _parse_email_address(value: str) -> str:
    """Extract email address from 'Name <addr@dom.ain>' form."""
    if not value:
        return ""
    if "<" in value and ">" in value:
        return value.split("<")[1].split(">")[0].strip()
    return value.strip()


def _extract_sender_name(from_header: str) -> str:
    """Extract display name from 'Name <addr@dom.ain>' form."""
    if not from_header:
        return ""
    if "<" in from_header and ">" in from_header:
        return from_header.split("<")[0].strip().strip("\"'")
    return ""


_NO_REPLY_PATTERNS: tuple[str, ...] = (
    "no-reply", "noreply", "no_reply", "noreplay",
    "noresponder", "donotreply", "do-not-reply",
    "mailer-daemon", "mailer_daemon",
    "notifications", "notification",
    "nepagesu", "nepagas",
)


def _is_likely_temporary_local_part(local: str) -> bool:
    """Check if local part looks like a temporary/throwaway address."""
    if len(local) > 30:
        return True
    digits = sum(1 for c in local if c.isdigit())
    if len(local) > 0 and digits / len(local) > 0.6:
        return True
    return False


def should_autosave_contact(email_addr: str) -> bool:
    """Check if an email address should be auto-saved as a contact.

    Skips: no-reply, noreply, mailer-daemon, long random local-parts, etc.
    """
    addr = _parse_email_address(email_addr)
    if "@" not in addr:
        return False
    local, _domain = addr.split("@", 1)
    local_low = local.lower()
    if any(pat in local_low for pat in _NO_REPLY_PATTERNS):
        return False
    if _is_likely_temporary_local_part(local_low):
        return False
    return True


def _parse_address_list(value: str) -> list[str]:
    """Parse a list of email addresses from a header value."""
    if not value:
        return []
    results = []
    for part in value.split(","):
        addr = _parse_email_address(part.strip())
        if addr:
            results.append(addr)
    return results


__all__ = [
    "_decode_mime_header",
    "_parse_email_address",
    "_extract_sender_name",
    "_NO_REPLY_PATTERNS",
    "_is_likely_temporary_local_part",
    "should_autosave_contact",
    "_parse_address_list",
]

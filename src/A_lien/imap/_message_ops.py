"""IMAP message operations — move, delete, flag, append, fetch."""

from __future__ import annotations

import imaplib


def move_message(
    conn: imaplib.IMAP4, source_folder: str, uid: int, target_folder: str,
) -> bool:
    """Move a message via IMAP MOVE (RFC 6851) or COPY+DELETE fallback."""
    conn.select(source_folder)
    try:
        typ, _ = conn.uid("MOVE", str(uid), target_folder)
        if typ == "OK":
            return True
    except imaplib.IMAP4.error:
        pass
    typ, _ = conn.uid("COPY", str(uid), target_folder)
    if typ != "OK":
        return False
    conn.uid("STORE", str(uid), "+FLAGS.SILENT", "(\\Deleted)")
    conn.expunge()
    return True


def delete_message(conn: imaplib.IMAP4, folder: str, uid: int) -> None:
    """Mark a message as ``\\Deleted`` in an IMAP folder."""
    conn.select(folder)
    conn.uid("STORE", str(uid), "+FLAGS.SILENT", "(\\Deleted)")


def set_flags(
    conn: imaplib.IMAP4, folder: str, uid: int,
    add: list[str] | None = None,
    remove: list[str] | None = None,
) -> None:
    """Add or remove IMAP flags on a message."""
    conn.select(folder)
    if add:
        flag_str = " ".join(add)
        conn.uid("STORE", str(uid), "+FLAGS.SILENT", f"({flag_str})")
    if remove:
        flag_str = " ".join(remove)
        conn.uid("STORE", str(uid), "-FLAGS.SILENT", f"({flag_str})")


def append_message(
    conn: imaplib.IMAP4, folder: str, raw_message: bytes,
    flags: list[str] | None = None,
) -> bool:
    """Append a raw message to an IMAP folder."""
    flag_str = " ".join(flags) if flags else ""
    try:
        typ, _ = conn.append(folder, flag_str, None, raw_message)
        return typ == "OK"
    except imaplib.IMAP4.error:
        return False


def fetch_raw_message(
    conn: imaplib.IMAP4, folder: str, uid: int,
) -> bytes | None:
    """Fetch raw RFC 5322 message bytes by UID."""
    conn.select(folder, readonly=True)
    try:
        typ, data = conn.uid("FETCH", str(uid), "(BODY[] UID)")
        if typ != "OK" or not data or not isinstance(data[0], tuple):
            return None
        return data[0][1]
    except imaplib.IMAP4.error:
        return None

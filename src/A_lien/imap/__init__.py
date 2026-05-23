"""IMAP sync engine for A-lien.

Provides async-free, concurrent IMAP folder and message synchronization
using stdlib imaplib and concurrent.futures.ThreadPoolExecutor.
"""

from __future__ import annotations

from A_lien.imap.helpers import (
    _decode_mime_header,
    _extract_sender_name,
    _is_likely_temporary_local_part,
    _NO_REPLY_PATTERNS,
    _parse_address_list,
    _parse_email_address,
    should_autosave_contact,
)
from A_lien.imap._sync_types import MessageStore, SyncResult
from A_lien.imap.client import IMAPClient
from A_lien.imap.sync import (
    sync_account,
    sync_accounts_concurrent,
)

__all__ = [
    "IMAPClient",
    "SyncResult",
    "MessageStore",
    "sync_account",
    "sync_accounts_concurrent",
    "should_autosave_contact",
    "_parse_email_address",
    "_extract_sender_name",
    "_NO_REPLY_PATTERNS",
]

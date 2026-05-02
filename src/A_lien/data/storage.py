"""A-lien data layer - SQLite storage for retposhto and kontakto."""

from __future__ import annotations

from pathlib import Path

from A import ensure_dirs as _ensure_dirs
from A.data.base import SQLiteDB

_DATA_DIR: Path = Path.home() / ".local" / "share" / "A"

# ──────────────────────────────────────────────────────────────────────────────
# Email accounts (retposto)
# ──────────────────────────────────────────────────────────────────────────────

_CREATE_KONTOJ = """
CREATE TABLE IF NOT EXISTS kontoj (
    uuid TEXT PRIMARY KEY,
    retposhto TEXT NOT NULL,
    uzantnomo TEXT NOT NULL,
    pasvorto TEXT NOT NULL,
    smtp_server TEXT NOT NULL,
    smtp_port INTEGER NOT NULL DEFAULT 587,
    imap_server TEXT NOT NULL,
    imap_port INTEGER NOT NULL DEFAULT 993,
    usessl INTEGER NOT NULL DEFAULT 1,
    kreita_je TEXT NOT NULL,
    modifita_je TEXT NOT NULL
);
"""

_CREATE_MESAGOJ = """
CREATE TABLE IF NOT EXISTS mesaghoj (
    uuid TEXT PRIMARY KEY,
    konto_uuid TEXT NOT NULL,
    foldero TEXT NOT NULL DEFAULT 'INBOX',
    sendinto TEXT NOT NULL,
    ricevinto TEXT NOT NULL,
   _cc TEXT NOT NULL DEFAULT '',
    titolo TEXT NOT NULL,
    teksto TEXT NOT NULL DEFAULT '',
    dato TEXT NOT NULL,
    legita INTEGER NOT NULL DEFAULT 0,
    kreita_je TEXT NOT NULL,
    modifita_je TEXT NOT NULL
);
"""

# ──────────────────────────────────────────────────────────────────────────────
# Contacts (kontakto)
# ──────────────────────────────────────────────────────────────────────────────

_CREATE_KONTAKTOJ = """
CREATE TABLE IF NOT EXISTS kontaktoj (
    uuid TEXT PRIMARY KEY,
    personanomo TEXT NOT NULL,
    retposhtoadreso TEXT NOT NULL DEFAULT '',
    telefono TEXT NOT NULL DEFAULT '',
    organizo TEXT NOT NULL DEFAULT '',
    kategorio TEXT NOT NULL DEFAULT '',
    notoj TEXT NOT NULL DEFAULT '',
    ligiloj TEXT NOT NULL DEFAULT '[]',
    kreita_je TEXT NOT NULL,
    modifita_je TEXT NOT NULL
);
"""

_CREATE_KATEGORIOJ = """
CREATE TABLE IF NOT EXISTS kategorioj (
    uuid TEXT PRIMARY KEY,
    nomo TEXT NOT NULL,
    koloro TEXT NOT NULL DEFAULT '',
    kreita_je TEXT NOT NULL,
    modifita_je TEXT NOT NULL
);
"""

# ──────────────────────────────────────────────────────────────────────────────
# Indexes
# ──────────────────────────────────────────────────────────────────────────────

_CREATE_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_mesaghoj_konto ON mesaghoj(konto_uuid);
CREATE INDEX IF NOT EXISTS idx_mesaghoj_dato ON mesaghoj(dato);
CREATE INDEX IF NOT EXISTS idx_kontaktoj_retposhto ON kontaktoj(retposhtoadreso);
"""


def ensure_dirs() -> None:
    """Ensure data directory exists."""
    _ensure_dirs(_DATA_DIR)


def get_db(path: Path = _DATA_DIR / "lien.db") -> SQLiteDB:
    """Get database connection."""
    ensure_dirs()
    db = SQLiteDB(path)
    
    stmts = [
        _CREATE_KONTOJ, _CREATE_MESAGOJ,
        _CREATE_KONTAKTOJ, _CREATE_KATEGORIOJ,
        _CREATE_INDEXES,
    ]
    for stmt in stmts:
        db.execute(stmt)
    
    return db


__all__ = ["ensure_dirs", "get_db"]
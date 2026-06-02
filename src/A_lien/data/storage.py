"""A-lien data layer — SQLite storage for retposhto and kontakto.

All tables in lien.db at A.core.paths.data_dir(). WAL mode via A.data.base.SQLiteDB.

Design decisions:
- No pasvorto column in kontoj — passwords go to system keyring
- FTS5 on kontaktoj only (messages use IMAP SEARCH)
- JSON arrays for multi-value fields (phones, emails, CC/BCC per A-encik pattern)
- Attachments: BLOB for small files, disk path for large files
- dosierujoj, mesagoj, aldonajxoj are NOT managed by CRUDService (too many records)
  — all others ARE managed by CRUDService for soft-delete + undo support
"""

from __future__ import annotations

from A.core.paths import data_dir
from A.core.paths import ensure_dirs as _ensure_dirs
from A.core.backup_targets import BackupTarget
from A.data.base import SQLiteDB
from A.data.search import FTSConfig
from A.utils.normalize import fold_search_text

# ══════════════════════════════════════════════════════════════════════════════
# DDL — each string is exactly one SQL statement (SQLiteDB.execute limitation)
# ══════════════════════════════════════════════════════════════════════════════

# ── Email accounts (retposto) ────────────────────────────────────────────────

_CREATE_KONTOJ = """
CREATE TABLE IF NOT EXISTS kontoj (
    uuid            TEXT PRIMARY KEY,
    ordo            INTEGER NOT NULL DEFAULT 0,
    nomo            TEXT NOT NULL,
    retposto        TEXT NOT NULL UNIQUE,
    imap_servilo    TEXT NOT NULL,
    imap_haveno     INTEGER NOT NULL DEFAULT 993,
    imap_ssl        INTEGER NOT NULL DEFAULT 1,
    smtp_servilo    TEXT NOT NULL,
    smtp_haveno     INTEGER NOT NULL DEFAULT 587,
    smtp_tls        INTEGER NOT NULL DEFAULT 1,
    imap_uzantonomo TEXT,
    smtp_uzantonomo TEXT,
    webmail_url     TEXT,
    sieve_servilo   TEXT,
    sieve_haveno    INTEGER NOT NULL DEFAULT 4190,
    sieve_starttls  INTEGER NOT NULL DEFAULT 1,
    sieve_uzantonomo TEXT,
    subskribo       TEXT,
    kreita_je       TEXT NOT NULL,
    modifita_je     TEXT NOT NULL
);
"""

# ── IMAP folders ─────────────────────────────────────────────────────────────

_CREATE_DOSIERUJOJ = """
CREATE TABLE IF NOT EXISTS dosierujoj (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid        TEXT NOT NULL UNIQUE,
    konto_id    TEXT NOT NULL REFERENCES kontoj(uuid) ON DELETE CASCADE,
    nomo        TEXT NOT NULL,
    patro_id    TEXT REFERENCES dosierujoj(uuid) ON DELETE CASCADE,
    server_nomo TEXT,
    delimejo    TEXT DEFAULT '/',
    kreita_je   TEXT NOT NULL,
    modifita_je TEXT NOT NULL,
    UNIQUE(konto_id, nomo, patro_id)
);
"""
_IDX_DOSIERUJOJ_KONTO = """
CREATE INDEX IF NOT EXISTS idx_dosierujoj_konto ON dosierujoj(konto_id);
"""

# ── Messages ─────────────────────────────────────────────────────────────────

_CREATE_MESAGXOJ = """
CREATE TABLE IF NOT EXISTS mesagoj (
    uuid           TEXT PRIMARY KEY,
    konto_id       TEXT NOT NULL REFERENCES kontoj(uuid) ON DELETE CASCADE,
    dosierujo_id   TEXT REFERENCES dosierujoj(uuid) ON DELETE SET NULL,
    message_id     TEXT,
    in_reply_to    TEXT,
    references_hdr TEXT,
    imap_uid       INTEGER,
    de             TEXT,
    al             TEXT NOT NULL DEFAULT '[]',
    kc             TEXT NOT NULL DEFAULT '[]',
    bkc            TEXT NOT NULL DEFAULT '[]',
    subjekto       TEXT,
    korpo          TEXT,
    html_korpo     TEXT,
    prioritato     INTEGER DEFAULT 5,
    legita         INTEGER NOT NULL DEFAULT 0,
    stelo          INTEGER NOT NULL DEFAULT 0,
    spamo          INTEGER NOT NULL DEFAULT 0,
    forigita       INTEGER NOT NULL DEFAULT 0,
    aldonajxoj     TEXT NOT NULL DEFAULT '[]',
    etikedoj       TEXT NOT NULL DEFAULT '[]',
    ricevita_je    TEXT,
    kreita_je      TEXT NOT NULL,
    modifita_je    TEXT NOT NULL
);
"""
_IDX_MESAGXOJ_KONTO = """
CREATE INDEX IF NOT EXISTS idx_mesagoj_konto ON mesagoj(konto_id);
"""
_IDX_MESAGXOJ_DOSIERUJO = """
CREATE INDEX IF NOT EXISTS idx_mesagoj_dosierujo ON mesagoj(dosierujo_id);
"""
_IDX_MESAGXOJ_IMAP_UID = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_mesagoj_imap_uid
    ON mesagoj(konto_id, dosierujo_id, imap_uid)
    WHERE imap_uid IS NOT NULL;
"""
_IDX_MESAGXOJ_MESSAGE_ID = """
CREATE INDEX IF NOT EXISTS idx_mesagoj_message_id ON mesagoj(konto_id, message_id);
"""
_IDX_MESAGXOJ_DATO = """
CREATE INDEX IF NOT EXISTS idx_mesagoj_dato ON mesagoj(ricevita_je);
"""

# ── Attachments ──────────────────────────────────────────────────────────────

_CREATE_ALDONAJXOJ = """
CREATE TABLE IF NOT EXISTS aldonajxoj (
    uuid         TEXT PRIMARY KEY,
    mesagxo_id   TEXT NOT NULL REFERENCES mesagoj(uuid) ON DELETE CASCADE,
    dosiernomo   TEXT NOT NULL,
    mime_tipo    TEXT NOT NULL DEFAULT 'application/octet-stream',
    grandeco     INTEGER NOT NULL DEFAULT 0,
    enhavo       BLOB,
    vojo         TEXT,
    cid          TEXT,
    kreita_je    TEXT NOT NULL,
    modifita_je  TEXT NOT NULL
);
"""
_IDX_ALDONAJXOJ_MESAGXO = """
CREATE INDEX IF NOT EXISTS idx_aldonajxoj_mesagxo ON aldonajxoj(mesagxo_id);
"""

# ── Signatures (CRUDService) ─────────────────────────────────────────────────

_CREATE_SUBSKRIBOJ = """
CREATE TABLE IF NOT EXISTS subskriboj (
    uuid         TEXT PRIMARY KEY,
    nomo         TEXT NOT NULL,
    teksto       TEXT NOT NULL,
    estas_html   INTEGER NOT NULL DEFAULT 0,
    apriora      INTEGER NOT NULL DEFAULT 0,
    kreita_je    TEXT NOT NULL,
    modifita_je  TEXT NOT NULL
);
"""

# ── Sieve filters (CRUDService) ──────────────────────────────────────────────

_CREATE_FILTRAJ = """
CREATE TABLE IF NOT EXISTS filtraj (
    uuid         TEXT PRIMARY KEY,
    nomo         TEXT NOT NULL UNIQUE,
    sieve_kodo   TEXT NOT NULL,
    aktiva       INTEGER NOT NULL DEFAULT 1,
    ordo         INTEGER NOT NULL DEFAULT 0,
    kreita_je    TEXT NOT NULL,
    modifita_je  TEXT NOT NULL
);
"""

# ── Spam blocks (CRUDService) ────────────────────────────────────────────────

_CREATE_SPAMO_BLOKOJ = """
CREATE TABLE IF NOT EXISTS spamo_blokoj (
    uuid       TEXT PRIMARY KEY,
    regulo     TEXT NOT NULL UNIQUE,
    kreas      TEXT,
    kreita_je  TEXT NOT NULL,
    modifita_je TEXT NOT NULL
);
"""

# ── Contacts (CRUDService + FTS5) ────────────────────────────────────────────

_CREATE_KONTAKTOJ = """
CREATE TABLE IF NOT EXISTS kontaktoj (
    uuid             TEXT PRIMARY KEY,
    nomo             TEXT,
    familia_nomo     TEXT,
    plena_nomo       TEXT,
    naskigx_dato     TEXT,
    naskigx_loko     TEXT,
    lingvoj          TEXT NOT NULL DEFAULT '[]',
    retposto         TEXT UNIQUE,
    organizo         TEXT,
    organiza_identiga_numero TEXT,
    telefonnumeroj   TEXT NOT NULL DEFAULT '[]',
    retposhtadresoj  TEXT NOT NULL DEFAULT '[]',
    kampoj           TEXT NOT NULL DEFAULT '{}',
    konfirmita       INTEGER NOT NULL DEFAULT 0,
    kategorioj       TEXT NOT NULL DEFAULT '[]',
    noto             TEXT,
    postadreso       TEXT,
    postkodo         TEXT,
    bildo            TEXT,
    kreita_je        TEXT NOT NULL,
    modifita_je      TEXT NOT NULL
);
"""
_IDX_KONTAKTOJ_NOMO = """
CREATE INDEX IF NOT EXISTS idx_kontaktoj_nomo ON kontaktoj(nomo);
"""
_IDX_KONTAKTOJ_RETPOSTO = """
CREATE INDEX IF NOT EXISTS idx_kontaktoj_retposto ON kontaktoj(retposto);
"""

# ── Categories (CRUDService) ─────────────────────────────────────────────────

_CREATE_KATEGORIOJ = """
CREATE TABLE IF NOT EXISTS kategorioj (
    uuid       TEXT PRIMARY KEY,
    nomo       TEXT NOT NULL UNIQUE,
    koloro     TEXT NOT NULL DEFAULT '',
    kreita_je  TEXT NOT NULL,
    modifita_je TEXT NOT NULL
);
"""

# ── Schema version tracking ──────────────────────────────────────────────────

_CREATE_SCHEMA_VERSION = """
CREATE TABLE IF NOT EXISTS _schema_version (
    version   INTEGER PRIMARY KEY,
    applied_je TEXT NOT NULL
);
"""

# ── Sync backlog (pending IMAP flag updates) ────────────────────────────────

_CREATE_SYNC_BACKLOG = """
CREATE TABLE IF NOT EXISTS _sync_backlog (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    msg_uuid    TEXT NOT NULL,
    konto_id    TEXT NOT NULL,
    dosierujo_id TEXT,
    imap_uid    INTEGER,
    legita      INTEGER,
    forigita    INTEGER,
    stelo       INTEGER,
    spamo       INTEGER,
    kreita_je   TEXT NOT NULL,
    last_attempt TEXT,
    provis      INTEGER NOT NULL DEFAULT 0
);
"""
_IDX_SYNC_BACKLOG_MSG = """
CREATE INDEX IF NOT EXISTS idx_sync_backlog_msg ON _sync_backlog(msg_uuid);
"""

_IDX_SUBSKRIBOJ_NOMO = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_subskriboj_nomo ON subskriboj(nomo);
"""

# ── All DDL statements in creation order ─────────────────────────────────────

_SCHEMA_STATEMENTS: list[str] = [
    # Tables
    _CREATE_KONTOJ,
    _CREATE_DOSIERUJOJ,
    _CREATE_MESAGXOJ,
    _CREATE_ALDONAJXOJ,
    _CREATE_SUBSKRIBOJ,
    _IDX_SUBSKRIBOJ_NOMO,
    _CREATE_FILTRAJ,
    _CREATE_SPAMO_BLOKOJ,
    _CREATE_KONTAKTOJ,
    _CREATE_KATEGORIOJ,
    _CREATE_SCHEMA_VERSION,
    _CREATE_SYNC_BACKLOG,
    # Indexes (must come after tables)
    _IDX_DOSIERUJOJ_KONTO,
    _IDX_MESAGXOJ_KONTO,
    _IDX_MESAGXOJ_DOSIERUJO,
    _IDX_MESAGXOJ_MESSAGE_ID,
    # _IDX_MESAGXOJ_IMAP_UID moved to migration v3
    # (column may not exist yet on legacy DBs from DDL alone)
    _IDX_MESAGXOJ_DATO,
    _IDX_ALDONAJXOJ_MESAGXO,
    _IDX_KONTAKTOJ_NOMO,
    _IDX_KONTAKTOJ_RETPOSTO,
    _IDX_SYNC_BACKLOG_MSG,
]

# ── FTS5 configuration for contacts ──────────────────────────────────────────

KONTAKTOJ_FTS_CONFIG = FTSConfig(
    table="kontaktoj",
    fts_columns=[
        "nomo",
        "familia_nomo",
        "plena_nomo",
        "retposto",
        "organizo",
        "noto",
    ],
    filter_columns=["konfirmita", "kategorioj"],
    normalize={col: fold_search_text for col in [
        "nomo",
        "familia_nomo",
        "plena_nomo",
        "retposto",
        "organizo",
        "noto",
    ]},
)

# ── Database initialization ──────────────────────────────────────────────────


def _path() -> Path:
    """Get database path using A.core.paths."""
    return data_dir() / "lien.db"


def ensure_dirs() -> None:
    """Ensure data directory exists."""
    _ensure_dirs()


def get_db(path: Path | str | None = None) -> SQLiteDB:
    """Get database connection with all tables created and migrations applied.

    Args:
        path: Optional override path (default: data_dir() / lien.db)

    Returns:
        SQLiteDB instance with schema + migrations applied
    """
    ensure_dirs()
    resolved = Path(path) if path else _path()

    # Fix legacy double-.db path (old _path() returned str, causing lien.db.db)
    # SQLiteDB with a str name appends .db → old code created "lien.db.db".
    # If the legacy file exists and the correct path doesn't, migrate it.
    legacy = resolved.parent / (resolved.name + ".db")
    if legacy.exists() and not resolved.exists():
        legacy.rename(resolved)

    db = SQLiteDB(resolved)

    for stmt in _SCHEMA_STATEMENTS:
        db.execute(stmt)

    # Apply any pending schema migrations (e.g. imap_uid column)
    from A_lien.data.migrate import migrate as _migrate

    _migrate(db)

    return db


def get_backup_targets() -> list[BackupTarget]:
    """Return backup targets for A-lien."""
    return [
        BackupTarget(
            path=data_dir() / "lien.db",
            category="data",
            module="lien",
            label="Lien database",
        ),
    ]


__all__ = [
    "ensure_dirs",
    "get_db",
    "KONTAKTOJ_FTS_CONFIG",
    "get_backup_targets",
]

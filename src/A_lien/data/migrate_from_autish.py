"""Migration from autish retposto.db to A-lien.

Run with:
    from A_lien.data.migrate_from_autish import migrate
    
    result = migrate()
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from A.core.paths import data_dir as _data_dir
from A.core.paths import ensure_dirs as _ensure_dirs
from A.data.base import SQLiteDB as _SQLiteDB

import uuid


# Legacy autish data path
_LEGACY_DIR = Path.home() / ".local" / "share" / "autish"
_LEGACY_DB = _LEGACY_DIR / "retposto.db"


def migrate() -> dict:
    """Migrate contacts from autish retposto.db to A-lien.
    
    Returns:
        Dict with migration results
    """
    if not _LEGACY_DB.exists():
        return {"skipped": True, "reason": "No legacy data found"}
    
    _ensure_dirs()
    
    # Connect to legacy DB
    legacy = sqlite3.connect(str(_LEGACY_DB))
    legacy.row_factory = sqlite3.Row
    
    # Connect to A-lien DB
    target = _SQLiteDB(str(_data_dir() / "lien.db"))
    
    migrated = 0
    errors = []
    
    # Migrate contacts
    rows = legacy.execute("SELECT * FROM kontakto").fetchall()
    
    for row in rows:
        try:
            # Generate new UUID (preserve old for reference)
            old_uuid = row["uuid"]
            new_uuid = str(uuid.uuid4())
            
            # Parse JSON fields from legacy format
            telefonnumeroj = _parse_json_field(row, "telefonnumeroj", "telefono")
            retposhtadresoj = _parse_json_field(row, "retposhtadresoj", "retposto")
            kampoj = _parse_json_field(row, "kampoj", "kampoj")
            kategorioj = _parse_json_field(row, "kategorioj", "kategorioj")
            lingvoj = _parse_json_field(row, "lingvoj", "lingvoj")
            
            # Insert into A-lien
            now = datetime.now(timezone.utc).isoformat()
            target.execute(
                """INSERT INTO kontaktoj (
                    uuid, nomo, familia_nomo, plena_nomo, 
                    naskigx_dato, naskigx_loko, lingvoj,
                    retposto, organizo, organiza_identiga_numero,
                    telefonnumeroj, retposhtadresoj, kampoj,
                    konfirmita, kategorioj, noto, bildo,
                    kreita_je, modifita_je
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    new_uuid,
                    row["nomo"],
                    row["familia_nomo"],
                    f"{row['nomo']} {row['familia_nomo']}".strip(),
                    row["naskig_dato"],
                    row["naskig_loko"],
                    json.dumps(lingvoj),
                    row["retposto"],
                    row["organizo"],
                    row["organiza_identiga_numero"],
                    json.dumps(telefonnumeroj),
                    json.dumps(retposhtadresoj),
                    json.dumps(kampoj),
                    row["konfirmita"],
                    json.dumps(kategorioj),
                    row["noto"],
                    row["bildo"] if "bildo" in row.keys() else "",
                    now,
                    now,
                ),
            )
            
            migrated += 1
            
        except Exception as e:
            errors.append(f"{row['uuid']}: {e}")
    
    legacy.close()
    
    return {
        "source_rows": len(rows),
        "migrated_rows": migrated,
        "errors": errors,
    }


def _parse_json_field(row: sqlite3.Row, field: str, fallback_field: str) -> dict | list:
    """Parse a JSON field, falling back to simple field if needed."""
    # Try the main field first
    val = row[field]
    if val:
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            pass
    
    # Fallback to simple field (for legacy phone/email migration)
    if fallback_field:
        fallback = row[fallback_field]
        if fallback:
            if field in ("telefonnumeroj",):
                return [{"valoro": fallback, "etikedo": "", "cxefa": True}]
            elif field in ("retposhtadresoj",):
                return [{"valoro": fallback, "etikedo": "", "cxefa": True}]
            else:
                return fallback
    
    return [] if field in ("telefonnumeroj", "retposhtadresoj", "kategorioj", "lingvoj") else {}


__all__ = ["migrate"]
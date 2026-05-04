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
from A_lien.data.storage import get_db as _get_db
from A_lien.keyring import set_password as _set_keyring_pw

import uuid


# Legacy autish data path
_LEGACY_DIR = Path.home() / ".local" / "share" / "autish"
_LEGACY_DB = _LEGACY_DIR / "retposto.db"


def migrate() -> dict:
    """Migrate contacts and email accounts from autish retposto.db to A-lien.
    
    Returns:
        Dict with migration results
    """
    if not _LEGACY_DB.exists():
        return {"skipped": True, "reason": "No legacy data found"}
    
    _ensure_dirs()
    
    # Connect to legacy DB
    legacy = sqlite3.connect(str(_LEGACY_DB))
    legacy.row_factory = sqlite3.Row
    
    # Connect to A-lien DB (creates tables via get_db())
    target = _get_db()
    
    results = {
        "contacts": {"source_rows": 0, "migrated_rows": 0, "errors": []},
        "accounts": {"source_rows": 0, "migrated_rows": 0, "errors": []},
    }
    
    # ── Migrate contacts (verified only) ────────────────────────────────────
    _migrate_contacts(legacy, target, results)
    
    # ── Migrate email accounts ──────────────────────────────────────────────
    _migrate_accounts(legacy, target, results)
    
    legacy.close()
    
    # Flatten results for backwards compatibility
    total_source = results["contacts"]["source_rows"] + results["accounts"]["source_rows"]
    total_migrated = results["contacts"]["migrated_rows"] + results["accounts"]["migrated_rows"]
    all_errors = results["contacts"]["errors"] + results["accounts"]["errors"]
    
    return {
        "source_rows": total_source,
        "migrated_rows": total_migrated,
        "errors": all_errors,
        "details": results,
    }


def _migrate_contacts(legacy: sqlite3.Connection, target: _SQLiteDB, results: dict) -> None:
    """Migrate verified contacts only."""
    # Check if kontakto table exists
    tables = [r[0] for r in legacy.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    if "kontakto" not in tables:
        return
    
    rows = legacy.execute("SELECT * FROM kontakto WHERE konfirmita = 1").fetchall()
    results["contacts"]["source_rows"] = len(rows)
    
    for row in rows:
        try:
            new_uuid = str(uuid.uuid4())
            
            telefonnumeroj = _parse_json_field(row, "telefonnumeroj", "telefono")
            retposhtadresoj = _parse_json_field(row, "retposhtadresoj", "retposto")
            kampoj = _parse_json_field(row, "kampoj", "kampoj")
            kategorioj = _parse_json_field(row, "kategorioj", "kategorioj")
            lingvoj = _parse_json_field(row, "lingvoj", "lingvoj")
            
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
            
            results["contacts"]["migrated_rows"] += 1
            
        except Exception as e:
            results["contacts"]["errors"].append(f"{row['uuid']}: {e}")


def _migrate_accounts(legacy: sqlite3.Connection, target: _SQLiteDB, results: dict) -> None:
    """Migrate email accounts from legacy konto table."""
    tables = [r[0] for r in legacy.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    if "konto" not in tables:
        return
    
    rows = legacy.execute("SELECT * FROM konto").fetchall()
    results["accounts"]["source_rows"] = len(rows)
    
    for row in rows:
        try:
            new_uuid = str(uuid.uuid4())
            email = row["retposto"]
            now = datetime.now(timezone.utc).isoformat()
            
            # Determine IMAP username: imap_uzantonomo > uzantonomo > email
            imap_user = row["imap_uzantonomo"] or row["uzantonomo"] or email
            smtp_user = row["smtp_uzantonomo"] or row["uzantonomo"] or email
            
            # Insert account into A-lien kontoj table
            target.execute(
                """INSERT INTO kontoj (
                    uuid, ordo, nomo, retposto,
                    imap_servilo, imap_haveno, imap_ssl,
                    smtp_servilo, smtp_haveno, smtp_tls,
                    imap_uzantonomo, smtp_uzantonomo,
                    webmail_url,
                    sieve_servilo, sieve_haveno, sieve_starttls, sieve_uzantonomo,
                    subskribo,
                    kreita_je, modifita_je
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    new_uuid,
                    row["ordo"],
                    row["nomo"],
                    email,
                    row["imap_servilo"],
                    row["imap_haveno"],
                    row["imap_ssl"],
                    row["smtp_servilo"],
                    row["smtp_haveno"],
                    row["smtp_tls"],
                    imap_user,
                    smtp_user,
                    row["webmail_url"],
                    row["sieve_servilo"],
                    row["sieve_haveno"],
                    row["sieve_starttls"],
                    row["sieve_uzantonomo"],
                    row["subskribo"],
                    now,
                    now,
                ),
            )
            
            # Migrate keyring password: autish-retposto/{id} → A-lien/{new_uuid}
            # autish uses: keyring.get_password("autish-retposto", str(account_id))
            password = None
            try:
                import keyring
                account_id = row["id"]
                password = keyring.get_password("autish-retposto", str(account_id))
            except Exception:
                pass
            
            if password:
                _set_keyring_pw(new_uuid, password)
                # Remove old keyring entry
                try:
                    import keyring
                    keyring.delete_password("autish-retposto", str(account_id))
                except Exception:
                    pass
            
            results["accounts"]["migrated_rows"] += 1
            
        except Exception as e:
            results["accounts"]["errors"].append(f"{row['retposto']}: {e}")


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
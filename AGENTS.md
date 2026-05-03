# AGENTS.md — Rules for A-lien

This file extends [root AGENTS.md](../AGENTS.md).

## Relationship to A-core

**A-lien depends on A-core** for:
- `A` package imports (i18n, output, subprocess, SQLite)
- Plugin discovery via entry points
- `A.core.service.CRUDService` — CRUD + soft-delete + undo + FTS5 + fuzzy search
- `A.core.paths` — XDG path resolution
- `A.core.export`, `A.core.import_` — import/export utilities
- `A.utils.normalize.fold_search_text` — accent-insensitive search normalization
- `A.data.base.SQLiteDB` — WAL mode SQLite

**All source code must import from `A`, never duplicate utilities.**

## Combined Plugin

A-lien combines two autish commands:
- retposto (email)
- kontakto (contacts)

This is intentional — they share the same SQLite database (`lien.db`) for contacts→email linking.

## Architecture

```
src/A_lien/
├── __init__.py            # exports: app
├── cli.py                 # Typer app (lien → retposto/kontakto sub-apps)
├── keyring.py             # Keyring abstraction (wraps `keyring` library)
├── imap.py                # IMAP sync logic (ThreadPoolExecutor)
├── smtp.py                # SMTP send logic (attachments, signatures)
├── utils.py               # VCF import/export, contact normalization
├── service/
│   ├── __init__.py        # exports both services
│   ├── kontakto_service.py # KontaktoService (contacts CRUD + FTS5 + VCF)
│   └── retposto_service.py # RetpostoService (accounts, IMAP, SMTP, filters)
└── data/
    ├── __init__.py
    ├── storage.py          # SQLite schema + FTSConfig + get_db()
    └── migrate.py          # Schema migrations
```

**Rationale for directory structure:**
- Services in separate files (`service/`) — RetpostoService has 20+ methods, KontaktoService has 15+. Combined = 800+ lines.
- IMAP and SMTP are extracted as modules — complex enough (concurrent fetch, attachment handling) to deserve own files.
- Keyring is a local abstraction — replaced by `A.core.keyring` when that exists.

## Database Schema

All tables in `lien.db` at `A.core.paths.data_dir()`. WAL mode via `A.data.base.SQLiteDB`.

### Tables

| Table | Description | CRUDService | FTS5 |
|-------|-------------|-------------|------|
| `kontoj` | Email accounts | Yes | No |
| `dosierujoj` | IMAP folders | No (manual) | No |
| `mesagxoj` | Messages | No (manual) | No |
| `aldonajxoj` | Attachments | No (manual) | No |
| `subskriboj` | Signatures | Yes | No |
| `filtraj` | Sieve filters | Yes | No |
| `spamo_blokoj` | Spam blocks | Yes | No |
| `kontaktoj` | Contacts | Yes | Yes (FTS5) |
| `kategorioj` | Categories | Yes | No |

### Security

- **No `pasvorto` column** in `kontoj` — passwords go to system keyring
- Keyring service pattern: `keyring.get_password("A-lien/{account_uuid}", "password")`
- Local `keyring.py` abstraction wraps `keyring` library; trivial to swap to `A.core.keyring` later

### Contacts Schema (with FTS5)

Multi-value fields stored as JSON arrays (phones, emails, languages, categories):
- `telefonnumeroj` — JSON array of `{valoro, etikedo, cxefa}`
- `retposhtadresoj` — JSON array of `{valoro, etikedo, cxefa}`
- `kampoj` — JSON object for custom fields
- `lingvoj`, `kategorioj` — JSON arrays

FTS5 index on: `nomo`, `familia_nomo`, `plena_nomo`, `retposto`, `organizo`, `noto`
Filters on: `konfirmita`, `kategorioj`

## Service Layer

### KontaktoService (extends CRUDService)

```
CRUD ─┬─ create, get, update, delete (JSON serialized)
      ├─ list, search, search_fts, search_fuzzy (inherited from CRUDService)
      └─ undo (inherited)

Domain ─┬─ find_by_email(email) → dict | None
         ├─ find_by_uuid_prefix(prefix) → list[dict]
         ├─ find_duplicates(contact) → list[dict]
         ├─ search_contacts(query, fuzzy, filters) → list[dict]
         ├─ import_vcf(path) → int
         ├─ export_vcf(uuid, path) → None
         ├─ list/create/update/delete_category()
         └─ import/export via A.core.export/import_
```

### RetpostoService (extends CRUDService)

```
CRUD ── accounts (kontoj), signatures, filters, spam blocks

Domain ─┬─ create_account(data, password) → stores pw in keyring
         ├─ get_password(uuid) → str
         ├─ sync_account(uuid) → SyncResult (IMAP via imap.py)
         ├─ sync_all() → dict[str, SyncResult] (ThreadPoolExecutor)
         ├─ send_email(account, to, subject, body, ...) → str (SMTP via smtp.py)
         ├─ get_messages(account, folder, page, per_page) → list[dict]
         ├─ mark_read/starred(uuid, bool) → None
         ├─ get_attachment/save_attachment(uuid) → None
         ├─ list/create/update/delete_signature()
         ├─ list/create/update/delete_filter()
         ├─ upload_filters(account) → None (Sieve)
         └─ list/add/remove_spam_block()
```

## Code Standards

1. Use `tr()` for all user-facing strings
2. Use `error()` for errors, `info()` for info
3. Type hints on all public functions
4. Docstrings on all public functions
5. Tests required for all modules
6. Use WAL mode for SQLite
7. Store passwords in system keyring (keyring library), never in SQLite
8. Use A-core `CRUDService` — never write raw SQL for CRUD operations
9. JSON arrays for multi-value fields (consistent with A-encik)

## CLI Command Tree

```
lien
├── retposto
│   ├── ls                        # List accounts
│   ├── vidi                      # View account details
│   ├── aldoni-konton             # Interactive account setup + keyring
│   ├── forigi-konton             # Delete account + keyring entry
│   ├── preni                     # Fetch mail (--account to filter)
│   ├── sendi                     # Compose + send
│   ├── dosierujoj                # List IMAP folders
│   ├── mesagxoj                  # List messages in folder
│   ├── montru                    # View single message
│   ├── subskriboj                # Signature management
│   ├── filtraj                   # Sieve filter management
│   └── spamo                     # Spam block management
│
└── kontakto
    ├── ls                        # List contacts
    ├── serci                     # Search (FTS5 + fuzzy + filters)
    ├── vidi                      # View contact detail
    ├── aldoni                    # Add contact
    ├── modifi                    # Modify contact
    ├── forigi                    # Delete (soft)
    ├── importi                   # Import VCF
    ├── eksporti                  # Export VCF
    ├── purigi                    # Clean duplicates
    ├── kategorio                 # Category management
    └── malfari                   # Undo last operation
```

## What to Avoid

- Don't duplicate A-core utilities
- Don't skip i18n (use `tr()`)
- Don't use `print()` — use `A` output functions
- Don't hardcode paths — use `A.core.paths`
- Don't implement utilities that should be in core
- Don't store passwords in plain text
- **Don't wait for A.core.keyring** — implement local `keyring.py` now, swap later

## Implementation Phases

### Phase 1: Foundation (DB + Storage)
- `data/storage.py` — complete schema + FTSConfig + `get_db()`
- `data/migrate.py` — migration logic
- `keyring.py` — keyring abstraction

### Phase 2: Contacts (KontaktoService)
- `service/kontakto_service.py` — full CRUD + FTS5 + JSON + VCF
- `utils.py` — VCF helpers, normalization
- CLI commands for kontakto

### Phase 3: Account Management + Keyring
- `service/retposto_service.py` — account CRUD
- CLI: `aldoni-konton`, `forigi-konton`, `ls`, `vidi`

### Phase 4: IMAP + SMTP
- `imap.py`, `smtp.py` — sync + send engines
- CLI: `preni`, `sendi`, `dosierujoj`, `mesagxoj`, `montru`
- Signature management

### Phase 5: Filters + Polish
- Sieve filters + spam blocks
- `filtraj`, `spamo` CLI sub-typers
- `purigi` (duplicate cleanup)
- Polish all help text, error messages

## Migration from autish

A-lien supports migration from autish retposto.db:

| Legacy | Target | Description |
|--------|--------|-------------|
| retposto.db → kontakto | A-lien → kontaktoj | Contacts (148 entries) |
| keyring: autish-retposto-* | A-lien/* | IMAP passwords |

**CLI:**
```bash
A migri           # Run migrations (imports contacts)
A migri-keyring  # Migrate keyring passwords
```

**Programmatic:**
```python
from A_lien.data.migrate_from_autish import migrate
result = migrate()
```

Features:
- JSON field conversions (telefono → telefonnumeroj array)
- Preserves timestamps
- Idempotent (safe to run multiple times)

## Branch Convention

All A-* repos use `main` as the primary branch. Use `main` for all development.

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
├── cli/                   # Typer app split by functional unit
│   ├── __init__.py        # Main app + wire sub-typers
│   ├── retposto.py        # retposto commands (preni, sendi, vidi, serci, dosierujoj)
│   ├── konton.py          # Account management (ls, vidi, aldoni, forigi, modifi)
│   ├── subskribo.py       # Signature management (ls, aldoni, forigi)
│   ├── filtraj.py         # Sieve filter management (ls, vidi, aldoni, forigi, aktivi)
│   ├── kontakto.py        # kontakto core commands (ls, serci, vidi, malfari, purigi)
│   ├── kontakto_edit.py   # kontakto write commands (aldoni, modifi, forigi, importi, eksporti)
│   ├── kategorio.py       # Category management (ls, aldoni, forigi)
│   ├── retposto_search.py # retposto search command (serci)
│   └── spamo.py           # Spam block management (ls, aldoni, forigi, sinkronigi)
├── sieve_spamo.py         # Sieve generation + merge for spam rules
├── imap/                   # IMAP sync engine (split from monolithic imap.py)
│   ├── __init__.py         # Re-exports all public API
│   ├── helpers.py          # Header decoding, email parsing, auto-contact filters
│   ├── client.py           # IMAPClient, MessageStore protocol, SyncResult
│   └── sync.py             # sync_account, sync_accounts_concurrent
├── keyring.py             # Keyring abstraction (wraps `keyring` library)
├── smtp.py                # SMTP send logic (attachments, signatures)
├── utils.py               # VCF import/export, contact normalization
├── service/
│   ├── __init__.py        # exports both services
│   ├── kontakto_service.py    # KontaktoService (CRUD + FTS5 + serialization)
│   ├── kontakto_vcf.py        # VCF import/export (KontaktoVCFMixin)
│   ├── kontakto_category.py   # Category management (KontaktoCategoryMixin)
│   ├── retposto_service.py       # RetpostoService (accounts, IMAP/SMTP, search, messages)
│   ├── retposto_signature.py     # Signature management (RetpostoSignatureMixin)
│   ├── retposto_contact_mixin.py # Contact auto-creation (RetpostoContactMixin)
│   └── retposto_spamo.py         # Spam block CRUD + Sieve sync (RetpostoSpamoMixin)
└── data/
    ├── __init__.py
    ├── storage.py          # SQLite schema + FTSConfig + get_db()
    └── migrate.py          # Schema migrations
```

**Rationale for directory structure:**
- CLI is split into a package (`cli/`) — no file exceeds 500 lines for readability.
- Each CLI file covers one functional area (retposto, konton, kontakto, filters, etc.)
- Services use Python mixin pattern: `retposto_service.py` + `retposto_signature.py`;
  `kontakto_service.py` + `kontakto_vcf.py` + `kontakto_category.py`
- IMAP is split into a package (`imap/`) — client, helpers, sync functions separated.
- No source file exceeds 500 lines.
- SMTP remains a single file (144 lines, simple send-only).
- Keyring is a local abstraction — replaced by `A.core.keyring` when that exists.

## Database Schema

All tables in `lien.db` at `A.core.paths.data_dir()`. WAL mode via `A.data.base.SQLiteDB`.

### DDL vs. Migration Contract

**DDL creates, migration alters.** This separation is critical:

| Concern | Responsibility | Location |
|---------|---------------|----------|
| Table creation | `CREATE TABLE IF NOT EXISTS` | `storage.py` (_SCHEMA_STATEMENTS) |
| Column changes | `ALTER TABLE` via `migrate()` | `migrate.py` (_MIGRATIONS) |
| Index creation | Both | `storage.py` for fresh DBs, `migrate.py` for legacy upgrades |

Rules:
1. **`CREATE TABLE IF NOT EXISTS` does NOT add columns.** Never rely on DDL replay to alter an existing table. Schema changes must go through migrations.
2. **`get_db()` must call `migrate()`.** See the bug history in issue #31 — A-lien forgot this, causing `no such column: imap_uid`.
3. **Indexes referencing new columns must NOT be in `_SCHEMA_STATEMENTS`.** They go in the migration step that adds the column, since the DDL loop runs before migrations and would fail on legacy DBs.
4. **Guard all migration steps.** Use `pragma_table_info()` to check column existence before `ALTER TABLE ADD/DROP COLUMN`. Fresh DBs already have the latest schema and don't need column migrations.

### Tables

| Table | Description | CRUDService | FTS5 |
|-------|-------------|-------------|------|
| `kontoj` | Email accounts | Yes | No |
| `dosierujoj` | IMAP folders | No (manual) | No |
| `mesagoj` | Messages | No (manual) | No |
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

## Optional Dependency Policy

When an optional dependency is missing (e.g., `keyring`):
1. Ask user to install: prompt with `typer.confirm(..., default=True)`
2. Install on confirmation via `pip install <pkg>`
3. Exit gracefully if declined

## CLI Command Tree

```
lien
├── retposto
│   ├── preni                     # Fetch mail (--konto to filter)
│   ├── sendi                     # Compose + send
│   ├── vidi <uuid>               # View single message by UUID
│   ├── serci                     # Search messages (FTS + filters)
│   ├── dosierujoj                # List IMAP folders
│   ├── mesagoj                  # [DEPRECATED] Use serci instead
│   ├── konton                    # Account management
│   │   ├── ls                    #   List accounts
│   │   ├── vidi                  #   View account details
│   │   ├── aldoni                #   Add account
│   │   ├── forigi                #   Delete account(s)
│   │   └── modifi                #   Modify account
│   ├── subskribo                 # Signature management
│   │   ├── ls                    #   List signatures
│   │   ├── aldoni                #   Add signature
│   │   └── forigi                #   Delete signature
│   └── filtraj                   # Sieve filter management
│       ├── ls                    #   List filters
│       ├── vidi                  #   View filter
│       ├── aldoni                #   Add filter
│       ├── forigi                #   Delete filter
│       └── aktivi                #   Enable/disable filter
│   └── spamo                     # Spam block management
│       ├── ls                    #   List blocks
│       ├── aldoni                #   Add block
│       ├── forigi                #   Remove block
│       └── sinkronigi            #   Sync to ManageSieve server
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



## Package Manager: `uv` is Required

All A-ecosystem development **must** use `uv` as the package manager:

| Operation | Command |
|-----------|---------|
| Install dependencies | `uv pip install <pkg>` |
| Install project in dev mode | `uv pip install -e .` |
| Run tests | `uv run pytest tests/` |
| Install CLI tools (poetry, etc.) | `uv tool install <tool>` |
| Add dev dependency | `uv add --dev <pkg>` |

**Exceptions:**
- `pip` in README install instructions is acceptable for end users who may not have `uv`
- Readthedocs platform build may require `pip` (platform constraint)
- Runtime `install-on-confirmation` code may fall back to `pip` if `uv` is unavailable (see A-core AGENTS.md)

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
- CLI: `preni`, `sendi`, `dosierujoj`, `mesagoj`, `montru`
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

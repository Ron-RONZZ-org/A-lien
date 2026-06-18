# Issue #60: subskribo aldoni -D/--dosiero file input + name-based lookup

## Problem
- `subskribo aldoni` required inline `--teksto/-t` — no way to load from file
- `--html` was a boolean flag, not a file path — users tried `--html /path/to/file.html` and got errors
- No way to reference signatures by name (needed for `retposto sendi --subskribo rz-pro`)

## Solution Implemented (commit 1ad6a31)

### Schema
- Added `UNIQUE INDEX idx_subskriboj_nomo ON subskriboj(nomo)` — keeps UUID as PK (CRUDService compat)
- Migration v7: deduplicates existing duplicate names by appending `-{uuid[:4]}` suffix, then creates index

### Service (`retposto_signature.py`)
- `find_signature_by_name(nomo)` — exact name lookup via `CRUDService.get_by_field("nomo", nomo)`
- `resolve_signature(ident)` — tries UUID prefix match first, falls back to exact name match
- Used by CLI `forigi` and intended for `retposto sendi --subskribo` integration

### CLI (`subskribo.py`)
- **`aldoni`**: Replaced `--html` boolean with `--dosiero/-D` file path. `-t` and `-D` are now mutually exclusive. Auto-detects HTML from `.html`/`.htm` extension. `--html` flag kept as override.
- **`forigi`**: Now accepts signature names or UUID prefixes (resolved via `resolve_signature()`)

## Architectural Decision
- **Rejected**: Dropping UUID PK for `nomo` PK (would break CRUDService)
- **Rejected**: Refactoring CRUDService for non-UUID PKs (disproportionate cost)
- **Approved**: UUID PK + `UNIQUE(nomo)` + `resolve_signature()` — achieves same UX with zero framework changes

## Files Changed
| File | Change |
|------|--------|
| `storage.py` | Added `_IDX_SUBSKRIBOJ_NOMO` to schema |
| `migrate.py` | Migration v7: dedup names + create unique index |
| `retposto_signature.py` | Added `find_signature_by_name()`, `resolve_signature()` |
| `subskribo.py` | Rewrote `aldoni` for `-D/--dosiero`; `forigi` for name-or-UUID |
| `test_retposto_service.py` | 7 new service-level tests |
| `test_subskribo_cli.py` | 21 new CLI tests |

## User-Simulation Verification
All flows verified: file input, inline text, HTML auto-detect, mutual exclusion, delete by name/UUID, non-existent graceful handling.

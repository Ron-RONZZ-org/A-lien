# Issue #55: Kontakto CLI option rename + postadreso/postkodo columns

## Problem
CLI options on `kontakto aldoni` and `kontakto modifi` were misconfigured:
- `--nomo/-n` pointed to given name, should be family name
- `--familia-nomo/--fn` pointed to family name, should be given name  
- `--plena-nomo/--pn` was redundant (auto-constructible)
- `--retposto/-r` was redundant (mergeable into `--retposhtadreso`)
- Missing `--poŝtkodo/-pk` option
- `postadreso` column was missing from DB schema (bug - crashes on `--postadreso` use)

## Fix (commit 46e324a)

### CLI changes
| Old | New |
|-----|-----|
| `--nomo/-n` → given name | `--persona-nomo/-pn` → given name |
| `--familia-nomo/--fn` → family name | `--nomo/-n` → family name |
| `--plena-nomo/--pn` | removed (auto-constructed) |
| `--retposto/-r` | removed (auto-extracted from retposhtadresoj) |
| *(missing)* | `--poŝtkodo/-pk` added |
| `--postadreso/-p` | kept (was crashing - no column) |

### DB schema changes
- `postadreso TEXT` added to `_CREATE_KONTAKTOJ` (bug fix)
- `postkodo TEXT` added to `_CREATE_KONTAKTOJ` (new feature)
- Migration v6: `_add_kontaktoj_fields()` guarded with `pragma_table_info()`

### Logic changes
- `plena_nomo` auto-constructed from persona_nomo + nomo
- `retposto` auto-extracted from retposhtadresoj (primary or first email)
- `split_full_name` import removed (no longer needed)

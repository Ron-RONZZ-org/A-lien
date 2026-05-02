# AGENTS.md — Rules for A-lien

This file extends root A-core AGENTS.md for the A-lien plugin.

## Relationship to A-core

**A-lien depends on A-core** for:
- `A` package imports (i18n, output, subprocess, SQLite)
- Plugin discovery via entry points
- Shared utilities
- **API Reference**: See [A-core AGENTS.md](https://github.com/Ron-RONZZ-org/A-core/blob/main/AGENTS.md#api-reference)

**All source code must import from `A`, never duplicate utilities.**

## Combined Plugin

A-lien combines two autish commands:
- retposto (email)
- kontakto (contacts)

This is intentional — they share the same SQLite database for contacts->email linking.

## If You Need Something in Core

If you need a utility that should be in A-core:

1. **Search existing issues** on [A-core](https://github.com/Ron-RONZZ-org/A-core/issues)
2. **Create an issue** describing the need
3. **Wait for core enhancement** before implementing locally
4. **Use feature detection** when available

## Architecture

```
src/A_lien/
├── __init__.py       # Plugin exports
├── cli.py           # Typer app with subcommands
├── service.py     # IMAP/SMTP + business logic
└── data/
    └── storage.py # SQLite (uses A.data.base)
```

## Code Standards

1. Use `tr()` for all user-facing strings
2. Use `error()` for errors, `info()` for info
3. Type hints on all public functions
4. Docstrings on all public functions
5. Tests required for all modules
6. Use WAL mode for SQLite
7. Store passwords in system keyring (keyring library)

## What to Avoid

- Don't duplicate A-core utilities
- Don't skip i18n (use `tr()`)
- Don't use `print()` — use `A` output functions
- Don't hardcode paths — use `A.core.paths`
- Don't implement utilities that should be in core
- Don't store passwords in plain text
# A-lien

## Context

This module uses [A-workspace](https://github.com/Ron-RONZZ-org/A-workspace) as a **git submodule**:


```bash
# Clone with submodules
git clone --recurse-submodules https://github.com/Ron-RONZZ-org/A-lien.git
# Or if already cloned:
git submodule update --init --recursive
```

**DO NOT edit workspace/ directly** - see [A-workspace](https://github.com/Ron-RONZZ-org/A-workspace) for master context.


A-lien - email and contacts microapp

## Install

```bash
pip install A-lien
```

Requires **A-core** (automatically installed as dependency).

## Usage

```bash
# Account management (konton subcommand)
A lien retposta konton ls          # List email accounts
A lien retposta konton aldoni -r user@domain.com -p password  # Add account
A lien retposta konton modifi <UUID> --nomo "My Account"   # Modify account
A lien retposta konton forigi <UUID>  # Delete account

# Email operations
A lien retposto preni   # Fetch mail
A lien retposto sendi -t user@domain.com -s "Subject"    # Send email

# Contact management
A lien kontakto ls     # List contacts
A lien kontakto serci <query>  # Search contacts
```

## Commands

A-lien provides three subcommands:

| Command | Description |
|---------|-------------|
| retposto | Email management (IMAP/SMTP) |
| └─ konton | Account management (ls, vidi, aldoni, forigi, modifi) |
| kontakto | Contact management |

## About

A-lien is a plugin for the [A](https://github.com/Ron-RONZZ-org/A-core/) framework.

**A-lien depends on A-core** for:
- Plugin discovery via entry points
- i18n (tr() for multilingual support)
- SQLite with WAL mode
- Shared utilities (error(), info(), run())

See the [A-core documentation](https://github.com/Ron-RONZZ-org/A-core/) for more on the framework.

## Migration from autish

A-lien supports migration from autish:

```bash
A migri           # Run migrations
A migri-keyring  # Migrate keyring passwords
```

| Legacy | Target | Description |
|--------|--------|-------------|
| retposto.db → kontakto | A-lien → kontaktoj | Contacts |
| keyring: autish-retposto-* | A-lien/* | IMAP passwords |

## History

A-lien combines [autish retposto](https://github.com/Ron-RONZZ-org/autish/) and [autish kontakto](https://github.com/Ron-RONZZ-org/autish/) into one plugin.

## License

GPL-3.0-only
---

**Branch:** Use `main` for all development.

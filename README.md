# A-lien

A-lien - email and contacts microapp

## Install

```bash
pip install A-lien
```

Requires **A-core** (automatically installed as dependency).

## Usage

```bash
A lien retposto ls       # List email accounts
A lien retposto preni   # Fetch mail
A lien kontakto ls     # List contacts
A lien kontakto serci <query>  # Search contacts
```

## Commands

A-lien provides two subcommands:

| Command | Description |
|---------|-------------|
| retposto | Email management (IMAP/SMTP) |
| kontakto | Contact management |

## About

A-lien is a plugin for the [A](https://github.com/Ron-RONZZ-org/A-core/) framework.

**A-lien depends on A-core** for:
- Plugin discovery via entry points
- i18n (tr() for multilingual support)
- SQLite with WAL mode
- Shared utilities (error(), info(), run())

See the [A-core documentation](https://github.com/Ron-RONZZ-org/A-core/) for more on the framework.

## History

A-lien combines [autish retposto](https://github.com/Ron-RONZZ-org/autish/) and [autish kontakto](https://github.com/Ron-RONZZ-org/autish/) into one plugin.

## License

GPL-3.0-only
# A-workspace

Shared workspace context for A project modules.

## Purpose

This repo contains the **master context** that AI agents use when working on A project modules. It ensures consistent context across all `A-*` repositories.

## Contents

| File | Description |
|------|-------------|
| `AGENTS.md` | Master context - architecture, patterns, API reference |

## Usage

Each A-* module links to this workspace:

- **README.md**: "For context, see [A-workspace](./workspace/)"
- **AGENTS.md**: Extends root `./AGENTS.md`

```markdown
## Context

For architecture and API reference, see [A-workspace](./workspace/AGENTS.md).
```

## Modules

Each module extends this workspace:

| Module | Repository |
|--------|-----------|
| A-core | https://github.com/Ron-RONZZ-org/A-core |
| A-tempo | https://github.com/Ron-RONZZ-org/A-tempo |
| A-vorto | https://github.com/Ron-RONZZ-org/A-vorto |
| A-encik | https://github.com/Ron-RONZZ-org/A-encik |
| A-sistemo | https://github.com/Ron-RONZZ-org/A-sistemo |
| A-organizi | https://github.com/Ron-RONZZ-org/A-organizi |
| A-lien | https://github.com/Ron-RONZZ-org/A-lien |
| A-medio | https://github.com/Ron-RONZZ-org/A-medio |

## Updating

When master context changes:

1. Update `AGENTS.md` here
2. Push to GitHub
3. Each module can refresh their reference

## License

GPL-3.0-only (same as A modules)
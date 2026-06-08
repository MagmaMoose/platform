# Quick Start

```bash
mise install
pnpm install
uv sync --all-packages
pnpm turbo run lint typecheck test build
pnpm lint
pnpm test
pnpm --filter @calebsargeant/diatreme test
pnpm --filter mikrotik-minder-worker test
uv run --package mikrotik-minder-agent pytest
uvx ruff check .
pnpm --filter mikrotik-minder-worker dev
mkdocs serve
mkdocs build
```

Docs require `mkdocs-material`; use `uvx --from mkdocs --with mkdocs-material mkdocs build` if it is not installed locally.

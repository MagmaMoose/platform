# Setup

## Toolchain

Install the pinned tools and dependencies from the repo root:

```bash
mise install
pnpm install
uv sync --all-packages
```

## Common Checks

```bash
pnpm turbo run lint typecheck test build
uvx ruff check .
```

For focused app checks:

```bash
pnpm --filter @calebsargeant/diatreme test
pnpm --filter mikrotik-minder-worker test
uv run --package mikrotik-minder-agent pytest
```

## Local Services

Run the Dunmir Worker locally with:

```bash
pnpm --filter mikrotik-minder-worker dev
```

Worker secrets should be set through `.dev.vars` for local-only development or `wrangler secret put` for deployed environments. Do not commit `.env*`, `.dev.vars*`, private keys, or generated secret material.

## Docs

The published docs surface is MkDocs Material:

```bash
mkdocs serve
mkdocs build
```

If MkDocs is not installed globally, use:

```bash
uvx --from mkdocs --with mkdocs-material mkdocs build
```

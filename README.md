# platform

MagmaMoose's **public** monorepo — the "golden stack" (pnpm · uv · Turborepo ·
mise) that consolidates our open-source products and the shared packages they're
built on. Proprietary apps live in the private counterpart,
[`platform-pro`](https://github.com/MagmaMoose/platform-pro), and consume these
packages via a submodule.

## What's inside

### Shared packages (`packages/*`)

| Package | Purpose |
| --- | --- |
| `@platform/config` | Shared `tsconfig` / `vitest` / `prettier` / `ruff` — one source of truth instead of a copy per app. |
| `@platform/schemas` | The typed contract: zod (TS) + Pydantic v2 (Python), same shapes. |
| `@platform/cf-auth` | Shared Stytch B2B session auth for Cloudflare. Claim core (was duplicated verbatim) + Web Crypto validator (Workers) + jose validator (Pages). |
| `@platform/api-client` | Typed client + TanStack Query hooks (placeholder per spec). |
| `@platform/ui` | Shared shadcn **web** components (placeholder; never React Native). |

### Apps (`apps/*`)

| App | What it is | License |
| --- | --- | --- |
| `diatreme` | GitHub Marketplace **Action** for semantic release + Docker image promotion, plus its Cloudflare Worker. | MIT |
| `mikrotik-minder` | "**Dun Mir**" — headless MikroTik maintenance platform: Cloudflare Worker (Hono + D1 + R2) control plane, Python agent (RouterOS), Helm chart. | Apache-2.0 |

## Develop

```bash
mise install        # Node 22 + Python 3.12 (+ pnpm, uv)
pnpm install        # JS/TS workspaces
uv sync             # Python workspace (mikrotik-minder agent)
pnpm turbo run lint typecheck test build
```

## Toolchain

- **pnpm** workspaces (JS deps) · **uv** (Python deps) · **Turborepo** (tasks) · **mise** (versions)
- **Node 22** · **Python 3.12** — pinned in `mise.toml`
- Lint/format: **Ruff** (Python), **Prettier** (JS/TS); quality gates in `.pre-commit-config.yaml`

## Note

This is the **first consolidation step**. The apps' original repos still serve
production; this monorepo is additive and does not replace them yet. See
[`CLAUDE.md`](CLAUDE.md) for conventions and the planned follow-ups.

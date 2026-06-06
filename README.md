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
| `diatreme` | Deployable Cloudflare **Worker** for Diatreme (token broker / commit signer / Copilot quota & review service). | MIT |
| `chargate` | Security + lint **scan scripts** (Trivy, Semgrep, TruffleHog, Checkov, ESLint, Hadolint, ShellCheck, …) — the single source of truth. | MIT |
| `dunmir` | "**Dun Mir**" (formerly Mikrotik Minder) — headless MikroTik maintenance platform: Cloudflare Worker (Hono + D1 + R2) control plane, Python agent (RouterOS), Helm chart. | Apache-2.0 |

**Marketplace actions live in their own repos.** `diatreme` and `chargate` are
GitHub Marketplace **composite actions**, and the Marketplace is **one repo per
action** — so each `action.yml` stays in its source repo
([MagmaMoose/diatreme](https://github.com/MagmaMoose/diatreme),
[MagmaMoose/chargate](https://github.com/MagmaMoose/chargate)) and *references* the
code kept here (diatreme's worker; chargate's scan scripts).

## Develop

```bash
mise install        # Node 22 + Python 3.12 (+ pnpm, uv)
pnpm install        # JS/TS workspaces
uv sync             # Python workspace (dunmir agent)
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

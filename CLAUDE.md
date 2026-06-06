# platform — MagmaMoose public monorepo

A **pnpm + uv + Turborepo** monorepo (the "golden stack") that consolidates
MagmaMoose's open-source products and the shared packages they're built on.
Its private counterpart is **`MagmaMoose/platform-pro`** (proprietary apps that
consume these packages via a git submodule).

## Hard rules (non-negotiable)

- **SQLAlchemy 2.0 style only** — `select()` + `session.execute()`. Never `session.query(...)`.
- **Pydantic v2 only** — `@field_validator` / `model_config`. Never v1.
- **Python deps: uv only.** No pip / poetry / `requirements.txt` for new work.
- **Python lint/format: Ruff only.** No Black / Flake8 / isort.
- **JS deps: pnpm workspaces only.** No npm / yarn.
- **Task orchestration: Turborepo only.**
- **Runtime versions pinned in `mise.toml`** (Node 22, Python 3.12); uv/pnpm manage deps.
- **Pin exact versions** in new `package.json` / `pyproject.toml`.
- **Single source of truth:** every shared shape/contract lives once in `packages/*`.

## Layout

```
packages/
  config/        @platform/config   — shared tsconfig / vitest / prettier / ruff (was duplicated per-app)
  schemas/       @platform/schemas  — zod (TS) + Pydantic (Python), one contract
  cf-auth/       @platform/cf-auth  — shared Stytch B2B session auth for Cloudflare (Workers + Pages)
  api-client/    @platform/api-client — typed client + TanStack hooks (placeholder)
  ui/            @platform/ui       — shared shadcn WEB components (placeholder; never RN)
apps/
  diatreme/          — GitHub Action: semantic release + Docker promotion (+ CF Worker). MIT.
  mikrotik-minder/   — "Dun Mir": CF Worker (Hono+D1) control plane + Python agent + Helm. Apache-2.0.
```

Per-app `LICENSE` files govern each app (see root `LICENSE` for the per-app map).
Per-app `.github/workflows/` are preserved for reference but inert in the monorepo;
root CI lives in `.github/workflows/ci.yml`.

## Status

First consolidation step. Apps are imported as-is; the originals
(`MagmaMoose/diatreme`, `MagmaMoose/mikrotik-minder`) still serve production —
this does **not** replace what's running yet. Next steps: rewire each app's
local config/auth copies onto the shared `packages/*` and migrate npm → pnpm.

# @platform/schemas

Shared contracts — **zod (TS) + Pydantic (Python), same shapes, single source of
truth** for request/response shapes the public apps speak.

- **TypeScript (zod)** — `src/*.ts`, package `@platform/schemas` (pnpm workspace).
- **Python (Pydantic v2)** — `python/platform_schemas/`, installable uv package
  `platform-schemas` (uv workspace member).

## Contracts

| Contract | zod | Pydantic | Runtimes |
|----------|-----|----------|----------|
| Dün Mir worker↔agent ingest (`/v1/ingest/*`: heartbeat, job report, command claim/result, enums) | `src/dunmir.ts` | `platform_schemas/dunmir.py` | worker keeps dependency-free hand validators; agent keeps stdlib dataclasses (published CLI, no Pydantic) — both are **documented mirrors** of this contract |
| Item (golden-stack example entity) | `src/item.ts` | `platform_schemas/item.py` | — |

## Consume it

**Python** (workspace member): add `platform-schemas` to dependencies with
`{ workspace = true }` under `[tool.uv.sources]`.

**TypeScript** (workspace package): `"@platform/schemas": "workspace:*"`.

## Lockstep rule

Change a shape → change **both** sides (and any documented runtime mirrors named
above) in the same commit. The zod and Pydantic definitions are intentionally
near-identical so a one-sided diff is an obvious review smell.

Proprietary contracts do **not** belong here — they live in the private repo's
`@platform-pro/schemas`.

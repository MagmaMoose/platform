# Architecture

The root workspace owns orchestration: pnpm for JavaScript/TypeScript packages, uv for Python, Turborepo for task fanout, and mise for pinned runtime versions.

## Applications

`apps/diatreme` is a Cloudflare Worker. Its main handler in `src/index.ts` routes GitHub OIDC/App token brokering, commit signing, Copilot quota/cache flows, webhook triage, dispatch requests, and release aggregation.

`apps/dunmir` has three cooperating surfaces. The Worker under `worker/` exposes Hono routes for agent ingest, admin/customer actions, tenant management, D1 state, R2 backups, and scheduled alert sweeps. The Python agent under `agent/` runs on the operator network, talks to RouterOS over API/SSH, and reports heartbeats and job outcomes back to the Worker. The Helm chart deploys that agent.

`apps/chargate` holds scanner scripts and pinned scanner versions. Marketplace action wrappers live in the separate Chargate repo.

## Shared Packages

`packages/config` centralizes tooling config. `packages/schemas` is the cross-runtime contract layer. `packages/cf-auth` holds Stytch B2B claim and JWKS validation helpers. `packages/api-client` and `packages/ui` are placeholders for future client and web UI code.

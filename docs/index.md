# Platform

MagmaMoose `platform` is the public monorepo for open-source apps and shared packages. It combines pnpm workspaces, uv, Turborepo, and mise so Cloudflare Workers, Python agent code, scan scripts, and shared contracts move together.

## Contents

- `apps/diatreme`: deployable Diatreme Cloudflare Worker.
- `apps/chargate`: security and lint scanner scripts used by Chargate wrappers.
- `apps/dunmir`: Dunmir Worker control plane, Python RouterOS agent, Helm chart, and protocol docs.
- `packages/*`: shared config, schemas, Cloudflare auth, API client, and web UI packages.

!!! note
    This monorepo is additive. Original app repos still serve their Marketplace or production surfaces unless a migration explicitly says otherwise.

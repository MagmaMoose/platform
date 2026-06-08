# Architecture Map

The root owns tooling and workspace orchestration. `apps/diatreme` is a deployable Cloudflare Worker, mostly in `src/index.ts`, for GitHub App/OIDC token brokering, commit signing, Copilot quota, triage, dispatch, and release endpoints. `apps/dunmir` contains a Hono Worker control plane with D1/R2, a Python RouterOS agent, a Helm chart, and protocol docs. `apps/chargate` is scanner shell/Python logic referenced by its Marketplace action repo. Shared packages are intentionally thin: config, schemas, Cloudflare auth, API client, and web-only UI.

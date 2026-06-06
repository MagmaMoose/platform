# diatreme (worker)

The deployable **Cloudflare Worker** behind Diatreme — the token broker, commit
signer, and Copilot quota/review service the Diatreme action calls at runtime
(`api.diatreme.magmamoose.com`: `/sign`, `/process`, `/dispatch`, `/copilot-quota`).

## The Marketplace action lives in its own repo

Diatreme's **GitHub Marketplace composite action** (`action.yml` plus its scripts,
examples, and docs) stays in **[MagmaMoose/diatreme](https://github.com/MagmaMoose/diatreme)** —
the Marketplace is **one repo per action**, so it cannot be published from a
monorepo subdirectory. That action *references* this worker (deployed from here)
where applicable. The monorepo owns the worker as a deployable service so it can
share `packages/*` (e.g. `@platform/cf-auth`).

> The private observability dashboard for this worker is `apps/diatreme-pro` in
> the [platform-pro](https://github.com/MagmaMoose/platform-pro) repo.

> Imported from `MagmaMoose/diatreme@main` (worker subtree only).

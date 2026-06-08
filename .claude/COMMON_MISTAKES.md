# Common Mistakes

- Do not add `action.yml` for Diatreme or Chargate here. Marketplace composite actions stay in `MagmaMoose/diatreme` and `MagmaMoose/chargate`; this monorepo holds code they reference.
- GitHub only runs root `.github/workflows/*`; per-app workflows are preserved as inert source-history context.
- Dunmir local Worker name is `mikrotik-minder`, but prod `env.prod.name` is `dunmir`. Avoid accidental prod deploys or renaming that domain-bound worker.
- Imported npm artifacts exist, but new JS work must use pnpm workspaces. Do not introduce npm/yarn workflows.
- Some imported docs mention `pip`; repo-standard Python work uses uv and Ruff.
- Secrets live in `.env*`, `.dev.vars*`, Wrangler secrets, or `*_env` references. Never inline, log, or commit secret values.
- `@platform/ui` is web-only shadcn/DOM UI, not React Native.

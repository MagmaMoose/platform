# platform — agent context

MagmaMoose's public "golden stack" monorepo: pnpm + uv + Turborepo + mise for shared open-source products and packages. Private/proprietary apps live in `MagmaMoose/platform-pro` and consume these packages via submodule. If a CodeGraph/repo-map MCP is available, prefer it; otherwise, before locating unfamiliar code, read `./PROJECT_INDEX.json` first.

@.claude/QUICK_START.md
@.claude/ARCHITECTURE_MAP.md
@.claude/COMMON_MISTAKES.md

Hard rules: JS deps use pnpm workspaces only; Python deps use uv only; orchestration uses Turborepo; Python lint/format is Ruff only; runtime versions are pinned in `mise.toml`; pin exact versions for new deps. Keep shared contracts in `packages/*`. If adding Python ORM or models, use SQLAlchemy 2.0 style and Pydantic v2 patterns only.

[tooling]
- Prefer targeted line-range reads over whole files; use PROJECT_INDEX.json to find the location.
- grep/find/glob: return matching paths and matched lines only.
- Commands that can flood output: pipe through head/tail/grep or redirect to .claude/last_output.txt and read ranges. Don't paste thousands of lines.
- After a successful write/edit, trust it; don't re-read just to "verify".

[maintenance]
- Bug that took >1h: append to .claude/COMMON_MISTAKES.md.
- Architectural decision: run /adr.
- Public behaviour/API/config/setup changed: run /update-docs.
- PROJECT_INDEX.json stale (new module, big refactor): regenerate the affected modules section only.
- Keep CLAUDE.md under ~500 tokens; push detail into on-demand .claude/ files.

Load `.claude/decisions` and `.claude/sessions` ONLY when the task relates to them, never by default.

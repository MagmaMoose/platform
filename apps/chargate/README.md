# chargate (scan scripts)

The **single source of truth** for Chargate's security + lint scanners — Trivy,
TruffleHog, Semgrep, Checkov, ESLint, Hadolint, ShellCheck, actionlint, and
dependency audits. Chargate's pitch is "write the scan logic once (`scripts/`),
run it everywhere," so the scripts live here and the wrappers reference them.
`versions.env` pins the scanner tool versions.

## The Marketplace action lives in its own repo

Chargate's **composite action**, its **reusable workflow**, and its **pre-commit
hooks** — the three thin wrappers around these scripts — stay in
**[MagmaMoose/chargate](https://github.com/MagmaMoose/chargate)** (Marketplace is
**one repo per action**). Those wrappers *reference* the scan logic kept here.

> Sibling to `apps/diatreme`: diatreme ships your releases; chargate guards what
> goes into them.

## Layout

```
scripts/        the scanners (security-*.sh, lint-*.sh) + shared lib/
versions.env    pinned scanner tool versions
```

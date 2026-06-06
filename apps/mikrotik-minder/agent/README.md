# Mikrotik Minder agent

Local Python daemon that probes RouterOS devices over the **RouterOS API** and **SSH**, and reports heartbeats and job outcomes to a [Mikrotik Minder control plane](../worker/) (Cloudflare Worker).

The agent runs on a trusted host inside the operator's network. It initiates outbound connections only — no inbound access to routers or to the public Worker is needed beyond what normal admin already requires. See [docs/agent-protocol.md](../docs/agent-protocol.md) for the wire contract.

## Install

```bash
cd agent
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

## Configure

Copy [`examples/config.example.yaml`](examples/config.example.yaml) and edit:

```yaml
server:
  url: https://mikrotik-minder.<your-subdomain>.workers.dev
  agent_token_env: MTM_AGENT_TOKEN     # bearer issued by POST /v1/admin/agents

defaults:
  transport:
    primary: api
    fallback: ssh
  heartbeat_interval_seconds: 300
  export_interval_seconds: 3600        # optional; omit to disable exports
  update_check_interval_seconds: 21600 # optional; omit to disable
  backup_interval_seconds: 86400       # optional; omit to disable

# Required when export_interval_seconds is set.
git:
  repo: /var/lib/mikrotik-minder/configs
  # Optional offsite mirror. SSH and HTTPS+token both work.
  remote:
    url: git@github.com:acme/network-configs.git
    branch: main
    ssh_key_path: /var/lib/mikrotik-minder/.ssh/git_deploy
    # OR for HTTPS:
    # url: https://github.com/acme/network-configs.git
    # token_env: MTM_GIT_TOKEN
    push: true                         # set to false to pause pushing without removing the section

# Required when backup_interval_seconds is set, or for `update apply`.
backup:
  dir: /var/lib/mikrotik-minder/backups
  password_env: MTM_BACKUP_PASSWORD    # encrypts the .backup file (aes-sha256)
  retention: 14                        # keep last N per device

devices:
  - name: core-rtr-01
    address: 10.0.0.1
    username: minder
    password_env: CORE_RTR_01_PASSWORD
    site: dc1
    role: core
    # export_interval_seconds: 86400   # per-device override allowed
    # backup_interval_seconds: 43200
```

Secrets are referenced by environment variable name (`*_env` suffix). The agent reads them at startup and never logs the values.

### Three outbound trust relationships

| To             | Protocol         | Credential                | Scope                                      |
| -------------- | ---------------- | ------------------------- | ------------------------------------------ |
| routers        | RouterOS API / SSH | per-device password / key | probe, export, backup, update              |
| worker         | HTTPS            | `MTM_AGENT_TOKEN` bearer   | post heartbeats and job results            |
| git remote     | SSH or HTTPS     | deploy key OR PAT          | push-only write to one private repo        |

Each is independent and least-privilege. A compromised agent host leaks one fleet's configs, not your whole git org.

### Setting up the git remote

**SSH + deploy key (recommended for self-hosted Gitea, GitHub private repos, etc.):**

```bash
# 1. On the agent host, generate a key with NO passphrase (it's a service credential)
install -d -m 0700 /var/lib/mikrotik-minder/.ssh
ssh-keygen -t ed25519 -N "" -C "mikrotik-minder@$(hostname)" \
  -f /var/lib/mikrotik-minder/.ssh/git_deploy
chmod 600 /var/lib/mikrotik-minder/.ssh/git_deploy

# 2. Add the .pub half as a deploy key with WRITE access on the private repo:
#    GitHub: Settings → Deploy keys → Add deploy key (✓ Allow write access)
#    Gitea/GitLab: Settings → Deploy Keys → Add Key

# 3. Point the agent at the key (in your minder.yaml):
#    git.remote.ssh_key_path: /var/lib/mikrotik-minder/.ssh/git_deploy

# 4. First-run host-key acceptance: the agent uses `StrictHostKeyChecking=accept-new`
#    so the very first push records the remote's host key in
#    /var/lib/mikrotik-minder/.ssh/known_hosts and pins it from then on. To pre-pin:
ssh-keyscan github.com >> /var/lib/mikrotik-minder/.ssh/known_hosts
```

**HTTPS + PAT (when outbound 22 is blocked):**

```bash
# 1. Create a fine-grained PAT scoped to one repo with contents:write only.
# 2. Export it:
export MTM_GIT_TOKEN=ghp_...
# 3. Point the agent at it (in minder.yaml):
#    git.remote.url: https://github.com/acme/network-configs.git
#    git.remote.token_env: MTM_GIT_TOKEN
```

The agent never writes the token into `.git/config` — it injects it inline on push, so a `cat .git/config` on the agent host won't reveal it.

### What's in the repo

`/export` is captured with RouterOS' default `hide-sensitive=yes`, so the committed files contain **topology, not credentials** — interfaces, addresses, routing, comments, WireGuard *public* keys. They're still sensitive enough to keep in a private repo. Recommended:

- private repo with audit-logged access
- `chmod 0700` on `git.repo` and run the agent as a dedicated unprivileged user
- full-disk encryption on the trusted agent host (LUKS, FileVault) — the baseline that makes a stolen disk a non-event

### Maintenance jobs

The daemon runs five kinds of work, each on its own cadence:

| Job kind         | What runs                          | Cadence default                    | Worker alert on warning/failure   |
| ---------------- | ---------------------------------- | ---------------------------------- | --------------------------------- |
| heartbeat        | probe + status report              | `heartbeat_interval_seconds`       | `heartbeat_missed` after grace    |
| health_check     | one job per probe                  | every heartbeat tick               | `job_failed` on failure           |
| export           | `/export` → normalise → git commit | `export_interval_seconds`          | `drift_detected` on real change   |
| update_check     | available packages + ROS firmware  | `update_check_interval_seconds`    | `update_available` when an update is ready |
| backup           | encrypted backup → SFTP pull       | `backup_interval_seconds`          | `job_failed` on failure           |

Only heartbeat is mandatory; everything else is opt-in via the corresponding interval.

### Update apply (destructive)

Applying a RouterOS update is the only daemon-skipping, opt-in, explicitly-approved action:

```bash
mikrotik-minder-agent update apply core-rtr-01 \
    --config minder.yaml \
    --approve CHG-1234
```

Pre-checks (each can be bypassed; default is "all must pass"):
- device currently reachable
- update is actually available (no-op if already on the latest version)
- a backup newer than 24 h exists locally (`--skip-backup-check` to bypass; not recommended)
- free disk space ≥ `--min-free-mib` (default 100)

Then the agent issues `/system package update install`, waits for the router to reboot (default 600 s budget via `--max-wait`), and posts `kind=update_apply` with before/after versions and downtime.

If a pre-check fails the router is **not touched** — the failed job is reported with `aborted_pre_install=true`. If the install starts but the router doesn't return in time, the agent reports a critical `update_failed` alert.

## Run

```bash
export MTM_AGENT_TOKEN=mtm_...
export CORE_RTR_01_PASSWORD=...

# Long-running daemon (one thread per device)
mikrotik-minder-agent run --config minder.yaml -v

# Single pass for cron / systemd timers
mikrotik-minder-agent run --config minder.yaml --once

# Verify worker URL + token without touching any routers
mikrotik-minder-agent run --config minder.yaml --once --dry-run

# Probe a single device locally, do not call the worker
mikrotik-minder-agent check --config minder.yaml core-rtr-01

# Capture /export for one device, commit to Git, do not call the worker
mikrotik-minder-agent export-once --config minder.yaml core-rtr-01
```

## systemd

```ini
# /etc/systemd/system/mikrotik-minder-agent.service
[Unit]
Description=Mikrotik Minder agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=minder
EnvironmentFile=/etc/mikrotik-minder/agent.env
ExecStart=/opt/mikrotik-minder/.venv/bin/mikrotik-minder-agent run \
  --config /etc/mikrotik-minder/config.yaml -v
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

`agent.env` holds the `MTM_AGENT_TOKEN` and per-device passwords referenced by `*_env` in the config.

## Tests

```bash
pip install -e ".[dev]"
ruff check src tests
pytest
```

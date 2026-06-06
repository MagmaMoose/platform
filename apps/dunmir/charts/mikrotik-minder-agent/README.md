# mikrotik-minder-agent

Helm chart for the Mikrotik Minder agent — the component that runs *inside* your network, reaches MikroTik routers over RouterOS API + SSH, and reports back to the Mikrotik Minder control plane (Cloudflare Worker).

The agent is **stateful per fleet** and the chart deliberately runs it as a single replica. Two pods would race over the same git repo, fight for the same `/system backup save` slot on each router, and post duplicate heartbeats. The chart pins `replicas: 1` and uses a `Recreate` strategy so the PVC isn't held during rollout.

## TL;DR

```bash
helm install minder oci://ghcr.io/magmamoose/charts/mikrotik-minder-agent \
    --namespace minder --create-namespace \
    -f my-values.yaml
```

Until a chart registry is published, you can install from a local checkout:

```bash
helm install minder ./charts/mikrotik-minder-agent \
    --namespace minder --create-namespace \
    -f my-values.yaml
```

## Minimal `my-values.yaml`

```yaml
config:
  server:
    url: https://mikrotik-minder.<your-subdomain>.workers.dev
    agent_token_env: MTM_AGENT_TOKEN
  defaults:
    heartbeat_interval_seconds: 300
    export_interval_seconds: 3600
    backup_interval_seconds: 86400
  git:
    repo: /var/lib/mikrotik-minder/configs
    remote:
      url: git@github.com:acme/network-configs.git
      branch: main
      # Key is mounted from a Secret at /etc/mikrotik-minder/ssh/ (outside
      # the PVC) so a fresh install doesn't fail on a missing parent dir.
      ssh_key_path: /etc/mikrotik-minder/ssh/git_deploy
  backup:
    dir: /var/lib/mikrotik-minder/backups
    password_env: MTM_BACKUP_PASSWORD
    retention: 14
  devices:
    - name: core-rtr-01
      address: 10.0.0.1
      username: minder
      password_env: CORE_RTR_01_PASSWORD
      site: dc1

secrets:
  create: true
  data:
    MTM_AGENT_TOKEN: mtm_...
    MTM_BACKUP_PASSWORD: long-random-string
    CORE_RTR_01_PASSWORD: ...

git:
  sshKey: |
    -----BEGIN OPENSSH PRIVATE KEY-----
    ...the deploy key the agent uses to push to the private repo...
    -----END OPENSSH PRIVATE KEY-----
  knownHosts: |
    github.com ssh-ed25519 AAAAC3...   # pin host keys ahead of first push
```

## Secrets in production

Putting plaintext under `secrets.data` is fine for kicking the tyres. For real deployments use one of:

- **external-secrets.io** — point `secrets.existingSecretName: minder-env` at a Secret your `ExternalSecret` reconciles from Vault / AWS SM / GCP SM / 1Password Connect.
- **sealed-secrets** — encrypt the rendered Secret with `kubeseal` and commit it to git alongside your values.
- **vault-csi** — mount a CSI volume; you'd need to extend the chart's `volumes` and `volumeMounts` via a patch (issue welcome).

When `existingSecretName` is set, `secrets.create=false` and the chart leaves the Secret untouched.

## What gets created

| Kind                  | Name                        | Notes                                                          |
| --------------------- | --------------------------- | -------------------------------------------------------------- |
| ServiceAccount        | `{release}-{name}`          | `automountServiceAccountToken: false`                          |
| ConfigMap             | `{name}-config`             | Renders `config.yaml` from `values.config`                     |
| Secret                | `{name}-env`                | When `secrets.create=true`. Mounted via `envFrom`              |
| Secret                | `{name}-git-ssh`            | When `git.sshKey` is set. `defaultMode: 0400`                  |
| PersistentVolumeClaim | `{name}-state`              | When `persistence.enabled` (default true)                      |
| Deployment            | `{name}`                    | `replicas: 1`, `strategy: Recreate`                            |
| NetworkPolicy         | `{name}`                    | When `networkPolicy.enabled`                                   |

## Verifying

```bash
kubectl -n minder logs -f deploy/minder-mikrotik-minder-agent

# Ad-hoc probe of one device, no worker call
kubectl -n minder exec deploy/minder-mikrotik-minder-agent -- \
    mikrotik-minder-agent check -c /etc/mikrotik-minder/config.yaml core-rtr-01

# Verify worker URL + token, no router calls
kubectl -n minder exec deploy/minder-mikrotik-minder-agent -- \
    mikrotik-minder-agent test-connection -c /etc/mikrotik-minder/config.yaml
```

## Values reference (excerpt)

| Key                                  | Default                                                    | Notes |
| ------------------------------------ | ---------------------------------------------------------- | ----- |
| `image.repository`                   | `ghcr.io/magmamoose/mikrotik-minder-agent`                 | |
| `image.tag`                          | `""` (uses `.Chart.appVersion`)                            | |
| `config`                             | minimal placeholder                                        | Whatever you put here becomes `/etc/mikrotik-minder/config.yaml` verbatim. |
| `secrets.create`                     | `true`                                                     | Toggle off when bringing your own Secret. |
| `secrets.existingSecretName`         | `""`                                                       | Existing Secret name; pod uses `envFrom` against it. |
| `git.sshKey`                         | `""`                                                       | PEM private key body. Mounted at `/etc/mikrotik-minder/ssh/git_deploy` (mode 0400), outside the PVC. |
| `git.knownHosts`                     | `""`                                                       | Optional `ssh-keyscan` output to pin remote hosts. |
| `persistence.enabled`                | `true`                                                     | Set false to use `emptyDir` (loses git history on pod restart). |
| `persistence.size`                   | `10Gi`                                                     | |
| `resources.requests` / `limits`      | 50m/128Mi → 500m/512Mi                                     | Tune for fleet size. |
| `securityContext`                    | non-root, fsGroup 1000, seccomp RuntimeDefault             | |
| `containerSecurityContext`           | drop all caps, RO rootfs, no priv-esc                      | |
| `networkPolicy.enabled`              | `false`                                                    | Egress-only allow-list. Provide rules in `networkPolicy.egress`. |
| `verbosity`                          | `1`                                                        | `-v` passed to the daemon. 0–3. |

See [`values.yaml`](./values.yaml) for the full list with inline comments.

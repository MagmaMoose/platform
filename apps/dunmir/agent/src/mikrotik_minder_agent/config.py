"""Config loader: parse YAML, resolve env-var references, validate fields.

The schema intentionally mirrors README.md's "Data model and config example" so the
config file matches what operators have already drafted from the design doc.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class ConfigError(ValueError):
    """Raised when the config file is malformed or references missing env vars."""


@dataclass(frozen=True)
class ServerConfig:
    url: str
    agent_token: str
    timeout_seconds: float = 10.0


@dataclass(frozen=True)
class APIDefaults:
    port: int = 8728
    use_tls: bool = False
    tls_port: int = 8729


@dataclass(frozen=True)
class SSHDefaults:
    port: int = 22
    username: str | None = None
    known_hosts_path: str | None = None  # pin router host keys (TOFU) when set


@dataclass(frozen=True)
class TransportPolicy:
    primary: str = "api"           # 'api' | 'ssh'
    fallback: str | None = "ssh"   # 'api' | 'ssh' | None


@dataclass(frozen=True)
class GitRemoteConfig:
    """Optional offsite mirror for the export history."""

    url: str
    branch: str = "main"
    ssh_key_path: str | None = None      # for SSH remotes (git@host:org/repo.git)
    token: str | None = None             # for HTTPS remotes (x-access-token:$TOKEN@…)
    known_hosts_path: str | None = None  # optional, alongside ssh_key_path if both set
    push: bool = True


@dataclass(frozen=True)
class GitConfig:
    repo: str
    author_name: str = "mikrotik-minder"
    author_email: str = "mikrotik-minder@localhost"
    remote: GitRemoteConfig | None = None


@dataclass(frozen=True)
class BackupConfig:
    dir: str
    password: str          # resolved value; never logged
    retention: int = 14    # how many backups to keep per device


@dataclass(frozen=True)
class Defaults:
    transport: TransportPolicy = field(default_factory=TransportPolicy)
    heartbeat_interval_seconds: int = 300
    export_interval_seconds: int | None = None        # None = exports disabled
    update_check_interval_seconds: int | None = None  # None = update checks disabled
    backup_interval_seconds: int | None = None        # None = backups disabled
    inventory_check_interval_seconds: int | None = 3600  # CHR/licence/cloud facts; None/0 = off
    config_refresh_interval_seconds: int = 300  # remote mode: re-fetch device config every N s
    connect_timeout_seconds: float = 5.0
    export_timeout_seconds: float = 30.0
    update_check_timeout_seconds: float = 30.0
    backup_save_timeout_seconds: float = 120.0
    backup_pull_timeout_seconds: float = 300.0
    ping_target: str | None = None  # router pings this address; None = packet-loss probe off
    ping_count: int = 5
    api: APIDefaults = field(default_factory=APIDefaults)
    ssh: SSHDefaults = field(default_factory=SSHDefaults)


@dataclass(frozen=True)
class DeviceConfig:
    name: str
    address: str
    username: str
    password: str | None = None
    ssh_key_path: str | None = None
    site: str | None = None
    role: str | None = None
    tags: tuple[str, ...] = ()
    heartbeat_interval_seconds: int | None = None
    export_interval_seconds: int | None = None
    update_check_interval_seconds: int | None = None
    backup_interval_seconds: int | None = None
    inventory_check_interval_seconds: int | None = None
    ping_target: str | None = None
    transport: TransportPolicy | None = None
    api_port: int | None = None
    use_tls: bool | None = None
    ssh_port: int | None = None


@dataclass(frozen=True)
class AgentConfig:
    server: ServerConfig
    defaults: Defaults
    devices: tuple[DeviceConfig, ...]
    git: GitConfig | None = None
    backup: BackupConfig | None = None
    config_source: str = "local"  # 'local' | 'remote' (fetch device list from control plane)
    agent_key_path: str | None = None  # Curve25519 key for the Pro vault; None = no sealed creds


# --- Loader --------------------------------------------------------------------------------------


def load_config(path: str | Path, *, require_server_token: bool = True) -> AgentConfig:
    """Load and validate the agent's YAML config.

    ``require_server_token=False`` lets local-only commands (``check``) work
    without the agent's bearer token being set in the environment.
    """
    path = Path(path).expanduser()
    if not path.exists():
        raise ConfigError(f"config file not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"{path} must contain a YAML mapping at the root")
    return parse_config(raw, require_server_token=require_server_token)


def parse_config(raw: dict[str, Any], *, require_server_token: bool = True) -> AgentConfig:
    server = _parse_server(
        _require_section(raw, "server"),
        require_token=require_server_token,
    )
    defaults = _parse_defaults(raw.get("defaults") or {})
    git = _parse_git(raw.get("git") or {})
    backup = _parse_backup(raw.get("backup") or {})
    config_source = raw.get("config_source", "local")
    if config_source not in ("local", "remote"):
        raise ConfigError("config_source must be 'local' or 'remote'")
    devices_raw = raw.get("devices")
    if config_source == "local":
        if not isinstance(devices_raw, list) or not devices_raw:
            raise ConfigError("config must contain a non-empty 'devices' list")
        devices = tuple(_parse_device(d, idx) for idx, d in enumerate(devices_raw))
    else:
        # remote: the device list comes from the control plane (GET /v1/ingest/config);
        # any local devices are an optional fallback for a failed startup fetch.
        devices = (
            tuple(_parse_device(d, idx) for idx, d in enumerate(devices_raw))
            if isinstance(devices_raw, list)
            else ()
        )
    _check_unique_names(devices)
    if defaults.export_interval_seconds and not git:
        raise ConfigError(
            "defaults.export_interval_seconds requires a 'git' section with a repo path",
        )
    if defaults.backup_interval_seconds and not backup:
        raise ConfigError(
            "defaults.backup_interval_seconds requires a 'backup' section",
        )
    return AgentConfig(
        server=server,
        defaults=defaults,
        devices=devices,
        git=git,
        backup=backup,
        config_source=config_source,
        agent_key_path=raw.get("agent_key_path"),
    )


# --- Section parsers -----------------------------------------------------------------------------


def _parse_server(raw: dict[str, Any], *, require_token: bool = True) -> ServerConfig:
    url = _require_str(raw, "server.url")
    if "agent_token" in raw and "agent_token_env" in raw:
        raise ConfigError("server.agent_token and server.agent_token_env are mutually exclusive")
    token: str = ""
    if "agent_token_env" in raw:
        env_name = _require_str(raw, "server.agent_token_env")
        env_value = os.environ.get(env_name)
        if env_value:
            token = env_value
        elif require_token:
            raise ConfigError(f"env var '{env_name}' (server.agent_token_env) is not set")
    elif "agent_token" in raw:
        token = _require_str(raw, "server.agent_token")
    elif require_token:
        raise ConfigError("server must set either 'agent_token' or 'agent_token_env'")
    timeout = float(raw.get("timeout_seconds", 10.0))
    return ServerConfig(url=url.rstrip("/"), agent_token=token, timeout_seconds=timeout)


def _parse_defaults(raw: dict[str, Any]) -> Defaults:
    transport = _parse_transport_policy(raw.get("transport") or {}) or TransportPolicy()
    api_raw = raw.get("api", {}) or {}
    api = APIDefaults(
        port=int(api_raw.get("port", 8728)),
        use_tls=_strict_bool(api_raw.get("use_tls"), "defaults.api.use_tls", default=False),
        tls_port=int(api_raw.get("tls_port", 8729)),
    )
    ssh_raw = raw.get("ssh", {}) or {}
    ssh = SSHDefaults(
        port=int(ssh_raw.get("port", 22)),
        username=ssh_raw.get("username"),
        known_hosts_path=ssh_raw.get("known_hosts_path"),
    )
    export_interval = raw.get("export_interval_seconds")
    update_check_interval = raw.get("update_check_interval_seconds")
    backup_interval = raw.get("backup_interval_seconds")
    # Inventory defaults ON (hourly) — it's cheap, read-only facts. Explicit 0/null disables it.
    inventory_interval = raw.get("inventory_check_interval_seconds", 3600)
    ping_target_raw = raw.get("ping_target")
    ping_target = (
        ping_target_raw.strip()
        if isinstance(ping_target_raw, str) and ping_target_raw.strip()
        else None
    )
    return Defaults(
        transport=transport,
        heartbeat_interval_seconds=int(raw.get("heartbeat_interval_seconds", 300)),
        export_interval_seconds=int(export_interval) if export_interval else None,
        update_check_interval_seconds=int(update_check_interval) if update_check_interval else None,
        backup_interval_seconds=int(backup_interval) if backup_interval else None,
        inventory_check_interval_seconds=int(inventory_interval) if inventory_interval else None,
        config_refresh_interval_seconds=int(raw.get("config_refresh_interval_seconds", 300)),
        connect_timeout_seconds=float(raw.get("connect_timeout_seconds", 5.0)),
        export_timeout_seconds=float(raw.get("export_timeout_seconds", 30.0)),
        update_check_timeout_seconds=float(raw.get("update_check_timeout_seconds", 30.0)),
        backup_save_timeout_seconds=float(raw.get("backup_save_timeout_seconds", 120.0)),
        backup_pull_timeout_seconds=float(raw.get("backup_pull_timeout_seconds", 300.0)),
        ping_target=ping_target,
        ping_count=int(raw.get("ping_count", 5)),
        api=api,
        ssh=ssh,
    )


def _parse_git(raw: dict[str, Any]) -> GitConfig | None:
    if not raw:
        return None
    repo = raw.get("repo")
    if not isinstance(repo, str) or not repo.strip():
        raise ConfigError("git.repo is required when the 'git' section is present")
    return GitConfig(
        repo=repo.strip(),
        author_name=raw.get("author_name", "mikrotik-minder"),
        author_email=raw.get("author_email", "mikrotik-minder@localhost"),
        remote=_parse_git_remote(raw.get("remote") or {}),
    )


def _parse_git_remote(raw: dict[str, Any]) -> GitRemoteConfig | None:
    if not raw:
        return None
    url = raw.get("url")
    if not isinstance(url, str) or not url.strip():
        raise ConfigError("git.remote.url is required when the 'remote' section is present")
    url = url.strip()
    ssh_key_path = raw.get("ssh_key_path")
    token = _resolve_secret(raw, field_name="token", field_path="git.remote.token")
    if ssh_key_path and token:
        raise ConfigError(
            "git.remote: pick one of ssh_key_path or token/token_env, not both",
        )
    if not ssh_key_path and not token:
        if url.startswith(("git@", "ssh://")):
            raise ConfigError(
                "git.remote: SSH-style url needs ssh_key_path (path to a private key)",
            )
        # HTTPS without token is allowed (e.g. self-hosted Gitea with anon-write — rare)
        # but warn-worthy. We don't fail; just leave token=None.
    push = raw.get("push", True)
    if not isinstance(push, bool):
        raise ConfigError("git.remote.push must be a boolean")
    return GitRemoteConfig(
        url=url,
        branch=str(raw.get("branch", "main")),
        ssh_key_path=ssh_key_path,
        token=token,
        known_hosts_path=raw.get("known_hosts_path"),
        push=push,
    )


def _parse_backup(raw: dict[str, Any]) -> BackupConfig | None:
    if not raw:
        return None
    directory = raw.get("dir")
    if not isinstance(directory, str) or not directory.strip():
        raise ConfigError("backup.dir is required when the 'backup' section is present")
    password = _resolve_secret(raw, field_name="password", field_path="backup.password")
    if not password:
        raise ConfigError("backup.password (or backup.password_env) is required")
    retention = int(raw.get("retention", 14))
    if retention < 1:
        raise ConfigError("backup.retention must be >= 1")
    return BackupConfig(dir=directory.strip(), password=password, retention=retention)


def _parse_transport_policy(raw: dict[str, Any]) -> TransportPolicy | None:
    if not raw:
        return None
    primary = raw.get("primary", "api")
    fallback = raw.get("fallback", "ssh")
    if primary not in ("api", "ssh"):
        raise ConfigError(f"transport.primary must be 'api' or 'ssh', got {primary!r}")
    if fallback not in ("api", "ssh", None, ""):
        raise ConfigError(f"transport.fallback must be 'api', 'ssh', or null; got {fallback!r}")
    return TransportPolicy(primary=primary, fallback=fallback or None)


def _parse_device(raw: Any, idx: int) -> DeviceConfig:
    if not isinstance(raw, dict):
        raise ConfigError(f"devices[{idx}] must be a mapping")
    name = _require_str(raw, f"devices[{idx}].name")
    address = _require_str(raw, f"devices[{idx}].address")
    username = _require_str(raw, f"devices[{idx}].username")

    password = _resolve_secret(raw, field_name="password", field_path=f"devices[{idx}].password")
    ssh_key_path = raw.get("ssh_key_path")
    if password is None and not ssh_key_path:
        raise ConfigError(
            f"devices[{idx}] ({name}) needs at least one of password / password_env / ssh_key_path",
        )
    tags = raw.get("tags") or ()
    if tags and not (isinstance(tags, list) and all(isinstance(t, str) for t in tags)):
        raise ConfigError(f"devices[{idx}].tags must be a list of strings")
    transport = _parse_transport_policy(raw.get("transport") or {})
    return DeviceConfig(
        name=name,
        address=address,
        username=username,
        password=password,
        ssh_key_path=ssh_key_path,
        site=raw.get("site"),
        role=raw.get("role"),
        tags=tuple(tags),
        heartbeat_interval_seconds=raw.get("heartbeat_interval_seconds"),
        export_interval_seconds=raw.get("export_interval_seconds"),
        update_check_interval_seconds=raw.get("update_check_interval_seconds"),
        backup_interval_seconds=raw.get("backup_interval_seconds"),
        inventory_check_interval_seconds=raw.get("inventory_check_interval_seconds"),
        ping_target=raw.get("ping_target"),
        transport=transport,
        api_port=raw.get("api_port"),
        use_tls=_strict_bool(raw.get("use_tls"), f"devices[{idx}].use_tls"),
        ssh_port=raw.get("ssh_port"),
    )


# --- Helpers -------------------------------------------------------------------------------------


def _require_section(raw: dict[str, Any], name: str) -> dict[str, Any]:
    val = raw.get(name)
    if not isinstance(val, dict):
        raise ConfigError(f"'{name}' section is required and must be a mapping")
    return val


def _require_str(raw: dict[str, Any], path: str) -> str:
    key = path.split(".")[-1]
    val = raw.get(key)
    if not isinstance(val, str) or not val.strip():
        raise ConfigError(f"'{path}' is required and must be a non-empty string")
    return val.strip()


def _strict_bool(value: Any, path: str, *, default: bool | None = None) -> bool | None:
    """Reject string-form booleans.

    Python's ``bool("false")`` is True, so unquoted YAML booleans round-trip
    correctly but a quoted ``"false"`` would silently flip a flag. This helper
    requires a real boolean (or ``None`` / missing → ``default``) and raises a
    clear error otherwise.
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    raise ConfigError(
        f"{path} must be a boolean (true/false). Got {type(value).__name__}: {value!r}",
    )


def _resolve_secret(raw: dict[str, Any], field_name: str, field_path: str) -> str | None:
    env_key = f"{field_name}_env"
    if field_name in raw and env_key in raw:
        raise ConfigError(f"{field_path} and {field_path}_env are mutually exclusive")
    if env_key in raw:
        env_name = raw[env_key]
        if not isinstance(env_name, str) or not env_name.strip():
            raise ConfigError(f"{field_path}_env must be a non-empty string")
        value = os.environ.get(env_name.strip())
        if not value:
            raise ConfigError(f"env var '{env_name}' ({field_path}_env) is not set")
        return value
    if field_name in raw:
        val = raw[field_name]
        if val is None:
            return None
        if not isinstance(val, str):
            raise ConfigError(f"{field_path} must be a string")
        return val
    return None


def _check_unique_names(devices: tuple[DeviceConfig, ...]) -> None:
    seen: set[str] = set()
    for d in devices:
        if d.name in seen:
            raise ConfigError(f"device name '{d.name}' is duplicated")
        seen.add(d.name)


# --- Per-device resolution -----------------------------------------------------------------------


def heartbeat_interval(device: DeviceConfig, defaults: Defaults) -> int:
    return device.heartbeat_interval_seconds or defaults.heartbeat_interval_seconds


def export_interval(device: DeviceConfig, defaults: Defaults) -> int | None:
    """Resolve the device's export interval, or None if exports are disabled for it."""
    return device.export_interval_seconds or defaults.export_interval_seconds


def update_check_interval(device: DeviceConfig, defaults: Defaults) -> int | None:
    """Resolve the device's update-check interval, or None if disabled."""
    return device.update_check_interval_seconds or defaults.update_check_interval_seconds


def backup_interval(device: DeviceConfig, defaults: Defaults) -> int | None:
    """Resolve the device's backup interval, or None if disabled."""
    return device.backup_interval_seconds or defaults.backup_interval_seconds


def inventory_check_interval(device: DeviceConfig, defaults: Defaults) -> int | None:
    """Resolve the device's inventory interval, or None if disabled."""
    return device.inventory_check_interval_seconds or defaults.inventory_check_interval_seconds


def ping_target(device: DeviceConfig, defaults: Defaults) -> str | None:
    """Resolve the device's packet-loss ping target, or None if the probe is off."""
    return device.ping_target or defaults.ping_target


def effective_transport(device: DeviceConfig, defaults: Defaults) -> TransportPolicy:
    return device.transport or defaults.transport

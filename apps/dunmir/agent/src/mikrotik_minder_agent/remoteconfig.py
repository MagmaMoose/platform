"""Build DeviceConfig objects from a control-plane config doc (config_source: remote).

The doc is the body of ``GET /v1/ingest/config``. Credentials arrive as
references (``credential.kind == "ref"``): ``password_env`` / ``ssh_key_path``
are resolved from the agent's OWN environment — the control plane never sends a
secret. Devices we can't build (missing address, an unresolved credential, or
Pro-only ``sealed`` credentials) are skipped with a warning so the rest of the
fleet still runs.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Mapping
from typing import Any

from .agentkeys import AgentKeyError
from .config import DeviceConfig, TransportPolicy

log = logging.getLogger(__name__)


def build_devices(
    doc: dict[str, Any],
    *,
    env: Mapping[str, str] | None = None,
    unseal: Callable[[str], str] | None = None,
) -> tuple[DeviceConfig, ...]:
    """Map the config doc's ``devices`` into DeviceConfig, resolving credentials.

    ``unseal`` decrypts ``kind: "sealed"`` credentials with the agent's vault
    key; when it's None, sealed devices are skipped.
    """
    environ = env if env is not None else os.environ
    entries = doc.get("devices")
    if not isinstance(entries, list):
        return ()
    out: list[DeviceConfig] = []
    for entry in entries:
        if isinstance(entry, dict):
            device = _build_one(entry, environ, unseal)
            if device is not None:
                out.append(device)
    return tuple(out)


def devices_changed(
    current: tuple[DeviceConfig, ...],
    fetched: tuple[DeviceConfig, ...],
) -> bool:
    """True if two device sets differ by name → full config (order-independent).

    DeviceConfig is a frozen dataclass, so this compares every field — including
    the resolved credential — and ignores ordering.
    """
    return {d.name: d for d in current} != {d.name: d for d in fetched}


def _build_one(
    entry: dict[str, Any],
    environ: Mapping[str, str],
    unseal: Callable[[str], str] | None,
) -> DeviceConfig | None:
    name = entry.get("name")
    address = entry.get("address")
    if not isinstance(name, str) or not name or not isinstance(address, str) or not address:
        log.warning("remote config: skipping device with missing name/address: %r", entry)
        return None

    cred = entry.get("credential")
    cred = cred if isinstance(cred, dict) else {}
    password: str | None = None
    ssh_key_path: str | None = None
    if cred.get("kind") == "sealed":
        blob = cred.get("blob")
        if unseal is None or not isinstance(blob, str):
            log.warning(
                "remote config: device %s is sealed but the agent has no vault key; skipping",
                name,
            )
            return None
        try:
            password = unseal(blob)
        except AgentKeyError as exc:
            log.warning(
                "remote config: device %s sealed credential decrypt failed (%s); skipping",
                name,
                exc,
            )
            return None
    else:
        # "ref" (or unspecified): resolve references from the local environment.
        pw_env = cred.get("password_env")
        if isinstance(pw_env, str) and pw_env:
            password = environ.get(pw_env)
            if not password:
                # Don't log the env-var name — keep credential references out of logs.
                log.warning(
                    "remote config: device %s password env var is not set; skipping",
                    name,
                )
                return None
        key_path = cred.get("ssh_key_path")
        if isinstance(key_path, str) and key_path:
            ssh_key_path = key_path
    if not password and not ssh_key_path:
        log.warning("remote config: device %s has no usable credential; skipping", name)
        return None

    transport = entry.get("transport")
    transport = transport if isinstance(transport, dict) else {}
    policy: TransportPolicy | None = None
    primary = transport.get("primary")
    if isinstance(primary, str) and primary:
        fallback = transport.get("fallback")
        policy = TransportPolicy(
            primary=primary,
            fallback=fallback if isinstance(fallback, str) else None,
        )

    tags = entry.get("tags")
    tags_tuple = tuple(t for t in tags if isinstance(t, str)) if isinstance(tags, list) else ()

    return DeviceConfig(
        name=name,
        address=address,
        username=entry.get("username") if isinstance(entry.get("username"), str) else "",
        password=password,
        ssh_key_path=ssh_key_path,
        site=entry.get("site") if isinstance(entry.get("site"), str) else None,
        role=entry.get("role") if isinstance(entry.get("role"), str) else None,
        tags=tags_tuple,
        heartbeat_interval_seconds=_as_int(entry.get("heartbeat_interval_seconds")),
        transport=policy,
        api_port=_as_int(entry.get("api_port")),
        use_tls=entry.get("use_tls") if isinstance(entry.get("use_tls"), bool) else None,
        ssh_port=_as_int(entry.get("ssh_port")),
    )


def _as_int(v: Any) -> int | None:
    # bool is an int subclass — exclude it so use_tls-style values don't leak in.
    return v if isinstance(v, int) and not isinstance(v, bool) else None

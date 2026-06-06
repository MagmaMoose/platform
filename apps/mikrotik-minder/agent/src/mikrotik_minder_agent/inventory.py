"""Read-only device inventory: CHR/routerboard, licence, and /ip cloud facts.

Every command here is a non-mutating ``print``. Output varies a lot across
RouterOS versions and editions (CHR has no routerboard; licence layout differs
between CHR and RouterBOARD), so each field is optional and a missing or garbled
block degrades to ``None`` rather than raising. Only a failed *first* connect is
fatal — once we're in, a single probe failing doesn't sink the others.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Protocol

from .config import Defaults, DeviceConfig
from .rosparse import is_unknown_command, kv_dict
from .transports import TransportError
from .transports.ssh import SSHTransport
from .updates import parse_firmware

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class LicenseInfo:
    level: str | None
    software_id: str | None
    deadline: str | None


@dataclass(frozen=True)
class CloudInfo:
    dns_name: str | None  # mynetname — the <id>.sn.mynetname.net handle
    public_address: str | None
    status: str | None
    ddns_enabled: bool | None


@dataclass(frozen=True)
class InventoryResult:
    started_at: int
    finished_at: int
    has_routerboard: bool
    model: str | None
    address: str | None  # the host/IP the agent connects to (from config)
    identity: str | None  # the router's own /system identity name
    license: LicenseInfo
    cloud: CloudInfo


class InventoryError(RuntimeError):
    """Raised when the inventory probe couldn't even connect to the device."""


class _Capture(Protocol):
    def capture(self, command: str, *, timeout: float | None = ...) -> str: ...


def run_inventory(
    device: DeviceConfig,
    defaults: Defaults,
    *,
    capture: _Capture | None = None,
) -> InventoryResult:
    """Gather CHR/routerboard, licence and /ip cloud facts over SSH."""
    started = int(time.time())
    client = capture or SSHTransport(device, defaults)
    timeout = defaults.connect_timeout_seconds + 5

    # The routerboard print doubles as the connectivity check — if it can't run,
    # the device is unreachable and there's no point trying the rest.
    try:
        rb_text = client.capture("/system routerboard print", timeout=timeout)
    except TransportError as exc:
        raise InventoryError(f"inventory capture failed: {exc}") from exc
    fw = parse_firmware(rb_text)

    license = LicenseInfo(None, None, None)
    try:
        license = parse_license(client.capture("/system license print", timeout=timeout))
    except TransportError as exc:
        log.warning("device %s licence probe failed: %s", device.name, exc)

    cloud = CloudInfo(None, None, None, None)
    try:
        cloud = parse_cloud(client.capture("/ip cloud print", timeout=timeout))
    except TransportError as exc:
        log.warning("device %s cloud probe failed: %s", device.name, exc)

    identity: str | None = None
    try:
        identity = parse_identity(client.capture("/system identity print", timeout=timeout))
    except TransportError as exc:
        log.warning("device %s identity probe failed: %s", device.name, exc)

    return InventoryResult(
        started_at=started,
        finished_at=int(time.time()),
        has_routerboard=fw.has_routerboard,
        model=fw.model,
        address=device.address,
        identity=identity,
        license=license,
        cloud=cloud,
    )


def parse_identity(text: str) -> str | None:
    """Parse ``/system identity print`` — the router's own name."""
    if is_unknown_command(text):
        return None
    return kv_dict(text).get("name") or None


def parse_license(text: str) -> LicenseInfo:
    """Parse ``/system license print``. CHR and RouterBOARD use different keys."""
    if is_unknown_command(text):
        return LicenseInfo(None, None, None)
    kv = kv_dict(text)
    # CHR: level + system-id (+ deadline-at / next-renewal-at).
    # RouterBOARD: nlevel + software-id.
    level = kv.get("level") or kv.get("nlevel")
    software_id = kv.get("software-id") or kv.get("system-id")
    deadline = kv.get("deadline-at") or kv.get("next-renewal-at") or kv.get("deadline")
    return LicenseInfo(
        level=level or None,
        software_id=software_id or None,
        deadline=deadline or None,
    )


def parse_cloud(text: str) -> CloudInfo:
    """Parse ``/ip cloud print`` — dns-name is RouterOS's "mynetname" handle."""
    if is_unknown_command(text):
        return CloudInfo(None, None, None, None)
    kv = kv_dict(text)
    ddns = kv.get("ddns-enabled")
    return CloudInfo(
        dns_name=kv.get("dns-name") or None,
        public_address=kv.get("public-address") or None,
        status=kv.get("status") or None,
        ddns_enabled=(ddns.lower() == "yes") if ddns else None,
    )


def inventory_summary(result: InventoryResult) -> str:
    parts: list[str] = [result.model or ("CHR" if not result.has_routerboard else "router")]
    if result.license.level:
        parts.append(f"licence {result.license.level}")
    if result.cloud.dns_name:
        parts.append(result.cloud.dns_name)
    return " · ".join(parts)

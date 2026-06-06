"""Update availability + routerboard firmware checks.

These are read-only — they ask RouterOS what's available and report back. Applying
the update is a separate, approval-gated workflow (see ``apply.py``).
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

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class UpdateInfo:
    channel: str | None
    installed_version: str | None
    latest_version: str | None
    status: str | None
    available: bool


@dataclass(frozen=True)
class FirmwareInfo:
    has_routerboard: bool
    model: str | None
    current_firmware: str | None
    upgrade_firmware: str | None
    mismatch: bool


@dataclass(frozen=True)
class UpdateCheckResult:
    started_at: int
    finished_at: int
    update: UpdateInfo
    firmware: FirmwareInfo


class UpdateCheckError(RuntimeError):
    """Raised when neither the package check nor the firmware check could run."""


class _Capture(Protocol):
    def capture(self, command: str, *, timeout: float | None = ...) -> str: ...


def run_update_check(
    device: DeviceConfig,
    defaults: Defaults,
    *,
    capture: _Capture | None = None,
) -> UpdateCheckResult:
    """Run the package + routerboard checks over SSH and parse the output."""
    started = int(time.time())
    client = capture or SSHTransport(device, defaults)
    timeout = defaults.update_check_timeout_seconds
    try:
        # check-for-updates triggers the server query AND prints the result
        # in the same call, so we don't need a separate `print` afterwards.
        update_text = client.capture(
            "/system package update check-for-updates",
            timeout=timeout,
        )
        firmware_text = client.capture(
            "/system routerboard print",
            timeout=defaults.connect_timeout_seconds + 2,
        )
    except TransportError as exc:
        raise UpdateCheckError(f"capture failed: {exc}") from exc

    return UpdateCheckResult(
        started_at=started,
        finished_at=int(time.time()),
        update=parse_update(update_text),
        firmware=parse_firmware(firmware_text),
    )


def parse_update(text: str) -> UpdateInfo:
    """Extract package update state from `check-for-updates` output."""
    kv = kv_dict(text)
    installed = kv.get("installed-version")
    latest = kv.get("latest-version")
    # `latest-version` is only populated once the server responded. If we caught
    # the "finding out latest version..." snapshot, treat as not-yet-available.
    available = bool(installed and latest and installed != latest)
    return UpdateInfo(
        channel=kv.get("channel"),
        installed_version=installed,
        latest_version=latest,
        status=kv.get("status"),
        available=available,
    )


def parse_firmware(text: str) -> FirmwareInfo:
    """Extract routerboard firmware state. Returns ``has_routerboard=False`` on CHR."""
    if is_unknown_command(text):
        return FirmwareInfo(
            has_routerboard=False,
            model=None,
            current_firmware=None,
            upgrade_firmware=None,
            mismatch=False,
        )
    kv = kv_dict(text)
    has_routerboard = kv.get("routerboard", "").lower() == "yes"
    current = kv.get("current-firmware")
    upgrade = kv.get("upgrade-firmware")
    mismatch = bool(has_routerboard and current and upgrade and current != upgrade)
    return FirmwareInfo(
        has_routerboard=has_routerboard,
        model=kv.get("model"),
        current_firmware=current,
        upgrade_firmware=upgrade,
        mismatch=mismatch,
    )


def update_summary(result: UpdateCheckResult) -> str:
    upd = result.update
    parts: list[str] = []
    if upd.available:
        parts.append(f"update {upd.installed_version} → {upd.latest_version} ({upd.channel})")
    elif upd.installed_version:
        parts.append(f"up to date on {upd.installed_version} ({upd.channel})")
    else:
        parts.append("update status unknown")
    fw = result.firmware
    if fw.has_routerboard and fw.mismatch:
        parts.append(f"firmware mismatch {fw.current_firmware} → {fw.upgrade_firmware}")
    elif fw.has_routerboard and fw.current_firmware:
        parts.append(f"firmware {fw.current_firmware}")
    return " · ".join(parts)

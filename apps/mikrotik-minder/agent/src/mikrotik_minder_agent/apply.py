"""Approval-gated RouterOS update apply.

Workflow (mirrors README §"Safe update flow"):

1. Approval ticket is required and recorded in the job report.
2. Pre-checks: device reachable, update actually available, recent backup on disk,
   free space above ``min_free_mib``.
3. Capture ``before`` snapshot (version, free space, identity).
4. Issue ``/system package update install`` — RouterOS downloads, installs, reboots.
5. Wait for the router to disappear, then return (configurable timeouts).
6. Capture ``after`` snapshot and report ``kind=update_apply``.

Failures at any stage produce ``status=failed`` jobs, which the worker turns into
``update_failed`` critical alerts.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .config import AgentConfig, DeviceConfig
from .rosparse import kv_dict
from .transports import TransportError
from .transports.ssh import SSHTransport
from .updates import run_update_check

log = logging.getLogger(__name__)


class ApplyError(RuntimeError):
    """Update apply could not start."""


class ApplyAborted(ApplyError):
    """A pre-check failed — the router was NOT touched."""


class ApplyTimedOut(ApplyError):
    """The router did not return to service within the deadline."""


@dataclass(frozen=True)
class ResourceSnapshot:
    version: str | None
    free_hdd_space: str | None
    identity: str | None
    uptime: str | None
    board_name: str | None


@dataclass(frozen=True)
class ApplyResult:
    started_at: int
    finished_at: int
    ticket: str
    before: ResourceSnapshot
    after: ResourceSnapshot
    downtime_seconds: int


class _Capture(Protocol):
    def capture(self, command: str, *, timeout: float | None = ...) -> str: ...


def find_recent_backup(
    backup_dir: Path,
    device_name: str,
    *,
    max_age_seconds: int,
    now: float | None = None,
) -> Path | None:
    """Return the newest ``*.backup`` for the device if it's fresh enough."""
    device_dir = backup_dir / device_name
    if not device_dir.is_dir():
        return None
    now_ts = now if now is not None else time.time()
    fresh = [
        p for p in device_dir.glob("*.backup")
        if now_ts - p.stat().st_mtime <= max_age_seconds
    ]
    if not fresh:
        return None
    return max(fresh, key=lambda p: p.stat().st_mtime)


_FREE_MIB_RE = re.compile(r"^([\d.]+)\s*([KMG]i?B)?$", re.IGNORECASE)


def parse_free_space_mib(value: str | None) -> float | None:
    """Parse ``free-hdd-space`` strings like ``46.2GiB`` / ``739.6MiB``."""
    if not value:
        return None
    m = _FREE_MIB_RE.match(value.strip())
    if not m:
        return None
    num = float(m.group(1))
    unit = (m.group(2) or "B").upper().replace("I", "")
    factor = {"B": 1 / 1024 / 1024, "KB": 1 / 1024, "MB": 1.0, "GB": 1024.0}.get(unit)
    if factor is None:
        return None
    return num * factor


def snapshot(channel: _Capture, *, timeout: float = 10.0) -> ResourceSnapshot:
    """Pull the version / free space / identity used for before/after comparison.

    Two commands: ``/system identity get name`` for the operator-set device
    name, and ``/system resource print`` for hardware / version state. We keep
    them as distinct fields because ``board-name`` is the model (e.g.
    ``RB5009UPr+S+``), not the identity an operator would search by.
    """
    raw = channel.capture("/system resource print", timeout=timeout)
    kv = kv_dict(raw)
    # identity is informational; if the second command fails for any reason
    # (different transport, permission, network blip) we keep the snapshot.
    try:
        identity_raw = channel.capture(":put [/system identity get name]", timeout=timeout)
    except (TransportError, OSError):
        identity_raw = ""
    identity = identity_raw.strip() or None
    return ResourceSnapshot(
        version=kv.get("version"),
        free_hdd_space=kv.get("free-hdd-space"),
        identity=identity,
        uptime=kv.get("uptime"),
        board_name=kv.get("board-name"),
    )


def wait_for_reboot(
    device: DeviceConfig,
    defaults,
    *,
    max_wait_seconds: int = 600,
    poll_seconds: float = 10.0,
    grace_after_install_seconds: float = 5.0,
) -> tuple[int, int]:
    """Wait for the router to drop and return. Returns (offline_at, online_at)."""
    # 1. Grace period: the router needs a moment to actually start tearing down.
    time.sleep(grace_after_install_seconds)
    deadline = time.time() + max_wait_seconds

    # 2. Wait for "gone". A successful probe means we missed the drop; keep trying.
    offline_at: int | None = None
    while time.time() < deadline and offline_at is None:
        try:
            SSHTransport(device, defaults).capture(
                ":put [/system identity get name]",
                timeout=3,
            )
        except TransportError:
            offline_at = int(time.time())
            break
        time.sleep(poll_seconds)
    if offline_at is None:
        raise ApplyTimedOut("router never went offline; update may not have started")

    # 3. Wait for "back". Same probe, expect success.
    online_at: int | None = None
    while time.time() < deadline and online_at is None:
        try:
            SSHTransport(device, defaults).capture(
                ":put [/system identity get name]",
                timeout=5,
            )
            online_at = int(time.time())
        except TransportError:
            time.sleep(poll_seconds)
    if online_at is None:
        raise ApplyTimedOut(
            f"router still unreachable after {max_wait_seconds}s",
        )
    return offline_at, online_at


def apply_update(
    config: AgentConfig,
    device: DeviceConfig,
    *,
    ticket: str,
    min_free_mib: float = 100.0,
    max_backup_age_seconds: int = 24 * 60 * 60,
    max_wait_seconds: int = 600,
    require_backup: bool = True,
    channel: _Capture | None = None,
) -> ApplyResult:
    """Run the full safe-update flow against ``device``.

    Raises ``ApplyAborted`` for pre-check failures (the router is not touched).
    Raises ``ApplyTimedOut`` if the router never returns.
    Raises ``ApplyError`` for transport failures during the install command.
    """
    if not ticket or not ticket.strip():
        raise ApplyAborted("--approve TICKET is required")
    started = int(time.time())

    ssh = channel or SSHTransport(device, config.defaults)

    # Pre-check 1: reachable + capture before snapshot.
    try:
        before = snapshot(ssh)
    except TransportError as exc:
        raise ApplyAborted(f"device unreachable for pre-check: {exc}") from exc
    log.info("device %s before: version=%s free=%s",
             device.name, before.version, before.free_hdd_space)

    # Pre-check 2: free space.
    free_mib = parse_free_space_mib(before.free_hdd_space)
    if free_mib is None:
        raise ApplyAborted(f"could not parse free-hdd-space {before.free_hdd_space!r}")
    if free_mib < min_free_mib:
        raise ApplyAborted(
            f"only {free_mib:.0f} MiB free; require >= {min_free_mib:.0f} MiB",
        )

    # Pre-check 3: an update has to actually be available.
    update = run_update_check(device, config.defaults, capture=ssh).update
    if not update.available:
        raise ApplyAborted(
            f"no update available (installed {update.installed_version}, "
            f"latest {update.latest_version})",
        )

    # Pre-check 4: a recent backup exists locally.
    if require_backup:
        if config.backup is None:
            raise ApplyAborted("recent backup required, but no 'backup' section in config")
        backup_dir = Path(config.backup.dir).expanduser().resolve()
        recent = find_recent_backup(
            backup_dir, device.name, max_age_seconds=max_backup_age_seconds,
        )
        if recent is None:
            raise ApplyAborted(
                f"no backup for {device.name} newer than "
                f"{max_backup_age_seconds // 3600}h in {backup_dir}",
            )
        log.info("device %s pre-check backup: %s", device.name, recent)

    # Issue install. This reboots the router; the SSH session usually dies mid-command.
    log.info("device %s: issuing /system package update install (ticket %s)", device.name, ticket)
    try:
        ssh.capture(
            "/system package update install",
            timeout=config.defaults.connect_timeout_seconds + 30,
        )
    except TransportError as exc:
        # Sometimes the SSH session drops mid-install — that's expected. We can't
        # distinguish "router rebooted before reply" from "command actually failed"
        # without re-probing, so we proceed and let wait_for_reboot decide.
        log.info("device %s: install command ended with %s (often the reboot)", device.name, exc)

    # Wait for the reboot to complete.
    offline_at, online_at = wait_for_reboot(
        device, config.defaults,
        max_wait_seconds=max_wait_seconds,
    )

    # Capture after snapshot.
    try:
        after = snapshot(SSHTransport(device, config.defaults))
    except TransportError as exc:
        raise ApplyTimedOut(f"router back online but unreachable for snapshot: {exc}") from exc
    log.info(
        "device %s after: version=%s free=%s downtime=%ds",
        device.name, after.version, after.free_hdd_space, online_at - offline_at,
    )

    finished = int(time.time())
    return ApplyResult(
        started_at=started,
        finished_at=finished,
        ticket=ticket,
        before=before,
        after=after,
        downtime_seconds=online_at - offline_at,
    )


def apply_summary(result: ApplyResult) -> str:
    return (
        f"update_apply ok · {result.before.version} → {result.after.version} · "
        f"downtime {result.downtime_seconds}s · ticket {result.ticket}"
    )

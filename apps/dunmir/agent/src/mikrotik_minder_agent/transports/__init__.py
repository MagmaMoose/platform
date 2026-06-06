"""Pluggable transports for talking to RouterOS devices.

Two implementations: the RouterOS API (binary protocol on 8728/8729) and SSH (port 22).
Both expose the same ``Transport`` protocol so the agent can fall back from one to the
other without the rest of the agent caring which is in use.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..config import Defaults, DeviceConfig, effective_transport


class TransportError(RuntimeError):
    """Raised when a transport cannot connect or its probe fails."""


@dataclass(frozen=True)
class RouterboardFacts:
    """RouterBOARD hardware + firmware facts (``/system routerboard``).

    The API probe fills this so a hardware device shows its board model and
    firmware state without an SSH session. ``None`` means CHR / no routerboard.
    """

    model: str | None = None
    serial: str | None = None
    current_firmware: str | None = None
    upgrade_firmware: str | None = None

    @property
    def mismatch(self) -> bool:
        return bool(
            self.current_firmware
            and self.upgrade_firmware
            and self.current_firmware != self.upgrade_firmware
        )


@dataclass(frozen=True)
class ProbeResult:
    kind: str            # 'api' | 'ssh'
    identity: str | None
    version: str | None
    latency_ms: int
    board: str | None = None   # RouterOS board-name; the API probe fills it, SSH leaves None
    # RouterBOARD model + firmware, pulled over the API probe (None on CHR or SSH).
    routerboard: RouterboardFacts | None = None


class Transport(Protocol):
    kind: str

    def probe(self) -> ProbeResult:
        """Connect, run a cheap read-only command, close, return identifying info."""


def build_transports(device: DeviceConfig, defaults: Defaults) -> list[Transport]:
    """Resolve the transport order (primary first, fallback second) for a device.

    Imports are local so the agent doesn't pay the import cost of paramiko / librouteros
    when running in dry-run mode.
    """
    policy = effective_transport(device, defaults)
    order: list[str] = [policy.primary]
    if policy.fallback and policy.fallback != policy.primary:
        order.append(policy.fallback)

    out: list[Transport] = []
    for kind in order:
        if kind == "api":
            from .api import APITransport

            out.append(APITransport(device, defaults))
        elif kind == "ssh":
            from .ssh import SSHTransport

            out.append(SSHTransport(device, defaults))
    return out

"""RouterOS ICMP ping probe — packet loss + average RTT for health trends.

Runs ``/ping address=<target> count=<n>`` on the router (so it measures the
router's own path to the target, not the agent's) and parses the summary line:

    sent=5 received=5 packet-loss=0% min-rtt=9ms562us avg-rtt=10ms max-rtt=12ms

Off by default — the daemon only runs it when a ``ping_target`` is configured,
so we never generate surprise egress from a fleet of routers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from .config import Defaults, DeviceConfig
from .transports.ssh import SSHTransport

# A ping target is a hostname or IP (v4/v6). Validated before interpolation so a
# malformed config can't smuggle extra arguments into the RouterOS command.
_TARGET_RE = re.compile(r"^[A-Za-z0-9.:_-]+$")
# Summary tokens are space-separated key=value pairs on the final line(s).
_LOSS_RE = re.compile(r"packet-loss=(\d+(?:\.\d+)?)%")
_SENT_RE = re.compile(r"sent=(\d+)")
_RECEIVED_RE = re.compile(r"received=(\d+)")
_AVG_RE = re.compile(r"avg-rtt=([0-9a-z.]+)")
# RouterOS durations are concatenated unit chunks, e.g. "1s200ms", "9ms562us".
_DURATION_PART = re.compile(r"(\d+(?:\.\d+)?)(us|ms|s|m)")
_UNIT_MS = {"us": 0.001, "ms": 1.0, "s": 1000.0, "m": 60000.0}


@dataclass(frozen=True)
class PingResult:
    sent: int
    received: int
    packet_loss_pct: float
    avg_rtt_ms: float | None


class PingError(RuntimeError):
    """Raised when the ping output couldn't be parsed into a summary."""


class _Capture(Protocol):
    def capture(self, command: str, *, timeout: float | None = ...) -> str: ...


def run_ping(
    device: DeviceConfig,
    defaults: Defaults,
    target: str,
    count: int,
    *,
    capture: _Capture | None = None,
) -> PingResult:
    if not _TARGET_RE.match(target):
        raise PingError(f"invalid ping target: {target!r}")
    client = capture or SSHTransport(device, defaults)
    # Give RouterOS ~1s per echo plus the connect budget, so a slow target that
    # times out per-packet still returns its summary before we cut the channel.
    timeout = defaults.connect_timeout_seconds + count + 2
    text = client.capture(f"/ping address={target} count={int(count)}", timeout=timeout)
    return parse_ping(text)


def parse_ping(text: str) -> PingResult:
    loss = _LOSS_RE.search(text or "")
    if not loss:
        raise PingError("no packet-loss summary in ping output")
    sent_m = _SENT_RE.search(text)
    recv_m = _RECEIVED_RE.search(text)
    avg_m = _AVG_RE.search(text)
    return PingResult(
        sent=int(sent_m.group(1)) if sent_m else 0,
        received=int(recv_m.group(1)) if recv_m else 0,
        packet_loss_pct=float(loss.group(1)),
        avg_rtt_ms=_parse_ros_duration_ms(avg_m.group(1)) if avg_m else None,
    )


def _parse_ros_duration_ms(s: str) -> float | None:
    """Convert a RouterOS duration like ``9ms562us`` / ``1s200ms`` to milliseconds."""
    parts = _DURATION_PART.findall(s or "")
    if not parts:
        return None
    total = sum(float(value) * _UNIT_MS[unit] for value, unit in parts)
    return round(total, 3)

from __future__ import annotations

import pytest

from mikrotik_minder_agent.config import Defaults, DeviceConfig
from mikrotik_minder_agent.ping import (
    PingError,
    _parse_ros_duration_ms,
    parse_ping,
    run_ping,
)

PING_OK = """
  SEQ HOST                                     SIZE TTL TIME       STATUS
    0 1.1.1.1                                    56  56 9ms562us
    1 1.1.1.1                                    56  56 10ms
    2 1.1.1.1                                    56  56 11ms
    3 1.1.1.1                                    56  56 10ms
    4 1.1.1.1                                    56  56 12ms
    sent=5 received=5 packet-loss=0% min-rtt=9ms562us avg-rtt=10ms562us max-rtt=12ms
"""

PING_LOSS = """
  SEQ HOST                                     SIZE TTL TIME  STATUS
    0 1.1.1.1                                          timeout
    1 1.1.1.1                                    56  56 30ms
    sent=5 received=2 packet-loss=60% min-rtt=28ms avg-rtt=30ms max-rtt=33ms
"""

PING_ALL_LOST = """
    0 192.0.2.1                                        timeout
    sent=5 received=0 packet-loss=100%
"""

PING_GARBAGE = "login failure: not enough permissions"


def test_parse_ping_ok() -> None:
    r = parse_ping(PING_OK)
    assert r.sent == 5
    assert r.received == 5
    assert r.packet_loss_pct == 0.0
    assert r.avg_rtt_ms == pytest.approx(10.562, abs=0.001)


def test_parse_ping_partial_loss() -> None:
    r = parse_ping(PING_LOSS)
    assert r.packet_loss_pct == 60.0
    assert r.received == 2
    assert r.avg_rtt_ms == 30.0


def test_parse_ping_total_loss_has_no_rtt() -> None:
    r = parse_ping(PING_ALL_LOST)
    assert r.packet_loss_pct == 100.0
    assert r.received == 0
    assert r.avg_rtt_ms is None


def test_parse_ping_unparseable_raises() -> None:
    with pytest.raises(PingError):
        parse_ping(PING_GARBAGE)


def test_parse_duration_units() -> None:
    assert _parse_ros_duration_ms("10ms") == 10.0
    assert _parse_ros_duration_ms("9ms562us") == pytest.approx(9.562)
    assert _parse_ros_duration_ms("1s200ms") == 1200.0
    assert _parse_ros_duration_ms("500us") == 0.5
    assert _parse_ros_duration_ms("") is None


def test_run_ping_issues_count_bounded_command() -> None:
    class Cap:
        def __init__(self) -> None:
            self.commands: list[str] = []

        def capture(self, command: str, *, timeout: float | None = None) -> str:
            self.commands.append(command)
            return PING_OK

    cap = Cap()
    device = DeviceConfig(name="r", address="1.1.1.1", username="u", password="p")
    r = run_ping(device, Defaults(), "1.1.1.1", 5, capture=cap)
    assert r.packet_loss_pct == 0.0
    assert cap.commands == ["/ping address=1.1.1.1 count=5"]


def test_run_ping_rejects_malformed_target() -> None:
    class Cap:
        def capture(self, command: str, *, timeout: float | None = None) -> str:
            raise AssertionError("should not reach the transport for a bad target")

    device = DeviceConfig(name="r", address="1.1.1.1", username="u", password="p")
    with pytest.raises(PingError):
        run_ping(device, Defaults(), "1.1.1.1 count=99999;/system reboot", 5, capture=Cap())

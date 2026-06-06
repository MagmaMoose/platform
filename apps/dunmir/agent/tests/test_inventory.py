from __future__ import annotations

import pytest

from mikrotik_minder_agent.config import Defaults, DeviceConfig
from mikrotik_minder_agent.inventory import (
    InventoryError,
    inventory_summary,
    parse_cloud,
    parse_identity,
    parse_license,
    run_inventory,
)
from mikrotik_minder_agent.transports import TransportError

# CHR and RouterBOARD print licence info under different keys.
LICENSE_CHR = """
        system-id: ABCD1234WXYZ
            level: p1
      deadline-at: 2026-12-01
"""

LICENSE_ROUTERBOARD = """
      software-id: ABCD-EFGH
           nlevel: 6
"""

LICENSE_UNKNOWN = "bad command name license (line 1 column 9)"

CLOUD_FULL = """
          ddns-enabled: yes
  ddns-update-interval: none
        public-address: 203.0.113.7
              dns-name: 1234abcd5678.sn.mynetname.net
                status: updated
"""

CLOUD_DISABLED = """
          ddns-enabled: no
                status:
"""

# On a CHR the routerboard command doesn't exist.
ROUTERBOARD_CHR = "bad command name routerboard (line 1 column 9)"
ROUTERBOARD_RB = """
        routerboard: yes
              model: RB5009UPr+S+
   current-firmware: 7.18.2
   upgrade-firmware: 7.18.2
"""

IDENTITY = """
       name: oci-rtr-01
"""


class FakeCapture:
    """Maps a command prefix to canned output; raises on anything unexpected."""

    def __init__(self, responses: dict[str, str]) -> None:
        self._responses = responses
        self.commands: list[str] = []

    def capture(self, command: str, *, timeout: float | None = None) -> str:
        self.commands.append(command)
        for prefix, text in self._responses.items():
            if command.startswith(prefix):
                return text
        raise AssertionError(f"unexpected command: {command}")


def _device() -> DeviceConfig:
    return DeviceConfig(name="rtr", address="1.1.1.1", username="u", password="p")


def test_parse_license_chr() -> None:
    lic = parse_license(LICENSE_CHR)
    assert lic.level == "p1"
    assert lic.software_id == "ABCD1234WXYZ"
    assert lic.deadline == "2026-12-01"


def test_parse_license_routerboard() -> None:
    lic = parse_license(LICENSE_ROUTERBOARD)
    assert lic.level == "6"
    assert lic.software_id == "ABCD-EFGH"
    assert lic.deadline is None


def test_parse_license_unknown_command() -> None:
    lic = parse_license(LICENSE_UNKNOWN)
    assert lic.level is None
    assert lic.software_id is None


def test_parse_cloud_full() -> None:
    c = parse_cloud(CLOUD_FULL)
    assert c.dns_name == "1234abcd5678.sn.mynetname.net"
    assert c.public_address == "203.0.113.7"
    assert c.status == "updated"
    assert c.ddns_enabled is True


def test_parse_cloud_disabled() -> None:
    c = parse_cloud(CLOUD_DISABLED)
    assert c.ddns_enabled is False
    assert c.dns_name is None


def test_parse_identity() -> None:
    assert parse_identity(IDENTITY) == "oci-rtr-01"
    assert parse_identity("bad command name identity") is None


def test_run_inventory_chr_marks_no_routerboard() -> None:
    cap = FakeCapture(
        {
            "/system routerboard print": ROUTERBOARD_CHR,
            "/system license print": LICENSE_CHR,
            "/ip cloud print": CLOUD_FULL,
            "/system identity print": IDENTITY,
        },
    )
    result = run_inventory(_device(), Defaults(), capture=cap)
    assert result.has_routerboard is False
    assert result.model is None
    assert result.address == "1.1.1.1"
    assert result.identity == "oci-rtr-01"
    assert result.license.level == "p1"
    assert result.cloud.dns_name == "1234abcd5678.sn.mynetname.net"
    assert "CHR" in inventory_summary(result)


def test_run_inventory_routerboard() -> None:
    cap = FakeCapture(
        {
            "/system routerboard print": ROUTERBOARD_RB,
            "/system license print": LICENSE_ROUTERBOARD,
            "/ip cloud print": CLOUD_DISABLED,
            "/system identity print": IDENTITY,
        },
    )
    result = run_inventory(_device(), Defaults(), capture=cap)
    assert result.has_routerboard is True
    assert result.model == "RB5009UPr+S+"
    assert "RB5009UPr+S+" in inventory_summary(result)


def test_run_inventory_survives_partial_probe_failure() -> None:
    # routerboard succeeds, licence raises mid-run → licence stays empty, no crash.
    class FlakyCapture:
        def capture(self, command: str, *, timeout: float | None = None) -> str:
            if command.startswith("/system routerboard"):
                return ROUTERBOARD_RB
            raise TransportError("session dropped")

    result = run_inventory(_device(), Defaults(), capture=FlakyCapture())
    assert result.has_routerboard is True
    assert result.license.level is None
    assert result.cloud.dns_name is None


def test_run_inventory_connect_failure_raises() -> None:
    class Boom:
        def capture(self, command: str, *, timeout: float | None = None) -> str:
            raise TransportError("connect refused")

    with pytest.raises(InventoryError):
        run_inventory(_device(), Defaults(), capture=Boom())

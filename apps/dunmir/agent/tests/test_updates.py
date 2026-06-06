from __future__ import annotations

from mikrotik_minder_agent.updates import parse_firmware, parse_update

# These fixtures are real captured output from RouterOS 7.18.2 (oci-rtr-01),
# plus a small synthetic "no updates" variant for the up-to-date path.

UPDATE_AVAILABLE = """
            channel: stable
  installed-version: 7.18.2
     latest-version: 7.22.3
             status: New version is available
"""

UPDATE_INTERIM = """
            channel: stable
  installed-version: 7.18.2
             status: finding out latest version...
"""

UPDATE_UP_TO_DATE = """
            channel: stable
  installed-version: 7.22.3
     latest-version: 7.22.3
             status: System is already up to date
"""

ROUTERBOARD_MATCH = """
        routerboard: yes
              model: RB5009UPr+S+
       serial-number: HG7081JV8K
       firmware-type: ipq8019L
   factory-firmware: 7.7
    current-firmware: 7.18.2
    upgrade-firmware: 7.18.2
"""

ROUTERBOARD_MISMATCH = """
        routerboard: yes
              model: RB5009UPr+S+
    current-firmware: 7.17.2
    upgrade-firmware: 7.18.2
"""

CHR_RESPONSE = "bad command name routerboard (line 1 column 9)"


def test_parse_update_available() -> None:
    info = parse_update(UPDATE_AVAILABLE)
    assert info.available is True
    assert info.installed_version == "7.18.2"
    assert info.latest_version == "7.22.3"
    assert info.channel == "stable"


def test_parse_update_interim_state_not_available() -> None:
    """If we sample before the check finished, don't flag a false alert."""
    info = parse_update(UPDATE_INTERIM)
    assert info.available is False
    assert info.latest_version is None


def test_parse_update_up_to_date() -> None:
    info = parse_update(UPDATE_UP_TO_DATE)
    assert info.available is False
    assert info.installed_version == "7.22.3"
    assert info.latest_version == "7.22.3"


def test_parse_firmware_aligned() -> None:
    fw = parse_firmware(ROUTERBOARD_MATCH)
    assert fw.has_routerboard is True
    assert fw.model == "RB5009UPr+S+"
    assert fw.mismatch is False


def test_parse_firmware_mismatch() -> None:
    fw = parse_firmware(ROUTERBOARD_MISMATCH)
    assert fw.has_routerboard is True
    assert fw.mismatch is True
    assert fw.current_firmware == "7.17.2"
    assert fw.upgrade_firmware == "7.18.2"


def test_parse_firmware_chr_no_routerboard() -> None:
    fw = parse_firmware(CHR_RESPONSE)
    assert fw.has_routerboard is False
    assert fw.mismatch is False
    assert fw.current_firmware is None

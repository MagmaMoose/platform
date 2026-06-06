from __future__ import annotations

from mikrotik_minder_agent.normalise import normalise_export


def test_strips_routeros_timestamp_header() -> None:
    raw = "\n".join(
        [
            "# 2024-03-15 14:23:45 by RouterOS 7.18.2",
            "# software id = ABCD-EFGH",
            "/system identity",
            'set name="rtr-01"',
        ],
    )
    out = normalise_export(raw)
    assert out.startswith("# software id")
    assert "by RouterOS" not in out


def test_passes_through_when_no_header() -> None:
    raw = "/system identity\nset name=\"rtr-01\"\n"
    assert normalise_export(raw) == raw


def test_handles_empty_input() -> None:
    assert normalise_export("") == ""
    assert normalise_export("\n\n\n") == ""


def test_trailing_newline_is_idempotent() -> None:
    raw = "/ip address\nadd address=1.1.1.1/32\n"
    assert normalise_export(raw) == raw
    assert normalise_export(normalise_export(raw)) == raw

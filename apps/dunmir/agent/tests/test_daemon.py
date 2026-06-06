from __future__ import annotations

from mikrotik_minder_agent.config import AgentConfig, Defaults, DeviceConfig, ServerConfig
from mikrotik_minder_agent.daemon import (
    _STARTUP_STAGGER_MAX_SECONDS,
    _STARTUP_STAGGER_STEP_SECONDS,
    Daemon,
)
from mikrotik_minder_agent.minder import MinderError
from mikrotik_minder_agent.transports import ProbeResult


class _HeartbeatOnlyMinder:
    """Heartbeat succeeds, but the follow-up job POST fails (transient hiccup)."""

    def send_heartbeat(self, device: str, status: str = "ok") -> None:
        pass

    def send_job(self, report: object) -> None:
        raise MinderError("simulated jobs-endpoint failure")


def _config(n: int) -> AgentConfig:
    return AgentConfig(
        server=ServerConfig(url="https://x", agent_token="t"),
        defaults=Defaults(),
        devices=tuple(
            DeviceConfig(name=f"rtr-{i:02d}", address=f"10.0.0.{i}", username="u", password="p")
            for i in range(n)
        ),
    )


def test_startup_offsets_are_staggered_per_device() -> None:
    cfg = _config(5)
    daemon = Daemon(cfg)
    offsets = [daemon._state[d.name].startup_offset for d in cfg.devices]
    # Distinct and increasing, first device runs immediately — so a restart can't
    # fire all five devices' exports/backups in the same instant.
    assert offsets == [i * _STARTUP_STAGGER_STEP_SECONDS for i in range(5)]
    assert offsets[0] == 0.0
    assert len(set(offsets)) == 5


def test_startup_offset_is_capped_for_large_fleets() -> None:
    n = int(_STARTUP_STAGGER_MAX_SECONDS // _STARTUP_STAGGER_STEP_SECONDS) + 5
    cfg = _config(n)
    daemon = Daemon(cfg)
    offsets = [daemon._state[d.name].startup_offset for d in cfg.devices]
    assert max(offsets) == _STARTUP_STAGGER_MAX_SECONDS
    assert all(0.0 <= o <= _STARTUP_STAGGER_MAX_SECONDS for o in offsets)


def test_default_probe_features() -> None:
    d = Defaults()
    assert d.inventory_check_interval_seconds == 3600  # inventory on by default
    assert d.ping_target is None  # packet-loss probe off until a target is configured
    assert d.ping_count == 5


def test_inventory_due_respects_interval_and_last_run() -> None:
    cfg = _config(1)
    daemon = Daemon(cfg)
    device = cfg.devices[0]
    # Default interval is hourly and last_inventory starts at 0 → due immediately.
    assert daemon._inventory_due(device, 1000.0) is True
    daemon._state[device.name].last_inventory = 1000.0
    assert daemon._inventory_due(device, 1000.0 + 100) is False
    assert daemon._inventory_due(device, 1000.0 + 3600) is True


def test_inventory_due_false_when_disabled() -> None:
    cfg = AgentConfig(
        server=ServerConfig(url="https://x", agent_token="t"),
        defaults=Defaults(inventory_check_interval_seconds=None),
        devices=(DeviceConfig(name="rtr", address="1.1.1.1", username="u", password="p"),),
    )
    daemon = Daemon(cfg)
    assert daemon._inventory_due(cfg.devices[0], 99999.0) is False


def test_job_send_failure_does_not_flip_healthy_device() -> None:
    """A successful heartbeat is the source of truth: if the secondary health_check
    job POST fails, the device must still be treated as healthy (not flipped to a
    failure that drives a false 'down')."""
    cfg = _config(1)
    daemon = Daemon(cfg)
    dev = cfg.devices[0]
    result = ProbeResult(kind="ssh", identity="rtr-00", version="7.18.2", latency_ms=5)
    healthy = daemon._report(
        dev,
        _HeartbeatOnlyMinder(),
        ok=True,
        status_label="ok",
        transport_kind="ssh",
        result=result,
        error=None,
        started=1,
        finished=2,
    )
    assert healthy is True

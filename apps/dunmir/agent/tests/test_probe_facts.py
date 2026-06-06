"""RouterBOARD-over-API parsing + per-transport status in the health_check job."""

from __future__ import annotations

import pytest

from mikrotik_minder_agent.config import AgentConfig, Defaults, DeviceConfig, ServerConfig
from mikrotik_minder_agent.daemon import Daemon
from mikrotik_minder_agent.transports import ProbeResult, RouterboardFacts, TransportError
from mikrotik_minder_agent.transports.api import _as_bool, _routerboard_facts


class _FakeApi:
    """Stand-in for a librouteros connection: callable, yields rows per command."""

    def __init__(self, rows: dict[str, list[dict]]) -> None:
        self._rows = rows

    def __call__(self, *, cmd: str):
        return iter(self._rows.get(cmd, []))


def test_routerboard_facts_hardware() -> None:
    api = _FakeApi(
        {
            "/system/routerboard/print": [
                {
                    "routerboard": True,
                    "model": "RB5009UG+S+IN",
                    "serial-number": "HEX123",
                    "current-firmware": "7.21.2",
                    "upgrade-firmware": "7.21.2",
                },
            ],
        },
    )
    rb = _routerboard_facts(api)
    assert rb is not None
    assert rb.model == "RB5009UG+S+IN"
    assert rb.serial == "HEX123"
    assert rb.current_firmware == "7.21.2"
    assert rb.mismatch is False


def test_routerboard_firmware_mismatch() -> None:
    api = _FakeApi(
        {
            "/system/routerboard/print": [
                {"routerboard": "true", "current-firmware": "7.20.0", "upgrade-firmware": "7.21.2"},
            ],
        },
    )
    rb = _routerboard_facts(api)
    assert rb is not None and rb.mismatch is True


def test_routerboard_chr_is_none() -> None:
    api = _FakeApi({"/system/routerboard/print": [{"routerboard": False}]})
    assert _routerboard_facts(api) is None


def test_routerboard_read_error_is_swallowed() -> None:
    class _Boom:
        def __call__(self, *, cmd: str):
            raise RuntimeError("api blew up")

    assert _routerboard_facts(_Boom()) is None


def test_as_bool_accepts_real_and_string_booleans() -> None:
    assert _as_bool(True) and _as_bool("true") and _as_bool("TRUE")
    assert not _as_bool(False) and not _as_bool("false") and not _as_bool(None)


# --- daemon health_check details -----------------------------------------------------------------


def _config() -> AgentConfig:
    return AgentConfig(
        server=ServerConfig(url="https://x", agent_token="t"),
        defaults=Defaults(),
        devices=(DeviceConfig(name="senixa", address="10.0.0.9", username="u", password="p"),),
    )


class _CapturingMinder:
    def __init__(self) -> None:
        self.jobs: list[object] = []

    def send_heartbeat(self, device: str, status: str = "ok") -> None:
        pass

    def send_job(self, report: object) -> None:
        self.jobs.append(report)


def test_health_details_carry_routerboard_and_transports() -> None:
    cfg = _config()
    daemon = Daemon(cfg)
    dev = cfg.devices[0]
    rb = RouterboardFacts(
        model="RB5009UG+S+IN", current_firmware="7.21.2", upgrade_firmware="7.21.2",
    )
    result = ProbeResult(
        kind="api", identity="senixa", version="7.21.2", latency_ms=12,
        board="RB5009UG+S+IN", routerboard=rb,
    )
    minder = _CapturingMinder()
    daemon._report(
        dev, minder, ok=True, status_label="ok", transport_kind="api",
        result=result, error=None, started=1, finished=2,
        probes={"api": (result, None), "ssh": (None, "SSH connect failed: Authentication failed.")},
    )
    job = minder.jobs[-1]
    assert job.kind == "health_check"
    details = job.details
    assert details["routerboard"]["model"] == "RB5009UG+S+IN"
    assert details["routerboard"]["mismatch"] is False
    assert details["transports"]["api"]["ok"] is True
    assert details["transports"]["ssh"]["ok"] is False
    assert "Authentication failed" in details["transports"]["ssh"]["reason"]


def test_tick_probes_every_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    import mikrotik_minder_agent.daemon as daemon_mod

    cfg = _config()
    daemon = Daemon(cfg)
    dev = cfg.devices[0]

    class _T:
        def __init__(self, kind: str, ok: bool) -> None:
            self.kind = kind
            self._ok = ok

        def probe(self) -> ProbeResult:
            if self._ok:
                return ProbeResult(
                    kind=self.kind, identity="senixa", version="7.21.2", latency_ms=3,
                )
            raise TransportError(f"{self.kind} unreachable")

    # API works, SSH fails — the device is up, but SSH must still be reported red.
    monkeypatch.setattr(
        daemon_mod, "build_transports", lambda d, defaults: [_T("api", True), _T("ssh", False)],
    )
    minder = _CapturingMinder()
    assert daemon._tick(dev, minder) is True
    health = [j for j in minder.jobs if j.kind == "health_check"][-1]
    assert health.details["transports"]["api"]["ok"] is True
    assert health.details["transports"]["ssh"]["ok"] is False
    assert "unreachable" in health.details["transports"]["ssh"]["reason"]

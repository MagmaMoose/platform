from __future__ import annotations

from pathlib import Path

import pytest

from mikrotik_minder_agent.config import Defaults, DeviceConfig, SSHDefaults
from mikrotik_minder_agent.transports import ProbeResult, TransportError
from mikrotik_minder_agent.transports.ssh import SSHTransport


def _device() -> DeviceConfig:
    return DeviceConfig(name="r", address="1.1.1.1", username="u", password="p")


class _Out:
    """Stand-in for a paramiko stdout/stderr stream."""

    def __init__(self, data: bytes = b"", *, raise_timeout: bool = False) -> None:
        self._data = data
        self._raise = raise_timeout

    def read(self) -> bytes:
        if self._raise:
            raise TimeoutError("timed out")  # TimeoutError is an OSError subclass
        return self._data


class _FakeClient:
    """Minimal paramiko SSHClient stand-in, injected via _open_session."""

    def __init__(self, responder) -> None:
        self._responder = responder
        self.closed = False

    def exec_command(self, command: str, timeout: float | None = None):
        return self._responder(command)

    def close(self) -> None:
        self.closed = True


def test_capture_wraps_read_timeout_as_transport_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A socket.timeout from stdout.read() (slow /export) must surface as a
    TransportError, not an uncaught OSError that would kill the device thread."""
    t = SSHTransport(_device(), Defaults())
    client = _FakeClient(lambda cmd: (None, _Out(raise_timeout=True), _Out(b"")))
    monkeypatch.setattr(t, "_open_session", lambda paramiko: client)
    with pytest.raises(TransportError):
        t.capture("/export", timeout=1)
    assert client.closed  # the finally still closed the session


def test_probe_treats_identity_as_best_effort(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failing identity sub-command must not fail the probe — version/resource
    is the liveness signal."""

    def responder(cmd: str):
        if "resource" in cmd:
            return (None, _Out(b"  version: 7.18.2\n"), _Out(b""))
        return (None, _Out(raise_timeout=True), _Out(b""))  # identity times out

    t = SSHTransport(_device(), Defaults())
    monkeypatch.setattr(t, "_open_session", lambda paramiko: _FakeClient(responder))
    result = t.probe()
    assert isinstance(result, ProbeResult)
    assert result.version == "7.18.2"
    assert result.identity is None


def _fake_paramiko(recorded: dict):
    class FakeClient:
        def set_missing_host_key_policy(self, policy) -> None:
            recorded["policy"] = type(policy).__name__

        def load_host_keys(self, path: str) -> None:
            recorded["loaded"] = path

        def save_host_keys(self, path: str) -> None:
            recorded["saved"] = path

        def connect(self, **kwargs) -> None:
            recorded["connected"] = True

        def close(self) -> None:
            pass

    class SSHException(Exception):
        pass

    ns = type("FakeParamiko", (), {})
    ns.SSHClient = FakeClient
    ns.SSHException = SSHException
    return ns


def test_open_session_uses_warn_accept_without_known_hosts() -> None:
    recorded: dict = {}
    t = SSHTransport(_device(), Defaults())
    t._open_session(_fake_paramiko(recorded))
    assert recorded["policy"] == "_WarnAcceptPolicy"
    assert "saved" not in recorded  # nothing pinned when unset


def test_open_session_pins_host_keys_when_configured(tmp_path: Path) -> None:
    recorded: dict = {}
    kh = tmp_path / "router_known_hosts"
    t = SSHTransport(_device(), Defaults(ssh=SSHDefaults(known_hosts_path=str(kh))))
    t._open_session(_fake_paramiko(recorded))
    assert recorded["policy"] == "_TofuAddPolicy"
    assert recorded.get("saved") == str(kh)  # persisted for next-connect verification


def _fake_paramiko_auth(exc_to_raise):
    """Fake paramiko whose connect() raises a given auth exception."""

    class SSHException(Exception):
        pass

    class AuthenticationException(SSHException):
        pass

    class BadAuthenticationType(AuthenticationException):
        def __init__(self, message: str, allowed_types: list[str]) -> None:
            super().__init__(message)
            self.allowed_types = allowed_types

    class FakeClient:
        def set_missing_host_key_policy(self, policy) -> None:
            pass

        def connect(self, **kwargs) -> None:
            raise exc_to_raise(BadAuthenticationType, AuthenticationException)

        def close(self) -> None:
            pass

    ns = type("FakeParamiko", (), {})
    ns.SSHClient = FakeClient
    ns.SSHException = SSHException
    ns.AuthenticationException = AuthenticationException
    ns.BadAuthenticationType = BadAuthenticationType
    return ns


def test_bad_auth_type_reports_allowed_methods_and_routeros_hint() -> None:
    # Router only offers publickey → we surface that + the RouterOS knob to check.
    ns = _fake_paramiko_auth(lambda bad, _auth: bad("no password", ["publickey"]))
    t = SSHTransport(_device(), Defaults())
    with pytest.raises(TransportError) as ei:
        t._open_session(ns)
    msg = str(ei.value)
    assert "publickey" in msg
    assert "always-allow-password-login" in msg


def test_auth_failure_points_at_router_not_password() -> None:
    # Password mode: secret rejected — note it's the same password the API uses.
    ns = _fake_paramiko_auth(lambda _bad, auth: auth("Authentication failed."))
    t = SSHTransport(_device(), Defaults())  # _device() has a password
    msg = _raise_msg(t, ns)
    assert "same password the API probe uses" in msg


def test_auth_failure_with_key_only_does_not_claim_api_parity() -> None:
    # Key-only mode: the API probe uses a password, so the "same credential" claim
    # would be wrong — the message must stay accurate.
    ns = _fake_paramiko_auth(lambda _bad, auth: auth("Authentication failed."))
    dev = DeviceConfig(name="r", address="1.1.1.1", username="u", ssh_key_path="id_ed25519")
    msg = _raise_msg(SSHTransport(dev, Defaults()), ns)
    assert "an SSH key" in msg
    assert "same password the API probe uses" not in msg
    assert "independent" in msg


def _raise_msg(transport: SSHTransport, ns) -> str:
    with pytest.raises(TransportError) as ei:
        transport._open_session(ns)
    return str(ei.value)

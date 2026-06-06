"""RouterOS API transport (librouteros)."""

from __future__ import annotations

import logging
import time
from typing import Any

from ..config import Defaults, DeviceConfig
from . import ProbeResult, TransportError

log = logging.getLogger(__name__)


class APITransport:
    kind = "api"

    def __init__(self, device: DeviceConfig, defaults: Defaults) -> None:
        if not device.password:
            raise TransportError(f"device {device.name}: API transport needs a password")
        self._device = device
        self._defaults = defaults

    @property
    def port(self) -> int:
        if self._device.api_port is not None:
            return self._device.api_port
        use_tls = (
            self._device.use_tls if self._device.use_tls is not None else self._defaults.api.use_tls
        )
        return self._defaults.api.tls_port if use_tls else self._defaults.api.port

    def probe(self) -> ProbeResult:
        # librouteros raises a variety of errors on failure; normalise to TransportError.
        try:
            from librouteros import connect
            from librouteros.exceptions import LibRouterosError
        except ImportError as exc:  # pragma: no cover - dependency declared in pyproject
            raise TransportError("librouteros is required for the API transport") from exc

        start = time.monotonic()
        try:
            api = connect(
                host=self._device.address,
                username=self._device.username,
                password=self._device.password or "",
                port=self.port,
                # librouteros uses this as the socket timeout for the connect AND
                # the login handshake; a busy RouterOS can be slow to log in, so
                # don't let the short TCP-connect default cut a healthy login off.
                timeout=max(self._defaults.connect_timeout_seconds, 15.0),
            )
        except (TimeoutError, LibRouterosError, OSError) as exc:
            raise TransportError(f"API connect failed: {exc}") from exc

        try:
            identity = _first_value(api, "/system/identity/print", "name")
            # One /system/resource row carries BOTH the RouterOS version and the
            # board-name, so the API probe can report hardware too — no SSH needed.
            resource = _first_row(api, "/system/resource/print")
        except (LibRouterosError, OSError) as exc:
            raise TransportError(f"API probe command failed: {exc}") from exc
        finally:
            try:
                api.close()
            except Exception:
                log.debug("api close raised, ignoring", exc_info=True)

        return ProbeResult(
            kind=self.kind,
            identity=identity,
            version=_str(resource.get("version")),
            board=_str(resource.get("board-name")),
            latency_ms=int((time.monotonic() - start) * 1000),
        )


def _first_value(api: Any, command: str, key: str) -> str | None:
    for row in api(cmd=command):
        if key in row:
            return str(row[key])
    return None


def _first_row(api: Any, command: str) -> dict[str, Any]:
    for row in api(cmd=command):
        return dict(row)
    return {}


def _str(value: Any) -> str | None:
    return None if value is None else str(value)

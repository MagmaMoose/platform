"""HTTP client for the Mikrotik Minder control plane.

Canonical contract: the JobReport / CommandRef shapes (and the /v1/ingest
protocol they ride) mirror ``@platform/schemas`` —
``packages/schemas/python/platform_schemas/dunmir.py`` (Pydantic) and
``packages/schemas/src/dunmir.ts`` (zod). They stay stdlib dataclasses HERE
because this agent is a published standalone CLI that deliberately avoids a
Pydantic dependency — change the contract in the package first, then keep
these in lockstep.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from .config import ServerConfig

log = logging.getLogger(__name__)


class MinderError(RuntimeError):
    """Raised when the control plane returns an error or is unreachable."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass
class JobReport:
    device: str | None
    kind: str
    status: str          # 'success' | 'warning' | 'failed' | 'skipped'
    started_at: int
    finished_at: int
    summary: str | None = None
    details: dict[str, Any] | None = None


@dataclass(frozen=True)
class CommandRef:
    """One pending command claimed from GET /v1/ingest/commands."""

    id: str
    device: str | None
    kind: str            # 'backup' | 'export' | 'update_apply' | 'sensitive_export'
    params: dict[str, Any]


class MinderClient:
    """Thin wrapper around the worker's /v1/ingest endpoints.

    Single retry on 5xx because we want fast paths to recover from transient
    Worker hiccups, but we don't want to mask sustained outages from the operator.
    """

    def __init__(self, server: ServerConfig, *, client: httpx.Client | None = None) -> None:
        self._server = server
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=server.url,
            timeout=server.timeout_seconds,
            headers={
                "authorization": f"Bearer {server.agent_token}",
                "content-type": "application/json",
                "user-agent": "mikrotik-minder-agent/0.0.0",
            },
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> MinderClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # --- Public API ---

    def send_heartbeat(self, device: str, status: str = "ok") -> str:
        """POST a heartbeat. Returns the device id assigned by the server."""
        data = self._post_json("/v1/ingest/heartbeat", {"device": device, "status": status})
        return str(data.get("device_id", ""))

    def send_job(self, job: JobReport) -> str:
        """POST a job report. Returns the job id."""
        body: dict[str, Any] = {
            "kind": job.kind,
            "status": job.status,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
        }
        if job.device is not None:
            body["device"] = job.device
        if job.summary is not None:
            body["summary"] = job.summary
        if job.details is not None:
            body["details"] = job.details
        data = self._post_json("/v1/ingest/jobs", body)
        return str(data.get("job_id", ""))

    def fetch_config(self) -> dict[str, Any]:
        """GET the agent's device config (used by ``config_source: remote``).

        Old workers without the endpoint return 404 → ``MinderError(status_code=404)``,
        which the caller treats as "fall back to local devices".
        """
        return self._get_json("/v1/ingest/config")

    def register_public_key(self, public_key: str) -> None:
        """Register the agent's Curve25519 public key (Pro vault) so the licensed
        UI can seal credentials to it. Best-effort: old workers without the
        endpoint return 404, which the caller can ignore."""
        self._post_json("/v1/ingest/agent-key", {"public_key": public_key})

    def get_commands(self) -> list[CommandRef]:
        """Claim queued commands for this agent. Empty list = nothing to do.

        Old workers without the command-dispatch endpoint return 404 — treated
        as "nothing to do" so the agent stays compatible across worker versions.
        """
        try:
            data = self._get_json("/v1/ingest/commands")
        except MinderError as exc:
            if exc.status_code == 404:
                return []
            raise
        items = data.get("commands") or []
        out: list[CommandRef] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            params = item.get("params")
            out.append(
                CommandRef(
                    id=str(item.get("id") or ""),
                    device=item.get("device") if isinstance(item.get("device"), str) else None,
                    kind=str(item.get("kind") or ""),
                    params=params if isinstance(params, dict) else {},
                ),
            )
        return out

    def report_command_result(
        self,
        cmd_id: str,
        status: str,
        *,
        result: dict[str, Any] | None = None,
        artifact: str | None = None,
    ) -> None:
        """Report a claimed command's outcome (succeeded / failed)."""
        body: dict[str, Any] = {"status": status}
        if result is not None:
            body["result"] = result
        if artifact is not None:
            body["artifact"] = artifact
        self._post_json(f"/v1/ingest/commands/{cmd_id}/result", body)

    def upload_backup(
        self,
        device: str,
        file_path: Path,
        *,
        sha256: str | None = None,
    ) -> str:
        """Stream an encrypted backup body to the worker. Returns the backup id.

        Body is the raw RouterOS-encrypted ``.backup`` file — we never touch
        plaintext. The worker writes it to R2 and catalogues the metadata so
        the Pro UI can list / download it. Older workers without backup
        endpoints return 404 → ``MinderError(status_code=404)`` lets the
        caller treat the upload as optional.
        """
        name = file_path.name
        path = f"/v1/ingest/backups/{quote(device, safe='')}/{quote(name, safe='')}"
        if sha256:
            path += f"?sha256={sha256}"
        last_exc: Exception | None = None
        for attempt in (1, 2):
            try:
                with file_path.open("rb") as f:
                    resp = self._client.put(
                        path,
                        content=f,
                        headers={"content-type": "application/octet-stream"},
                        timeout=self._server.timeout_seconds * 6,
                    )
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt == 1:
                    log.warning("minder PUT %s transport error, retrying once: %s", path, exc)
                    continue
                raise MinderError(f"transport error uploading backup: {exc}") from exc

            if 500 <= resp.status_code < 600 and attempt == 1:
                log.warning("minder PUT %s -> %s, retrying once", path, resp.status_code)
                continue

            if resp.status_code >= 400:
                detail = _safe_error(resp)
                raise MinderError(
                    f"minder PUT {path} returned HTTP {resp.status_code}: {detail}",
                    status_code=resp.status_code,
                )

            try:
                data = resp.json()
            except ValueError as exc:
                raise MinderError("upload response was not JSON") from exc
            backup_id = data.get("id")
            if not isinstance(backup_id, str) or not backup_id:
                raise MinderError(
                    f"minder PUT {path} returned success with missing/empty id",
                )
            return backup_id

        raise MinderError(f"upload backup {name} failed: {last_exc}")


    # --- Internals ---

    def _post_json(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        last_exc: Exception | None = None
        for attempt in (1, 2):
            try:
                resp = self._client.post(path, json=body)
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt == 1:
                    log.warning("minder %s transport error, retrying once: %s", path, exc)
                    continue
                raise MinderError(f"transport error talking to minder: {exc}") from exc

            if 500 <= resp.status_code < 600 and attempt == 1:
                log.warning("minder %s -> %s, retrying once", path, resp.status_code)
                continue

            if resp.status_code >= 400:
                detail = _safe_error(resp)
                raise MinderError(
                    f"minder {path} returned HTTP {resp.status_code}: {detail}",
                    status_code=resp.status_code,
                )

            try:
                return resp.json()
            except ValueError as exc:
                raise MinderError(f"minder {path} returned non-JSON body") from exc

        # Unreachable, but mypy/runtime safety.
        raise MinderError(f"minder {path} failed: {last_exc}")

    def _get_json(self, path: str) -> dict[str, Any]:
        last_exc: Exception | None = None
        for attempt in (1, 2):
            try:
                resp = self._client.get(path)
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt == 1:
                    log.warning("minder GET %s transport error, retrying once: %s", path, exc)
                    continue
                raise MinderError(f"transport error talking to minder: {exc}") from exc

            if 500 <= resp.status_code < 600 and attempt == 1:
                log.warning("minder GET %s -> %s, retrying once", path, resp.status_code)
                continue

            if resp.status_code >= 400:
                detail = _safe_error(resp)
                raise MinderError(
                    f"minder GET {path} returned HTTP {resp.status_code}: {detail}",
                    status_code=resp.status_code,
                )

            try:
                return resp.json()
            except ValueError as exc:
                raise MinderError(f"minder GET {path} returned non-JSON body") from exc

        raise MinderError(f"minder GET {path} failed: {last_exc}")


def _safe_error(resp: httpx.Response) -> str:
    try:
        data = resp.json()
        if isinstance(data, dict) and "error" in data:
            return str(data["error"])
    except ValueError:
        pass
    body = resp.text or ""
    return body[:200] or "<empty body>"

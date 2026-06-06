from __future__ import annotations

import json

import httpx
import pytest
import respx

from mikrotik_minder_agent.config import ServerConfig
from mikrotik_minder_agent.minder import JobReport, MinderClient, MinderError

SERVER = ServerConfig(url="https://minder.example.workers.dev", agent_token="mtm_test")


@respx.mock
def test_heartbeat_sends_expected_body() -> None:
    response = httpx.Response(200, json={"ok": True, "device_id": "dev_123", "created": True})
    route = respx.post("https://minder.example.workers.dev/v1/ingest/heartbeat").mock(
        return_value=response,
    )
    with MinderClient(SERVER) as client:
        device_id = client.send_heartbeat("core-rtr-01", status="ok")
    assert device_id == "dev_123"
    call = route.calls.last
    assert call.request.headers["authorization"] == "Bearer mtm_test"
    assert call.request.headers["content-type"] == "application/json"
    assert json.loads(call.request.read()) == {"device": "core-rtr-01", "status": "ok"}


@respx.mock
def test_job_includes_optional_fields() -> None:
    route = respx.post("https://minder.example.workers.dev/v1/ingest/jobs").mock(
        return_value=httpx.Response(201, json={"ok": True, "job_id": "job_x"}),
    )
    job = JobReport(
        device="core-rtr-01",
        kind="health_check",
        status="success",
        started_at=1779000000,
        finished_at=1779000005,
        summary="api ok",
        details={"latency_ms": 42},
    )
    with MinderClient(SERVER) as client:
        assert client.send_job(job) == "job_x"
    body = json.loads(route.calls.last.request.read())
    assert body["summary"] == "api ok"
    assert body["details"] == {"latency_ms": 42}
    assert body["device"] == "core-rtr-01"
    assert body["kind"] == "health_check"
    assert body["status"] == "success"


@respx.mock
def test_5xx_retried_once_then_succeeds() -> None:
    route = respx.post("https://minder.example.workers.dev/v1/ingest/heartbeat").mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(200, json={"ok": True, "device_id": "dev_x"}),
        ],
    )
    with MinderClient(SERVER) as client:
        client.send_heartbeat("dev")
    assert route.call_count == 2


@respx.mock
def test_4xx_is_immediate_failure_with_useful_message() -> None:
    respx.post("https://minder.example.workers.dev/v1/ingest/heartbeat").mock(
        return_value=httpx.Response(401, json={"error": "unauthorized"}),
    )
    with MinderClient(SERVER) as client, pytest.raises(MinderError, match="unauthorized"):
        client.send_heartbeat("dev")


@respx.mock
def test_upload_backup_puts_raw_body_with_sha256_query(tmp_path) -> None:
    """`upload_backup` streams the file's raw bytes to /v1/ingest/backups/...

    The body must be the unmodified ciphertext (RouterOS has already encrypted
    it) — anything else would corrupt the backup. The sha256 goes via the URL
    so the worker can match it against its own digest.
    """
    body = b"\x00\xffROUTEROS-BACKUP\x00\x01" * 32
    src = tmp_path / "minder-core-rtr-01-20260523T070200Z.backup"
    src.write_bytes(body)

    route = respx.put(
        "https://minder.example.workers.dev/v1/ingest/backups/core-rtr-01/"
        "minder-core-rtr-01-20260523T070200Z.backup",
    ).mock(return_value=httpx.Response(201, json={"id": "bkp_abc"}))

    with MinderClient(SERVER) as client:
        backup_id = client.upload_backup("core-rtr-01", src, sha256="deadbeef" * 8)

    assert backup_id == "bkp_abc"
    assert route.call_count == 1
    request = route.calls.last.request
    assert request.url.params["sha256"] == "deadbeef" * 8
    assert request.headers["content-type"] == "application/octet-stream"
    # Body sent verbatim — no JSON encoding, no trimming, no base64.
    assert request.read() == body


@respx.mock
def test_upload_backup_retries_once_on_5xx(tmp_path) -> None:
    src = tmp_path / "core-rtr-01.backup"
    src.write_bytes(b"x")
    route = respx.put(
        "https://minder.example.workers.dev/v1/ingest/backups/dev/core-rtr-01.backup",
    ).mock(
        side_effect=[
            httpx.Response(503, json={"error": "transient"}),
            httpx.Response(201, json={"id": "bkp_x"}),
        ],
    )
    with MinderClient(SERVER) as client:
        assert client.upload_backup("dev", src) == "bkp_x"
    assert route.call_count == 2


@respx.mock
def test_upload_backup_propagates_404_with_status(tmp_path) -> None:
    """Older workers without the upload endpoint return 404; the agent uses
    `MinderError.status_code` to treat that as "control plane not ready yet"
    (warning, not fatal)."""
    src = tmp_path / "a.backup"
    src.write_bytes(b"x")
    respx.put(
        "https://minder.example.workers.dev/v1/ingest/backups/dev/a.backup",
    ).mock(return_value=httpx.Response(404, json={"error": "not_found"}))
    with MinderClient(SERVER) as client:
        try:
            client.upload_backup("dev", src)
        except MinderError as exc:
            assert exc.status_code == 404
        else:
            raise AssertionError("expected MinderError")

from __future__ import annotations

import base64
from typing import Any

from mikrotik_minder_agent.remoteconfig import build_devices, devices_changed


def _doc(**overrides: Any) -> dict[str, Any]:
    device: dict[str, Any] = {
        "name": "rtr-01",
        "address": "10.0.0.1",
        "username": "minder",
        "transport": {"primary": "api", "fallback": "ssh"},
        "api_port": 8728,
        "use_tls": False,
        "ssh_port": 22,
        "site": "dc1",
        "role": "core",
        "tags": ["prod", "core"],
        "heartbeat_interval_seconds": 180,
        "credential": {"kind": "ref", "password_env": "RTR01_PW"},
    }
    device.update(overrides)
    return {"version": 1, "devices": [device]}


def test_build_devices_resolves_password_ref() -> None:
    devices = build_devices(_doc(), env={"RTR01_PW": "s3cret"})
    assert len(devices) == 1
    d = devices[0]
    assert (d.name, d.address, d.username) == ("rtr-01", "10.0.0.1", "minder")
    assert d.password == "s3cret"
    assert d.ssh_key_path is None
    assert d.transport is not None
    assert (d.transport.primary, d.transport.fallback) == ("api", "ssh")
    assert d.api_port == 8728
    assert d.use_tls is False
    assert d.ssh_port == 22
    assert d.tags == ("prod", "core")
    assert d.heartbeat_interval_seconds == 180


def test_build_devices_skips_unresolved_password() -> None:
    # password_env not present in the environment → device can't connect → skipped.
    assert build_devices(_doc(), env={}) == ()


def test_build_devices_skips_sealed_without_unseal() -> None:
    # No vault key on the agent → sealed devices are skipped.
    doc = _doc(credential={"kind": "sealed", "blob": "ciphertext"})
    assert build_devices(doc, env={"RTR01_PW": "x"}) == ()


def test_build_devices_decrypts_sealed_with_unseal() -> None:
    from nacl.public import PrivateKey, PublicKey, SealedBox

    from mikrotik_minder_agent.agentkeys import make_unsealer

    sk = PrivateKey.generate()
    pub = base64.b64encode(bytes(sk.public_key)).decode()
    sealed = SealedBox(PublicKey(base64.b64decode(pub))).encrypt(b"vault-pw")
    doc = _doc(credential={"kind": "sealed", "blob": base64.b64encode(sealed).decode()})
    devices = build_devices(doc, unseal=make_unsealer(sk))
    assert len(devices) == 1
    assert devices[0].password == "vault-pw"


def test_build_devices_accepts_ssh_key_ref_without_password() -> None:
    doc = _doc(credential={"kind": "ref", "ssh_key_path": "/keys/rtr"})
    devices = build_devices(doc, env={})
    assert len(devices) == 1
    assert devices[0].ssh_key_path == "/keys/rtr"
    assert devices[0].password is None


def test_build_devices_skips_missing_address() -> None:
    assert build_devices(_doc(address=None), env={"RTR01_PW": "x"}) == ()


def test_build_devices_no_transport_falls_back_to_none() -> None:
    devices = build_devices(_doc(transport={}), env={"RTR01_PW": "x"})
    assert devices[0].transport is None


def test_build_devices_empty_or_absent() -> None:
    assert build_devices({"devices": []}) == ()
    assert build_devices({}) == ()


def test_devices_changed_false_for_identical() -> None:
    env = {"RTR01_PW": "x"}
    assert devices_changed(build_devices(_doc(), env=env), build_devices(_doc(), env=env)) is False


def test_devices_changed_detects_field_change() -> None:
    env = {"RTR01_PW": "x"}
    before = build_devices(_doc(), env=env)
    after = build_devices(_doc(role="edge"), env=env)
    assert devices_changed(before, after) is True


def test_devices_changed_ignores_order() -> None:
    env = {"PW": "x"}
    cred = {"kind": "ref", "password_env": "PW"}
    devs = [
        {"name": "a", "address": "1.1.1.1", "credential": cred},
        {"name": "b", "address": "2.2.2.2", "credential": cred},
    ]
    a = build_devices({"devices": devs}, env=env)
    b = build_devices({"devices": list(reversed(devs))}, env=env)
    assert devices_changed(a, b) is False


def test_devices_changed_on_add_or_remove() -> None:
    one = build_devices(_doc(), env={"RTR01_PW": "x"})
    assert devices_changed(one, ()) is True
    assert devices_changed((), one) is True

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from mikrotik_minder_agent.agentkeys import AgentKeyError, load_or_create_keypair, make_unsealer


def test_keypair_created_persisted_and_private(tmp_path: Path) -> None:
    key_path = str(tmp_path / "agent_key")
    _sk1, pub1 = load_or_create_keypair(key_path)
    assert Path(key_path).exists()
    # No group/world access on the private key.
    assert (Path(key_path).stat().st_mode & 0o077) == 0
    # Reloading returns the SAME key (persisted, not regenerated).
    _sk2, pub2 = load_or_create_keypair(key_path)
    assert pub1 == pub2
    # Public key is base64 of a 32-byte Curve25519 key.
    assert len(base64.b64decode(pub1)) == 32


def test_unseal_round_trip(tmp_path: Path) -> None:
    # Simulate the licensed UI sealing a credential to the agent's public key,
    # then the agent decrypting it — the cross-component contract.
    from nacl.public import PublicKey, SealedBox

    sk, pub_b64 = load_or_create_keypair(str(tmp_path / "k"))
    sealed = SealedBox(PublicKey(base64.b64decode(pub_b64))).encrypt(b"s3cret-pw")
    unseal = make_unsealer(sk)
    assert unseal(base64.b64encode(sealed).decode()) == "s3cret-pw"


def test_unseal_rejects_garbage(tmp_path: Path) -> None:
    sk, _ = load_or_create_keypair(str(tmp_path / "k"))
    unseal = make_unsealer(sk)
    with pytest.raises(AgentKeyError):
        unseal("not-valid-base64!!")
    with pytest.raises(AgentKeyError):
        unseal(base64.b64encode(b"not a sealed box").decode())


def test_invalid_key_file_raises(tmp_path: Path) -> None:
    key_path = tmp_path / "bad_key"
    key_path.write_bytes(b"not a 32-byte key")
    with pytest.raises(AgentKeyError):
        load_or_create_keypair(str(key_path))

"""Agent keypair for the Pro credential vault (libsodium sealed boxes).

The agent holds a Curve25519 keypair. Its PUBLIC key is registered with the
control plane so the licensed UI can seal a credential to it; the PRIVATE key
never leaves the agent, and sealed credentials are decrypted locally. Inactive
unless ``agent_key_path`` is configured — agents without it simply skip any
``sealed`` credential.

PyNaCl is already present (a transitive dependency of paramiko); it's imported
lazily so the dependency only matters when the vault is actually used.
"""

from __future__ import annotations

import base64
import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nacl.public import PrivateKey

log = logging.getLogger(__name__)


class AgentKeyError(RuntimeError):
    """Raised when the agent keypair can't be created, loaded, or used."""


def load_or_create_keypair(path: str) -> tuple[PrivateKey, str]:
    """Load the agent's Curve25519 private key from ``path``, creating it on
    first run (written 0600). Returns (private_key, base64 public key)."""
    try:
        from nacl.public import PrivateKey
    except ImportError as exc:  # pragma: no cover - pynacl ships with paramiko
        raise AgentKeyError("PyNaCl is required for the credential vault") from exc

    key_path = Path(path).expanduser()
    if key_path.exists():
        try:
            private_key = PrivateKey(key_path.read_bytes())
        except Exception as exc:
            raise AgentKeyError(f"invalid agent key at {key_path}: {exc}") from exc
    else:
        private_key = PrivateKey.generate()
        key_path.parent.mkdir(parents=True, exist_ok=True)
        # Create with 0600 from the outset (O_EXCL: never clobber an existing key).
        fd = os.open(str(key_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(fd, bytes(private_key))
        finally:
            os.close(fd)
        log.info("generated agent keypair at %s", key_path)

    public_b64 = base64.b64encode(bytes(private_key.public_key)).decode("ascii")
    return private_key, public_b64


def make_unsealer(private_key: PrivateKey) -> Callable[[str], str]:
    """Return a function that decrypts a base64 libsodium sealed-box ciphertext
    (sealed to this agent's public key) back to its plaintext string."""
    from nacl.public import SealedBox

    box = SealedBox(private_key)

    def unseal(blob_b64: str) -> str:
        try:
            return box.decrypt(base64.b64decode(blob_b64, validate=True)).decode("utf-8")
        except Exception as exc:
            raise AgentKeyError(f"sealed credential decrypt failed: {exc}") from exc

    return unseal

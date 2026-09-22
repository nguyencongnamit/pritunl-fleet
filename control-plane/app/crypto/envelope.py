"""Envelope encryption for node credentials at rest.

Model (KMS-style envelope, portable to a real KMS later):
  - A master key (KEK) is supplied via env/secret store (FLEET_MASTER_KEY).
  - Each secret gets a fresh random data key (DEK).
  - The DEK encrypts the plaintext with AES-256-GCM.
  - The KEK wraps (encrypts) the DEK with AES-256-GCM.
  - We persist: version || wrapped-DEK frame || ciphertext frame.

Swapping to AWS KMS / Vault / age later means replacing only wrap()/unwrap()
of the DEK — the record format and call sites stay the same.

Guarantees: authenticated encryption (GCM) so tampering is detected on decrypt.
Credentials are only ever held in memory transiently by the service layer.
"""

from __future__ import annotations

import base64
import os
import struct

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import get_settings

_VERSION = b"\x01"
_NONCE_LEN = 12
_KEY_LEN = 32  # AES-256

# Deterministic key used ONLY when running the dev/lab environment without a
# configured master key. Never used when FLEET_MASTER_KEY is set, and its use
# is loudly refused outside environment=="dev".
_DEV_MASTER_KEY = b"pritunl-fleet-dev-master-key-32!"  # exactly 32 bytes (AES-256)
assert len(_DEV_MASTER_KEY) == _KEY_LEN, "dev master key must be exactly 32 bytes"


class CredentialSealError(RuntimeError):
    pass


def _master_key() -> bytes:
    settings = get_settings()
    raw = settings.master_key
    if raw:
        try:
            key = base64.b64decode(raw)
        except Exception as exc:  # noqa: BLE001
            raise CredentialSealError("FLEET_MASTER_KEY is not valid base64") from exc
        if len(key) != _KEY_LEN:
            raise CredentialSealError("FLEET_MASTER_KEY must decode to exactly 32 bytes")
        return key
    if settings.environment != "dev":
        raise CredentialSealError(
            "FLEET_MASTER_KEY is required outside the dev environment"
        )
    return _DEV_MASTER_KEY


def _frame(data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + data


def _unframe(buf: bytes, offset: int) -> tuple[bytes, int]:
    (length,) = struct.unpack_from(">I", buf, offset)
    start = offset + 4
    end = start + length
    return buf[start:end], end


def seal(plaintext: bytes) -> bytes:
    """Encrypt plaintext under a fresh DEK wrapped by the master key."""
    kek = AESGCM(_master_key())
    dek = os.urandom(_KEY_LEN)

    wrap_nonce = os.urandom(_NONCE_LEN)
    wrapped_dek = kek.encrypt(wrap_nonce, dek, None)

    data_nonce = os.urandom(_NONCE_LEN)
    ciphertext = AESGCM(dek).encrypt(data_nonce, plaintext, None)

    return (
        _VERSION
        + _frame(wrap_nonce + wrapped_dek)
        + _frame(data_nonce + ciphertext)
    )


def open_(blob: bytes) -> bytes:
    """Decrypt a blob produced by seal(). Raises on tamper / wrong key."""
    if not blob or blob[:1] != _VERSION:
        raise CredentialSealError("unsupported credential blob version")
    try:
        wrap_part, offset = _unframe(blob, 1)
        data_part, _ = _unframe(blob, offset)
        kek = AESGCM(_master_key())
        dek = kek.decrypt(wrap_part[:_NONCE_LEN], wrap_part[_NONCE_LEN:], None)
        return AESGCM(dek).decrypt(data_part[:_NONCE_LEN], data_part[_NONCE_LEN:], None)
    except (InvalidTag, struct.error, IndexError) as exc:
        raise CredentialSealError("failed to decrypt credentials (tampered or wrong key)") from exc

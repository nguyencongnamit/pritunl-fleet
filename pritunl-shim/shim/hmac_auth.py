"""HMAC-SHA256 request authentication — the shared source of truth.

This scheme intentionally mirrors Pritunl's own API auth (Auth-Token /
Auth-Timestamp / Auth-Nonce / Auth-Signature) so that:
  * the shim adapter and the shim/mock node agree byte-for-byte, and
  * migrating to Pritunl's licensed Enterprise API later needs no re-signing.

Signed string:  token & timestamp & nonce & METHOD & path & sha256(body)
Signature:      base64( HMAC-SHA256(secret, signed_string) )

This ONE file is imported by both the control-plane adapter (to sign) and the
node shim/mock (to verify). Keep it dependency-free (stdlib only) so it drops
into a Pritunl OSS host without pulling extra packages.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from dataclasses import dataclass

# Header names (title-case on the wire; compared case-insensitively on verify).
H_TOKEN = "Auth-Token"
H_TIMESTAMP = "Auth-Timestamp"
H_NONCE = "Auth-Nonce"
H_SIGNATURE = "Auth-Signature"

# Reject requests whose timestamp is further than this from now (seconds).
DEFAULT_MAX_SKEW = 300


def _body_hash(body: bytes) -> str:
    return hashlib.sha256(body or b"").hexdigest()


def _signed_string(token: str, timestamp: str, nonce: str, method: str, path: str, body: bytes) -> str:
    return "&".join([token, timestamp, nonce, method.upper(), path, _body_hash(body)])


def _compute_signature(secret: str, signed_string: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), signed_string.encode("utf-8"), hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")


def sign_request(
    *,
    token: str,
    secret: str,
    method: str,
    path: str,
    body: bytes = b"",
    timestamp: int | None = None,
    nonce: str | None = None,
) -> dict[str, str]:
    """Return the Auth-* headers for a request. `path` is the URL path only."""
    ts = str(timestamp if timestamp is not None else int(time.time()))
    nc = nonce if nonce is not None else base64.b16encode(os.urandom(16)).decode("ascii")
    signed = _signed_string(token, ts, nc, method, path, body)
    return {
        H_TOKEN: token,
        H_TIMESTAMP: ts,
        H_NONCE: nc,
        H_SIGNATURE: _compute_signature(secret, signed),
    }


@dataclass(slots=True)
class VerifyResult:
    ok: bool
    token: str | None = None
    error: str | None = None


def verify_request(
    *,
    secret: str,
    method: str,
    path: str,
    headers: dict,
    body: bytes = b"",
    max_skew: int = DEFAULT_MAX_SKEW,
    seen_nonce: NonceCache | None = None,
    now: int | None = None,
) -> VerifyResult:
    """Constant-time verify of the Auth-* headers against `secret`.

    Caller resolves token -> secret first (the token is public, the secret is
    not). Pass a NonceCache to enforce single-use nonces (replay protection).
    """
    h = {k.lower(): v for k, v in headers.items()}
    token = h.get(H_TOKEN.lower())
    timestamp = h.get(H_TIMESTAMP.lower())
    nonce = h.get(H_NONCE.lower())
    signature = h.get(H_SIGNATURE.lower())
    if not all([token, timestamp, nonce, signature]):
        return VerifyResult(ok=False, error="missing auth headers")

    try:
        ts_int = int(timestamp)
    except ValueError:
        return VerifyResult(ok=False, error="bad timestamp")

    current = now if now is not None else int(time.time())
    if abs(current - ts_int) > max_skew:
        return VerifyResult(ok=False, token=token, error="timestamp outside allowed skew")

    expected = _compute_signature(secret, _signed_string(token, timestamp, nonce, method, path, body))
    if not hmac.compare_digest(expected, signature):
        return VerifyResult(ok=False, token=token, error="bad signature")

    if seen_nonce is not None:
        if seen_nonce.seen(nonce):
            return VerifyResult(ok=False, token=token, error="nonce replay detected")
        seen_nonce.add(nonce, ts_int)

    return VerifyResult(ok=True, token=token)


class NonceCache:
    """Minimal in-memory single-use nonce store with TTL eviction.

    Sufficient for a single-process node shim / mock. A multi-process shim
    should back this with Redis or Mongo keyed on (token, nonce).
    """

    def __init__(self, ttl: int = DEFAULT_MAX_SKEW * 2):
        self._ttl = ttl
        self._store: dict[str, int] = {}

    def _evict(self, now: int) -> None:
        expired = [n for n, ts in self._store.items() if now - ts > self._ttl]
        for n in expired:
            self._store.pop(n, None)

    def seen(self, nonce: str) -> bool:
        return nonce in self._store

    def add(self, nonce: str, ts: int) -> None:
        self._evict(ts)
        self._store[nonce] = ts

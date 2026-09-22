"""In-process login rate limiter (per username+IP).

Throttles credential and MFA-code guessing: after N failed attempts within the
window, the key is locked out for the lockout period. Successful auth resets it.

In-memory is sufficient for a single control-plane instance; a multi-instance
deployment should back this with Redis keyed the same way.
"""

from __future__ import annotations

import time

from fastapi import Request

from app.config import get_settings

# key -> (list[failure_timestamps], locked_until)
_state: dict[str, tuple[list[float], float]] = {}


def key_for(request: Request, identifier: str) -> str:
    # Trust the tunnel's forwarded client IP if present, else the socket peer.
    fwd = request.headers.get("x-forwarded-for", "")
    ip = fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?")
    return f"{identifier}:{ip}"


def blocked(key: str) -> float:
    """Return seconds remaining in lockout, or 0 if not locked."""
    now = time.time()
    entry = _state.get(key)
    if not entry:
        return 0.0
    _fails, locked_until = entry
    return max(0.0, locked_until - now)


def record_failure(key: str) -> None:
    s = get_settings()
    now = time.time()
    fails, locked_until = _state.get(key, ([], 0.0))
    fails = [t for t in fails if now - t < s.rate_limit_window_seconds]
    fails.append(now)
    if len(fails) >= s.rate_limit_max_attempts:
        locked_until = now + s.rate_limit_lockout_seconds
        fails = []
    _state[key] = (fails, locked_until)


def reset(key: str) -> None:
    _state.pop(key, None)

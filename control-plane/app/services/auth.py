"""Authentication + session tokens for control-plane principals.

Login is two-step and MFA is mandatory:

  1. POST /auth/login (username+password)
       -> if MFA enrolled:  scope="mfa"    token (needs a TOTP code next)
       -> if not enrolled:  scope="enroll" token (must enrol TOTP next)
  2a. POST /auth/mfa/verify (code, mfa token)     -> scope="full" session token
  2b. POST /auth/mfa/enroll then /verify (enroll) -> scope="full" session token

Only scope="full" tokens are accepted by the RBAC dependency for the API. The
step tokens are short-lived and usable ONLY on the auth endpoints.
"""

from __future__ import annotations

import base64
import hashlib
from datetime import UTC, datetime, timedelta

import jwt
import pyotp
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.crypto import envelope
from app.crypto.passwords import hash_password, verify_password
from app.models.identity import Principal, Role

ALGO = "HS256"
SCOPE_FULL = "full"
SCOPE_MFA = "mfa"
SCOPE_ENROLL = "enroll"


class AuthError(Exception):
    pass


def _jwt_secret() -> str:
    settings = get_settings()
    if settings.jwt_secret:
        return settings.jwt_secret
    if settings.environment != "dev":
        raise AuthError("FLEET_JWT_SECRET is required outside the dev environment")
    # Dev-only: derive a stable secret from the (dev) master key material.
    seed = (settings.master_key or "dev").encode()
    return base64.b64encode(hashlib.sha256(b"jwt:" + seed).digest()).decode()


def create_token(principal_id: str, scope: str, ttl_minutes: int) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": principal_id,
        "scope": scope,
        "iat": now,
        "exp": now + timedelta(minutes=ttl_minutes),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=ALGO)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, _jwt_secret(), algorithms=[ALGO])
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError("invalid token") from exc


def full_token(principal_id: str) -> str:
    return create_token(principal_id, SCOPE_FULL, get_settings().jwt_full_ttl_minutes)


def step_token(principal_id: str, scope: str) -> str:
    return create_token(principal_id, scope, get_settings().jwt_step_ttl_minutes)


# --- Principal helpers -------------------------------------------------------


def get_by_username(session: Session, username: str) -> Principal | None:
    return session.scalar(select(Principal).where(Principal.username == username))


def authenticate(session: Session, username: str, password: str) -> Principal:
    principal = get_by_username(session, username)
    # Verify against a dummy hash when the user is unknown to reduce timing
    # signal, then fail uniformly.
    ok = verify_password(
        principal.password_hash if principal else _DUMMY_HASH, password
    )
    if not principal or principal.disabled or not ok:
        raise AuthError("invalid credentials")
    return principal


# Precomputed argon2 hash of a random value, for constant-ish-time failure.
_DUMMY_HASH = hash_password("pritunl-fleet-dummy-password")


# --- TOTP --------------------------------------------------------------------


def begin_enrollment(session: Session, principal: Principal) -> tuple[str, str]:
    """Generate + store (sealed) a fresh TOTP secret; return (secret, otpauth_uri).

    mfa_enabled stays False until a code is verified.
    """
    secret = pyotp.random_base32()
    principal.totp_secret_enc = envelope.seal(secret.encode("utf-8"))
    principal.mfa_enabled = False
    session.add(principal)
    session.flush()
    uri = pyotp.totp.TOTP(secret).provisioning_uri(
        name=principal.username, issuer_name="Pritunl Fleet"
    )
    return secret, uri


def _totp_secret(principal: Principal) -> str:
    if not principal.totp_secret_enc:
        raise AuthError("no TOTP secret enrolled")
    return envelope.open_(principal.totp_secret_enc).decode("utf-8")


def verify_totp(principal: Principal, code: str) -> bool:
    secret = _totp_secret(principal)
    return pyotp.TOTP(secret).verify(code, valid_window=1)


def confirm_enrollment(session: Session, principal: Principal, code: str) -> None:
    if not verify_totp(principal, code):
        raise AuthError("invalid TOTP code")
    principal.mfa_enabled = True
    session.add(principal)
    session.flush()


# --- Bootstrap ---------------------------------------------------------------


def bootstrap_admin(session: Session) -> None:
    settings = get_settings()
    count = session.scalar(select(func.count()).select_from(Principal))
    if count and count > 0:
        return
    if not settings.bootstrap_admin_user or not settings.bootstrap_admin_password:
        return
    admin = Principal(
        username=settings.bootstrap_admin_user,
        password_hash=hash_password(settings.bootstrap_admin_password),
        global_role=Role.admin,
        mfa_enabled=False,
    )
    session.add(admin)
    session.commit()

"""Control-plane configuration.

All secrets come from the environment / secret store — never from the repo.
See .env.example for the full list. Loaded once and cached via get_settings().
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FLEET_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Core ---
    environment: str = "dev"
    log_level: str = "INFO"

    # --- Control-plane database ---
    # Registry, user mapping, RBAC, audit log.
    database_url: PostgresDsn = Field(
        default="postgresql+psycopg://fleet:fleet@postgres:5432/fleet",
    )

    # --- Secrets at rest ---
    # Master key for envelope encryption of node credentials (base64, 32 bytes).
    # MUST be supplied via env/secret store in any non-dev environment.
    # In dev, a fixed dev key is used if this is unset (see crypto.envelope).
    master_key: str | None = None

    # --- Control-plane auth (MFA + RBAC) ---
    # JWT signing secret. Required outside dev; in dev it is derived from the
    # master key if unset.
    jwt_secret: str | None = None
    jwt_full_ttl_minutes: int = 720   # session lifetime after full auth (MFA satisfied)
    jwt_step_ttl_minutes: int = 10    # short-lived pre-auth (mfa/enroll) token lifetime

    # First-run bootstrap admin, created only if there are zero principals.
    # Supply via secret store; leave unset once real accounts exist.
    bootstrap_admin_user: str | None = None
    bootstrap_admin_password: str | None = None

    # --- Node access hardening ---
    # Verify node TLS certificates by default. Only disable for local mock lab.
    verify_node_tls: bool = True
    # Per-node health check timeout (seconds).
    node_request_timeout: float = 8.0

    # --- Health check engine ---
    # Interval for the periodic health sweep across all nodes (seconds).
    health_sweep_interval: float = 30.0
    # Consecutive failures before a node is marked "down" (vs "degraded").
    health_down_threshold: int = 3

    # --- Sync engine ---
    # Interval for the periodic drift-reconciliation sweep (seconds).
    sync_sweep_interval: float = 60.0

    # --- Profile delivery (Resend) ---
    # Optional: set to enable emailing client profiles. If unset, the email
    # endpoint returns 501 (not configured) rather than failing silently.
    resend_api_key: str | None = None
    resend_from: str = '"Pritunl Fleet" <fleet@dev-test.org>'


@lru_cache
def get_settings() -> Settings:
    return Settings()

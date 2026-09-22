"""Node registry model — one row per managed Pritunl OSS site.

Credentials (Mongo creds / SSH key / shim API secret) are stored as an
envelope-encrypted blob in `credentials_enc` and are NEVER returned in API
responses or written to logs. Only the service layer decrypts them, at the
moment an adapter call is made.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, new_uuid


class AdapterType(str, enum.Enum):
    shim = "shim"   # default: HMAC-authed REST shim on the OSS node
    mongo = "mongo"  # read-only fast path (stub)
    ssh = "ssh"     # bootstrap / break-glass (stub)


class HealthStatus(str, enum.Enum):
    unknown = "unknown"
    reachable = "reachable"
    degraded = "degraded"
    down = "down"


class Node(Base, TimestampMixin):
    __tablename__ = "nodes"
    __table_args__ = (UniqueConstraint("name", name="uq_nodes_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)

    # --- Identity / addressing ---
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    region: Mapped[str] = mapped_column(String(64), nullable=False)  # e.g. DN, HCMC, SG
    # Base endpoint for the adapter, e.g. https://vpn-sg.internal:9700 (shim)
    # or mongodb://... (mongo) or ssh host (ssh). Interpreted per adapter.
    endpoint: Mapped[str] = mapped_column(String(512), nullable=False)
    adapter_type: Mapped[AdapterType] = mapped_column(
        Enum(AdapterType, name="adapter_type"), nullable=False, default=AdapterType.shim
    )

    # --- Security posture ---
    verify_tls: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Envelope-encrypted credentials blob (adapter-specific JSON, sealed).
    credentials_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    # --- Health (updated by the health engine) ---
    status: Mapped[HealthStatus] = mapped_column(
        Enum(HealthStatus, name="health_status"), nullable=False, default=HealthStatus.unknown
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

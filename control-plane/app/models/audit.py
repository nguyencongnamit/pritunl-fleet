"""Append-only, tamper-evident audit log.

Every mutating action (who / what / which site / when / result) is recorded as a
row whose `entry_hash` chains the previous row's hash:

    entry_hash = SHA-256( prev_hash + canonical(payload) )

Any edit, deletion, or reordering of a historical row breaks the chain from that
point forward, which `verify_chain()` detects. Rows are never updated or deleted
by the application. Secrets are never placed in `params`.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow

GENESIS_HASH = "0" * 64


class AuditEntry(Base):
    __tablename__ = "audit_log"

    # Monotonic sequence — also the chain order.
    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    actor: Mapped[str] = mapped_column(String(128), nullable=False)          # who
    action: Mapped[str] = mapped_column(String(64), nullable=False)          # what
    node_id: Mapped[str | None] = mapped_column(String(36), nullable=True)   # which site
    node_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    target_type: Mapped[str | None] = mapped_column(String(32), nullable=True)  # user/server/profile/node
    target_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    result: Mapped[str] = mapped_column(String(16), nullable=False)          # success/failure
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Sanitized, non-secret parameters as a canonical JSON string.
    params: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    # Retry/idempotency marker (optional).
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

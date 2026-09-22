"""Cross-site provisioning model.

A LogicalUser is one identity the operator manages centrally. Each UserPlacement
records that identity's existence on a specific site (node + org), including the
node-local user id. This is what lets us "issue one logical user to multiple
sites in one action" and later reconcile against reality (drift detection).
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, new_uuid


class PlacementStatus(str, enum.Enum):
    pending = "pending"     # queued, not yet created on the node
    active = "active"       # confirmed present on the node
    failed = "failed"       # create/update failed
    revoked = "revoked"     # profile revoked on the node
    missing = "missing"     # tracked here but absent on the node (drift)


class LogicalUser(Base, TimestampMixin):
    __tablename__ = "logical_users"
    __table_args__ = (UniqueConstraint("username", name="uq_logical_users_username"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    username: Mapped[str] = mapped_column(String(128), nullable=False)
    email: Mapped[str | None] = mapped_column(String(256), nullable=True)

    placements: Mapped[list[UserPlacement]] = relationship(
        back_populates="logical_user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class UserPlacement(Base, TimestampMixin):
    __tablename__ = "user_placements"
    __table_args__ = (
        UniqueConstraint("logical_user_id", "node_id", name="uq_placement_user_node"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    logical_user_id: Mapped[str] = mapped_column(
        ForeignKey("logical_users.id", ondelete="CASCADE"), nullable=False
    )
    node_id: Mapped[str] = mapped_column(
        ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False
    )
    org_id: Mapped[str] = mapped_column(String(128), nullable=False)
    remote_user_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[PlacementStatus] = mapped_column(
        Enum(PlacementStatus, name="placement_status"), nullable=False, default=PlacementStatus.pending
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    logical_user: Mapped[LogicalUser] = relationship(back_populates="placements")

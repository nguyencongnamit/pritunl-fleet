"""Control-plane identity + RBAC.

A Principal is an operator who logs into the control plane (distinct from the VPN
end-users managed on nodes). Access is role-based:

    viewer   < operator < admin

Each principal has a global_role plus optional per-site overrides (RoleBinding).
The effective role for a site is max(global_role, binding-for-that-site). Admin
is required for node-registry and principal management; operator for mutations;
viewer for reads.

Secrets: password_hash is an argon2 hash; totp_secret_enc is the envelope-sealed
TOTP secret. Neither is ever returned by the API.
"""

from __future__ import annotations

import enum

from sqlalchemy import Boolean, Enum, ForeignKey, LargeBinary, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, new_uuid


class Role(str, enum.Enum):
    viewer = "viewer"
    operator = "operator"
    admin = "admin"


ROLE_ORDER = {Role.viewer: 1, Role.operator: 2, Role.admin: 3}


def role_at_least(have: Role, need: Role) -> bool:
    return ROLE_ORDER[have] >= ROLE_ORDER[need]


class Principal(Base, TimestampMixin):
    __tablename__ = "principals"
    __table_args__ = (UniqueConstraint("username", name="uq_principals_username"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    username: Mapped[str] = mapped_column(String(128), nullable=False)
    email: Mapped[str | None] = mapped_column(String(256), nullable=True)

    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    global_role: Mapped[Role] = mapped_column(
        Enum(Role, name="role"), nullable=False, default=Role.viewer
    )
    disabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # MFA (TOTP). Secret is sealed; mfa_enabled flips true only after a verified code.
    totp_secret_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    bindings: Mapped[list[RoleBinding]] = relationship(
        back_populates="principal", cascade="all, delete-orphan", lazy="selectin"
    )

    def effective_role(self, node_id: str | None) -> Role:
        role = self.global_role
        if node_id:
            for b in self.bindings:
                if b.node_id == node_id and ROLE_ORDER[b.role] > ROLE_ORDER[role]:
                    role = b.role
        return role


class RoleBinding(Base, TimestampMixin):
    __tablename__ = "role_bindings"
    __table_args__ = (
        UniqueConstraint("principal_id", "node_id", name="uq_binding_principal_node"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    principal_id: Mapped[str] = mapped_column(
        ForeignKey("principals.id", ondelete="CASCADE"), nullable=False
    )
    node_id: Mapped[str] = mapped_column(
        ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[Role] = mapped_column(Enum(Role, name="role"), nullable=False)

    principal: Mapped[Principal] = relationship(back_populates="bindings")

"""Cross-site provisioning — issue/revoke one logical user across many sites.

provision() creates (or reuses) a LogicalUser and fans out user creation to each
target site through its adapter, recording a UserPlacement per site and an audit
entry per action. A failure on one site does not abort the others; that site's
placement is marked failed with the error.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.base import AdapterError
from app.models.base import utcnow
from app.models.node import HealthStatus, Node
from app.models.provisioning import LogicalUser, PlacementStatus, UserPlacement
from app.services import audit as audit_service
from app.services.nodes import build_adapter_for_node


@dataclass
class Target:
    node_id: str
    org_id: str


def _get_or_create_logical(session: Session, username: str, email: str | None) -> LogicalUser:
    existing = session.scalar(select(LogicalUser).where(LogicalUser.username == username))
    if existing is not None:
        if email and not existing.email:
            existing.email = email
        return existing
    lu = LogicalUser(username=username, email=email)
    session.add(lu)
    session.flush()
    return lu


async def provision(
    session: Session, *, actor: str, username: str, email: str | None, targets: list[Target]
) -> LogicalUser:
    lu = _get_or_create_logical(session, username, email)

    for target in targets:
        node = session.get(Node, target.node_id)
        placement = session.scalar(
            select(UserPlacement).where(
                UserPlacement.logical_user_id == lu.id,
                UserPlacement.node_id == target.node_id,
            )
        )
        if placement is None:
            placement = UserPlacement(
                logical_user_id=lu.id, node_id=target.node_id, org_id=target.org_id,
                status=PlacementStatus.pending,
            )
            session.add(placement)

        if node is None:
            placement.status = PlacementStatus.failed
            placement.last_error = "node not found"
            continue

        adapter = build_adapter_for_node(node)
        try:
            user = await adapter.create_user(org_id=target.org_id, name=username, email=email)
            placement.remote_user_id = user.id
            placement.org_id = target.org_id
            placement.status = PlacementStatus.active
            placement.last_error = None
            placement.last_synced_at = utcnow()
            audit_service.append(
                session, actor=actor, action="provision_user", result="success",
                node_id=node.id, node_name=node.name, target_type="user", target_id=user.id,
                params={"username": username, "org_id": target.org_id},
            )
        except AdapterError as exc:
            placement.status = PlacementStatus.failed
            placement.last_error = str(exc)
            audit_service.append(
                session, actor=actor, action="provision_user", result="failure",
                node_id=node.id, node_name=node.name, target_type="user", target_id=None,
                params={"username": username, "org_id": target.org_id}, detail=str(exc),
            )
        finally:
            await adapter.close()

    session.commit()
    session.refresh(lu)
    return lu


async def deprovision(session: Session, *, actor: str, logical_user_id: str, hard: bool = False) -> LogicalUser:
    """Revoke (or hard-delete) a logical user across every site it exists on."""
    lu = session.get(LogicalUser, logical_user_id)
    if lu is None:
        raise LookupError(logical_user_id)

    for placement in lu.placements:
        node = session.get(Node, placement.node_id)
        if node is None or placement.remote_user_id is None:
            continue
        adapter = build_adapter_for_node(node)
        action = "deprovision_delete" if hard else "deprovision_revoke"
        try:
            if hard:
                await adapter.delete_user(user_id=placement.remote_user_id, org_id=placement.org_id)
            else:
                await adapter.revoke_profile(user_id=placement.remote_user_id, org_id=placement.org_id)
            placement.status = PlacementStatus.revoked
            placement.last_error = None
            audit_service.append(
                session, actor=actor, action=action, result="success",
                node_id=node.id, node_name=node.name, target_type="user",
                target_id=placement.remote_user_id, params={"username": lu.username},
            )
        except AdapterError as exc:
            placement.last_error = str(exc)
            audit_service.append(
                session, actor=actor, action=action, result="failure",
                node_id=node.id, node_name=node.name, target_type="user",
                target_id=placement.remote_user_id, params={"username": lu.username}, detail=str(exc),
            )
        finally:
            await adapter.close()

    session.commit()
    session.refresh(lu)
    return lu


def list_identities(session: Session) -> list[LogicalUser]:
    return list(session.scalars(select(LogicalUser).order_by(LogicalUser.username)))


# Health ordering: reachable sites first (client tries them in bundle order).
_HEALTH_RANK = {
    HealthStatus.reachable: 0,
    HealthStatus.degraded: 1,
    HealthStatus.unknown: 2,
    HealthStatus.down: 3,
}


async def build_identity_bundle(session: Session, logical_user_id: str) -> tuple[str, bytes]:
    """ZIP of the logical user's per-site client profiles, health-ordered.

    Each Pritunl site has its own PKI, so a user has a distinct profile per site;
    the bundle lets a client import all and fail over across sites. (A single
    multi-remote .ovpn only works within one site's replica hosts.)
    """
    lu = session.get(LogicalUser, logical_user_id)
    if lu is None:
        raise LookupError(logical_user_id)

    pairs = []
    for p in lu.placements:
        if not p.remote_user_id or p.status != PlacementStatus.active:
            continue
        node = session.get(Node, p.node_id)
        if node is not None:
            pairs.append((p, node))
    pairs.sort(key=lambda pn: _HEALTH_RANK.get(pn[1].status, 9))

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(
            "README.txt",
            f"VPN profiles for '{lu.username}', one per site (health-ordered).\n"
            f"Import all into your OpenVPN/Pritunl client; it will fail over across them.\n",
        )
        for idx, (p, node) in enumerate(pairs):
            adapter = build_adapter_for_node(node)
            try:
                data = await adapter.issue_profile(
                    user_id=p.remote_user_id, org_id=p.org_id, fmt="tar"
                )
                z.writestr(f"{idx + 1:02d}-{node.region}-{node.name}-{lu.username}.tar", data)
            except AdapterError:
                continue
            finally:
                await adapter.close()

    return f"{lu.username}-profiles.zip", buf.getvalue()

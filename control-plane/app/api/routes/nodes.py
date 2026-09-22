"""Node registry API — CRUD plus on-demand health check.

Responses use NodeOut, which has no credentials field, so secrets can never be
returned. (Audit logging of mutations is added in Phase 3.)
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.adapters.base import AdapterError
from app.adapters.factory import available_adapters
from app.api.deps import get_db
from app.models.base import utcnow
from app.schemas.node import NodeCreate, NodeHealthOut, NodeOut, NodeUpdate
from app.schemas.read import OrgRead, ServerRead, SessionRead, UserRead
from app.services import dashboard as dashboard_service
from app.services import health as health_service
from app.services import nodes as node_service
from app.services.nodes import DuplicateNodeError, NodeNotFoundError

router = APIRouter(prefix="/nodes", tags=["nodes"])


def _to_out(node) -> NodeOut:
    out = NodeOut.model_validate(node)
    out.admin_url = node_service.get_admin_url(node)
    return out


@router.get("/adapters", response_model=list[str])
def list_adapter_types() -> list[str]:
    return available_adapters()


@router.get("", response_model=list[NodeOut])
def list_nodes(db: Session = Depends(get_db)) -> list[NodeOut]:
    return [_to_out(n) for n in node_service.list_nodes(db)]


@router.post("", response_model=NodeOut, status_code=status.HTTP_201_CREATED)
def create_node(payload: NodeCreate, db: Session = Depends(get_db)) -> NodeOut:
    try:
        node = node_service.create_node(db, payload)
    except DuplicateNodeError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, f"node name already exists: {exc}") from exc
    return _to_out(node)


@router.get("/{node_id}", response_model=NodeOut)
def get_node(node_id: str, db: Session = Depends(get_db)) -> NodeOut:
    try:
        return _to_out(node_service.get_node(db, node_id))
    except NodeNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "node not found") from exc


@router.patch("/{node_id}", response_model=NodeOut)
def update_node(node_id: str, payload: NodeUpdate, db: Session = Depends(get_db)) -> NodeOut:
    try:
        node = node_service.update_node(db, node_id, payload)
    except NodeNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "node not found") from exc
    except DuplicateNodeError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, f"node name already exists: {exc}") from exc
    return _to_out(node)


@router.delete("/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_node(node_id: str, db: Session = Depends(get_db)) -> None:
    try:
        node_service.delete_node(db, node_id)
    except NodeNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "node not found") from exc


@router.post("/{node_id}/check", response_model=NodeHealthOut)
async def check_node(node_id: str, db: Session = Depends(get_db)) -> NodeHealthOut:
    """Probe a node immediately and persist the result."""
    try:
        node = node_service.get_node(db, node_id)
    except NodeNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "node not found") from exc

    result = await health_service.check_node(db, node)
    db.commit()
    return NodeHealthOut(
        node_id=node.id,
        status=node.status,
        latency_ms=result.latency_ms,
        detail=result.detail,
        error=result.error,
        checked_at=node.last_checked_at or utcnow(),
    )


# --- Per-node reads (Phase 2) ------------------------------------------------


def _require_node(db: Session, node_id: str):
    try:
        return node_service.get_node(db, node_id)
    except NodeNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "node not found") from exc


async def _read(db: Session, node_id: str, method: str):
    node = _require_node(db, node_id)
    adapter = node_service.build_adapter_for_node(node)
    try:
        return await getattr(adapter, method)()
    except AdapterError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    except NotImplementedError as exc:
        raise HTTPException(
            status.HTTP_501_NOT_IMPLEMENTED,
            f"{node.adapter_type.value} adapter does not support {method}",
        ) from exc
    finally:
        await adapter.close()


@router.get("/{node_id}/servers", response_model=list[ServerRead])
async def node_servers(node_id: str, db: Session = Depends(get_db)) -> list[ServerRead]:
    return [ServerRead(**asdict(s)) for s in await _read(db, node_id, "list_servers")]


@router.get("/{node_id}/orgs", response_model=list[OrgRead])
async def node_orgs(node_id: str, db: Session = Depends(get_db)) -> list[OrgRead]:
    return [OrgRead(**asdict(o)) for o in await _read(db, node_id, "list_orgs")]


@router.get("/{node_id}/users", response_model=list[UserRead])
async def node_users(node_id: str, db: Session = Depends(get_db)) -> list[UserRead]:
    return [UserRead(**asdict(u)) for u in await _read(db, node_id, "list_users")]


@router.get("/{node_id}/sessions", response_model=list[SessionRead])
async def node_sessions(node_id: str, db: Session = Depends(get_db)) -> list[SessionRead]:
    node = _require_node(db, node_id)
    return await dashboard_service.node_sessions(node)


@router.get("/{node_id}/admin-url")
def node_admin_url(node_id: str, db: Session = Depends(get_db)) -> dict:
    """One-click deep-link target: the node's native Pritunl admin URL."""
    node = _require_node(db, node_id)
    url = node_service.get_admin_url(node)
    if not url:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "no admin_url set for this node (add it to the node's credentials)",
        )
    return {"url": url}

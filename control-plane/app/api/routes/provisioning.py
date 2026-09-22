"""Cross-site provisioning + sync/drift API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_actor, get_db
from app.schemas.provisioning import (
    DeprovisionIn,
    DriftItemOut,
    LogicalUserOut,
    NodeSyncReportOut,
    ProvisionIn,
)
from app.services import provisioning as prov_service
from app.services import sync as sync_service
from app.services.nodes import NodeNotFoundError, get_node
from app.services.provisioning import Target

router = APIRouter(tags=["provisioning"])


@router.post("/provision", response_model=LogicalUserOut, status_code=201)
async def provision(
    payload: ProvisionIn, db: Session = Depends(get_db), actor: str = Depends(get_actor)
) -> LogicalUserOut:
    targets = [Target(node_id=t.node_id, org_id=t.org_id) for t in payload.targets]
    lu = await prov_service.provision(
        db, actor=actor, username=payload.username, email=payload.email, targets=targets
    )
    return LogicalUserOut.model_validate(lu)


@router.get("/identities", response_model=list[LogicalUserOut])
def list_identities(db: Session = Depends(get_db)) -> list[LogicalUserOut]:
    return [LogicalUserOut.model_validate(lu) for lu in prov_service.list_identities(db)]


@router.post("/identities/{logical_user_id}/deprovision", response_model=LogicalUserOut)
async def deprovision(
    logical_user_id: str, payload: DeprovisionIn,
    db: Session = Depends(get_db), actor: str = Depends(get_actor),
) -> LogicalUserOut:
    try:
        lu = await prov_service.deprovision(
            db, actor=actor, logical_user_id=logical_user_id, hard=payload.hard
        )
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "identity not found") from exc
    return LogicalUserOut.model_validate(lu)


def _report_out(r: sync_service.NodeSyncReport) -> NodeSyncReportOut:
    return NodeSyncReportOut(
        node_id=r.node_id, node_name=r.node_name, reachable=r.reachable,
        tracked=r.tracked, present=r.present,
        missing=[DriftItemOut(kind=d.kind, remote_user_id=d.remote_user_id, username=d.username) for d in r.missing],
        untracked=[DriftItemOut(kind=d.kind, remote_user_id=d.remote_user_id, username=d.username) for d in r.untracked],
        in_sync=r.in_sync, error=r.error,
    )


@router.post("/sync", response_model=list[NodeSyncReportOut])
async def sync_all() -> list[NodeSyncReportOut]:
    return [_report_out(r) for r in await sync_service.sync_all()]


@router.post("/nodes/{node_id}/sync", response_model=NodeSyncReportOut)
async def sync_one(node_id: str, db: Session = Depends(get_db)) -> NodeSyncReportOut:
    try:
        node = get_node(db, node_id)
    except NodeNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "node not found") from exc
    return _report_out(await sync_service.sync_node(db, node))

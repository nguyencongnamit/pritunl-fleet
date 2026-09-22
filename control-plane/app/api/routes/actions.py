"""Mutating actions across sites + the audit log API.

Every mutation is recorded to the hash-chained audit log with actor / action /
site / target / result — on both success and failure — before the response is
returned. Node credentials never appear in audit params.
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.adapters.base import AdapterError
from app.api.deps import get_actor, get_db
from app.models.node import Node
from app.schemas.actions import (
    AuditOut,
    BulkActionIn,
    BulkCreateIn,
    ChainStatusOut,
    CreateOrgIn,
    CreateUserIn,
    DisableUserIn,
    EmailProfileIn,
    IssueProfileIn,
    RevokeProfileIn,
    ServerActionIn,
    UserPolicyIn,
)
from app.schemas.read import OrgRead, ServerRead, UserRead
from app.services import audit as audit_service
from app.services import delivery as delivery_service
from app.services import nodes as node_service
from app.services.nodes import NodeNotFoundError

router = APIRouter(tags=["actions"])


def _node(db: Session, node_id: str) -> Node:
    try:
        return node_service.get_node(db, node_id)
    except NodeNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "node not found") from exc


async def _perform(
    db: Session,
    node: Node,
    actor: str,
    action: str,
    target_type: str,
    target_id: str | None,
    params: dict,
    coro,
):
    """Run a mutation through the node's adapter and audit the outcome."""
    adapter = node_service.build_adapter_for_node(node)
    try:
        result = await coro(adapter)
        audit_service.append(
            db, actor=actor, action=action, result="success",
            node_id=node.id, node_name=node.name,
            target_type=target_type, target_id=target_id or _result_id(result), params=params,
        )
        db.commit()
        return result
    except AdapterError as exc:
        audit_service.append(
            db, actor=actor, action=action, result="failure",
            node_id=node.id, node_name=node.name,
            target_type=target_type, target_id=target_id, params=params, detail=str(exc),
        )
        db.commit()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    finally:
        await adapter.close()


def _result_id(result) -> str | None:
    return getattr(result, "id", None)


# --- User lifecycle ----------------------------------------------------------


@router.post("/nodes/{node_id}/users", response_model=UserRead, status_code=201)
async def create_user(
    node_id: str, payload: CreateUserIn,
    db: Session = Depends(get_db), actor: str = Depends(get_actor),
) -> UserRead:
    node = _node(db, node_id)
    user = await _perform(
        db, node, actor, "create_user", "user", None,
        {"org_id": payload.org_id, "name": payload.name},
        lambda a: a.create_user(org_id=payload.org_id, name=payload.name, email=payload.email),
    )
    return UserRead(**asdict(user))


@router.post("/nodes/{node_id}/users/{user_id}/disable", response_model=UserRead)
async def set_user_disabled(
    node_id: str, user_id: str, payload: DisableUserIn,
    db: Session = Depends(get_db), actor: str = Depends(get_actor),
) -> UserRead:
    node = _node(db, node_id)
    user = await _perform(
        db, node, actor, "disable_user" if payload.disabled else "enable_user", "user", user_id,
        {"org_id": payload.org_id, "disabled": payload.disabled},
        lambda a: a.set_user_disabled(user_id=user_id, org_id=payload.org_id, disabled=payload.disabled),
    )
    return UserRead(**asdict(user))


@router.delete("/nodes/{node_id}/users/{user_id}", status_code=204)
async def delete_user(
    node_id: str, user_id: str, org_id: str = Query(...),
    db: Session = Depends(get_db), actor: str = Depends(get_actor),
) -> Response:
    node = _node(db, node_id)
    await _perform(
        db, node, actor, "delete_user", "user", user_id, {"org_id": org_id},
        lambda a: a.delete_user(user_id=user_id, org_id=org_id),
    )
    return Response(status_code=204)


# --- Key / profile lifecycle -------------------------------------------------


@router.post("/nodes/{node_id}/users/{user_id}/profile")
async def issue_profile(
    node_id: str, user_id: str, payload: IssueProfileIn,
    db: Session = Depends(get_db), actor: str = Depends(get_actor),
) -> Response:
    node = _node(db, node_id)
    content = await _perform(
        db, node, actor, "issue_profile", "profile", user_id,
        {"org_id": payload.org_id, "fmt": payload.fmt},
        lambda a: a.issue_profile(user_id=user_id, org_id=payload.org_id, fmt=payload.fmt),
    )
    filename = f"{user_id}.{payload.fmt}"
    return Response(
        content=content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/nodes/{node_id}/users/{user_id}/profile/email", status_code=202)
async def email_profile(
    node_id: str, user_id: str, payload: EmailProfileIn,
    db: Session = Depends(get_db), actor: str = Depends(get_actor),
) -> dict:
    node = _node(db, node_id)
    adapter = node_service.build_adapter_for_node(node)
    try:
        content = await adapter.issue_profile(user_id=user_id, org_id=payload.org_id, fmt=payload.fmt)
    except AdapterError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    finally:
        await adapter.close()

    try:
        msg_id = await delivery_service.send_profile_email(
            to=payload.to, filename=f"{user_id}.{payload.fmt}", content=content, user_name=user_id,
        )
    except delivery_service.NotConfiguredError as exc:
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        audit_service.append(
            db, actor=actor, action="email_profile", result="failure",
            node_id=node.id, node_name=node.name, target_type="user", target_id=user_id,
            params={"to": payload.to, "fmt": payload.fmt}, detail=str(exc),
        )
        db.commit()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"email failed: {exc}") from exc

    audit_service.append(
        db, actor=actor, action="email_profile", result="success",
        node_id=node.id, node_name=node.name, target_type="user", target_id=user_id,
        params={"to": payload.to, "fmt": payload.fmt},
    )
    db.commit()
    return {"status": "sent", "message_id": msg_id}


@router.post("/nodes/{node_id}/users/{user_id}/revoke", status_code=204)
async def revoke_profile(
    node_id: str, user_id: str, payload: RevokeProfileIn,
    db: Session = Depends(get_db), actor: str = Depends(get_actor),
) -> Response:
    node = _node(db, node_id)
    await _perform(
        db, node, actor, "revoke_profile", "profile", user_id, {"org_id": payload.org_id},
        lambda a: a.revoke_profile(user_id=user_id, org_id=payload.org_id),
    )
    return Response(status_code=204)


# --- Bulk user ops (E4) ------------------------------------------------------


@router.post("/nodes/{node_id}/users/bulk", status_code=201)
async def bulk_create_users(
    node_id: str, payload: BulkCreateIn,
    db: Session = Depends(get_db), actor: str = Depends(get_actor),
) -> dict:
    node = _node(db, node_id)
    adapter = node_service.build_adapter_for_node(node)
    results = []
    try:
        for row in payload.users:
            try:
                user = await adapter.create_user(org_id=payload.org_id, name=row.name, email=row.email)
                audit_service.append(
                    db, actor=actor, action="create_user", result="success",
                    node_id=node.id, node_name=node.name, target_type="user", target_id=user.id,
                    params={"org_id": payload.org_id, "name": row.name, "bulk": True},
                )
                results.append({"name": row.name, "status": "created", "id": user.id})
            except AdapterError as exc:
                audit_service.append(
                    db, actor=actor, action="create_user", result="failure",
                    node_id=node.id, node_name=node.name, target_type="user",
                    params={"org_id": payload.org_id, "name": row.name, "bulk": True}, detail=str(exc),
                )
                results.append({"name": row.name, "status": "failed", "error": str(exc)})
        db.commit()
    finally:
        await adapter.close()
    return {"created": sum(1 for r in results if r["status"] == "created"), "results": results}


@router.post("/nodes/{node_id}/users/bulk-action")
async def bulk_user_action(
    node_id: str, payload: BulkActionIn,
    db: Session = Depends(get_db), actor: str = Depends(get_actor),
) -> dict:
    node = _node(db, node_id)
    adapter = node_service.build_adapter_for_node(node)
    results = []
    try:
        for uid in payload.user_ids:
            try:
                if payload.action == "delete":
                    await adapter.delete_user(user_id=uid, org_id=payload.org_id)
                elif payload.action == "revoke":
                    await adapter.revoke_profile(user_id=uid, org_id=payload.org_id)
                else:  # disable / enable
                    await adapter.set_user_disabled(
                        user_id=uid, org_id=payload.org_id, disabled=(payload.action == "disable")
                    )
                audit_service.append(
                    db, actor=actor, action=f"bulk_{payload.action}", result="success",
                    node_id=node.id, node_name=node.name, target_type="user", target_id=uid,
                    params={"org_id": payload.org_id},
                )
                results.append({"id": uid, "status": "ok"})
            except AdapterError as exc:
                audit_service.append(
                    db, actor=actor, action=f"bulk_{payload.action}", result="failure",
                    node_id=node.id, node_name=node.name, target_type="user", target_id=uid,
                    params={"org_id": payload.org_id}, detail=str(exc),
                )
                results.append({"id": uid, "status": "failed", "error": str(exc)})
        db.commit()
    finally:
        await adapter.close()
    return {"ok": sum(1 for r in results if r["status"] == "ok"), "results": results}


# --- Orgs + user policy (E4) -------------------------------------------------


@router.post("/nodes/{node_id}/orgs", response_model=OrgRead, status_code=201)
async def create_org(
    node_id: str, payload: CreateOrgIn,
    db: Session = Depends(get_db), actor: str = Depends(get_actor),
) -> OrgRead:
    node = _node(db, node_id)
    org = await _perform(
        db, node, actor, "create_org", "org", None, {"name": payload.name},
        lambda a: a.create_org(name=payload.name),
    )
    return OrgRead(**asdict(org))


@router.delete("/nodes/{node_id}/orgs/{org_id}", status_code=204)
async def delete_org(
    node_id: str, org_id: str,
    db: Session = Depends(get_db), actor: str = Depends(get_actor),
) -> Response:
    node = _node(db, node_id)
    await _perform(
        db, node, actor, "delete_org", "org", org_id, {},
        lambda a: a.delete_org(org_id=org_id),
    )
    return Response(status_code=204)


@router.patch("/nodes/{node_id}/users/{user_id}/policy", response_model=UserRead)
async def set_user_policy(
    node_id: str, user_id: str, payload: UserPolicyIn,
    db: Session = Depends(get_db), actor: str = Depends(get_actor),
) -> UserRead:
    node = _node(db, node_id)
    policy = payload.model_dump(exclude_none=True, exclude={"org_id"})
    user = await _perform(
        db, node, actor, "set_user_policy", "user", user_id, policy,
        lambda a: a.set_user_policy(user_id=user_id, org_id=payload.org_id, policy=policy),
    )
    return UserRead(**asdict(user))


# --- Server lifecycle --------------------------------------------------------


@router.post("/nodes/{node_id}/servers/{server_id}/action", response_model=ServerRead)
async def server_action(
    node_id: str, server_id: str, payload: ServerActionIn,
    db: Session = Depends(get_db), actor: str = Depends(get_actor),
) -> ServerRead:
    node = _node(db, node_id)
    server = await _perform(
        db, node, actor, f"server_{payload.action}", "server", server_id,
        {"action": payload.action},
        lambda a: a.set_server_state(server_id=server_id, action=payload.action),
    )
    return ServerRead(**asdict(server))


# --- Audit log ---------------------------------------------------------------


@router.get("/audit", response_model=list[AuditOut])
def list_audit(
    limit: int = Query(default=100, le=1000),
    node_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[AuditOut]:
    return [AuditOut.model_validate(e) for e in audit_service.list_entries(db, limit=limit, node_id=node_id)]


@router.get("/audit/verify", response_model=ChainStatusOut)
def verify_audit(db: Session = Depends(get_db)) -> ChainStatusOut:
    status_ = audit_service.verify_chain(db)
    return ChainStatusOut(ok=status_.ok, count=status_.count, broken_at=status_.broken_at, detail=status_.detail)

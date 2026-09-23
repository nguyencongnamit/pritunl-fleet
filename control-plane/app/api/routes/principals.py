"""Principal + RBAC management (admin-only, enforced by rbac_guard)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_actor, get_db
from app.crypto.passwords import hash_password
from app.models.identity import Principal, RoleBinding
from app.schemas.auth import (
    PrincipalCreateIn,
    PrincipalOut,
    PrincipalUpdateIn,
    RoleBindingIn,
)
from app.services import audit as audit_service

router = APIRouter(prefix="/principals", tags=["principals"])


def _get(db: Session, principal_id: str) -> Principal:
    p = db.get(Principal, principal_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "principal not found")
    return p


@router.get("", response_model=list[PrincipalOut])
def list_principals(db: Session = Depends(get_db)) -> list[PrincipalOut]:
    principals = db.scalars(select(Principal).order_by(Principal.username))
    return [PrincipalOut.model_validate(p) for p in principals]


@router.post("", response_model=PrincipalOut, status_code=201)
def create_principal(
    payload: PrincipalCreateIn, db: Session = Depends(get_db), actor: str = Depends(get_actor)
) -> PrincipalOut:
    if db.scalar(select(Principal).where(Principal.username == payload.username)):
        raise HTTPException(status.HTTP_409_CONFLICT, "username already exists")
    p = Principal(
        username=payload.username,
        email=payload.email,
        password_hash=hash_password(payload.password),
        global_role=payload.global_role,
    )
    db.add(p)
    db.flush()
    audit_service.append(
        db, actor=actor, action="create_principal", result="success",
        target_type="principal", target_id=p.id,
        params={"username": p.username, "global_role": p.global_role.value},
    )
    db.commit()
    return PrincipalOut.model_validate(p)


@router.patch("/{principal_id}", response_model=PrincipalOut)
def update_principal(
    principal_id: str, payload: PrincipalUpdateIn,
    db: Session = Depends(get_db), actor: str = Depends(get_actor),
) -> PrincipalOut:
    p = _get(db, principal_id)
    data = payload.model_dump(exclude_unset=True)
    if "password" in data and data["password"]:
        p.password_hash = hash_password(data.pop("password"))
    else:
        data.pop("password", None)
    if data.pop("reset_mfa", False):
        p.totp_secret_enc = None
        p.mfa_enabled = False
    for k, v in data.items():
        setattr(p, k, v)
    db.flush()
    audit_service.append(
        db, actor=actor, action="update_principal", result="success",
        target_type="principal", target_id=p.id, params={"fields": sorted(data.keys())},
    )
    db.commit()
    return PrincipalOut.model_validate(p)


@router.delete("/{principal_id}", status_code=204)
def delete_principal(
    principal_id: str, db: Session = Depends(get_db), actor: str = Depends(get_actor)
):
    p = _get(db, principal_id)
    username = p.username
    db.delete(p)
    audit_service.append(
        db, actor=actor, action="delete_principal", result="success",
        target_type="principal", target_id=principal_id, params={"username": username},
    )
    db.commit()


@router.put("/{principal_id}/bindings", response_model=PrincipalOut)
def set_binding(
    principal_id: str, payload: RoleBindingIn,
    db: Session = Depends(get_db), actor: str = Depends(get_actor),
) -> PrincipalOut:
    p = _get(db, principal_id)
    binding = next((b for b in p.bindings if b.node_id == payload.node_id), None)
    if binding is None:
        binding = RoleBinding(principal_id=p.id, node_id=payload.node_id, role=payload.role)
        db.add(binding)
    else:
        binding.role = payload.role
    db.flush()
    audit_service.append(
        db, actor=actor, action="set_role_binding", result="success",
        node_id=payload.node_id, target_type="principal", target_id=p.id,
        params={"role": payload.role.value},
    )
    db.commit()
    db.refresh(p)
    return PrincipalOut.model_validate(p)


@router.delete("/{principal_id}/bindings/{node_id}", response_model=PrincipalOut)
def delete_binding(
    principal_id: str, node_id: str,
    db: Session = Depends(get_db), actor: str = Depends(get_actor),
) -> PrincipalOut:
    p = _get(db, principal_id)
    binding = next((b for b in p.bindings if b.node_id == node_id), None)
    if binding is not None:
        db.delete(binding)
        db.flush()
        audit_service.append(
            db, actor=actor, action="delete_role_binding", result="success",
            node_id=node_id, target_type="principal", target_id=p.id,
        )
        db.commit()
        db.refresh(p)
    return PrincipalOut.model_validate(p)

"""Authentication + MFA endpoints (unauthenticated router — no rbac_guard).

These issue and upgrade tokens; the RBAC guard protects everything else.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_principal, get_db, get_preauth_principal
from app.models.identity import Principal
from app.schemas.auth import EnrollOut, LoginIn, LoginOut, MeOut, TokenOut, VerifyIn
from app.services import audit as audit_service
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginOut)
def login(payload: LoginIn, db: Session = Depends(get_db)) -> LoginOut:
    try:
        principal = auth_service.authenticate(db, payload.username, payload.password)
    except auth_service.AuthError as exc:
        audit_service.append(
            db, actor=payload.username, action="login", result="failure",
            target_type="principal", detail="invalid credentials",
        )
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials") from exc

    if principal.mfa_enabled:
        token = auth_service.step_token(principal.id, auth_service.SCOPE_MFA)
        return LoginOut(token=token, scope=auth_service.SCOPE_MFA, mfa_required=True)

    # No MFA yet -> force enrolment before a full session can be issued.
    token = auth_service.step_token(principal.id, auth_service.SCOPE_ENROLL)
    return LoginOut(token=token, scope=auth_service.SCOPE_ENROLL, enroll_required=True)


@router.post("/mfa/enroll", response_model=EnrollOut)
def mfa_enroll(
    ctx: tuple[Principal, str] = Depends(get_preauth_principal), db: Session = Depends(get_db)
) -> EnrollOut:
    principal, scope = ctx
    if scope != auth_service.SCOPE_ENROLL:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "already enrolled; verify a code instead")
    secret, uri = auth_service.begin_enrollment(db, principal)
    db.commit()
    return EnrollOut(secret=secret, otpauth_uri=uri)


@router.post("/mfa/verify", response_model=TokenOut)
def mfa_verify(
    payload: VerifyIn,
    ctx: tuple[Principal, str] = Depends(get_preauth_principal),
    db: Session = Depends(get_db),
) -> TokenOut:
    principal, scope = ctx
    try:
        if scope == auth_service.SCOPE_ENROLL:
            auth_service.confirm_enrollment(db, principal, payload.code)
        elif not auth_service.verify_totp(principal, payload.code):
            raise auth_service.AuthError("invalid TOTP code")
    except auth_service.AuthError as exc:
        audit_service.append(
            db, actor=principal.username, action="mfa_verify", result="failure",
            target_type="principal", target_id=principal.id, detail=str(exc),
        )
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc

    audit_service.append(
        db, actor=principal.username, action="login", result="success",
        target_type="principal", target_id=principal.id,
    )
    db.commit()
    return TokenOut(token=auth_service.full_token(principal.id), scope=auth_service.SCOPE_FULL)


@router.get("/me", response_model=MeOut)
def me(principal: Principal = Depends(get_current_principal)) -> MeOut:
    return MeOut.model_validate(principal)

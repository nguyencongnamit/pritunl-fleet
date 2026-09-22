"""Shared FastAPI dependencies: DB session, auth, and RBAC.

`rbac_guard` is attached at the API-router level so every /api/v1 route requires
a full-scope (MFA-satisfied) session token, and enforces role by method + route:

    GET                                   -> viewer
    other methods (mutations)             -> operator (scoped to node_id if present)
    node registry create/edit/delete      -> admin
    /principals/*                         -> admin

The authenticated principal is stashed on request.state for `get_actor`.
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import get_session
from app.models.identity import Principal, Role, role_at_least
from app.services import auth as auth_service

_bearer = HTTPBearer(auto_error=False)

# Route matching is by suffix so it is robust to router prefixes.
def _is_admin_route(method: str, template: str) -> bool:
    if "/principals" in template:  # all principal/RBAC management is admin-only
        return True
    # Node registry lifecycle (create/edit/delete the node itself) is admin-only.
    if method == "POST" and template.endswith("/nodes"):
        return True
    if method in ("PATCH", "DELETE") and template.endswith("/nodes/{node_id}"):
        return True
    return False


def get_db() -> Iterator[Session]:
    yield from get_session()


def _principal_from_token(
    db: Session, creds: HTTPAuthorizationCredentials | None, required_scope: str
) -> Principal:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    try:
        claims = auth_service.decode_token(creds.credentials)
    except auth_service.AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    if claims.get("scope") != required_scope:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token scope not accepted here")
    principal = db.get(Principal, claims.get("sub"))
    if principal is None or principal.disabled:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "principal not found or disabled")
    return principal


def get_current_principal(
    db: Session = Depends(get_db), creds: HTTPAuthorizationCredentials | None = Depends(_bearer)
) -> Principal:
    return _principal_from_token(db, creds, auth_service.SCOPE_FULL)


def get_preauth_principal(
    db: Session = Depends(get_db), creds: HTTPAuthorizationCredentials | None = Depends(_bearer)
) -> tuple[Principal, str]:
    """Accept a step token (mfa or enroll) for the MFA endpoints."""
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    try:
        claims = auth_service.decode_token(creds.credentials)
    except auth_service.AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    scope = claims.get("scope")
    if scope not in (auth_service.SCOPE_MFA, auth_service.SCOPE_ENROLL):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "step token required")
    principal = db.get(Principal, claims.get("sub"))
    if principal is None or principal.disabled:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "principal not found or disabled")
    return principal, scope


def _required_role(request: Request) -> Role:
    route = request.scope.get("route")
    template = getattr(route, "path", "") or request.url.path
    method = request.method

    if _is_admin_route(method, template):
        return Role.admin
    if method == "GET":
        return Role.viewer
    return Role.operator


def rbac_guard(
    request: Request,
    db: Session = Depends(get_db),
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Principal:
    principal = _principal_from_token(db, creds, auth_service.SCOPE_FULL)
    need = _required_role(request)
    node_id = request.path_params.get("node_id")
    have = principal.effective_role(node_id)
    if not role_at_least(have, need):
        scope_txt = f" on node {node_id}" if node_id else ""
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"requires {need.value}{scope_txt}; you have {have.value}",
        )
    request.state.principal = principal
    return principal


def get_actor(request: Request) -> str:
    """Username of the authenticated principal (set by rbac_guard)."""
    principal = getattr(request.state, "principal", None)
    return principal.username if principal is not None else "anonymous"

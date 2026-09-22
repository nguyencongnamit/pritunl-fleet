"""Schemas for authentication, MFA, and principal/RBAC management."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.identity import Role


class LoginIn(BaseModel):
    username: str
    password: str


class LoginOut(BaseModel):
    token: str
    scope: str
    mfa_required: bool = False
    enroll_required: bool = False


class EnrollOut(BaseModel):
    secret: str
    otpauth_uri: str


class VerifyIn(BaseModel):
    code: str = Field(min_length=6, max_length=10)


class TokenOut(BaseModel):
    token: str
    scope: str


class BindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    node_id: str
    role: Role


class MeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    username: str
    email: str | None
    global_role: Role
    mfa_enabled: bool
    bindings: list[BindingOut]


class PrincipalCreateIn(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    email: str | None = None
    password: str = Field(min_length=8)
    global_role: Role = Role.viewer


class PrincipalUpdateIn(BaseModel):
    email: str | None = None
    global_role: Role | None = None
    disabled: bool | None = None
    password: str | None = Field(default=None, min_length=8)


class RoleBindingIn(BaseModel):
    node_id: str
    role: Role


class PrincipalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    username: str
    email: str | None
    global_role: Role
    disabled: bool
    mfa_enabled: bool
    created_at: datetime
    bindings: list[BindingOut]

"""Request/response models for mutating actions and the audit log."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CreateUserIn(BaseModel):
    org_id: str
    name: str = Field(min_length=1, max_length=128)
    email: str | None = None


class DisableUserIn(BaseModel):
    org_id: str
    disabled: bool = True


class DeleteUserIn(BaseModel):
    org_id: str


class IssueProfileIn(BaseModel):
    org_id: str
    fmt: Literal["ovpn", "tar", "key"] = "ovpn"


class RevokeProfileIn(BaseModel):
    org_id: str


class ServerActionIn(BaseModel):
    action: Literal["start", "stop", "restart"]


class CreateOrgIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)


class EmailProfileIn(BaseModel):
    org_id: str
    to: str = Field(min_length=3, max_length=256)
    fmt: Literal["ovpn", "tar", "key"] = "tar"


class BulkUserRow(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    email: str | None = None


class BulkCreateIn(BaseModel):
    org_id: str
    users: list[BulkUserRow] = Field(min_length=1, max_length=1000)


class BulkActionIn(BaseModel):
    org_id: str
    action: Literal["disable", "enable", "revoke", "delete"]
    user_ids: list[str] = Field(min_length=1, max_length=1000)


class UserPolicyIn(BaseModel):
    org_id: str
    pin: str | None = None
    otp_auth: bool | None = None
    client_to_client: bool | None = None
    disabled: bool | None = None
    reset_otp: bool | None = None


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    seq: int
    ts: datetime
    actor: str
    action: str
    node_id: str | None
    node_name: str | None
    target_type: str | None
    target_id: str | None
    result: str
    detail: str | None
    entry_hash: str
    prev_hash: str


class ChainStatusOut(BaseModel):
    ok: bool
    count: int
    broken_at: int | None = None
    detail: str | None = None

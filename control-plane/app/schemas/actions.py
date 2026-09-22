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

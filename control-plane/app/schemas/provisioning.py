"""Request/response models for cross-site provisioning and the sync engine."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.provisioning import PlacementStatus


class TargetIn(BaseModel):
    node_id: str
    org_id: str


class ProvisionIn(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    email: str | None = None
    targets: list[TargetIn] = Field(min_length=1)


class DeprovisionIn(BaseModel):
    hard: bool = False  # False = revoke profiles; True = delete users


class PlacementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    node_id: str
    org_id: str
    remote_user_id: str | None
    status: PlacementStatus
    last_error: str | None
    last_synced_at: datetime | None


class LogicalUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    email: str | None
    created_at: datetime
    placements: list[PlacementOut]


class DriftItemOut(BaseModel):
    kind: str
    remote_user_id: str | None
    username: str | None = None


class NodeSyncReportOut(BaseModel):
    node_id: str
    node_name: str
    reachable: bool
    tracked: int
    present: int
    missing: list[DriftItemOut]
    untracked: list[DriftItemOut]
    in_sync: bool
    error: str | None = None

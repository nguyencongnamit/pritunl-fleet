"""Pydantic request/response models for the node registry.

Security contract: `credentials` is WRITE-ONLY. It is accepted on create/update
but never appears in any response model — the API can never echo a node's
secrets back, and they are not logged.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.node import AdapterType, HealthStatus


class NodeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    region: str = Field(min_length=1, max_length=64)
    endpoint: str = Field(min_length=1, max_length=512)
    adapter_type: AdapterType = AdapterType.shim
    verify_tls: bool = True
    enabled: bool = True
    # Adapter-specific secret material. Shape depends on adapter_type:
    #   shim  -> {"token": "...", "secret": "..."}
    #   mongo -> {"mongo_uri": "..."}
    #   ssh   -> {"host": "...", "username": "...", "private_key": "..."}
    credentials: dict = Field(default_factory=dict, repr=False)


class NodeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    region: str | None = Field(default=None, min_length=1, max_length=64)
    endpoint: str | None = Field(default=None, min_length=1, max_length=512)
    adapter_type: AdapterType | None = None
    verify_tls: bool | None = None
    enabled: bool | None = None
    # Provide only to rotate credentials; omit to leave them unchanged.
    credentials: dict | None = Field(default=None, repr=False)


class NodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    region: str
    endpoint: str
    adapter_type: AdapterType
    verify_tls: bool
    enabled: bool

    status: HealthStatus
    last_checked_at: datetime | None
    last_synced_at: datetime | None
    last_latency_ms: int | None
    consecutive_failures: int
    last_error: str | None

    created_at: datetime
    updated_at: datetime


class NodeHealthOut(BaseModel):
    node_id: str
    status: HealthStatus
    latency_ms: int | None = None
    detail: dict = Field(default_factory=dict)
    error: str | None = None
    checked_at: datetime | None = None

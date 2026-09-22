"""Response models for cross-site reads: dashboard, servers/orgs/users, sessions."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.node import AdapterType, HealthStatus


class ServerRead(BaseModel):
    id: str
    name: str
    status: str
    protocol: str
    port: int | None = None
    online_clients: int = 0
    org_ids: list[str] = Field(default_factory=list)


class OrgRead(BaseModel):
    id: str
    name: str
    user_count: int = 0


class UserRead(BaseModel):
    id: str
    name: str
    org_id: str
    org_name: str | None = None
    disabled: bool = False
    revoked: bool = False
    email: str | None = None


class SessionRead(BaseModel):
    user_id: str
    user_name: str
    server_id: str
    virtual_address: str | None = None
    real_address: str | None = None
    connected_since: datetime | None = None
    bytes_sent: int = 0
    bytes_received: int = 0


class ScopedUser(UserRead):
    """A user annotated with the site it lives on (for cross-node search)."""
    node_id: str
    node_name: str
    region: str


class ScopedServer(ServerRead):
    """A server annotated with the site it lives on (for cross-site control)."""
    node_id: str
    node_name: str
    region: str


class SiteSummary(BaseModel):
    node_id: str
    name: str
    region: str
    adapter_type: AdapterType
    status: HealthStatus
    servers_total: int = 0
    servers_online: int = 0
    orgs: int = 0
    users_total: int = 0
    users_disabled: int = 0
    active_sessions: int = 0
    online_clients: int = 0  # OpenVPN load proxy
    last_checked_at: datetime | None = None
    last_synced_at: datetime | None = None
    last_latency_ms: int | None = None
    error: str | None = None


class DashboardTotals(BaseModel):
    sites: int = 0
    sites_reachable: int = 0
    servers_total: int = 0
    servers_online: int = 0
    users_total: int = 0
    active_sessions: int = 0
    online_clients: int = 0


class DashboardOut(BaseModel):
    generated_at: datetime
    totals: DashboardTotals
    sites: list[SiteSummary]

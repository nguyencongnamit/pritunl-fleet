"""NodeAdapter — the common interface every Pritunl-OSS access method implements.

The control plane never talks to a node directly; it always goes through a
NodeAdapter. Three concrete adapters exist, selected per-node via config:

  - shim  (DEFAULT): a small HMAC-authed REST endpoint added to the OSS node
           that reuses Pritunl's own Python modules. Correct mutation semantics,
           smallest attack surface, and 1:1 with the Enterprise HMAC API so it
           can be swapped for the licensed API later with no call-site changes.
  - mongo (stub): read-only fast path straight from the node's MongoDB, used to
           accelerate dashboard/sync reads. Never used for mutations.
  - ssh   (stub): bootstrap / break-glass over SSH + CLI, for installing the
           shim, restarting services, and disaster recovery.

Only health() must be implemented for Phase 1. Every other method has a default
that raises NotImplementedError, so adapters can fill capabilities in
incrementally (later phases) while still being instantiable now.

All methods are async so N nodes can be swept concurrently.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Reachability(str, Enum):
    reachable = "reachable"
    degraded = "degraded"
    down = "down"


@dataclass(slots=True)
class NodeHealth:
    reachability: Reachability
    latency_ms: int | None = None
    # Free-form node facts surfaced by the adapter (version, server counts…).
    detail: dict = field(default_factory=dict)
    error: str | None = None


# --- Read shapes (populated from Phase 2 onward) -----------------------------


@dataclass(slots=True)
class ServerInfo:
    id: str
    name: str
    status: str          # online / offline
    protocol: str        # openvpn / wireguard
    port: int | None = None
    online_clients: int = 0
    org_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class OrgInfo:
    id: str
    name: str
    user_count: int = 0


@dataclass(slots=True)
class UserInfo:
    id: str
    name: str
    org_id: str
    org_name: str | None = None
    disabled: bool = False
    revoked: bool = False
    email: str | None = None


@dataclass(slots=True)
class SessionInfo:
    user_id: str
    user_name: str
    server_id: str
    virtual_address: str | None = None
    real_address: str | None = None
    connected_since: datetime | None = None
    bytes_sent: int = 0
    bytes_received: int = 0


@dataclass(slots=True)
class NodeState:
    """Full snapshot used by the sync engine to reconcile drift."""
    servers: list[ServerInfo] = field(default_factory=list)
    orgs: list[OrgInfo] = field(default_factory=list)
    users: list[UserInfo] = field(default_factory=list)


class AdapterError(RuntimeError):
    """Raised for any adapter-level failure (network, auth, node error)."""


class NodeAdapter(abc.ABC):
    """One instance per node call. Construct via adapters.factory.build_adapter."""

    #: adapter registry key; set by each subclass.
    adapter_type: str = "base"

    def __init__(self, *, endpoint: str, credentials: dict, verify_tls: bool, timeout: float):
        self.endpoint = endpoint
        self._credentials = credentials
        self.verify_tls = verify_tls
        self.timeout = timeout

    # --- Phase 1: liveness ---------------------------------------------------
    @abc.abstractmethod
    async def health(self) -> NodeHealth:
        """Cheap reachability + basic facts. Must not mutate node state."""
        ...

    # --- Phase 2: reads ------------------------------------------------------
    async def get_state(self) -> NodeState:
        raise NotImplementedError

    async def list_servers(self) -> list[ServerInfo]:
        raise NotImplementedError

    async def list_orgs(self) -> list[OrgInfo]:
        raise NotImplementedError

    async def list_users(self) -> list[UserInfo]:
        raise NotImplementedError

    # --- Phase 3: mutations --------------------------------------------------
    async def create_user(self, *, org_id: str, name: str, email: str | None = None) -> UserInfo:
        raise NotImplementedError

    async def set_user_disabled(self, *, user_id: str, org_id: str, disabled: bool) -> UserInfo:
        raise NotImplementedError

    async def delete_user(self, *, user_id: str, org_id: str) -> None:
        raise NotImplementedError

    async def issue_profile(self, *, user_id: str, org_id: str, fmt: str = "ovpn") -> bytes:
        """Return the client profile bytes (.ovpn / .tar) or key URI."""
        raise NotImplementedError

    async def revoke_profile(self, *, user_id: str, org_id: str) -> None:
        raise NotImplementedError

    async def set_server_state(self, *, server_id: str, action: str) -> ServerInfo:
        """action in {start, stop, restart}."""
        raise NotImplementedError

    # --- Phase 7: monitoring -------------------------------------------------
    async def list_sessions(self) -> list[SessionInfo]:
        raise NotImplementedError

    async def close(self) -> None:
        """Release any transport resources. Safe to call multiple times."""
        return None

    async def __aenter__(self) -> NodeAdapter:
        return self

    async def __aexit__(self, *exc) -> None:
        await self.close()

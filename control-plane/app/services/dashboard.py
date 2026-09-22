"""Cross-site aggregation for the unified dashboard and global user search.

Live node facts are fetched concurrently through each node's adapter; reachability
comes from the persisted health status (kept fresh by the health loop). One slow
or down node never blocks the others, and its live counts degrade to zero with an
error note rather than failing the whole view.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.base import NodeState, SessionInfo
from app.models.base import utcnow
from app.models.node import HealthStatus, Node
from app.schemas.read import (
    DashboardOut,
    DashboardTotals,
    ScopedServer,
    ScopedUser,
    SessionRead,
    SiteSummary,
)
from app.services.nodes import build_adapter_for_node


async def _fetch_node(node: Node) -> tuple[NodeState | None, list[SessionInfo], str | None]:
    """Return (state, sessions, error) for one node. Never raises."""
    if not node.enabled or node.status == HealthStatus.down:
        return None, [], None if node.enabled else "node disabled"
    adapter = build_adapter_for_node(node)
    try:
        state, sessions = await asyncio.gather(adapter.get_state(), adapter.list_sessions())
        return state, sessions, None
    except Exception as exc:  # noqa: BLE001 — isolate per-node failures
        return None, [], f"live fetch failed: {exc}"
    finally:
        await adapter.close()


def _summarize(node: Node, state: NodeState | None, sessions: list, error: str | None) -> SiteSummary:
    summary = SiteSummary(
        node_id=node.id,
        name=node.name,
        region=node.region,
        adapter_type=node.adapter_type,
        status=node.status,
        last_checked_at=node.last_checked_at,
        last_synced_at=node.last_synced_at,
        last_latency_ms=node.last_latency_ms,
        error=error,
    )
    if state is not None:
        summary.servers_total = len(state.servers)
        summary.servers_online = sum(1 for s in state.servers if s.status == "online")
        summary.orgs = len(state.orgs)
        summary.users_total = len(state.users)
        summary.users_disabled = sum(1 for u in state.users if u.disabled)
        summary.online_clients = sum(s.online_clients for s in state.servers)
        summary.active_sessions = len(sessions)
    return summary


async def build_dashboard(session: Session) -> DashboardOut:
    nodes = list(session.scalars(select(Node).order_by(Node.region, Node.name)))
    results = await asyncio.gather(*(_fetch_node(n) for n in nodes)) if nodes else []

    sites: list[SiteSummary] = []
    totals = DashboardTotals(sites=len(nodes))
    for node, (state, node_sessions, error) in zip(nodes, results):
        summary = _summarize(node, state, node_sessions, error)
        sites.append(summary)
        if node.status == HealthStatus.reachable:
            totals.sites_reachable += 1
        totals.servers_total += summary.servers_total
        totals.servers_online += summary.servers_online
        totals.users_total += summary.users_total
        totals.active_sessions += summary.active_sessions
        totals.online_clients += summary.online_clients

    return DashboardOut(generated_at=utcnow(), totals=totals, sites=sites)


async def search_users(session: Session, query: str | None = None) -> list[ScopedUser]:
    nodes = list(session.scalars(select(Node).where(Node.enabled.is_(True))))
    results = await asyncio.gather(*(_fetch_node(n) for n in nodes)) if nodes else []

    q = (query or "").strip().lower()
    scoped: list[ScopedUser] = []
    for node, (state, _sessions, _error) in zip(nodes, results):
        if state is None:
            continue
        for u in state.users:
            if q and q not in u.name.lower() and q not in (u.email or "").lower():
                continue
            scoped.append(
                ScopedUser(
                    id=u.id, name=u.name, org_id=u.org_id, org_name=u.org_name,
                    disabled=u.disabled, revoked=u.revoked, email=u.email,
                    node_id=node.id, node_name=node.name, region=node.region,
                )
            )
    return scoped


async def list_servers(session: Session) -> list[ScopedServer]:
    nodes = list(session.scalars(select(Node).where(Node.enabled.is_(True))))
    results = await asyncio.gather(*(_fetch_node(n) for n in nodes)) if nodes else []
    servers: list[ScopedServer] = []
    for node, (state, _sessions, _error) in zip(nodes, results):
        if state is None:
            continue
        for s in state.servers:
            servers.append(
                ScopedServer(
                    **asdict(s), node_id=node.id, node_name=node.name, region=node.region
                )
            )
    return servers


async def node_sessions(node: Node) -> list[SessionRead]:
    _state, sessions, error = await _fetch_node(node)
    if error:
        from fastapi import HTTPException, status
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, error)
    return [SessionRead(**asdict(s)) for s in sessions]

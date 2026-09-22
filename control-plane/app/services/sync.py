"""Sync engine — reconcile control-plane placements with node reality.

For each node it fetches the live user set and compares against the placements
we track:
  * present    — placement's remote user still exists on the node
  * missing    — placement recorded here, user absent on the node (DRIFT)
  * untracked  — user exists on the node with no placement (created out-of-band)

It updates placement/node sync status and returns a per-node drift report.
Runs on demand and on the periodic sync loop.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.base import AdapterError
from app.db import SessionLocal
from app.models.base import utcnow
from app.models.node import Node
from app.models.provisioning import PlacementStatus, UserPlacement
from app.services.nodes import build_adapter_for_node

logger = logging.getLogger("fleet.sync")


@dataclass
class DriftItem:
    kind: str  # missing | untracked
    remote_user_id: str | None
    username: str | None = None


@dataclass
class NodeSyncReport:
    node_id: str
    node_name: str
    reachable: bool
    tracked: int = 0
    present: int = 0
    missing: list[DriftItem] = field(default_factory=list)
    untracked: list[DriftItem] = field(default_factory=list)
    error: str | None = None

    @property
    def in_sync(self) -> bool:
        return self.reachable and not self.missing and not self.untracked


async def sync_node(session: Session, node: Node) -> NodeSyncReport:
    report = NodeSyncReport(node_id=node.id, node_name=node.name, reachable=True)
    placements = list(
        session.scalars(select(UserPlacement).where(UserPlacement.node_id == node.id))
    )
    report.tracked = len(placements)

    adapter = build_adapter_for_node(node)
    try:
        users = await adapter.list_users()
    except AdapterError as exc:
        report.reachable = False
        report.error = str(exc)
        return report
    finally:
        await adapter.close()  # idempotent

    node_user_ids = {u.id: u for u in users}
    tracked_remote_ids = set()

    now = utcnow()
    for p in placements:
        if p.remote_user_id and p.remote_user_id in node_user_ids:
            p.status = PlacementStatus.active
            p.last_error = None
            report.present += 1
            tracked_remote_ids.add(p.remote_user_id)
        elif p.remote_user_id:
            p.status = PlacementStatus.missing
            report.missing.append(DriftItem(kind="missing", remote_user_id=p.remote_user_id))
        p.last_synced_at = now

    for uid, u in node_user_ids.items():
        if uid not in tracked_remote_ids:
            report.untracked.append(DriftItem(kind="untracked", remote_user_id=uid, username=u.name))

    node.last_synced_at = now
    session.commit()
    return report


async def sync_all() -> list[NodeSyncReport]:
    session = SessionLocal()
    reports: list[NodeSyncReport] = []
    try:
        nodes = list(session.scalars(select(Node).where(Node.enabled.is_(True))))
        for node in nodes:
            try:
                reports.append(await sync_node(session, node))
            except Exception as exc:  # noqa: BLE001 — isolate per-node
                logger.exception("sync failed for node %s", node.name)
                reports.append(
                    NodeSyncReport(node_id=node.id, node_name=node.name, reachable=False, error=str(exc))
                )
    finally:
        session.close()
    return reports


async def run_sync_loop(stop_event: asyncio.Event, interval: float) -> None:
    logger.info("sync loop started (interval=%.0fs)", interval)
    while not stop_event.is_set():
        try:
            reports = await sync_all()
            drift = sum(1 for r in reports if not r.in_sync)
            logger.debug("sync swept %d node(s), %d with drift/unreachable", len(reports), drift)
        except Exception:  # noqa: BLE001
            logger.exception("sync sweep errored")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except TimeoutError:
            pass
    logger.info("sync loop stopped")

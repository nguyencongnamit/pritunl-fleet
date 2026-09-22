"""Health check engine — per-node liveness probing and status roll-up.

check_node() probes one node through its adapter and folds the result into the
node's persisted health fields, applying the consecutive-failure threshold that
distinguishes a transient 'degraded' blip from a sustained 'down'.

run_health_loop() is the periodic background sweep started at app startup.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.base import NodeHealth, Reachability
from app.config import get_settings
from app.db import SessionLocal
from app.models.base import utcnow
from app.models.node import HealthStatus, Node
from app.services.nodes import build_adapter_for_node

logger = logging.getLogger("fleet.health")

_REACHABILITY_TO_STATUS = {
    Reachability.reachable: HealthStatus.reachable,
    Reachability.degraded: HealthStatus.degraded,
    Reachability.down: HealthStatus.down,
}


async def _probe(node: Node) -> NodeHealth:
    settings = get_settings()
    adapter = build_adapter_for_node(node)
    try:
        return await asyncio.wait_for(
            adapter.health(), timeout=settings.node_request_timeout + 2.0
        )
    except TimeoutError:
        return NodeHealth(reachability=Reachability.down, error="health probe timed out")
    except Exception as exc:  # noqa: BLE001 — never let one node break the sweep
        return NodeHealth(reachability=Reachability.down, error=f"probe error: {exc}")
    finally:
        await adapter.close()


async def check_node(session: Session, node: Node) -> NodeHealth:
    """Probe one node and persist the outcome. Caller commits the session."""
    settings = get_settings()
    result = await _probe(node)

    node.last_checked_at = utcnow()
    node.last_latency_ms = result.latency_ms

    if result.reachability is Reachability.reachable:
        node.consecutive_failures = 0
        node.status = HealthStatus.reachable
        node.last_error = None
    else:
        node.consecutive_failures += 1
        node.last_error = result.error
        if node.consecutive_failures >= settings.health_down_threshold:
            node.status = HealthStatus.down
        else:
            node.status = _REACHABILITY_TO_STATUS.get(result.reachability, HealthStatus.degraded)

    session.add(node)
    return result


async def sweep_once() -> int:
    """Probe every enabled node once. Returns the number of nodes checked."""
    session = SessionLocal()
    checked = 0
    try:
        nodes = list(session.scalars(select(Node).where(Node.enabled.is_(True))))
        for node in nodes:
            await check_node(session, node)
            checked += 1
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("health sweep failed")
        raise
    finally:
        session.close()
    return checked


async def run_health_loop(stop_event: asyncio.Event) -> None:
    """Background task: sweep all nodes on the configured interval until stopped."""
    interval = get_settings().health_sweep_interval
    logger.info("health loop started (interval=%.0fs)", interval)
    while not stop_event.is_set():
        try:
            count = await sweep_once()
            logger.debug("health sweep checked %d node(s)", count)
        except Exception:  # noqa: BLE001 — keep the loop alive across failures
            logger.exception("health sweep iteration errored")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except TimeoutError:
            pass
    logger.info("health loop stopped")

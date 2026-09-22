"""Audit service — append-only hash-chained writes and chain verification.

append() is the ONLY way mutations are recorded. It reads the current chain
head, computes this entry's hash over (prev_hash + canonical payload), and
inserts. verify_chain() recomputes the whole chain and reports the first break.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit import GENESIS_HASH, AuditEntry
from app.models.base import utcnow


def _canonical(entry: AuditEntry) -> str:
    """Deterministic serialization of the hashed fields (excludes hashes/seq)."""
    payload = {
        "ts": entry.ts.isoformat(),
        "actor": entry.actor,
        "action": entry.action,
        "node_id": entry.node_id,
        "node_name": entry.node_name,
        "target_type": entry.target_type,
        "target_id": entry.target_id,
        "result": entry.result,
        "detail": entry.detail,
        "params": entry.params,
        "request_id": entry.request_id,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _hash(prev_hash: str, entry: AuditEntry) -> str:
    return hashlib.sha256((prev_hash + _canonical(entry)).encode("utf-8")).hexdigest()


def _head_hash(session: Session) -> str:
    last = session.scalars(select(AuditEntry).order_by(AuditEntry.seq.desc()).limit(1)).first()
    return last.entry_hash if last is not None else GENESIS_HASH


def append(
    session: Session,
    *,
    actor: str,
    action: str,
    result: str,
    node_id: str | None = None,
    node_name: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    detail: str | None = None,
    params: dict | None = None,
    request_id: str | None = None,
) -> AuditEntry:
    prev = _head_hash(session)
    entry = AuditEntry(
        ts=utcnow(),
        actor=actor,
        action=action,
        result=result,
        node_id=node_id,
        node_name=node_name,
        target_type=target_type,
        target_id=target_id,
        detail=detail,
        params=json.dumps(params or {}, sort_keys=True, separators=(",", ":"), default=str),
        request_id=request_id,
        prev_hash=prev,
    )
    entry.entry_hash = _hash(prev, entry)
    session.add(entry)
    session.flush()
    return entry


def list_entries(session: Session, *, limit: int = 100, node_id: str | None = None) -> list[AuditEntry]:
    stmt = select(AuditEntry).order_by(AuditEntry.seq.desc()).limit(limit)
    if node_id:
        stmt = select(AuditEntry).where(AuditEntry.node_id == node_id).order_by(
            AuditEntry.seq.desc()
        ).limit(limit)
    return list(session.scalars(stmt))


@dataclass
class ChainStatus:
    ok: bool
    count: int
    broken_at: int | None = None
    detail: str | None = None


def verify_chain(session: Session) -> ChainStatus:
    entries = list(session.scalars(select(AuditEntry).order_by(AuditEntry.seq.asc())))
    prev = GENESIS_HASH
    for e in entries:
        if e.prev_hash != prev:
            return ChainStatus(False, len(entries), e.seq, "prev_hash mismatch")
        if _hash(prev, e) != e.entry_hash:
            return ChainStatus(False, len(entries), e.seq, "entry_hash mismatch (row tampered)")
        prev = e.entry_hash
    return ChainStatus(True, len(entries))

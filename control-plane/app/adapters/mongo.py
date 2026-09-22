"""Mongo adapter (STUB) — read-only fast path from a node's MongoDB.

Role: accelerate dashboard/sync READS by querying the node's datastore
directly. It is deliberately incapable of mutations: writing to Mongo bypasses
Pritunl's PKI, OpenVPN config generation, and process reload, producing broken
state. Mutations must always go through the shim adapter.

Least-privilege requirement: a dedicated MongoDB user with **read-only** access
to the node's Pritunl database, reachable ONLY over mTLS or an SSH tunnel —
never expose Mongo to the network in the clear.

Credentials dict shape:  {"mongo_uri": "mongodb://ro-user:***@host:27017/pritunl"}

Only health() is implemented in Phase 1 (a ping). Read methods are filled in a
later phase (they map to find() queries on orgs/users/servers collections).
"""

from __future__ import annotations

from app.adapters.base import AdapterError, NodeAdapter, NodeHealth, Reachability


class MongoAdapter(NodeAdapter):
    adapter_type = "mongo"

    # WRITE GUARD — this adapter must never mutate a node.
    read_only = True

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        creds = self._credentials or {}
        self._mongo_uri = creds.get("mongo_uri") or self.endpoint
        if not self._mongo_uri:
            raise AdapterError("mongo adapter requires a 'mongo_uri' credential or endpoint")

    async def health(self) -> NodeHealth:
        # Stub: a real implementation runs `db.command('ping')` via motor with a
        # short serverSelectionTimeout and TLS. Until the mongo extra is wired
        # into the lab, report 'unknown' rather than fabricating reachability.
        return NodeHealth(
            reachability=Reachability.degraded,
            error="mongo adapter is a stub (read-only fast path — not yet implemented)",
            detail={"read_only": True},
        )

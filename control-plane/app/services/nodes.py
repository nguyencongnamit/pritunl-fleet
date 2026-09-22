"""Node registry service — CRUD over the registry plus adapter construction.

This is the only layer that touches node credentials: it seals them on write
and decrypts them transiently to build an adapter. Credentials never leave this
layer in plaintext except inside a live adapter instance.
"""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.base import NodeAdapter
from app.adapters.factory import build_adapter
from app.config import get_settings
from app.crypto import envelope
from app.models.node import Node
from app.schemas.node import NodeCreate, NodeUpdate


class NodeNotFoundError(LookupError):
    pass


class DuplicateNodeError(ValueError):
    pass


def _seal_credentials(credentials: dict) -> bytes:
    return envelope.seal(json.dumps(credentials or {}, separators=(",", ":")).encode("utf-8"))


def _unseal_credentials(blob: bytes) -> dict:
    return json.loads(envelope.open_(blob).decode("utf-8"))


def list_nodes(session: Session) -> list[Node]:
    return list(session.scalars(select(Node).order_by(Node.region, Node.name)))


def get_node(session: Session, node_id: str) -> Node:
    node = session.get(Node, node_id)
    if node is None:
        raise NodeNotFoundError(node_id)
    return node


def create_node(session: Session, payload: NodeCreate) -> Node:
    existing = session.scalar(select(Node).where(Node.name == payload.name))
    if existing is not None:
        raise DuplicateNodeError(payload.name)

    node = Node(
        name=payload.name,
        region=payload.region,
        endpoint=payload.endpoint,
        adapter_type=payload.adapter_type,
        verify_tls=payload.verify_tls,
        enabled=payload.enabled,
        credentials_enc=_seal_credentials(payload.credentials),
    )
    session.add(node)
    session.flush()
    return node


def update_node(session: Session, node_id: str, payload: NodeUpdate) -> Node:
    node = get_node(session, node_id)
    data = payload.model_dump(exclude_unset=True)

    if "name" in data and data["name"] != node.name:
        clash = session.scalar(select(Node).where(Node.name == data["name"], Node.id != node.id))
        if clash is not None:
            raise DuplicateNodeError(data["name"])

    if "credentials" in data:
        creds = data.pop("credentials")
        if creds is not None:  # None => leave unchanged
            node.credentials_enc = _seal_credentials(creds)

    for key, value in data.items():
        setattr(node, key, value)

    session.flush()
    return node


def delete_node(session: Session, node_id: str) -> None:
    node = get_node(session, node_id)
    session.delete(node)
    session.flush()


def get_admin_url(node: Node) -> str | None:
    """The node's native Pritunl web-admin URL, stored (non-secret) in the sealed
    credentials blob as `admin_url`. Used for the one-click "Open admin" deep-link
    (Pritunl OSS has no admin SSO; auto-login would require forging Pritunl's
    custom-signed session cookie on the node's web origin — see SHIM_DESIGN.md)."""
    creds = _unseal_credentials(node.credentials_enc)
    return creds.get("admin_url")


def build_adapter_for_node(node: Node) -> NodeAdapter:
    """Decrypt this node's credentials and return a ready adapter instance."""
    settings = get_settings()
    credentials = _unseal_credentials(node.credentials_enc)
    return build_adapter(
        adapter_type=node.adapter_type.value,
        endpoint=node.endpoint,
        credentials=credentials,
        verify_tls=node.verify_tls,
        timeout=settings.node_request_timeout,
    )

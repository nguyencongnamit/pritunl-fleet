"""Adapter factory — resolve the concrete NodeAdapter for a node.

The adapter type is a per-node config value, so switching a site between the
shim / mongo / ssh access methods is a registry edit, not a code change.
Credentials are passed in already-decrypted by the service layer (the factory
never touches the database or the master key).
"""

from __future__ import annotations

from app.adapters.base import NodeAdapter
from app.adapters.mongo import MongoAdapter
from app.adapters.shim import ShimAdapter
from app.adapters.ssh import SSHAdapter

_REGISTRY: dict[str, type[NodeAdapter]] = {
    ShimAdapter.adapter_type: ShimAdapter,
    MongoAdapter.adapter_type: MongoAdapter,
    SSHAdapter.adapter_type: SSHAdapter,
}


def available_adapters() -> list[str]:
    return sorted(_REGISTRY)


def build_adapter(
    *,
    adapter_type: str,
    endpoint: str,
    credentials: dict,
    verify_tls: bool,
    timeout: float,
) -> NodeAdapter:
    try:
        cls = _REGISTRY[adapter_type]
    except KeyError as exc:
        raise ValueError(f"unknown adapter type: {adapter_type!r}") from exc
    return cls(
        endpoint=endpoint,
        credentials=credentials,
        verify_tls=verify_tls,
        timeout=timeout,
    )

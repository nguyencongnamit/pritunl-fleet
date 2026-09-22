"""Shim adapter (DEFAULT) — talk to a Pritunl OSS node via its HMAC REST shim.

The shim is a small blueprint added to each OSS node that reuses Pritunl's own
Python modules behind an HMAC check (see pritunl-shim/). This adapter signs
every request with the shared HMAC scheme and speaks JSON.

Credentials dict shape:  {"token": "<public token>", "secret": "<hmac secret>"}

Phase 1 implements health(). Read/mutation methods land in later phases; each
maps onto a signed REST call, so the wire contract is stable now.
"""

from __future__ import annotations

import json
import time
from datetime import datetime

import httpx

from app.adapters.base import (
    AdapterError,
    NodeAdapter,
    NodeHealth,
    NodeState,
    OrgInfo,
    Reachability,
    ServerInfo,
    SessionInfo,
    UserInfo,
)

try:  # canonical HMAC module, shared with the node shim/mock
    from shim.hmac_auth import H_NONCE, H_SIGNATURE, H_TIMESTAMP, H_TOKEN, sign_request
except ModuleNotFoundError:  # local dev outside the container image
    import pathlib
    import sys

    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "pritunl-shim"))
    from shim.hmac_auth import H_NONCE, H_SIGNATURE, H_TIMESTAMP, H_TOKEN, sign_request

_AUTH_HEADERS = (H_TOKEN, H_TIMESTAMP, H_NONCE, H_SIGNATURE)


class ShimAdapter(NodeAdapter):
    adapter_type = "shim"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        creds = self._credentials or {}
        self._token = creds.get("token")
        self._secret = creds.get("secret")
        if not self._token or not self._secret:
            raise AdapterError("shim adapter requires 'token' and 'secret' credentials")
        self._base = self.endpoint.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base,
                timeout=self.timeout,
                verify=self.verify_tls,
            )
        return self._client

    async def _request(self, method: str, path: str, body: bytes = b"") -> httpx.Response:
        headers = sign_request(
            token=self._token,
            secret=self._secret,
            method=method,
            path=path,
            body=body,
        )
        if body:
            headers["Content-Type"] = "application/json"
        try:
            resp = await self._http().request(method, path, headers=headers, content=body or None)
        except httpx.HTTPError as exc:
            raise AdapterError(f"transport error to {self._base}{path}: {exc}") from exc
        return resp

    async def health(self) -> NodeHealth:
        started = time.perf_counter()
        try:
            resp = await self._request("GET", "/v1/ping")
        except AdapterError as exc:
            return NodeHealth(reachability=Reachability.down, error=str(exc))

        latency_ms = int((time.perf_counter() - started) * 1000)

        if resp.status_code == 401:
            return NodeHealth(
                reachability=Reachability.degraded,
                latency_ms=latency_ms,
                error="authentication rejected by node shim (check token/secret/clock skew)",
            )
        if resp.status_code >= 500:
            return NodeHealth(
                reachability=Reachability.degraded,
                latency_ms=latency_ms,
                error=f"node shim returned {resp.status_code}",
            )
        if resp.status_code != 200:
            return NodeHealth(
                reachability=Reachability.degraded,
                latency_ms=latency_ms,
                error=f"unexpected status {resp.status_code}",
            )

        try:
            data = resp.json()
        except ValueError:
            data = {}
        return NodeHealth(
            reachability=Reachability.reachable,
            latency_ms=latency_ms,
            detail={
                "version": data.get("version"),
                "servers_total": data.get("servers_total"),
                "servers_online": data.get("servers_online"),
                "online_clients": data.get("online_clients"),
            },
        )

    # --- Reads (Phase 2) -----------------------------------------------------

    async def _get_json(self, path: str) -> dict:
        resp = await self._request("GET", path)
        if resp.status_code == 401:
            raise AdapterError("authentication rejected by node shim")
        if resp.status_code != 200:
            raise AdapterError(f"node shim returned {resp.status_code} for {path}")
        try:
            return resp.json()
        except ValueError as exc:
            raise AdapterError(f"invalid JSON from {path}") from exc

    async def get_state(self) -> NodeState:
        data = await self._get_json("/v1/state")
        return NodeState(
            servers=[_parse_server(s) for s in data.get("servers", [])],
            orgs=[_parse_org(o) for o in data.get("orgs", [])],
            users=[_parse_user(u) for u in data.get("users", [])],
        )

    async def list_servers(self) -> list[ServerInfo]:
        data = await self._get_json("/v1/state")
        return [_parse_server(s) for s in data.get("servers", [])]

    async def list_orgs(self) -> list[OrgInfo]:
        data = await self._get_json("/v1/state")
        return [_parse_org(o) for o in data.get("orgs", [])]

    async def list_users(self) -> list[UserInfo]:
        data = await self._get_json("/v1/state")
        return [_parse_user(u) for u in data.get("users", [])]

    async def list_sessions(self) -> list[SessionInfo]:
        data = await self._get_json("/v1/sessions")
        return [_parse_session(s) for s in data.get("sessions", [])]

    # --- Mutations (Phase 3) -------------------------------------------------

    async def _mutate(self, method: str, path: str, payload: dict | None = None) -> httpx.Response:
        body = json.dumps(payload).encode("utf-8") if payload is not None else b""
        resp = await self._request(method, path, body=body)
        if resp.status_code == 401:
            raise AdapterError("authentication rejected by node shim")
        if resp.status_code >= 400:
            detail = resp.text
            try:
                detail = resp.json().get("error", detail)
            except ValueError:
                pass
            raise AdapterError(f"node shim {resp.status_code}: {detail}")
        return resp

    async def create_user(self, *, org_id: str, name: str, email: str | None = None) -> UserInfo:
        resp = await self._mutate("POST", f"/v1/orgs/{org_id}/users", {"name": name, "email": email})
        return _parse_user(resp.json())

    async def set_user_disabled(self, *, user_id: str, org_id: str, disabled: bool) -> UserInfo:
        resp = await self._mutate("POST", f"/v1/users/{user_id}/disable", {"disabled": disabled})
        return _parse_user(resp.json())

    async def delete_user(self, *, user_id: str, org_id: str) -> None:
        await self._mutate("DELETE", f"/v1/users/{user_id}")

    async def issue_profile(self, *, user_id: str, org_id: str, fmt: str = "ovpn") -> bytes:
        resp = await self._mutate("POST", f"/v1/users/{user_id}/profile", {"fmt": fmt})
        return resp.content

    async def revoke_profile(self, *, user_id: str, org_id: str) -> None:
        await self._mutate("POST", f"/v1/users/{user_id}/revoke", {})

    async def set_server_state(self, *, server_id: str, action: str) -> ServerInfo:
        resp = await self._mutate("POST", f"/v1/servers/{server_id}/state", {"action": action})
        return _parse_server(resp.json())

    async def create_org(self, *, name: str) -> OrgInfo:
        resp = await self._mutate("POST", "/v1/orgs", {"name": name})
        return _parse_org(resp.json())

    async def delete_org(self, *, org_id: str) -> None:
        await self._mutate("DELETE", f"/v1/orgs/{org_id}")

    async def set_user_policy(self, *, user_id: str, org_id: str, policy: dict) -> UserInfo:
        resp = await self._mutate("PATCH", f"/v1/users/{user_id}", policy)
        return _parse_user(resp.json())

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


# --- Wire -> dataclass parsers (tolerant of missing keys) --------------------


def _parse_server(s: dict) -> ServerInfo:
    return ServerInfo(
        id=s["id"],
        name=s.get("name", ""),
        status=s.get("status", "unknown"),
        protocol=s.get("protocol", "openvpn"),
        port=s.get("port"),
        online_clients=s.get("online_clients", 0),
        org_ids=list(s.get("org_ids", [])),
    )


def _parse_org(o: dict) -> OrgInfo:
    return OrgInfo(id=o["id"], name=o.get("name", ""), user_count=o.get("user_count", 0))


def _parse_user(u: dict) -> UserInfo:
    return UserInfo(
        id=u["id"],
        name=u.get("name", ""),
        org_id=u.get("org_id", ""),
        org_name=u.get("org_name"),
        disabled=u.get("disabled", False),
        revoked=u.get("revoked", False),
        email=u.get("email"),
    )


def _parse_session(s: dict) -> SessionInfo:
    ts = s.get("connected_since")
    connected_since = None
    if ts:
        try:
            connected_since = datetime.fromisoformat(ts)
        except ValueError:
            connected_since = None
    return SessionInfo(
        user_id=s.get("user_id", ""),
        user_name=s.get("user_name", ""),
        server_id=s.get("server_id", ""),
        virtual_address=s.get("virtual_address"),
        real_address=s.get("real_address"),
        connected_since=connected_since,
        bytes_sent=s.get("bytes_sent", 0),
        bytes_received=s.get("bytes_received", 0),
    )

"""Mock Pritunl OSS node — stands in for a real node's HMAC REST shim.

Implements the same signed contract the real shim exposes, so the control
plane's multi-site behaviour is testable end-to-end without deploying actual
Pritunl/OpenVPN. State is in-memory and mutable, so create/disable/delete,
issue/revoke, and server start/stop are observable.

All /v1/* endpoints are HMAC-protected (see shim.hmac_auth). Config via env:
  MOCK_TOKEN, MOCK_SECRET   the node's HMAC credentials
  MOCK_NODE_NAME            label used in responses
  MOCK_FAIL                 if "1", force auth failures (to test 'degraded')
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from shim.hmac_auth import NonceCache, verify_request

TOKEN = os.environ.get("MOCK_TOKEN", "mock-token")
SECRET = os.environ.get("MOCK_SECRET", "mock-secret")
NODE_NAME = os.environ.get("MOCK_NODE_NAME", "mock-node")
FORCE_FAIL = os.environ.get("MOCK_FAIL", "0") == "1"
VERSION = "1.30.3-oss+shim0.1"

app = FastAPI(title=f"Mock Pritunl Node ({NODE_NAME})")
_nonces = NonceCache()


def _now() -> str:
    return datetime.now(UTC).isoformat()


# --- Seeded, mutable state ---------------------------------------------------
STATE = {
    "servers": [
        {"id": "srv-1", "name": f"{NODE_NAME}-vpn", "status": "online",
         "protocol": "openvpn", "port": 1194, "online_clients": 2, "org_ids": ["org-1"]},
    ],
    "orgs": [
        {"id": "org-1", "name": f"{NODE_NAME}-corp"},
    ],
    "users": [
        {"id": "usr-1", "name": "alice", "org_id": "org-1", "email": "alice@example.com",
         "disabled": False, "revoked": False, "has_profile": True},
        {"id": "usr-2", "name": "bob", "org_id": "org-1", "email": "bob@example.com",
         "disabled": False, "revoked": False, "has_profile": True},
    ],
    "sessions": [
        {"user_id": "usr-1", "user_name": "alice", "server_id": "srv-1",
         "virtual_address": "10.8.0.2", "real_address": "203.0.113.7",
         "connected_since": _now(), "bytes_sent": 1048576, "bytes_received": 5242880},
        {"user_id": "usr-2", "user_name": "bob", "server_id": "srv-1",
         "virtual_address": "10.8.0.3", "real_address": "198.51.100.4",
         "connected_since": _now(), "bytes_sent": 2097152, "bytes_received": 3145728},
    ],
}


def _org_name(org_id: str) -> str | None:
    return next((o["name"] for o in STATE["orgs"] if o["id"] == org_id), None)


def _find_user(user_id: str) -> dict | None:
    return next((u for u in STATE["users"] if u["id"] == user_id), None)


def _find_server(server_id: str) -> dict | None:
    return next((s for s in STATE["servers"] if s["id"] == server_id), None)


def _user_view(u: dict) -> dict:
    return {
        "id": u["id"], "name": u["name"], "org_id": u["org_id"],
        "org_name": _org_name(u["org_id"]), "email": u.get("email"),
        "disabled": u["disabled"], "revoked": u["revoked"],
    }


def _auth(request: Request, body: bytes) -> JSONResponse | None:
    if FORCE_FAIL:
        return JSONResponse({"error": "forced failure"}, status_code=401)
    if request.headers.get("Auth-Token") != TOKEN:
        return JSONResponse({"error": "unknown token"}, status_code=401)
    result = verify_request(
        secret=SECRET, method=request.method, path=request.url.path,
        headers=dict(request.headers), body=body, seen_nonce=_nonces,
    )
    if not result.ok:
        return JSONResponse({"error": result.error or "unauthorized"}, status_code=401)
    return None


# --- Liveness ----------------------------------------------------------------
@app.get("/")
def liveness() -> dict:
    return {"node": NODE_NAME, "status": "up"}


# --- Reads -------------------------------------------------------------------
@app.get("/v1/ping")
async def ping(request: Request):
    if (err := _auth(request, await request.body())) is not None:
        return err
    servers = STATE["servers"]
    return {
        "status": "ok", "node": NODE_NAME, "version": VERSION,
        "servers_total": len(servers),
        "servers_online": sum(1 for s in servers if s["status"] == "online"),
        "online_clients": sum(s["online_clients"] for s in servers),
    }


@app.get("/v1/state")
async def state(request: Request):
    if (err := _auth(request, await request.body())) is not None:
        return err
    orgs = [
        {**o, "user_count": sum(1 for u in STATE["users"] if u["org_id"] == o["id"])}
        for o in STATE["orgs"]
    ]
    return {"servers": STATE["servers"], "orgs": orgs, "users": [_user_view(u) for u in STATE["users"]]}


@app.get("/v1/sessions")
async def sessions(request: Request):
    if (err := _auth(request, await request.body())) is not None:
        return err
    # Only connected (non-disabled, non-revoked) users have live sessions.
    active_ids = {u["id"] for u in STATE["users"] if not u["disabled"] and not u["revoked"]}
    return {"sessions": [s for s in STATE["sessions"] if s["user_id"] in active_ids]}


# --- Mutations (Phase 3) -----------------------------------------------------
@app.post("/v1/orgs/{org_id}/users")
async def create_user(org_id: str, request: Request):
    body = await request.body()
    if (err := _auth(request, body)) is not None:
        return err
    if _org_name(org_id) is None:
        return JSONResponse({"error": "org not found"}, status_code=404)
    data = json.loads(body or b"{}")
    name = data.get("name")
    if not name:
        return JSONResponse({"error": "name required"}, status_code=400)
    user = {
        "id": f"usr-{uuid.uuid4().hex[:8]}", "name": name, "org_id": org_id,
        "email": data.get("email"), "disabled": False, "revoked": False, "has_profile": False,
    }
    STATE["users"].append(user)
    return JSONResponse(_user_view(user), status_code=201)


@app.post("/v1/users/{user_id}/disable")
async def set_disabled(user_id: str, request: Request):
    body = await request.body()
    if (err := _auth(request, body)) is not None:
        return err
    user = _find_user(user_id)
    if user is None:
        return JSONResponse({"error": "user not found"}, status_code=404)
    user["disabled"] = bool(json.loads(body or b"{}").get("disabled", True))
    return _user_view(user)


@app.delete("/v1/users/{user_id}")
async def delete_user(user_id: str, request: Request):
    if (err := _auth(request, await request.body())) is not None:
        return err
    user = _find_user(user_id)
    if user is None:
        return JSONResponse({"error": "user not found"}, status_code=404)
    STATE["users"].remove(user)
    STATE["sessions"] = [s for s in STATE["sessions"] if s["user_id"] != user_id]
    return JSONResponse({"status": "deleted", "id": user_id})


@app.post("/v1/users/{user_id}/profile")
async def issue_profile(user_id: str, request: Request):
    body = await request.body()
    if (err := _auth(request, body)) is not None:
        return err
    user = _find_user(user_id)
    if user is None:
        return JSONResponse({"error": "user not found"}, status_code=404)
    if user["revoked"]:
        return JSONResponse({"error": "user is revoked"}, status_code=409)
    user["has_profile"] = True
    fmt = json.loads(body or b"{}").get("fmt", "ovpn")
    profile = (
        f"# Pritunl profile ({fmt}) for {user['name']} @ {NODE_NAME}\n"
        f"client\ndev tun\nproto udp\nremote {NODE_NAME}.vpn.example 1194\n"
        f"# key-id {uuid.uuid4().hex}\n"
    )
    return PlainTextResponse(profile, media_type="application/x-openvpn-profile")


@app.post("/v1/users/{user_id}/revoke")
async def revoke_profile(user_id: str, request: Request):
    if (err := _auth(request, await request.body())) is not None:
        return err
    user = _find_user(user_id)
    if user is None:
        return JSONResponse({"error": "user not found"}, status_code=404)
    user["revoked"] = True
    user["has_profile"] = False
    STATE["sessions"] = [s for s in STATE["sessions"] if s["user_id"] != user_id]
    return _user_view(user)


@app.post("/v1/servers/{server_id}/state")
async def set_server_state(server_id: str, request: Request):
    body = await request.body()
    if (err := _auth(request, body)) is not None:
        return err
    server = _find_server(server_id)
    if server is None:
        return JSONResponse({"error": "server not found"}, status_code=404)
    action = json.loads(body or b"{}").get("action")
    if action not in {"start", "stop", "restart"}:
        return JSONResponse({"error": "action must be start|stop|restart"}, status_code=400)
    server["status"] = "offline" if action == "stop" else "online"
    if action == "stop":
        server["online_clients"] = 0
    return server

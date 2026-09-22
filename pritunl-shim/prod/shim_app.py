"""Production shim — drives a REAL Pritunl OSS node by reusing its Python modules.

Runs as a sidecar built FROM the node's Pritunl image, sharing its MongoDB. It
speaks the same HMAC contract as the mock, so Fleet's shim adapter works
unchanged, plus the richer server/user/org endpoints.

Zero extra dependencies: uses the Flask that ships in the Pritunl image, and the
stdlib-only shared HMAC module. See SHIM_DESIGN.md for the verified API map.
"""

from __future__ import annotations

import functools
import json
import os

import flask
from shim.hmac_auth import NonceCache, verify_request

TOKEN = os.environ.get("SHIM_TOKEN", "shim-token")
SECRET = os.environ.get("SHIM_SECRET", "shim-secret")
NODE_NAME = os.environ.get("SHIM_NODE_NAME", os.environ.get("HOSTNAME", "pritunl"))

app = flask.Flask(__name__)
_nonces = NonceCache()

# --- Pritunl runtime init (data ops only; no VPN runners) --------------------
from pritunl import setup  # noqa: E402

setup.setup_db()
setup.setup_settings()
import pritunl.poolers  # noqa: E402,F401  registers pooler types (avoids KeyError)
import pritunl.queues  # noqa: E402,F401  registers init_org_pooled / init_user
from bson import ObjectId  # noqa: E402
from pritunl import constants, organization, server  # noqa: E402

VERSION = getattr(constants, "VERSION", "unknown")


# --- Auth --------------------------------------------------------------------
def hmac_required(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if flask.request.headers.get("Auth-Token") != TOKEN:
            return flask.jsonify({"error": "unknown token"}), 401
        body = flask.request.get_data() or b""
        res = verify_request(
            secret=SECRET,
            method=flask.request.method,
            path=flask.request.path,
            headers=dict(flask.request.headers),
            body=body,
            seen_nonce=_nonces,
        )
        if not res.ok:
            return flask.jsonify({"error": res.error or "unauthorized"}), 401
        return fn(*args, **kwargs)

    return wrapper


def body_json() -> dict:
    try:
        return json.loads(flask.request.get_data() or b"{}")
    except ValueError:
        return {}


# --- Object -> JSON views (shape matches the mock contract) ------------------
def _org_view(o) -> dict:
    return {"id": str(o.id), "name": o.name, "user_count": getattr(o, "user_count", 0)}


def _user_view(o, u) -> dict:
    return {
        "id": str(u.id),
        "name": u.name,
        "org_id": str(o.id),
        "org_name": o.name,
        "email": getattr(u, "email", None),
        "disabled": bool(getattr(u, "disabled", False)),
        "revoked": bool(getattr(u, "disabled", False)),  # OSS has no separate revoke
    }


def _server_view(s) -> dict:
    return {
        "id": str(s.id),
        "name": s.name,
        "status": getattr(s, "status", "offline") or "offline",
        "protocol": getattr(s, "protocol", "openvpn") or "openvpn",
        "port": getattr(s, "port", None),
        "online_clients": len(getattr(s, "clients", None) or {}),
        "org_ids": [str(x) for x in (getattr(s, "organizations", None) or [])],
    }


def _find_user(user_id: str):
    """Return (org, user) for a user id, scanning orgs. None,None if absent."""
    oid = ObjectId(user_id)
    for o in organization.iter_orgs():
        try:
            u = o.get_user(oid)
        except Exception:  # noqa: BLE001
            u = None
        if u:
            return o, u
    return None, None


def _find_server(server_id: str):
    return server.get_by_id(ObjectId(server_id))


# --- Liveness ----------------------------------------------------------------
@app.get("/")
def liveness():
    return {"node": NODE_NAME, "status": "up"}


# --- Reads -------------------------------------------------------------------
@app.get("/v1/ping")
@hmac_required
def ping():
    servers = list(server.iter_servers())
    return {
        "status": "ok",
        "node": NODE_NAME,
        "version": VERSION,
        "servers_total": len(servers),
        "servers_online": sum(1 for s in servers if getattr(s, "status", None) == "online"),
        "online_clients": sum(len(getattr(s, "clients", None) or {}) for s in servers),
    }


@app.get("/v1/state")
@hmac_required
def state():
    orgs = list(organization.iter_orgs())
    users = []
    for o in orgs:
        for u in o.iter_users():
            users.append(_user_view(o, u))
    return {
        "servers": [_server_view(s) for s in server.iter_servers()],
        "orgs": [_org_view(o) for o in orgs],
        "users": users,
    }


@app.get("/v1/sessions")
@hmac_required
def sessions():
    out = []
    for s in server.iter_servers():
        for _cid, c in (getattr(s, "clients", None) or {}).items():
            out.append({
                "user_id": str(c.get("user_id", "")),
                "user_name": c.get("user_name", ""),
                "server_id": str(s.id),
                "virtual_address": c.get("virt_address"),
                "real_address": c.get("real_address"),
                "bytes_sent": c.get("bytes_sent", 0),
                "bytes_received": c.get("bytes_received", 0),
            })
    return {"sessions": out}


# --- Orgs --------------------------------------------------------------------
@app.post("/v1/orgs")
@hmac_required
def create_org():
    name = body_json().get("name")
    if not name:
        return flask.jsonify({"error": "name required"}), 400
    o = organization.new_org(name=name, type=constants.ORG_DEFAULT)
    return flask.jsonify(_org_view(o)), 201


@app.delete("/v1/orgs/<org_id>")
@hmac_required
def delete_org(org_id):
    o = organization.get_by_id(ObjectId(org_id))
    if not o:
        return flask.jsonify({"error": "org not found"}), 404
    o.remove()
    return flask.jsonify({"status": "deleted", "id": org_id})


# --- Users -------------------------------------------------------------------
@app.post("/v1/orgs/<org_id>/users")
@hmac_required
def create_user(org_id):
    o = organization.get_by_id(ObjectId(org_id))
    if not o:
        return flask.jsonify({"error": "org not found"}), 404
    data = body_json()
    name = data.get("name")
    if not name:
        return flask.jsonify({"error": "name required"}), 400
    u = o.new_user(name=name, email=data.get("email"), type=constants.CERT_CLIENT, pool=False)
    return flask.jsonify(_user_view(o, u)), 201


@app.post("/v1/users/<user_id>/disable")
@hmac_required
def set_disabled(user_id):
    o, u = _find_user(user_id)
    if not u:
        return flask.jsonify({"error": "user not found"}), 404
    u.disabled = bool(body_json().get("disabled", True))
    u.commit("disabled")
    return flask.jsonify(_user_view(o, u))


@app.post("/v1/users/<user_id>/revoke")
@hmac_required
def revoke(user_id):
    o, u = _find_user(user_id)
    if not u:
        return flask.jsonify({"error": "user not found"}), 404
    u.disabled = True  # OSS: revoking access == disabling the cert user
    u.commit("disabled")
    return flask.jsonify(_user_view(o, u))


@app.delete("/v1/users/<user_id>")
@hmac_required
def delete_user(user_id):
    o, u = _find_user(user_id)
    if not u:
        return flask.jsonify({"error": "user not found"}), 404
    u.remove()
    return flask.jsonify({"status": "deleted", "id": user_id})


@app.patch("/v1/users/<user_id>")
@hmac_required
def patch_user(user_id):
    """Per-user policy: pin, otp_auth, client_to_client, bypass, disabled, etc."""
    o, u = _find_user(user_id)
    if not u:
        return flask.jsonify({"error": "user not found"}), 404
    data = body_json()
    changed = []
    for field in ("pin", "otp_auth", "disabled", "email", "name", "client_to_client"):
        if field in data:
            setattr(u, field, data[field])
            changed.append(field)
    if data.get("reset_otp"):
        u.generate_otp_secret()
        changed.append("otp_secret")
    if changed:
        u.commit(changed)
    return flask.jsonify(_user_view(o, u))


@app.post("/v1/users/<user_id>/profile")
@hmac_required
def profile(user_id):
    o, u = _find_user(user_id)
    if not u:
        return flask.jsonify({"error": "user not found"}), 404
    fmt = body_json().get("fmt", "tar")
    if fmt == "keyurl":
        link = o.create_user_key_link(u.id)
        return flask.jsonify(link)
    if fmt == "ovpn":
        srv = next(iter(server.iter_servers()), None)
        if srv is not None:
            conf = u.build_key_conf(srv.id)
            data = conf["conf"] if isinstance(conf, dict) else conf
            return app.response_class(data, mimetype="application/x-openvpn-profile")
    # default / tar: full multi-server archive
    data = u.build_key_tar_archive()
    return app.response_class(data, mimetype="application/x-tar")


# --- Servers -----------------------------------------------------------------
_SERVER_FIELDS = (
    "name", "network", "port", "protocol", "dns_servers", "cipher", "hash",
    "inter_client", "restrict_routes", "otp_auth", "multi_device", "ipv6",
    "max_clients", "lzo_compression", "network_mode", "dh_param_bits", "search_domain",
)


@app.post("/v1/servers")
@hmac_required
def create_server():
    data = body_json()
    if not data.get("name"):
        return flask.jsonify({"error": "name required"}), 400
    kwargs = {k: data[k] for k in _SERVER_FIELDS if k in data}
    s = server.new_server(**kwargs)
    s.commit()
    return flask.jsonify(_server_view(s)), 201


@app.patch("/v1/servers/<server_id>")
@hmac_required
def patch_server(server_id):
    s = _find_server(server_id)
    if not s:
        return flask.jsonify({"error": "server not found"}), 404
    data = body_json()
    changed = [k for k in _SERVER_FIELDS if k in data]
    for k in changed:
        setattr(s, k, data[k])
    if changed:
        s.commit(changed)
    return flask.jsonify(_server_view(s))


@app.delete("/v1/servers/<server_id>")
@hmac_required
def delete_server(server_id):
    s = _find_server(server_id)
    if not s:
        return flask.jsonify({"error": "server not found"}), 404
    if getattr(s, "status", None) == "online":
        try:
            s.stop()
        except Exception:  # noqa: BLE001
            pass
    s.remove()
    return flask.jsonify({"status": "deleted", "id": server_id})


@app.post("/v1/servers/<server_id>/routes")
@hmac_required
def add_route(server_id):
    s = _find_server(server_id)
    if not s:
        return flask.jsonify({"error": "server not found"}), 404
    data = body_json()
    net = data.get("network")
    if not net:
        return flask.jsonify({"error": "network required"}), 400
    try:
        s.upsert_route(
            net, data.get("nat", True), None, None,
            data.get("advertise", False), None, None, False,
            data.get("comment"), None,
        )
    except Exception as exc:  # noqa: BLE001 — surface pritunl route validation
        return flask.jsonify({"error": f"add route failed: {exc}"}), 400
    s.commit()
    return flask.jsonify(_server_view(s))


@app.delete("/v1/servers/<server_id>/routes")
@hmac_required
def remove_route(server_id):
    s = _find_server(server_id)
    if not s:
        return flask.jsonify({"error": "server not found"}), 404
    s.remove_route(body_json().get("network"))
    s.commit()
    return flask.jsonify(_server_view(s))


@app.post("/v1/servers/<server_id>/orgs/<org_id>")
@hmac_required
def attach_org(server_id, org_id):
    s = _find_server(server_id)
    if not s:
        return flask.jsonify({"error": "server not found"}), 404
    s.add_org(org_id)  # pritunl stores org ids as strings
    s.commit()
    return flask.jsonify(_server_view(s))


@app.delete("/v1/servers/<server_id>/orgs/<org_id>")
@hmac_required
def detach_org(server_id, org_id):
    s = _find_server(server_id)
    if not s:
        return flask.jsonify({"error": "server not found"}), 404
    s.remove_org(org_id)
    s.commit()
    return flask.jsonify(_server_view(s))


@app.post("/v1/servers/<server_id>/state")
@hmac_required
def server_state(server_id):
    s = _find_server(server_id)
    if not s:
        return flask.jsonify({"error": "server not found"}), 404
    action = body_json().get("action")
    if action not in ("start", "stop", "restart"):
        return flask.jsonify({"error": "action must be start|stop|restart"}), 400
    try:
        getattr(s, action)()
    except Exception as exc:  # noqa: BLE001 — lab has no tun; surface the reason
        return flask.jsonify({"error": f"{action} failed: {exc}"}), 502
    return flask.jsonify(_server_view(_find_server(server_id)))


if __name__ == "__main__":
    port = int(os.environ.get("SHIM_PORT", "9800"))
    app.run(host="0.0.0.0", port=port, threaded=True)

# Production shim — design

The mock node (`mock/`) implements the wire contract. The **production shim** is
a sidecar that speaks the same HMAC contract but drives a **real Pritunl OSS**
node by reusing Pritunl's own Python modules. This doc pins the exact API surface
(verified against Pritunl **1.32.3897.75**, Python 3.11) so the build is precise.

## Packaging (Docker/compose substrate)

- Build the shim image **`FROM` the same Pritunl image** the node runs. This
  guarantees version parity (the shim's module calls match the node's schema and
  cert logic exactly) and gives the shim Pritunl's Python + deps for free.
- Run it as a **sidecar** on the node's compose project, sharing:
  - the **MongoDB** (same `PRITUNL_MONGODB_URI` / conf), and
  - the network namespace / conf dir as needed.
- The sidecar runs a small ASGI app (uvicorn) exposing the HMAC REST on an
  internal port; it does **not** start VPN runners.

## Boot / init (connect to the node's datastore, no VPN)

```python
from pritunl import setup, settings
setup.setup_db()        # -> setup_mongo(): connects to the shared MongoDB
setup.setup_settings()  # loads settings from the DB
# NOTE: do NOT call setup_all() — it boots runners/servers. We only want data ops.
```

Mongo URI comes from the node's conf / `PRITUNL_MONGODB_URI`.

## API surface (verified module map)

### Organizations — `pritunl.organization`
- `utils.new_org(name=..., type=ORG_DEFAULT)` → create
- `utils.get_by_id(id)`, `utils.iter_orgs()`
- `org.dict()`, `org.user_count`, `org.commit()`, `org.remove()`
- `org.new_user(name=..., type=CERT_CLIENT, ...)` → create user in org
- `org.get_user(id)`, `org.find_user(name=...)`, `org.iter_users(page=, search=)`
- `org.create_user_key_link(user_id, one_time=False)` → temporary key/profile URL

### Users — `pritunl.user`
- Profile/cert generation (the crux — real PKI):
  - `user.build_key_conf(server_id)` → single `.ovpn` for a server
  - `user.build_key_tar_archive()` / `user.build_key_zip_archive()` → all-servers bundle
- `user.generate_otp_secret()` + `user.otp_secret` → per-user OTP/2FA
- Disable = set `user.disabled = True` then `user.commit()`
- `user.remove()`, `user.commit()`
- PIN and bypass flags are user fields (`pin`, `otp_auth`, `bypass_secondary`, …) committed via `commit()`

### Servers — `pritunl.server`
- `utils.new_server(name=, network=, port=, protocol=, ...)` → create
- `utils.get_by_id(id)`, `utils.iter_servers()` / `iter_servers_dict()`
- `server.add_route(network, ...)`, `server.remove_route(network)`
- `server.add_org(org_id)`, `server.remove_org(org_id)`
- `server.start()`, `server.stop()`, `server.restart()`
- `server.commit()`, `server.remove()`
- Config fields (set then `commit()`): network, port, protocol, dns_servers,
  cipher, hash, inter_client, restrict_routes, otp_auth, ipv6, multi_device, …

### SSO admin session — `pritunl.auth.administrator`
- `get_by_username(username)` → Administrator
- `admin.new_session()` → session id; set cookie `session=<id>` and `302 /`
  for one-click login into the node's native admin (OSS has no native SSO).
- `check_session(csrf_check)` for validation reference.

## Endpoints the shim exposes (superset of the mock contract)

Existing (parity with mock): `/v1/ping`, `/v1/state`, `/v1/sessions`,
`POST /v1/orgs/{org}/users`, `/v1/users/{id}/disable|revoke|profile`,
`DELETE /v1/users/{id}`, `/v1/servers/{id}/state`.

New (this expansion):
- Orgs: `GET/POST /v1/orgs`, `DELETE /v1/orgs/{id}`
- Servers: `POST /v1/servers` (create), `PATCH /v1/servers/{id}` (settings),
  `DELETE /v1/servers/{id}`, `POST /v1/servers/{id}/routes`,
  `DELETE /v1/servers/{id}/routes`, `POST/DELETE /v1/servers/{id}/orgs/{org}`
- Users: `PATCH /v1/users/{id}` (policy: routes/gateway/bandwidth/expiry/pin),
  `POST /v1/users/{id}/otp` (enable/reset 2FA), `GET /v1/users/{id}/profile?fmt=ovpn|tar|keyurl`
- SSO: `GET /v1/sso` → 302 with admin session cookie

All under the shared HMAC scheme (`shim/hmac_auth.py`); nonce + skew enforced.

## Build order

E2 core parity → E3 server settings/routes → E4 user depth/orgs/OTP →
E5 profile delivery + failover → E6 SSO. Each verified against a real Pritunl +
Mongo brought up in the compose lab (`profile: real`).

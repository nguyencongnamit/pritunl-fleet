# Architecture

Pritunl Fleet is a control plane that manages **N independent Pritunl OSS
servers** across sites/regions from one place. It never talks to a node
directly — every interaction goes through a pluggable **`NodeAdapter`**, so the
access method is a per-node config choice, not a code dependency.

## Component map

```
                         ┌───────────────────────────────────────────────┐
   Browser (React SPA) ─▶│                Control Plane (FastAPI)          │
   MFA login, RBAC UI    │                                                 │
                         │  api/routes  →  services  →  adapters           │
                         │  auth · nodes · dashboard · actions ·           │
                         │  provisioning · principals                      │
                         │                                                 │
                         │  health loop (30s) · sync loop (60s)            │
                         └───────┬───────────────────────┬─────────────────┘
                                 │                        │  NodeAdapter (per call)
                          ┌──────▼──────┐         ┌───────┴────────┬──────────┐
                          │ PostgreSQL  │         │ shim (default) │ mongo/ssh│
                          │ registry,   │         │ HMAC REST      │ (stubs)  │
                          │ audit, RBAC,│         └───────┬────────┴────┬─────┘
                          │ placements  │                 │             │
                          └─────────────┘        ┌────────▼───┐   ┌─────▼──────┐
                                                  │ Node: HCMC │   │ Node: SG   │
                                                  │ OpenVPN +  │   │ OpenVPN +  │
                                                  │ HMAC shim  │   │ HMAC shim  │
                                                  └────────────┘   └────────────┘
```

## Layering (control-plane/app)

- **api/routes/** — HTTP surface. Thin; delegates to services. `api/deps.py`
  holds the DB-session dependency and `rbac_guard` (attached to every `/api/v1`
  router).
- **services/** — business logic: `nodes` (registry + adapter build), `health`,
  `dashboard` (cross-site aggregation), `audit` (hash chain), `provisioning`,
  `sync` (drift), `auth` (JWT/MFA/bootstrap).
- **adapters/** — `NodeAdapter` ABC + `shim` (default), `mongo`/`ssh` (stubs),
  `factory` (resolve by type).
- **models/** — SQLAlchemy: `node`, `audit`, `provisioning`
  (LogicalUser/UserPlacement), `identity` (Principal/RoleBinding).
- **crypto/** — `envelope` (node-credential sealing), `passwords` (argon2).
- **schemas/** — Pydantic request/response models. Credentials are write-only.

## The NodeAdapter contract

One instance per node call; all methods async so N nodes sweep concurrently.

| Method | Phase | Notes |
|---|---|---|
| `health()` | 1 | cheap liveness + facts, never mutates |
| `get_state / list_servers / list_orgs / list_users / list_sessions` | 2 | reads |
| `create_user / set_user_disabled / delete_user` | 3 | user lifecycle |
| `issue_profile / revoke_profile` | 3 | key/profile lifecycle |
| `set_server_state` | 3 | start/stop/restart |

Only `health()` is abstract; the rest default to `NotImplementedError`, so
adapters fill capability incrementally. Route `_read`/`_perform` helpers map
`NotImplementedError` → HTTP 501 and `AdapterError` → 502.

### Adapters and why the shim is default

See the README "Adapter trade-offs" table. Summary: mutations in Pritunl are not
DB writes (they drive PKI, OpenVPN config, process reload), so only the **shim**
— which calls Pritunl's own Python modules behind an HMAC check — is safe for
mutations, has the smallest attack surface, and maps 1:1 onto the eventual
Enterprise HMAC API. `mongo` is a read-only fast path; `ssh` is bootstrap/
break-glass. Switch via a node's `adapter_type` field.

### HMAC scheme (`pritunl-shim/shim/hmac_auth.py`)

Single shared source of truth used by both the client adapter (sign) and the
node shim/mock (verify). Signed string:
`token & timestamp & nonce & METHOD & path & sha256(body)`; signature is
`base64(HMAC-SHA256(secret, signed))`. Enforces timestamp skew + single-use
nonces (replay protection). Mirrors Pritunl's native `Auth-*` headers.

## Production shim (v1.1.0)

The `shim` adapter talks to a **production shim** running beside each real
Pritunl node: a sidecar built `FROM` the node's own Pritunl image (guaranteeing
version parity), sharing its MongoDB. On boot it does `setup.setup_db()` +
`setup.setup_settings()` and imports `pritunl.queues`/`pritunl.poolers` so it can
call Pritunl's own `organization`/`user`/`server` classes — including **real
certificate/profile generation** — without running the VPN itself. It exposes the
same HMAC contract as the mock, plus orgs/policy/bulk/profile endpoints. See
[`pritunl-shim/SHIM_DESIGN.md`](./pritunl-shim/SHIM_DESIGN.md).

**Orchestration vs host-coupled boundary.** Cross-site user/org/profile/cert/
policy operations run through the shim. Operations coupled to Pritunl's running
host (server network locks, CA regen on org-attach) are **not** reimplemented in
the sidecar — the shim returns `409 host_coupled` and the console routes the
operator to the node's native admin via the one-click deep-link. This keeps Fleet
decoupled from Pritunl's internal host/runner/lock machinery (version-robust).

## Data model (PostgreSQL)

- `nodes` — registry: endpoint, region, adapter_type, verify_tls, enabled,
  `credentials_enc` (envelope-sealed), health fields (status, last_checked_at,
  last_synced_at, consecutive_failures, last_error).
- `audit_log` — append-only hash chain (`prev_hash`, `entry_hash`); who/what/
  site/target/result/params; verified by recomputing the chain.
- `logical_users` + `user_placements` — cross-site provisioning: one identity →
  many sites, each placement tracks `remote_user_id` + status
  (pending/active/failed/revoked/missing).
- `principals` + `role_bindings` — control-plane accounts: argon2 password,
  sealed TOTP secret, `global_role`, and per-node role overrides.

Phase 1 uses `create_all()` for zero-step lab startup; Alembic replaces this for
real deployments (see Roadmap).

## Security model

- **AuthN** — two-step, MFA mandatory. `login` (password) → step token
  (`mfa` or `enroll`) → `mfa/verify` (TOTP) → full session token. Only
  full-scope JWTs are accepted by the API.
- **AuthZ** — `rbac_guard` on every `/api/v1` router. Role by method + route:
  GET→viewer, mutations→operator (scoped to `node_id` when present), node
  registry + `/principals`→admin. Effective role = max(global, per-node binding).
- **Secrets at rest** — node credentials sealed with envelope encryption
  (per-record AES-256-GCM DEK wrapped by the master KEK from `FLEET_MASTER_KEY`).
  TOTP secrets sealed the same way. Passwords argon2id. Nothing secret is
  returned by the API or logged.
- **Tamper-evident audit** — hash-chained; any historical edit is detected by
  `GET /api/v1/audit/verify` (proven: editing a row → `broken_at`).
- **Transport** — `FLEET_VERIFY_NODE_TLS=true` by default (false only for the
  plain-HTTP mock lab). Security headers middleware; same-origin SPA (no CORS).

## Background loops

- **Health loop** (`FLEET_HEALTH_SWEEP_INTERVAL`, default 30s) — probes every
  enabled node, applies the consecutive-failure threshold (degraded vs down).
- **Sync loop** (`FLEET_SYNC_SWEEP_INTERVAL`, default 60s) — reconciles tracked
  placements against live node users; classifies present / missing / untracked.

## Deployment

Single container serves the built SPA (FastAPI `StaticFiles` at `/`) and the API
(`/api/v1`) on one port. `docker-compose.yml` runs control plane + Postgres +
two mock nodes. For public exposure, front the control-plane port with any
reverse proxy or tunnel that terminates TLS; the app enforces MFA + RBAC behind
it.

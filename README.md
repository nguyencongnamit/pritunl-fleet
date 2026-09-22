# Pritunl Fleet — Control Plane for Pritunl OSS

[![CI](https://github.com/nguyencongnamit/pritunl-fleet/actions/workflows/ci.yml/badge.svg)](https://github.com/nguyencongnamit/pritunl-fleet/actions/workflows/ci.yml)
[![CodeQL](https://github.com/nguyencongnamit/pritunl-fleet/actions/workflows/codeql.yml/badge.svg)](https://github.com/nguyencongnamit/pritunl-fleet/actions/workflows/codeql.yml)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/nguyencongnamit/pritunl-fleet/badge)](https://scorecard.dev/viewer/?uri=github.com/nguyencongnamit/pritunl-fleet)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Latest release](https://img.shields.io/github/v/release/nguyencongnamit/pritunl-fleet?sort=semver)](https://github.com/nguyencongnamit/pritunl-fleet/releases)

A single pane of glass to manage **N independent Pritunl Open Source servers**
across multiple sites/regions (e.g. DN, HCMC, SG), each with its own MongoDB and
OpenVPN/WireGuard instances — with **MFA + RBAC**, a **tamper-evident audit
log**, **cross-site provisioning**, and **drift detection**, all behind a
pluggable `NodeAdapter`.

Pritunl's HMAC token/secret REST API is an **Enterprise** feature, so this
control plane reaches each OSS node through a pluggable **`NodeAdapter`** and
ships an OSS-viable default that does not require a license.

> **🚀 v1.2.0 — manages real Pritunl OSS nodes.** A production **shim**
> (sidecar built from the node's Pritunl image) drives an actual node end-to-end:
> orgs (with a management UI), users, **real client-certificate generation**,
> server lifecycle, per-user PIN/OTP, bulk create + bulk actions, email profile
> delivery, and one-click "Open admin" — all behind MFA + RBAC + a tamper-evident
> audit log, with Alembic-managed schema. Verified against Pritunl 1.32.
> See [`pritunl-shim/SHIM_DESIGN.md`](./pritunl-shim/SHIM_DESIGN.md).
>
> v1.0.0 delivered the full control plane (registry, dashboard, mutations, audit,
> cross-site provisioning, sync, RBAC, MFA) against mock nodes.
>
> **Independent project.** "Pritunl" is a trademark of its respective owner.
> Pritunl Fleet is a community project, **not affiliated with or endorsed by**
> the Pritunl project.

---

## Architecture

```
                       ┌─────────────────────────────────────────┐
                       │            Control Plane (FastAPI)        │
   React + shadcn ───▶ │  API  ·  Registry  ·  Health engine       │
   (Phase 2 UI)        │  RBAC/MFA (P5) · Audit log (P3) · Sync(P4)│
                       └───────┬───────────────┬───────────────────┘
                               │               │
                        ┌──────▼─────┐   NodeAdapter (per node, per call)
                        │ PostgreSQL │   ┌───────┬────────┬──────┐
                        │ registry   │   │ shim  │ mongo  │ ssh  │
                        │ audit/RBAC │   │(deflt)│(ro RO) │(b-gl)│
                        └────────────┘   └───┬───┴───┬────┴──┬───┘
                                             │       │       │
             ┌───────────────────────────────┼───────┼───────┼─────────────┐
             ▼                                ▼       ▼       ▼             ▼
   ┌───────────────────┐            ┌───────────────────┐   ...   ┌──────────────────┐
   │  Pritunl node DN  │            │  Pritunl node SG  │         │  Pritunl node …  │
   │  OpenVPN + Mongo  │            │  OpenVPN + Mongo  │         │  OpenVPN + Mongo │
   │  + HMAC REST shim │            │  + HMAC REST shim │         │  + HMAC REST shim│
   └───────────────────┘            └───────────────────┘         └──────────────────┘
```

The control plane **never** talks to a node directly — every call goes through a
`NodeAdapter`, chosen per node in the registry. Switching a site's access method
is a config edit, not a code change.

---

## Adapter trade-offs

The critical distinction is **reads vs. mutations**. Creating a user, issuing or
revoking a key, or starting a server in Pritunl is *not* a database write — it
triggers Pritunl's internal PKI (cert gen/revocation), writes OpenVPN configs,
reloads the server process, and updates iptables. Any method that bypasses
Pritunl's own code paths for mutations silently produces broken state.

| Dimension | (a) Direct MongoDB | (b) SSH + CLI | (c) API shim *(default)* |
|---|---|---|---|
| Reads (dashboard/sync) | Excellent — aggregate queries | Brittle stdout parsing | Structured JSON |
| **Mutations** | **Dangerous** — bypasses PKI/config/reload | Stock CLI lacks org/user/key lifecycle | Correct — calls Pritunl's own modules |
| Attack surface | Mongo reachable across sites | Privileged SSH key per host | One HTTPS port, HMAC, cert-verified |
| Version coupling | Couples to Mongo schema | Couples to CLI output | Calls functions, not tables — most stable |
| Node deploy effort | None | None | Custom image/plugin (containerized) |
| Swap to Enterprise API | Total rewrite | Total rewrite | Near-free — shim mirrors the HMAC scheme |

**Decision:** the three are **complementary**, not rivals:

- **`shim` (default)** — the workhorse for all mutations *and* reads. Mirrors
  Pritunl's native `Auth-Token` / `Auth-Timestamp` / `Auth-Nonce` /
  `Auth-Signature` HMAC-SHA256 scheme, so migrating to the licensed Enterprise
  API later needs no call-site changes.
- **`mongo` (stub)** — optional **read-only** fast path for dashboard/sync.
  Never mutates.
- **`ssh` (stub)** — **bootstrap / break-glass**: install the shim, restart
  services, disaster recovery.

### Switching adapters

Per node, set `adapter_type` to `shim | mongo | ssh` (and supply matching
`credentials`). `app/adapters/factory.py` resolves the class; nothing else
changes. See the credential shapes documented at the top of each adapter in
`control-plane/app/adapters/`.

---

## Repository layout

```
pritunl-fleet/
├── control-plane/                 # FastAPI backend
│   └── app/
│       ├── config.py              # env-driven settings
│       ├── db.py                  # SQLAlchemy engine/session
│       ├── models/node.py         # node registry table
│       ├── schemas/node.py        # API models (credentials are write-only)
│       ├── crypto/envelope.py     # envelope encryption of node creds
│       ├── adapters/              # NodeAdapter interface + shim/mongo/ssh
│       ├── services/              # registry CRUD + health engine
│       └── api/routes/            # /healthz, /api/v1/nodes
├── pritunl-shim/
│   ├── shim/hmac_auth.py          # shared HMAC scheme (adapter + node agree)
│   └── mock/                      # mock Pritunl node for the lab
├── frontend/                      # React + shadcn/ui (Phase 2)
├── scripts/smoke_test.sh          # end-to-end Phase-1 check
└── docker-compose.yml             # control plane + Postgres + 2 mock nodes
```

---

## Quick start (test lab)

```bash
cp .env.example .env          # dev master key is auto-derived; edit for non-dev
docker compose up -d --build  # control plane + Postgres + node-hcmc + node-sg
./scripts/smoke_test.sh       # register both nodes and health-check them
```

Expected: both nodes register and report `status=reachable` with a version and
server/client counts pulled through the signed shim contract. The background
health loop then re-probes every `FLEET_HEALTH_SWEEP_INTERVAL` seconds.

API docs: <http://localhost:8200/docs> (host port 8200 → container 8080).

To see failure handling, set `MOCK_FAIL=1` on a node in `docker-compose.yml` and
re-run — that node moves to `degraded`, then `down` after
`FLEET_HEALTH_DOWN_THRESHOLD` consecutive failures.

---

## Security notes

- **Credentials at rest:** node secrets are sealed with **envelope encryption**
  (per-record AES-256-GCM data key wrapped by a master KEK). The master key
  comes from `FLEET_MASTER_KEY` (env/secret store); a fixed dev key is used only
  when `FLEET_ENVIRONMENT=dev` and no key is set. Swapping to AWS KMS / Vault /
  age later means replacing only the DEK wrap/unwrap.
- **Never echoed, never logged:** `credentials` is write-only in the API — no
  response model contains it, and it is not written to logs.
- **TLS by default:** `FLEET_VERIFY_NODE_TLS=true` verifies node certs; it is set
  to `false` only for the plain-HTTP mock lab.
- **Least privilege per adapter** (documented in each adapter file): `shim` needs
  only a token/secret over HTTPS; `mongo` needs a **read-only** Mongo user over
  mTLS/tunnel; `ssh` needs a key-only account restricted by forced-command.
- **Replay protection:** the HMAC scheme signs method + path + body hash, with
  timestamp-skew checks and single-use nonces.

### Next up

Alembic migrations (replacing the lab-only `create_all`), the production shim
blueprint, and the `mongo`/`ssh` adapters. See [ROADMAP.md](./ROADMAP.md).

---

## Build order (all complete)

| Phase | Scope | State |
|---|---|---|
| 1 | Scaffold · `NodeAdapter` · registry · health check | ✅ done |
| 2 | Default adapter reads · user/org read · dashboard | ✅ done |
| 3 | Mutations (user/key/server) · audit log | ✅ done |
| 4 | Cross-site provisioning · sync engine | ✅ done |
| 5 | RBAC · MFA · secrets hardening | ✅ done |

## Documentation

- [ARCHITECTURE.md](./ARCHITECTURE.md) — system design, adapters, data & security model
- [ROADMAP.md](./ROADMAP.md) — backlog and direction
- [CONTRIBUTING.md](./CONTRIBUTING.md) · [SECURITY.md](./SECURITY.md) · [CHANGELOG.md](./CHANGELOG.md)

## License

[MIT](./LICENSE) © Pritunl Fleet contributors

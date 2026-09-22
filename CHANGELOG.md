# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.0] - 2026-09-22

### Added
- **Orgs management UI** — pick a node, create/delete orgs, and bulk-add users.
- **Bulk user actions** — multi-select users on the Users page and disable /
  enable / revoke / delete across their sites in one action.
- **Alembic migrations** with safe auto-adopt (replaces `create_all`): fresh DBs
  upgrade to head; existing DBs are stamped without recreating.

### Fixed
- "Open admin" now appears only for nodes that have an `admin_url` set (surfaced
  on the node list), removing the error on mock/plain nodes.

[1.2.0]: https://github.com/nguyencongnamit/pritunl-fleet/releases/tag/v1.2.0

## [1.1.0] - 2026-09-22

Real Pritunl node management — the control plane now drives an actual Pritunl OSS
node end-to-end, not just mock nodes.

### Added

- **Production shim** — a sidecar built `FROM` the node's Pritunl image that
  reuses Pritunl's own Python modules over the shared HMAC contract (zero extra
  deps; uses the image's Flask). Verified against Pritunl 1.32: orgs, users,
  **real client-certificate/profile generation**, server create/delete/routes.
- **Real-node lab** (`docker-compose.real.yml`) — MongoDB + Pritunl + shim, for
  building/verifying against a genuine node.
- **Orgs management** and **per-user policy** (PIN, OTP/2FA) through the console.
- **Bulk user ops** — bulk create and bulk disable/enable/revoke/delete.
- **Profile delivery** — email a client profile via Resend (config-gated).
- **One-click "Open admin"** — deep-link into each node's native Pritunl admin.
- **Login + MFA rate limiting** — per username+IP lockout against guessing.

### Notes

- Architecture boundary: the shim owns cross-site orchestration; host-coupled
  network config (routes/attach on a running server) is delegated to the node's
  native admin and returns a clear `409 host_coupled` from the shim.
- Auto-login SSO is documented as an advanced same-origin-HTTPS opt-in (Pritunl
  OSS has no native SSO); the shipped path is the deep-link.

[1.1.0]: https://github.com/nguyencongnamit/pritunl-fleet/releases/tag/v1.1.0

## [1.0.0] - 2026-09-22

Initial public release.

### Added

- **NodeAdapter abstraction** — a common async interface over three OSS-viable
  access methods; `shim` (HMAC REST, default) implemented, `mongo` (read-only)
  and `ssh` (break-glass) as documented stubs. Selected per node via config.
- **Shared HMAC scheme** mirroring Pritunl's `Auth-Token/Timestamp/Nonce/
  Signature`, with timestamp-skew and single-use-nonce replay protection.
- **Node registry** with periodic health checks (reachable / degraded / down)
  and a per-node consecutive-failure threshold.
- **Unified dashboard** — per-site status plus aggregate totals across all sites,
  and cross-site user search.
- **User / org / key & profile lifecycle** — create/disable/delete users, issue
  and revoke client profiles, start/stop/restart servers.
- **Cross-site provisioning** — issue one logical user to multiple sites in one
  action, tracking placement per site.
- **Sync engine** — reconciles control-plane state with each node and surfaces
  drift (present / missing / untracked).
- **Tamper-evident audit log** — append-only hash chain over every mutation,
  with on-demand chain verification.
- **Control-plane auth** — mandatory TOTP MFA and RBAC (viewer / operator /
  admin, scoped per site).
- **Secrets at rest** — node credentials sealed with envelope encryption
  (per-record AES-256-GCM DEK wrapped by a master KEK); argon2 passwords.
- **docker-compose test lab** — control plane + PostgreSQL + two mock Pritunl
  nodes for end-to-end multi-site testing, plus a smoke-test script.

[1.0.0]: https://github.com/nguyencongnamit/pritunl-fleet/releases/tag/v1.0.0

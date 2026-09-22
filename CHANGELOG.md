# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

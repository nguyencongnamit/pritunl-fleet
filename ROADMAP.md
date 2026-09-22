# Roadmap & backlog

The five build phases are done (see the build-order table in the README). This is
what comes next, ordered by leverage. Checkboxes track intent, not commitment.

## Next up (highest leverage)

- [ ] **Real shim blueprint** — the production `pritunl-shim` that patches an OSS
      Pritunl node: a Flask blueprint reusing `pritunl.organization` /
      `pritunl.user` / `pritunl.server`, guarded by the shared HMAC module.
      Ship as a small overlay image so `mongo`/`ssh` stay stubs by choice.
- [ ] **Alembic migrations** — replace `create_all()`; versioned schema for real
      deployments and upgrades.
- [ ] **Mongo read adapter** — implement the read-only fast path (motor, TLS,
      short serverSelectionTimeout) to accelerate dashboard/sync on large fleets.
- [ ] **SSH break-glass adapter** — asyncssh with strict host-key checking +
      forced-command; used to install/upgrade the shim and restart services.
- [ ] **Login rate-limiting + lockout** — per-principal + per-IP throttle on
      `/auth/login` and `/auth/mfa/verify`.

## Reliability & scale

- [ ] Audit append under a row lock (or an append queue) for multi-instance HA.
- [ ] Cache last-known node state so the dashboard degrades gracefully when a
      node is briefly unreachable (currently zeros with an error note).
- [ ] Backoff + jitter on the health/sync loops; per-node circuit breaker.
- [ ] Pagination + server-side filtering on `/users` and `/audit` for big fleets.
- [ ] WireGuard parity checks across all adapter methods.

## Security hardening

- [ ] Move envelope KEK to a real KMS/Vault/age backend (only `wrap/unwrap`
      changes — the record format is stable).
- [ ] Recovery codes for MFA; optional WebAuthn/passkeys.
- [ ] Session revocation list / short full-token TTL + refresh.
- [ ] Export the audit chain to an external WORM store; periodic notarization.
- [ ] Per-node credential rotation workflow + audit.
- [ ] Content-Security-Policy header for the SPA.

## Product / UX

- [ ] Node detail page (servers, orgs, routes, sessions, per-node audit).
- [ ] Bandwidth/session history charts (connect/disconnect timeline, per-user
      transfer) — use the dataviz system for the charts.
- [ ] Bulk actions (multi-select disable/revoke, bulk provision from CSV).
- [ ] Route editing + org attach/detach from the UI.
- [ ] Drift auto-remediation ("re-create missing", "adopt untracked").
- [ ] QR code for MFA enrollment (currently secret + otpauth URI as text).

## Ideas / stretch (the "why this matters" bets)

- **Fleet-wide policy engine** — declare desired state (which identities on which
  sites, which routes) and let the sync engine converge to it (GitOps for VPN).
- **Multi-tenant** — org boundaries in the control plane itself, so an MSP can
  run one control plane over many customers' Pritunl fleets.
- **SCIM / IdP sync** — provision/deprovision logical users from Okta/Entra;
  cross-site placement driven by group membership.
- **Anomaly detection** on session/audit streams (impossible travel, off-hours
  admin actions) feeding the audit view.
- **Cost/usage reporting** per site and per identity.
- **Adapter marketplace** — the `NodeAdapter` interface is the extension point;
  community adapters for other VPN backends.

## Positioning

OSS control planes for self-hosted VPN fleets are thin on the ground, and
Pritunl's own multi-server management is gated behind Enterprise. The wedge is:
**OSS-viable multi-site management with real RBAC + MFA + a tamper-evident audit
trail**, adapter-abstracted so it can later ride Pritunl's licensed API or other
backends without rework.

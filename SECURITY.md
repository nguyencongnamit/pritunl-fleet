# Security Policy

Pritunl Fleet runs privileged access to VPN infrastructure, so we take security
reports seriously and appreciate coordinated disclosure.

## Reporting a vulnerability

**Please do not open a public issue for security vulnerabilities.**

Report privately via **GitHub Security Advisories** — the **"Report a
vulnerability"** button on the repository's **Security** tab. Include the
affected version/commit, reproduction steps, and impact. We aim to acknowledge
within 72 hours and to coordinate a fix and disclosure timeline with you.

## Supported versions

The latest released `vX.Y.Z` is supported. Older versions receive fixes at
maintainer discretion.

## Scope

In scope: the control-plane API and web app, the `NodeAdapter` implementations,
the HMAC auth scheme, the envelope-encryption of node credentials, the
authentication/RBAC/MFA logic, and the tamper-evident audit log.

Out of scope: issues that require an already-compromised control-plane host or
database, or physical access — unless they bypass a documented security boundary
(credential-at-rest encryption, RBAC, MFA, or audit-chain integrity).

## Handling credentials responsibly

- Never paste real node credentials, master keys, JWT secrets, or `.env`
  contents into an issue, PR, or advisory.
- The repository ships **no** secrets; all secrets are supplied at runtime via
  environment/secret store (see `.env.example`).

"""SSH adapter (STUB) — bootstrap / break-glass access over SSH + pritunl CLI.

Role: the operations the other adapters can't do — installing/updating the
shim, restarting the Pritunl service, and disaster recovery — plus a coarse
liveness check. The stock Pritunl CLI does NOT cover full org/user/key
lifecycle, so this adapter is intentionally NOT the path for routine
provisioning; that belongs to the shim adapter.

Least-privilege requirement: a dedicated, key-only SSH account restricted (via
forced-command / sudoers allowlist) to the specific `pritunl` and service
commands it needs. The private key is the crown jewel — store it encrypted at
rest and separate from routine operator credentials.

Credentials dict shape:
  {"host": "vpn-sg.internal", "port": 22, "username": "fleet",
   "private_key": "<PEM>", "known_hosts": "<host key line>"}

Only health() is stubbed in Phase 1.
"""

from __future__ import annotations

from app.adapters.base import AdapterError, NodeAdapter, NodeHealth, Reachability


class SSHAdapter(NodeAdapter):
    adapter_type = "ssh"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        creds = self._credentials or {}
        self._host = creds.get("host")
        self._private_key = creds.get("private_key")
        if not self._host or not self._private_key:
            raise AdapterError("ssh adapter requires 'host' and 'private_key' credentials")

    async def health(self) -> NodeHealth:
        # Stub: a real implementation opens an asyncssh connection with strict
        # host-key checking and runs `pritunl version` (or `systemctl is-active
        # pritunl`), mapping success -> reachable.
        return NodeHealth(
            reachability=Reachability.degraded,
            error="ssh adapter is a stub (bootstrap / break-glass — not yet implemented)",
            detail={"role": "bootstrap/break-glass"},
        )

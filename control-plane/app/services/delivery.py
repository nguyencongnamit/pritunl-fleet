"""Profile delivery — email a client's VPN profile via Resend.

Config-gated: if FLEET_RESEND_API_KEY is unset, callers get NotConfiguredError
(surfaced as HTTP 501) rather than a silent no-op. The profile is attached; its
bytes are never logged.
"""

from __future__ import annotations

import base64

import httpx

from app.config import get_settings

RESEND_URL = "https://api.resend.com/emails"


class NotConfiguredError(RuntimeError):
    pass


async def send_profile_email(
    *, to: str, filename: str, content: bytes, user_name: str
) -> str:
    settings = get_settings()
    if not settings.resend_api_key:
        raise NotConfiguredError("email delivery is not configured (set FLEET_RESEND_API_KEY)")

    payload = {
        "from": settings.resend_from,
        "to": [to],
        "subject": f"Your VPN profile ({user_name})",
        "text": (
            f"Hi,\n\nAttached is your VPN client profile ({filename}). Import it "
            f"into your OpenVPN / Pritunl client to connect.\n\n— Pritunl Fleet"
        ),
        "attachments": [
            {"filename": filename, "content": base64.b64encode(content).decode("ascii")}
        ],
    }
    headers = {"Authorization": f"Bearer {settings.resend_api_key}"}
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(RESEND_URL, json=payload, headers=headers)
    if resp.status_code >= 400:
        raise RuntimeError(f"email provider error {resp.status_code}: {resp.text[:200]}")
    try:
        return resp.json().get("id", "")
    except ValueError:
        return ""

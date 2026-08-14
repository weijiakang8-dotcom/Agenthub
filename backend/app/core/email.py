from __future__ import annotations

import httpx

from app.config import settings


async def send_email(to: str, subject: str, html: str) -> dict:
    if not settings.RESEND_API_KEY:
        return {"ok": False, "error": "RESEND_API_KEY is not configured"}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
                json={
                    "from": settings.RESEND_FROM or "onboarding@resend.dev",
                    "to": [to],
                    "subject": subject,
                    "html": html,
                },
            )
            resp.raise_for_status()
        return {"ok": True, "data": resp.json()}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}

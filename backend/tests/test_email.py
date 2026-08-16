from __future__ import annotations

import asyncio

from app.core import email as email_service


def test_send_email_uses_smtp_when_configured(monkeypatch):
    calls = []

    def fake_smtp(to, subject, text):
        calls.append((to, subject, text))
        return {"ok": True}

    monkeypatch.setattr(email_service.settings, "SMTP_HOST", "mailhog")
    monkeypatch.setattr(email_service, "_send_smtp", fake_smtp)

    result = asyncio.run(email_service.send_email("a@b.com", "Subject", "Body"))

    assert result == {"ok": True}
    assert calls == [("a@b.com", "Subject", "Body")]


def test_send_email_falls_back_to_resend_when_smtp_missing(monkeypatch):
    async def fake_resend(to, subject, text):
        return {"ok": True, "data": {"id": "resend-1"}}

    monkeypatch.setattr(email_service.settings, "SMTP_HOST", "")
    monkeypatch.setattr(email_service.settings, "RESEND_API_KEY", "key")
    monkeypatch.setattr(email_service.settings, "RESEND_FROM", "from@example.com")
    monkeypatch.setattr(email_service, "_send_resend", fake_resend)

    result = asyncio.run(email_service.send_email("a@b.com", "Subject", "Body"))

    assert result == {"ok": True, "data": {"id": "resend-1"}}

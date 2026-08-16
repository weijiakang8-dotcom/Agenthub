from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.routes import auth as auth_routes


class FakeRedis:
    def __init__(self):
        self.data = {}

    async def get(self, key):
        return self.data.get(key)

    async def set(self, key, value, ex=None):
        self.data[key] = value
        return True

    async def delete(self, key):
        self.data.pop(key, None)
        return 1

    async def aclose(self):
        return None


def test_verify_code_is_one_time_use(monkeypatch):
    redis = FakeRedis()
    redis.data["auth:code:user@example.com"] = "123456"
    monkeypatch.setattr(
        auth_routes.aioredis, "from_url", lambda *_args, **_kwargs: redis
    )

    assert asyncio.run(auth_routes._verify_code("user@example.com", "123456")) is True
    assert asyncio.run(auth_routes._verify_code("user@example.com", "123456")) is False


def test_verify_code_rejects_wrong_code(monkeypatch):
    redis = FakeRedis()
    redis.data["auth:code:user@example.com"] = "123456"
    monkeypatch.setattr(
        auth_routes.aioredis, "from_url", lambda *_args, **_kwargs: redis
    )

    assert asyncio.run(auth_routes._verify_code("user@example.com", "000000")) is False
    assert redis.data.get("auth:code:user@example.com") == "123456"


def test_send_code_email_rate_limited(monkeypatch):
    called = []

    async def reject(*_args, **_kwargs):
        return False

    async def fake_send_code(_email):
        called.append(_email)
        return {"ok": True}

    monkeypatch.setattr(auth_routes, "rate_limit", reject)
    monkeypatch.setattr(auth_routes, "_send_code", fake_send_code)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            auth_routes.send_code(
                payload=auth_routes.SendCodeRequest(email="user@example.com"),
                request=SimpleNamespace(
                    headers={"x-forwarded-for": "1.2.3.4"},
                    client=SimpleNamespace(host="1.2.3.4"),
                ),
            )
        )

    assert exc.value.status_code == 429
    assert called == []


def test_send_code_allowed(monkeypatch):
    calls = []

    async def allow(*_args, **_kwargs):
        return True

    async def fake_send_code(email):
        calls.append(email)
        return {"ok": True}

    monkeypatch.setattr(auth_routes, "rate_limit", allow)
    monkeypatch.setattr(auth_routes, "_send_code", fake_send_code)

    result = asyncio.run(
        auth_routes.send_code(
            payload=auth_routes.SendCodeRequest(email="user@example.com"),
            request=SimpleNamespace(
                headers={},
                client=SimpleNamespace(host="5.6.7.8"),
            ),
        )
    )

    assert result == {"status": "ok"}
    assert calls == ["user@example.com"]

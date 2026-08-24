from __future__ import annotations

import asyncio
import json

from app import main as main_module


def test_health_reports_build_sha(monkeypatch):
    class FakeConnection:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def execute(self, _query):
            return None

    class FakeRedis:
        async def ping(self):
            return True

        async def aclose(self):
            return None

    class FakeHttpClient:
        def __init__(self, *_args, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def get(self, _url):
            return None

    class FakeEngine:
        def connect(self):
            return FakeConnection()

    monkeypatch.setattr(main_module, "master_engine", FakeEngine())
    monkeypatch.setattr(main_module.aioredis, "from_url", lambda _url: FakeRedis())
    monkeypatch.setattr(main_module.httpx, "AsyncClient", FakeHttpClient)
    monkeypatch.setattr(main_module.settings, "BUILD_SHA", "abc123")

    response = asyncio.run(main_module.health())
    payload = json.loads(response.body)

    assert response.status_code == 200
    assert payload == {
        "status": "ok",
        "build_sha": "abc123",
        "database": True,
        "redis": True,
        "llm": True,
    }

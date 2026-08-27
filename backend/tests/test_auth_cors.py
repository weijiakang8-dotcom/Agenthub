from __future__ import annotations

from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app


def test_allowed_origin_preflight_supports_credentials(monkeypatch):
    async def allow(*_args, **_kwargs):
        return True

    monkeypatch.setattr(main_module, "rate_limit", allow)
    client = TestClient(app)

    response = client.options(
        "/api/auth/refresh",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_disallowed_origin_preflight_is_rejected(monkeypatch):
    async def allow(*_args, **_kwargs):
        return True

    monkeypatch.setattr(main_module, "rate_limit", allow)
    client = TestClient(app)

    response = client.options(
        "/api/auth/refresh",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers

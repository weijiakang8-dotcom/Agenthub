from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.api.deps import get_current_user
from app.api.routes import user_api_keys as route_module
from app.main import app


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.is_success = 200 <= status_code < 300

    def json(self) -> dict:
        return self._payload


class FakeClient:
    get_response = FakeResponse({"data": []})
    post_response = FakeResponse({"choices": []})

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def get(self, *_args, **_kwargs):
        return self.get_response

    async def post(self, *_args, **_kwargs):
        return self.post_response


@pytest.fixture()
def client(monkeypatch):
    async def allow_request(*_args, **_kwargs):
        return True

    async def current_user():
        return SimpleNamespace(
            id=uuid.uuid4(), organization_id=uuid.uuid4(), role="admin", is_active=True
        )

    monkeypatch.setattr(main_module, "rate_limit", allow_request)
    monkeypatch.setattr(route_module.httpx, "AsyncClient", FakeClient)
    app.dependency_overrides[get_current_user] = current_user
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_discover_models_returns_sorted_ids(client):
    FakeClient.get_response = FakeResponse(
        {"data": [{"id": "gpt-5.6-sol"}, {"id": "gpt-5.5"}]}
    )
    response = client.post(
        "/api/user-api-keys/discover-models",
        json={"base_url": "http://example.com/v1/", "api_key": "sk-test"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "base_url": "http://example.com/v1",
        "models": ["gpt-5.5", "gpt-5.6-sol"],
    }


def test_connection_success(client):
    FakeClient.post_response = FakeResponse(
        {"choices": [{"message": {"content": "OK"}}]}
    )
    response = client.post(
        "/api/user-api-keys/test-connection",
        json={
            "base_url": "http://example.com/v1",
            "api_key": "sk-test",
            "model": "gpt-5.6-sol",
        },
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["model"] == "gpt-5.6-sol"


def test_connection_failure_is_user_friendly_and_does_not_leak_key(client):
    FakeClient.post_response = FakeResponse(
        {"error": {"message": "Upstream request failed"}}, status_code=502
    )
    secret = "sk-sensitive-never-return"
    response = client.post(
        "/api/user-api-keys/test-connection",
        json={
            "base_url": "http://example.com/v1",
            "api_key": secret,
            "model": "gpt-5.4",
        },
    )
    assert response.status_code == 422
    body = response.text
    assert "gpt-5.4" in body
    assert "上游" in body
    assert secret not in body


def test_invalid_base_url_is_rejected(client):
    response = client.post(
        "/api/user-api-keys/discover-models",
        json={"base_url": "file:///etc/passwd", "api_key": "sk-test"},
    )
    assert response.status_code == 422


def test_probe_requires_login(monkeypatch):
    async def allow_request(*_args, **_kwargs):
        return True

    monkeypatch.setattr(main_module, "rate_limit", allow_request)
    app.dependency_overrides.clear()
    response = TestClient(app).post(
        "/api/user-api-keys/discover-models",
        json={"base_url": "http://example.com/v1", "api_key": "sk-test"},
    )
    assert response.status_code == 401

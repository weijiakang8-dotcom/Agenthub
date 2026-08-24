from __future__ import annotations

import socket
import uuid
from types import SimpleNamespace
from typing import ClassVar

import httpx
import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.api.deps import get_current_user
from app.api.routes import user_api_keys as route_module
from app.main import app


class FakeResponse:
    def __init__(
        self,
        payload: dict,
        status_code: int = 200,
        *,
        url: str = "https://example.com/v1/models",
        headers: dict | None = None,
    ):
        self._payload = payload
        self.status_code = status_code
        self.is_success = 200 <= status_code < 300
        self.is_redirect = status_code in {301, 302, 303, 307, 308}
        self.url = httpx.URL(url)
        self.headers = headers or {}

    def json(self) -> dict:
        return self._payload


REAL_VALIDATE_PUBLIC_URL = route_module._validate_public_url


class FakeClient:
    responses: ClassVar[list[FakeResponse]] = [FakeResponse({"data": []})]
    requests: ClassVar[list[tuple[str, str, dict]]] = []
    error: ClassVar[Exception | None] = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def request(self, method: str, url: str, **kwargs):
        self.requests.append((method, url, kwargs))
        if self.error:
            raise self.error
        if not self.responses:
            raise AssertionError("No fake response configured")
        return self.responses.pop(0)


@pytest.fixture()
def client(monkeypatch):
    async def allow_request(*_args, **_kwargs):
        return True

    async def current_user():
        return SimpleNamespace(
            id=uuid.uuid4(), organization_id=uuid.uuid4(), role="admin", is_active=True
        )

    async def allow_public_url(_url: str):
        return None

    FakeClient.responses = [FakeResponse({"data": []})]
    FakeClient.requests = []
    FakeClient.error = None
    monkeypatch.setattr(main_module, "rate_limit", allow_request)
    monkeypatch.setattr(route_module.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(route_module, "_validate_public_url", allow_public_url)
    app.dependency_overrides[get_current_user] = current_user
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_discover_models_returns_sorted_ids(client):
    FakeClient.responses = [
        FakeResponse({"data": [{"id": "gpt-5.6-sol"}, {"id": "gpt-5.5"}]})
    ]
    response = client.post(
        "/api/user-api-keys/discover-models",
        json={"base_url": "https://example.com/v1/", "api_key": "sk-test"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "base_url": "https://example.com/v1",
        "models": ["gpt-5.5", "gpt-5.6-sol"],
        "chat_models": ["gpt-5.5", "gpt-5.6-sol"],
        "api_mode": "chat_completions",
    }
    assert FakeClient.requests[0][1] == "https://example.com/v1/models"


def test_discover_models_adds_v1_when_root_models_is_missing(client):
    FakeClient.responses = [
        FakeResponse({}, 404, url="https://example.com/models"),
        FakeResponse(
            {"data": [{"id": "model-1"}]}, url="https://example.com/v1/models"
        ),
    ]
    response = client.post(
        "/api/user-api-keys/discover-models",
        json={"base_url": "https://example.com", "api_key": "sk-test"},
    )
    assert response.status_code == 200
    assert response.json()["base_url"] == "https://example.com/v1"
    assert [item[1] for item in FakeClient.requests] == [
        "https://example.com/models",
        "https://example.com/v1/models",
    ]


def test_full_endpoint_is_normalized_to_api_root(client):
    FakeClient.responses = [FakeResponse({"data": [{"id": "model-1"}]})]
    response = client.post(
        "/api/user-api-keys/discover-models",
        json={
            "base_url": "https://example.com/v1/chat/completions",
            "api_key": "sk-test",
        },
    )
    assert response.status_code == 200
    assert response.json()["base_url"] == "https://example.com/v1"
    assert FakeClient.requests[0][1] == "https://example.com/v1/models"


def test_connection_success(client):
    FakeClient.responses = [
        FakeResponse(
            {"choices": [{"message": {"content": "OK"}}]},
            url="https://example.com/v1/chat/completions",
        )
    ]
    response = client.post(
        "/api/user-api-keys/test-connection",
        json={
            "base_url": "https://example.com/v1",
            "api_key": "sk-test",
            "model": "gpt-5.6-sol",
        },
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["model"] == "gpt-5.6-sol"
    assert response.json()["api_mode"] == "chat_completions"


def test_openai_official_uses_responses_api(client):
    FakeClient.responses = [
        FakeResponse(
            {"output_text": "OK"},
            url="https://api.openai.com/v1/responses",
        )
    ]
    response = client.post(
        "/api/user-api-keys/test-connection",
        json={
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-test",
            "model": "gpt-5",
        },
    )
    assert response.status_code == 200
    assert response.json()["api_mode"] == "responses"
    assert response.json()["preview"] == "OK"
    method, url, kwargs = FakeClient.requests[0]
    assert method == "POST"
    assert url == "https://api.openai.com/v1/responses"
    assert kwargs["json"]["input"] == "Reply with exactly OK"


def test_chat_endpoint_rejection_falls_back_to_responses(client):
    FakeClient.responses = [
        FakeResponse(
            {"error": {"message": "This model is not supported in chat completions"}},
            status_code=400,
            url="https://example.com/v1/chat/completions",
        ),
        FakeResponse(
            {"output": [{"content": [{"type": "output_text", "text": "OK"}]}]},
            url="https://example.com/v1/responses",
        ),
    ]
    response = client.post(
        "/api/user-api-keys/test-connection",
        json={
            "base_url": "https://example.com/v1",
            "api_key": "sk-test",
            "model": "provider-reasoning-model",
        },
    )
    assert response.status_code == 200
    assert response.json()["api_mode"] == "responses"
    assert [request[1] for request in FakeClient.requests] == [
        "https://example.com/v1/chat/completions",
        "https://example.com/v1/responses",
    ]


def test_discovery_filters_openai_non_chat_models(client):
    FakeClient.responses = [
        FakeResponse(
            {
                "data": [
                    {"id": "text-embedding-3-large"},
                    {"id": "gpt-image-1"},
                    {"id": "whisper-1"},
                    {"id": "omni-moderation-latest"},
                    {"id": "gpt-5"},
                ]
            },
            url="https://api.openai.com/v1/models",
        )
    ]
    response = client.post(
        "/api/user-api-keys/discover-models",
        json={"base_url": "https://api.openai.com/v1", "api_key": "sk-test"},
    )
    assert response.status_code == 200
    assert response.json()["chat_models"] == ["gpt-5"]
    assert response.json()["api_mode"] == "responses"


def test_connection_failure_is_user_friendly_and_does_not_leak_key(client):
    FakeClient.responses = [
        FakeResponse(
            {"error": {"message": "Upstream request failed"}},
            status_code=502,
            url="https://example.com/v1/chat/completions",
        )
    ]
    secret = "test-secret-never-return"
    response = client.post(
        "/api/user-api-keys/test-connection",
        json={
            "base_url": "https://example.com/v1",
            "api_key": secret,
            "model": "gpt-5.4",
        },
    )
    assert response.status_code == 422
    body = response.text
    assert "gpt-5.4" in body
    assert "上游" in body
    assert secret not in body


def test_timeout_explains_likely_configuration_causes(client):
    FakeClient.error = httpx.ConnectTimeout("timed out")
    response = client.post(
        "/api/user-api-keys/discover-models",
        json={"base_url": "https://example.com", "api_key": "sk-test"},
    )
    assert response.status_code == 422
    assert "连接超时" in response.text
    assert "/v1" in response.text
    assert "sk-test" not in response.text


@pytest.mark.parametrize(
    "base_url",
    [
        "file:///etc/passwd",
        "http://127.0.0.1:8000/v1",
        "http://10.0.0.1/v1",
        "http://169.254.169.254/latest",
        "http://[::1]/v1",
    ],
)
def test_private_or_invalid_base_url_is_rejected(client, base_url, monkeypatch):
    monkeypatch.setattr(route_module, "_validate_public_url", REAL_VALIDATE_PUBLIC_URL)
    response = client.post(
        "/api/user-api-keys/discover-models",
        json={"base_url": base_url, "api_key": "sk-test"},
    )
    assert response.status_code == 422
    assert not FakeClient.requests


def test_hostname_resolving_to_private_ip_is_rejected(client, monkeypatch):
    def private_dns(*_args, **_kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 443))]

    monkeypatch.setattr(route_module, "_validate_public_url", REAL_VALIDATE_PUBLIC_URL)
    monkeypatch.setattr(route_module.socket, "getaddrinfo", private_dns)
    response = client.post(
        "/api/user-api-keys/discover-models",
        json={"base_url": "https://internal.example", "api_key": "sk-test"},
    )
    assert response.status_code == 422
    assert "私有网络" in response.text


def test_cross_origin_redirect_is_rejected_without_forwarding_key(client):
    FakeClient.responses = [
        FakeResponse(
            {},
            302,
            url="https://example.com/models",
            headers={"location": "https://other.example/models"},
        )
    ]
    response = client.post(
        "/api/user-api-keys/discover-models",
        json={"base_url": "https://example.com", "api_key": "sk-test"},
    )
    assert response.status_code == 422
    assert "其他域名" in response.text
    assert len(FakeClient.requests) == 1


def test_probe_requires_login(monkeypatch):
    async def allow_request(*_args, **_kwargs):
        return True

    monkeypatch.setattr(main_module, "rate_limit", allow_request)
    app.dependency_overrides.clear()
    response = TestClient(app).post(
        "/api/user-api-keys/discover-models",
        json={"base_url": "https://example.com/v1", "api_key": "sk-test"},
    )
    assert response.status_code == 401

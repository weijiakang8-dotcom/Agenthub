from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

os.environ.setdefault("OTEL_SDK_DISABLED", "true")

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.api.deps import get_current_user
from app.database import get_db
from app.main import app
from app.models import Document, ModelConfig, Notification

ORG_ID = uuid.uuid4()


def make_model() -> ModelConfig:
    return ModelConfig(
        id=uuid.uuid4(),
        organization_id=ORG_ID,
        name="deepseek",
        provider="deepseek",
        base_url="https://api.deepseek.com/v1",
        api_key="sk-test",
        model="deepseek-chat",
        max_tokens=4096,
        cost_per_1k_tokens=0.002,
        is_active=True,
        is_default=False,
        created_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
        updated_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
    )


def make_document() -> Document:
    return Document(
        id=uuid.uuid4(),
        organization_id=ORG_ID,
        user_id=uuid.uuid4(),
        name="knowledge.md",
        content="AgentHub 支持语义检索",
        metadata_json={"filename": "knowledge.md"},
        embedding=[0.1, 0.2],
        created_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
        updated_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
    )


def make_notification() -> Notification:
    return Notification(
        id=uuid.uuid4(),
        organization_id=ORG_ID,
        channel="email",
        template="alert",
        params={"message": "hello"},
        status="success",
        error="",
        created_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
        updated_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
    )


class FakeScalarResult:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class FakeResult:
    def __init__(self, scalars=None, one=None):
        self._scalars = scalars
        self._one = one

    def scalars(self):
        return FakeScalarResult(self._scalars or [])

    def one(self):
        return self._one


class FakeSession:
    def __init__(self, execute_results=None):
        self.execute_results = list(execute_results or [])

    async def execute(self, _stmt):
        if not self.execute_results:
            raise AssertionError("no execute result configured")
        return self.execute_results.pop(0)


@pytest.fixture()
def client_factory(monkeypatch):
    async def allow_request(*_args, **_kwargs):
        return True

    monkeypatch.setattr(main_module, "rate_limit", allow_request)

    def factory(execute_results):
        session = FakeSession(execute_results)
        user = SimpleNamespace(
            id=uuid.uuid4(),
            organization_id=ORG_ID,
            role="admin",
            is_active=True,
        )

        async def override_user():
            return user

        async def override_db():
            yield session

        app.dependency_overrides[get_current_user] = override_user
        app.dependency_overrides[get_db] = override_db
        return TestClient(app)

    yield factory
    app.dependency_overrides.clear()


def test_models_endpoint_returns_json(client_factory):
    model = make_model()
    client = client_factory([FakeResult(scalars=[model])])

    response = client.get("/api/models")

    assert response.status_code == 200
    assert response.json()[0]["name"] == "deepseek"
    assert response.json()[0]["model"] == "deepseek-chat"


def test_documents_endpoint_returns_json(client_factory):
    document = make_document()
    client = client_factory([FakeResult(scalars=[document])])

    response = client.get("/api/documents")

    assert response.status_code == 200
    assert response.json()[0]["name"] == "knowledge.md"
    assert response.json()[0]["metadata"]["filename"] == "knowledge.md"


def test_notifications_endpoint_returns_json(client_factory):
    notification = make_notification()
    client = client_factory([FakeResult(scalars=[notification])])

    response = client.get("/api/notifications")

    assert response.status_code == 200
    assert response.json()[0]["channel"] == "email"
    assert response.json()[0]["status"] == "success"


def test_usage_endpoint_returns_summary(client_factory):
    client = client_factory(
        [
            FakeResult(one=(12, 1000, 500, 0.25)),
            FakeResult(one=(300, 0.03)),
        ]
    )

    response = client.get("/api/usage")

    assert response.status_code == 200
    assert response.json()["total_executions"] == 12
    assert response.json()["total_tokens"] == 1500

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from app.api.routes import models as models_routes
from app.models import ModelConfig
from fastapi import HTTPException

ORG_ID = uuid.uuid4()
OTHER_ORG_ID = uuid.uuid4()


def make_user(organization_id: uuid.UUID | None = ORG_ID):
    return SimpleNamespace(id=uuid.uuid4(), organization_id=organization_id)


def make_model(
    organization_id: uuid.UUID | None = ORG_ID,
    **overrides,
) -> ModelConfig:
    values = {
        "id": uuid.uuid4(),
        "organization_id": organization_id,
        "name": "deepseek",
        "provider": "deepseek",
        "base_url": "https://api.deepseek.com/v1",
        "api_key": "sk-test",
        "model": "deepseek-chat",
        "max_tokens": 4096,
        "cost_per_1k_tokens": 0.002,
        "is_active": True,
        "is_default": False,
        "created_at": datetime(2026, 8, 15, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 8, 15, tzinfo=timezone.utc),
    }
    values.update(overrides)
    return ModelConfig(**values)


class FakeSession:
    def __init__(self, get_result=None):
        self.get_result = get_result
        self.commits = 0
        self.refreshes = 0

    async def get(self, _model, _obj_id):
        return self.get_result

    async def commit(self):
        self.commits += 1

    async def refresh(self, _obj):
        self.refreshes += 1


def test_update_model_success_updates_fields():
    model = make_model()
    session = FakeSession(get_result=model)
    payload = models_routes.ModelUpdate(
        name="openai-main",
        is_default=True,
    )

    result = asyncio.run(
        models_routes.update_model(
            model_id=model.id,
            payload=payload,
            session=session,
            user=make_user(),
        )
    )

    assert session.commits == 1
    assert model.name == "openai-main"
    assert model.is_default is True
    assert result["name"] == "openai-main"
    assert result["is_default"] is True


def test_update_model_missing_returns_404():
    session = FakeSession(get_result=None)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            models_routes.update_model(
                model_id=uuid.uuid4(),
                payload=models_routes.ModelUpdate(name="missing"),
                session=session,
                user=make_user(),
            )
        )

    assert exc.value.status_code == 404


def test_test_model_returns_connection_result(monkeypatch):
    model = make_model()
    session = FakeSession(get_result=model)

    async def fake_test_model(_model):
        return {"ok": True, "response": "pong"}

    monkeypatch.setattr(models_routes, "test_model", fake_test_model)

    result = asyncio.run(
        models_routes.test_model_endpoint(
            model_id=model.id,
            session=session,
            user=make_user(),
        )
    )

    assert result == {"ok": True, "response": "pong"}


def test_test_model_rejects_other_org(monkeypatch):
    model = make_model(OTHER_ORG_ID)
    session = FakeSession(get_result=model)
    called = False

    async def fake_test_model(_model):
        nonlocal called
        called = True
        return {"ok": True}

    monkeypatch.setattr(models_routes, "test_model", fake_test_model)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            models_routes.test_model_endpoint(
                model_id=model.id,
                session=session,
                user=make_user(ORG_ID),
            )
        )

    assert exc.value.status_code == 404
    assert called is False


def test_test_model_returns_failure_details(monkeypatch):
    model = make_model()
    session = FakeSession(get_result=model)

    async def fake_test_model(_model):
        return {"ok": False, "error": "connect timeout"}

    monkeypatch.setattr(models_routes, "test_model", fake_test_model)

    result = asyncio.run(
        models_routes.test_model_endpoint(
            model_id=model.id,
            session=session,
            user=make_user(),
        )
    )

    assert result == {"ok": False, "error": "connect timeout"}

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from app.api.routes.documents import delete_document, list_documents
from app.api.routes.eval import DatasetCreate, create_dataset
from app.api.routes.models import ModelCreate, create_model, list_models, update_model
from app.api.routes.notifications import list_notifications
from app.api.routes.usage import usage
from app.models import Document, ModelConfig, Notification
from fastapi import HTTPException

ORG_ID = uuid.uuid4()
OTHER_ORG_ID = uuid.uuid4()


def make_user(organization_id: uuid.UUID | None = ORG_ID):
    return SimpleNamespace(id=uuid.uuid4(), organization_id=organization_id)


def make_model(organization_id: uuid.UUID | None = ORG_ID, **overrides) -> ModelConfig:
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
        "priority": 100,
        "timeout": 120,
        "max_retries": 2,
        "enabled": True,
        "is_active": True,
        "is_default": False,
        "created_at": datetime(2026, 8, 15, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 8, 15, tzinfo=timezone.utc),
    }
    values.update(overrides)
    return ModelConfig(**values)


def make_document(organization_id: uuid.UUID | None = ORG_ID) -> Document:
    return Document(
        id=uuid.uuid4(),
        organization_id=organization_id,
        user_id=uuid.uuid4(),
        name="knowledge.md",
        content="AgentHub 支持语义检索",
        metadata_json={"filename": "knowledge.md"},
        embedding=[0.1, 0.2],
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
        if self._one is None:
            raise AssertionError("unexpected execute().one()")
        return self._one


class FakeSession:
    def __init__(
        self,
        execute_results=None,
        get_result=None,
    ):
        self.execute_results = list(execute_results or [])
        self.get_result = get_result
        self.added = []
        self.deleted = []
        self.commits = 0
        self.refreshes = 0

    async def execute(self, _stmt):
        if not self.execute_results:
            raise AssertionError("no execute result configured")
        return self.execute_results.pop(0)

    async def get(self, _model, _id):
        return self.get_result

    def add(self, obj):
        self.added.append(obj)

    async def delete(self, obj):
        self.deleted.append(obj)

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        self.refreshes += 1


def test_list_models_serializes_org_models():
    expected = make_model(ORG_ID, name="deepseek")
    session = FakeSession(execute_results=[FakeResult(scalars=[expected])])

    result = asyncio.run(list_models(session=session, user=make_user()))

    assert result == [
        {
            "id": str(expected.id),
            "name": "deepseek",
            "provider": "deepseek",
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-chat",
            "max_tokens": 4096,
            "cost_per_1k_tokens": 0.002,
            "priority": 100,
            "timeout": 120,
            "max_retries": 2,
            "enabled": True,
            "is_active": True,
            "is_default": False,
        }
    ]


def test_create_model_persists_organization():
    session = FakeSession()
    payload = ModelCreate(
        name="deepseek",
        provider="deepseek",
        base_url="https://api.deepseek.com/v1",
        api_key="sk-test",
        model="deepseek-chat",
        max_tokens=4096,
        cost_per_1k_tokens=0.002,
        is_default=False,
    )

    result = asyncio.run(
        create_model(
            payload=payload,
            session=session,
            user=make_user(),
        )
    )

    assert len(session.added) == 1
    assert session.added[0].organization_id == ORG_ID
    assert session.commits == 1
    assert result["name"] == "deepseek"


def test_update_model_rejects_other_org():
    model = make_model(OTHER_ORG_ID)
    session = FakeSession(get_result=model)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            update_model(
                model_id=model.id,
                payload={"name": "renamed"},
                session=session,
                user=make_user(ORG_ID),
            )
        )

    assert exc.value.status_code == 404


def test_list_documents_serializes_documents():
    document = make_document(ORG_ID)
    session = FakeSession(execute_results=[FakeResult(scalars=[document])])

    result = asyncio.run(list_documents(session=session, user=make_user()))

    assert len(result) == 1
    assert result[0]["name"] == "knowledge.md"
    assert result[0]["metadata"]["filename"] == "knowledge.md"


def test_delete_document_rejects_other_org():
    document = make_document(OTHER_ORG_ID)
    session = FakeSession(get_result=document)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            delete_document(
                document_id=document.id,
                session=session,
                user=make_user(ORG_ID),
            )
        )

    assert exc.value.status_code == 404


def test_usage_returns_token_and_cost_summary():
    session = FakeSession(
        execute_results=[
            FakeResult(one=(12, 1000, 500, 0.25, 1)),
            FakeResult(one=(300, 0.03)),
        ]
    )

    result = asyncio.run(usage(session=session, user=make_user()))

    assert result == {
        "total_executions": 12,
        "total_input_tokens": 1000,
        "total_output_tokens": 500,
        "total_tokens": 1500,
        "total_cost": 0.25,
        "cost_unknown_executions": 1,
        "today_tokens": 300,
        "today_cost": 0.03,
    }


def test_list_notifications_serializes_history():
    notification = Notification(
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
    session = FakeSession(execute_results=[FakeResult(scalars=[notification])])

    result = asyncio.run(list_notifications(session=session, user=make_user()))

    assert len(result) == 1
    assert result[0]["channel"] == "email"
    assert result[0]["status"] == "success"


def test_create_eval_dataset_rejects_empty_items():
    session = FakeSession()
    payload = DatasetCreate(name="empty", description="bad", items=[])

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            create_dataset(
                payload=payload,
                session=session,
                user=make_user(),
            )
        )

    assert exc.value.status_code == 422

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.routes import documents as documents_routes
from app.api.routes import eval as eval_routes
from app.core import notification as notification_routes
from app.models import Document, EvalDataset, ExecutionStatus

ORG_ID = uuid.uuid4()


def make_user(organization_id: uuid.UUID | None = ORG_ID):
    return SimpleNamespace(id=uuid.uuid4(), organization_id=organization_id)


class FakeSessionFactory:
    def __init__(self, session):
        self.session = session

    def __call__(self):
        return self

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *_args):
        return False


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
    def __init__(self, execute_result=None, get_result=None):
        self.execute_result = execute_result
        self.get_result = get_result
        self.objects = {}
        self.added = []
        self.deleted = []
        self.commits = 0
        self.refreshes = 0

    async def execute(self, _stmt):
        return self.execute_result

    async def get(self, _model, obj_id):
        if obj_id in self.objects:
            return self.objects[obj_id]
        return self.get_result

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        if getattr(obj, "created_at", None) is None:
            obj.created_at = datetime(2026, 8, 15, tzinfo=timezone.utc)
        if getattr(obj, "updated_at", None) is None:
            obj.updated_at = datetime(2026, 8, 15, tzinfo=timezone.utc)
        self.objects[obj.id] = obj
        self.added.append(obj)

    async def delete(self, obj):
        self.deleted.append(obj)

    async def commit(self):
        self.commits += 1

    async def refresh(self, _obj):
        self.refreshes += 1


class FakeUpload:
    def __init__(
        self,
        filename: str = "doc.txt",
        content_type: str = "text/plain",
        content: bytes = b"hello world",
    ):
        self.filename = filename
        self.content_type = content_type
        self.content = content

    async def read(self):
        return self.content


def make_document(name: str, content: str) -> Document:
    return Document(
        id=uuid.uuid4(),
        organization_id=ORG_ID,
        user_id=uuid.uuid4(),
        name=name,
        content=content,
        metadata_json={"filename": name},
        embedding=[0.1],
        created_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
        updated_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
    )


def test_send_notification_success(monkeypatch):
    session = FakeSession()
    factory = FakeSessionFactory(session)
    calls = []

    async def fake_dispatch(channel, _text, _params):
        calls.append(channel)

    monkeypatch.setattr(notification_routes, "async_session_factory", factory)
    monkeypatch.setattr(notification_routes, "_dispatch", fake_dispatch)

    result = asyncio.run(
        notification_routes.send_notification(
            "email",
            "alert",
            {"message": "hello"},
            str(ORG_ID),
        )
    )

    assert result == {"status": "success", "error": ""}
    assert calls == ["email"]
    assert session.commits == 2


def test_send_notification_failure_retries(monkeypatch):
    session = FakeSession()
    factory = FakeSessionFactory(session)
    calls = []

    async def fail_dispatch(_channel, _text, _params):
        calls.append(1)
        raise RuntimeError("smtp down")

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(notification_routes, "async_session_factory", factory)
    monkeypatch.setattr(notification_routes, "_dispatch", fail_dispatch)
    monkeypatch.setattr(notification_routes.asyncio, "sleep", no_sleep)

    result = asyncio.run(
        notification_routes.send_notification(
            "email",
            "alert",
            {"message": "hello"},
            str(ORG_ID),
        )
    )

    assert result["status"] == "failed"
    assert result["error"] == "smtp down"
    assert len(calls) == 3


def test_upload_document_uses_embedding(monkeypatch):
    session = FakeSession()

    async def fake_embed(_text):
        return [0.1, 0.2]

    monkeypatch.setattr(documents_routes, "embed_text", fake_embed)

    async def fake_rebuild(_document):
        return 1

    monkeypatch.setattr(documents_routes, "rebuild_document_chunks", fake_rebuild)

    result = asyncio.run(
        documents_routes.upload_document(
            session=session,
            user=make_user(),
            file=FakeUpload(),
        )
    )

    assert result["name"] == "doc.txt"
    assert session.added[0].embedding == [0.1, 0.2]


def test_upload_document_rejects_unsupported_type(monkeypatch):
    session = FakeSession()

    async def fake_embed(_text):
        return [0.1]

    monkeypatch.setattr(documents_routes, "embed_text", fake_embed)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            documents_routes.upload_document(
                session=session,
                user=make_user(),
                file=FakeUpload(filename="notes.docx", content_type="application/zip"),
            )
        )

    assert exc.value.status_code == 422
    assert session.added == []


def test_upload_document_rejects_empty_content(monkeypatch):
    session = FakeSession()

    async def fake_embed(_text):
        return [0.1]

    monkeypatch.setattr(documents_routes, "embed_text", fake_embed)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            documents_routes.upload_document(
                session=session,
                user=make_user(),
                file=FakeUpload(filename="empty.txt", content=b"   "),
            )
        )

    assert exc.value.status_code == 422
    assert session.added == []


def test_search_documents_scores_keywords(monkeypatch):
    doc_a = make_document("a.md", "hello world")
    doc_b = make_document("b.md", "nothing relevant")
    session = FakeSession(
        execute_result=FakeResult(scalars=[doc_b, doc_a]),
    )

    async def fake_embed(_text):
        return [0.1]

    def fake_cosine(_left, _right):
        return 0.5

    monkeypatch.setattr(documents_routes, "embed_text", fake_embed)
    monkeypatch.setattr(documents_routes, "cosine", fake_cosine)

    result = asyncio.run(
        documents_routes.search_documents(
            payload=documents_routes.SearchRequest(query="hello"),
            session=session,
            user=make_user(),
        )
    )

    assert [item["name"] for item in result] == ["a.md", "b.md"]


def test_run_eval_empty_dataset_reports_zero_items(monkeypatch):
    dataset = EvalDataset(
        id=uuid.uuid4(),
        organization_id=ORG_ID,
        name="empty",
        description="edge case",
        items=[],
        created_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
        updated_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
    )
    session = FakeSession()
    session.objects[dataset.id] = dataset
    factory = FakeSessionFactory(session)

    async def fake_workflow(*_args):
        return uuid.uuid4()

    monkeypatch.setattr(eval_routes, "async_session_factory", factory)
    monkeypatch.setattr(eval_routes, "_get_or_create_workflow", fake_workflow)

    result = asyncio.run(
        eval_routes.run_eval(
            payload=eval_routes.RunRequest(dataset_id=dataset.id),
            user=make_user(),
        )
    )

    assert result["status"] == "completed"
    assert result["report"]["total"] == 0
    assert result["report"]["scored"] == 0
    assert result["report"]["passed"] == 0
    assert result["report"]["average_score"] is None


def test_run_one_timeout_returns_timeout_status(monkeypatch):
    session = FakeSession()
    factory = FakeSessionFactory(session)
    delay_calls = []

    def fake_delay(execution_id):
        delay_calls.append(execution_id)

    async def fake_sleep(_seconds):
        return None

    monkeypatch.setattr(eval_routes, "async_session_factory", factory)
    monkeypatch.setattr(eval_routes.execute_workflow_task, "delay", fake_delay)
    monkeypatch.setattr(eval_routes.asyncio, "sleep", fake_sleep)

    result = asyncio.run(
        eval_routes._run_one(
            workflow_id=uuid.uuid4(),
            user_input="hello",
            org_id=ORG_ID,
        )
    )

    assert result == {"input": "hello", "status": "timeout", "score": None}
    assert delay_calls == [str(session.added[0].id)]


def test_run_one_failed_execution_returns_error(monkeypatch):
    session = FakeSession()
    factory = FakeSessionFactory(session)

    def fail_execution(_execution_id):
        execution = session.added[-1]
        execution.status = ExecutionStatus.FAILED
        execution.error_message = "worker crashed"

    async def fake_sleep(_seconds):
        return None

    monkeypatch.setattr(eval_routes, "async_session_factory", factory)
    monkeypatch.setattr(eval_routes.execute_workflow_task, "delay", fail_execution)
    monkeypatch.setattr(eval_routes.asyncio, "sleep", fake_sleep)

    result = asyncio.run(
        eval_routes._run_one(
            workflow_id=uuid.uuid4(),
            user_input="broken prompt",
            org_id=ORG_ID,
        )
    )

    assert result["input"] == "broken prompt"
    assert result["status"] == "failed"
    assert result["score"] is None
    assert result["error"] == "worker crashed"


def test_run_eval_failure_report_has_zero_score(monkeypatch):
    dataset = EvalDataset(
        id=uuid.uuid4(),
        organization_id=ORG_ID,
        name="failure-dataset",
        description="failure report edge case",
        items=[{"input": "trigger failure"}],
        created_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
        updated_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
    )
    session = FakeSession()
    session.objects[dataset.id] = dataset
    factory = FakeSessionFactory(session)

    async def fake_workflow(*_args):
        return uuid.uuid4()

    async def fake_run_one(_workflow_id, user_input, _org_id):
        return {
            "input": user_input,
            "status": "failed",
            "score": None,
            "error": "evaluation failed",
        }

    monkeypatch.setattr(eval_routes, "async_session_factory", factory)
    monkeypatch.setattr(eval_routes, "_get_or_create_workflow", fake_workflow)
    monkeypatch.setattr(eval_routes, "_run_one", fake_run_one)

    result = asyncio.run(
        eval_routes.run_eval(
            payload=eval_routes.RunRequest(dataset_id=dataset.id),
            user=make_user(),
        )
    )

    assert result["status"] == "completed"
    assert result["report"]["total"] == 1
    assert result["report"]["scored"] == 0
    assert result["report"]["passed"] == 0
    assert result["report"]["average_score"] is None
    assert result["report"]["items"][0]["status"] == "failed"

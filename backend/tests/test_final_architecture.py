from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

from app.core.failure import ErrorCategory, classify_error, should_retry
from app.memory import service as memory_service
from app.rag.chunking import split_text


def test_error_taxonomy_routes_by_layer():
    assert (
        classify_error(RuntimeError("connection reset by peer"))
        == ErrorCategory.TRANSIENT
    )
    assert (
        classify_error(RuntimeError("database unavailable"))
        == ErrorCategory.INFRASTRUCTURE
    )
    assert classify_error(RuntimeError("bad request")) == ErrorCategory.PERMANENT
    assert should_retry(ErrorCategory.PROVIDER, "llm") is True
    assert should_retry(ErrorCategory.PROVIDER, "celery") is False
    assert should_retry(ErrorCategory.INFRASTRUCTURE, "celery") is True
    assert should_retry(ErrorCategory.BUSINESS, "celery") is False


def test_chunking_respects_size_and_overlap():
    chunks = split_text("x" * 2500, chunk_size=800, chunk_overlap=100)
    assert all(len(chunk) <= 800 for chunk in chunks)
    assert len(chunks) >= 3


class FakeMemorySession:
    def __init__(self, rows):
        self.rows = rows

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def execute(self, stmt):
        return self

    def scalars(self):
        return SimpleList(self.rows)

    async def commit(self):
        return None


class SimpleList:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class FakeSessionFactory:
    def __init__(self, session):
        self.session = session

    def __call__(self):
        return self

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *_args):
        return False


def _memory(user_id, org_id, content, embedding=None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        organization_id=org_id,
        content=content,
        kind="fact",
        importance=0.5,
        source="user",
        embedding=embedding or [1.0, 0.0, 0.0],
        expires_at=None,
        last_accessed_at=None,
    )


def test_memory_retrieval_is_tenant_and_user_scoped(monkeypatch):
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    rows = [
        _memory(user_a, org_a, "A 的记忆"),
        _memory(user_a, org_b, "A 在另一租户的记忆"),
        _memory(user_b, org_a, "B 的记忆"),
    ]
    session = FakeMemorySession(rows)
    monkeypatch.setattr(
        memory_service,
        "async_session_factory",
        FakeSessionFactory(session),
    )

    async def fake_embed(_text):
        return [1.0, 0.0, 0.0]

    monkeypatch.setattr(memory_service, "embed_text", fake_embed)

    result = asyncio.run(
        memory_service.retrieve_memories(
            user_id=user_a,
            organization_id=org_a,
            query="记忆",
            top_k=5,
        )
    )
    assert [item["content"] for item in result] == ["A 的记忆"]

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

from app.rag import retrieval


class FakeScalarResult:
    def __init__(self, values):
        self.values = values

    def scalars(self):
        return SimpleNamespace(all=lambda: self.values)


class FakeSession:
    def __init__(self, documents):
        self.documents = documents

    async def execute(self, _stmt):
        return FakeScalarResult(self.documents)


class FakeSessionFactory:
    def __init__(self, session):
        self.session = session

    def __call__(self):
        return self

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *_args):
        return False


def make_doc(name, content, embedding):
    return SimpleNamespace(name=name, content=content, embedding=embedding)


def test_retrieve_documents_returns_empty_for_blank_query(monkeypatch):
    called = []

    async def fake_embed(_text):
        called.append(True)
        return []

    monkeypatch.setattr(retrieval, "embed_text", fake_embed)

    result = asyncio.run(retrieval.retrieve_documents("", None, top_k=3))

    assert result == []
    assert called == []


def test_retrieve_documents_scores_vector_and_keywords(monkeypatch):
    org_id = uuid.uuid4()
    docs = [
        make_doc("b.md", "nothing relevant", [0.1]),
        make_doc("a.md", "hello world", [0.2]),
    ]
    session = FakeSession(docs)
    monkeypatch.setattr(retrieval, "async_session_factory", FakeSessionFactory(session))

    async def fake_embed(_text):
        return [0.2]

    monkeypatch.setattr(retrieval, "embed_text", fake_embed)
    monkeypatch.setattr(retrieval, "cosine", lambda q, d: 1.0 if d else 0.0)

    result = asyncio.run(retrieval.retrieve_documents("hello world", org_id, top_k=1))

    assert len(result) == 1
    assert result[0]["name"] == "a.md"
    assert result[0]["content"] == "hello world"

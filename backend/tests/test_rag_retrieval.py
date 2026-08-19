from __future__ import annotations

import asyncio
import uuid

from app.rag import retrieval


def test_retrieve_documents_returns_empty_for_blank_query(monkeypatch):
    called = []

    async def fake_embed(_text):
        called.append(True)
        return []

    monkeypatch.setattr(retrieval, "embed_text", fake_embed)

    result = asyncio.run(retrieval.retrieve_documents("", None, top_k=3))

    assert result == []
    assert called == []


def test_retrieve_documents_dedupes_chunks_to_documents(monkeypatch):
    org_id = uuid.uuid4()

    async def fake_embed(_text):
        return [0.2]

    async def fake_search(_vector, *, organization_id, top_k):
        assert organization_id == org_id
        return [
            {
                "document_id": "d1",
                "name": "a.md",
                "content": "hello world",
                "score": 1.0,
            },
            {
                "document_id": "d1",
                "name": "a.md",
                "content": "second chunk",
                "score": 0.9,
            },
            {
                "document_id": "d2",
                "name": "b.md",
                "content": "nothing relevant",
                "score": 0.5,
            },
        ]

    monkeypatch.setattr(retrieval, "embed_text", fake_embed)
    monkeypatch.setattr(retrieval, "search_chunks", fake_search)

    result = asyncio.run(retrieval.retrieve_documents("hello world", org_id, top_k=1))

    assert len(result) == 1
    assert result[0]["name"] == "a.md"

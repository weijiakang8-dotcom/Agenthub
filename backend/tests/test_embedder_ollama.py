from __future__ import annotations

import asyncio

from app.rag import embedder


class FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"embeddings": [[1.0, 2.0]]}


class FakeClient:
    def __init__(self, *args, **kwargs) -> None:
        self.posted_url = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def post(self, url: str, json: dict | None = None):
        self.posted_url = url
        self.posted_json = json
        return FakeResponse()


def test_ollama_embedding_calls_api_and_normalizes(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(embedder.httpx, "AsyncClient", lambda *a, **k: client)
    monkeypatch.setattr(embedder.settings, "EMBEDDING_PROVIDER", "ollama")
    monkeypatch.setattr(
        embedder.settings, "EMBEDDING_BASE_URL", "http://embedding:11434"
    )
    monkeypatch.setattr(embedder.settings, "EMBEDDING_MODEL", "nomic-embed-text")
    monkeypatch.setattr(embedder.settings, "EMBEDDING_DIMENSION", 2)

    vector = asyncio.run(embedder.embed_text("hello"))

    assert client.posted_url == "http://embedding:11434/api/embed"
    assert client.posted_json == {
        "model": "nomic-embed-text",
        "input": "hello",
    }
    assert len(vector) == 2
    assert abs(sum(v * v for v in vector) - 1.0) < 1e-9


def test_ollama_dimension_mismatch_raises(monkeypatch):
    class WrongResponse(FakeResponse):
        def json(self) -> dict:
            return {"embeddings": [[1.0, 2.0, 3.0]]}

    class WrongClient(FakeClient):
        async def post(self, url: str, json: dict | None = None):
            self.posted_url = url
            return WrongResponse()

    monkeypatch.setattr(embedder.httpx, "AsyncClient", lambda *a, **k: WrongClient())
    monkeypatch.setattr(embedder.settings, "EMBEDDING_PROVIDER", "ollama")
    monkeypatch.setattr(embedder.settings, "EMBEDDING_DIMENSION", 2)

    try:
        asyncio.run(embedder.embed_text("hello"))
    except RuntimeError as exc:
        assert "dimension mismatch" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")

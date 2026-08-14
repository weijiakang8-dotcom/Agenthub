from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
from typing import Any

import redis.asyncio as aioredis
from prometheus_client import Counter

from app.config import settings

CACHE_HITS = Counter("cache_hits_total", "Semantic cache hits")
CACHE_MISSES = Counter("cache_misses_total", "Semantic cache misses")
TOKENS_SAVED = Counter("tokens_saved_total", "Estimated tokens saved by semantic cache")

_CACHE_KEY = "agenthub:semantic_cache"
_MAX_ENTRIES = 500
_model = None


class _HashEmbedder:
    """轻量级本地嵌入器：模型不可用时的兜底方案。"""

    def encode(self, texts: list[str], dims: int = 384) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            vec = [0.0] * dims
            tokens = re.findall(r"[a-zA-Z0-9\u4e00-\u9fff]+", text.lower())
            for i in range(len(tokens)):
                for n in (1, 2, 3):
                    gram = " ".join(tokens[i : i + n])
                    idx = int.from_bytes(hashlib.md5(gram.encode()).digest()[:4], "little") % dims
                    vec[idx] += 1.0
            norm = math.sqrt(sum(x * x for x in vec)) or 1.0
            vectors.append([x / norm for x in vec])
        return vectors


def _load_model():
    global _model
    if _model is not None:
        return _model
    try:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer("all-MiniLM-L6-v2")
    except Exception:  # noqa: BLE001
        _model = _HashEmbedder()
    return _model


async def _embed(text: str) -> list[float]:
    model = _load_model()
    vectors = await asyncio.to_thread(model.encode, [text])
    vector = vectors[0].tolist() if hasattr(vectors[0], "tolist") else list(vectors[0])
    norm = math.sqrt(sum(x * x for x in vector)) or 1.0
    return [x / norm for x in vector]


def _redis() -> aioredis.Redis:
    return aioredis.from_url(settings.REDIS_URL, decode_responses=True)


async def get_cached_response(query: str, threshold: float = 0.85) -> str | None:
    embedding = await _embed(query)
    client = _redis()
    try:
        entries = await client.lrange(_CACHE_KEY, 0, -1)
        best: tuple[float, dict[str, Any]] | None = None
        for raw in entries:
            try:
                item = json.loads(raw)
            except json.JSONDecodeError:
                continue
            cosine = sum(a * b for a, b in zip(embedding, item.get("embedding", [])))
            if best is None or cosine > best[0]:
                best = (cosine, item)

        if best is not None and best[0] >= threshold:
            CACHE_HITS.inc()
            TOKENS_SAVED.inc(500)
            return best[1]["response"]

        CACHE_MISSES.inc()
        return None
    finally:
        await client.aclose()


async def set_cached_response(query: str, response: str) -> None:
    embedding = await _embed(query)
    client = _redis()
    try:
        await client.rpush(
            _CACHE_KEY,
            json.dumps(
                {"query": query, "response": response, "embedding": embedding},
                ensure_ascii=False,
            ),
        )
        await client.ltrim(_CACHE_KEY, -_MAX_ENTRIES, -1)
    finally:
        await client.aclose()

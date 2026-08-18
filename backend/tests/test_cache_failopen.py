from __future__ import annotations

import asyncio
import logging
import time
import uuid

from app.core import cache

ORG_A = uuid.uuid4()
ORG_B = uuid.uuid4()


class FakeRedis:
    def __init__(self, read_error: bool = False, write_error: bool = False):
        self.lists: dict[str, list] = {}
        self.expired: dict[str, int] = {}
        self.read_error = read_error
        self.write_error = write_error

    async def lrange(self, key, _start, _end):
        if self.read_error:
            raise ConnectionError("redis read failed")
        return list(self.lists.get(key, []))

    async def rpush(self, key, *values):
        if self.write_error:
            raise ConnectionError("redis write failed")
        self.lists.setdefault(key, []).extend(values)
        return len(self.lists[key])

    async def ltrim(self, key, start, stop):
        if self.write_error:
            raise ConnectionError("redis write failed")
        items = self.lists.get(key, [])
        self.lists[key] = items[start:] if stop == -1 else items[start : stop + 1]

    async def expire(self, key, seconds):
        if self.write_error:
            raise ConnectionError("redis write failed")
        self.expired[key] = seconds

    async def aclose(self):
        return None


async def _fake_embed(_text):
    return [1.0]


def _get(query, org, model=None, ctx=None):
    return asyncio.run(
        cache.get_cached_response(
            query,
            organization_id=org,
            model=model,
            context_digest=ctx,
        )
    )


def _set(query, response, org, model=None, ctx=None):
    asyncio.run(
        cache.set_cached_response(
            query,
            response,
            organization_id=org,
            model=model,
            context_digest=ctx,
        )
    )


def _patch_redis(monkeypatch, **kwargs):
    fake = FakeRedis(**kwargs)
    monkeypatch.setattr(cache, "_redis", lambda: fake)
    return fake


def test_embedding_model_unavailable_is_bounded_cache_miss(monkeypatch, caplog):
    _patch_redis(monkeypatch)

    def unavailable():
        raise RuntimeError("sentence transformer unavailable")

    monkeypatch.setattr(cache, "_load_model", unavailable)
    with caplog.at_level(logging.WARNING, logger="app.core.cache"):
        start = time.monotonic()
        result = _get("问题", ORG_A, model="m")
        elapsed = time.monotonic() - start

    assert result is None
    assert elapsed < 1.0
    assert any("cache miss" in record.message for record in caplog.records)


def test_embedding_timeout_is_bounded_cache_miss(monkeypatch, caplog):
    _patch_redis(monkeypatch)
    monkeypatch.setattr(cache, "_EMBED_TIMEOUT_SECONDS", 0.05)

    def slow_load():
        time.sleep(0.5)
        return "model"

    monkeypatch.setattr(cache, "_load_model", slow_load)
    with caplog.at_level(logging.WARNING, logger="app.core.cache"):
        start = time.monotonic()
        result = _get("问题", ORG_A, model="m")
        elapsed = time.monotonic() - start

    assert result is None
    assert elapsed < 0.4
    assert any("timed out" in record.message for record in caplog.records)


def test_embedding_exception_is_cache_miss_and_never_raises(monkeypatch, caplog):
    _patch_redis(monkeypatch)

    class BrokenModel:
        def encode(self, texts):
            raise RuntimeError("encode failed")

    monkeypatch.setattr(cache, "_load_model", lambda: BrokenModel())
    with caplog.at_level(logging.WARNING, logger="app.core.cache"):
        assert _get("问题", ORG_A, model="m") is None
        _set("问题", "答案", ORG_A, model="m")

    assert any("cache miss" in record.message for record in caplog.records)


def test_redis_read_failure_is_cache_miss(monkeypatch):
    _patch_redis(monkeypatch, read_error=True)
    monkeypatch.setattr(cache, "_embed", _fake_embed)

    assert _get("问题", ORG_A, model="m") is None


def test_redis_write_failure_never_raises(monkeypatch):
    _patch_redis(monkeypatch, write_error=True)
    monkeypatch.setattr(cache, "_embed", _fake_embed)

    _set("问题", "答案", ORG_A, model="m")


def test_semantic_cache_disabled_is_direct_cache_miss(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(cache, "_SEMANTIC_CACHE_ENABLED", False)
    monkeypatch.setattr(cache, "_embed", lambda _text: calls.append("embed") or [1.0])
    monkeypatch.setattr(cache, "_redis", lambda: calls.append("redis"))

    assert _get("问题", ORG_A, model="m") is None
    _set("问题", "答案", ORG_A, model="m")
    assert calls == []


def test_cache_hit_happy_path_preserved(monkeypatch):
    _patch_redis(monkeypatch)
    monkeypatch.setattr(cache, "_embed", _fake_embed)

    _set("问题", "答案", ORG_A, model="m", ctx="ctx-1")
    assert _get("问题", ORG_A, model="m", ctx="ctx-1") == "答案"
    assert _get("问题", ORG_B, model="m", ctx="ctx-1") is None

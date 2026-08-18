from __future__ import annotations

import asyncio
import json
import uuid

from app.core import cache

ORG_A = uuid.uuid4()
ORG_B = uuid.uuid4()


class FakeRedis:
    def __init__(self):
        self.lists: dict[str, list] = {}
        self.expired: dict[str, int] = {}

    async def lrange(self, key, _start, _end):
        return list(self.lists.get(key, []))

    async def rpush(self, key, *values):
        self.lists.setdefault(key, []).extend(values)
        return len(self.lists[key])

    async def ltrim(self, key, start, stop):
        items = self.lists.get(key, [])
        self.lists[key] = items[start:] if stop == -1 else items[start : stop + 1]

    async def expire(self, key, seconds):
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


def _patch(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(cache, "_redis", lambda: fake)
    monkeypatch.setattr(cache, "_embed", _fake_embed)
    return fake


def test_cache_is_isolated_across_tenants(monkeypatch):
    _patch(monkeypatch)

    _set("相同问题", "A 的答案", ORG_A, model="m")

    assert _get("相同问题", ORG_A, model="m") == "A 的答案"
    assert _get("相同问题", ORG_B, model="m") is None


def test_cache_does_not_cross_models(monkeypatch):
    _patch(monkeypatch)

    _set("问题", "答案", ORG_A, model="gpt")

    assert _get("问题", ORG_A, model="deepseek") is None
    assert _get("问题", ORG_A, model="gpt") == "答案"


def test_cache_does_not_cross_conversation_context(monkeypatch):
    _patch(monkeypatch)

    _set("问题", "答案", ORG_A, model="m", ctx="ctx-1")

    assert _get("问题", ORG_A, model="m", ctx="ctx-2") is None
    assert _get("问题", ORG_A, model="m", ctx="ctx-1") == "答案"


def test_cache_org_filter_is_defense_in_depth(monkeypatch):
    fake = _patch(monkeypatch)

    # 模拟异常写入：往 A 的 key 里塞了一条属于 B 的缓存
    key = cache._cache_key(ORG_A)
    fake.lists[key] = [
        json.dumps(
            {
                "query": "问题",
                "response": "B 的数据",
                "embedding": [1.0],
                "organization_id": str(ORG_B),
                "model": "m",
                "context_digest": None,
            }
        )
    ]

    assert _get("问题", ORG_A, model="m") is None


def test_cache_sets_ttl(monkeypatch):
    fake = _patch(monkeypatch)

    _set("问题", "答案", ORG_A, model="m")

    key = cache._cache_key(ORG_A)
    assert fake.expired.get(key) == cache._CACHE_TTL_SECONDS


def test_cache_returns_none_for_blank_query(monkeypatch):
    _patch(monkeypatch)

    assert _get("", ORG_A, model="m") is None

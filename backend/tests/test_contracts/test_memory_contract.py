from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

import pytest
from app.memory import service as memory_service


def test_recall_top_k_default_is_three():
    import inspect

    signature = inspect.signature(memory_service.retrieve_memories)
    assert signature.parameters["top_k"].default == 3


def test_memory_service_has_no_auto_extract_entry():
    public = {
        name
        for name in dir(memory_service)
        if not name.startswith("_") and callable(getattr(memory_service, name))
    }
    assert "extract_memory" not in public
    assert "auto_memorize" not in public


class _FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return _SimpleList(self.rows)


class _SimpleList:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class _FakeSession:
    def __init__(self, store):
        self.store = store

    async def execute(self, _stmt):
        return _FakeResult(list(self.store))

    async def get(self, _model, memory_id):
        return next((memory for memory in self.store if memory.id == memory_id), None)

    def add(self, memory):
        if getattr(memory, "id", None) is None:
            memory.id = uuid.uuid4()
        self.store.append(memory)

    async def commit(self):
        return None

    async def refresh(self, _memory):
        return None


class _FakeSessionFactory:
    def __init__(self, store):
        self.store = store

    def __call__(self):
        return self

    async def __aenter__(self):
        return _FakeSession(self.store)

    async def __aexit__(self, *_args):
        return False


def _memory(user_id, org_id, content, memory_id=None, importance=0.5):
    return SimpleNamespace(
        id=memory_id or uuid.uuid4(),
        user_id=user_id,
        organization_id=org_id,
        content=content,
        kind="fact",
        importance=importance,
        source="user",
        embedding=[1.0, 0.0, 0.0],
        expires_at=None,
        last_accessed_at=None,
    )


def test_update_action_exists_and_merges():
    assert callable(getattr(memory_service, "update_memory", None))

    user_id = uuid.uuid4()
    org_id = uuid.uuid4()
    memory = _memory(user_id, org_id, "我叫魏家康")
    store = [memory]

    async def fake_embed(_text):
        return [0.0, 1.0, 0.0]

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        memory_service,
        "async_session_factory",
        _FakeSessionFactory(store),
    )
    monkeypatch.setattr(memory_service, "embed_text", fake_embed)

    updated = asyncio.run(
        memory_service.update_memory(
            memory_id=memory.id,
            user_id=user_id,
            content="我叫魏家豪",
            importance=0.9,
            organization_id=org_id,
        )
    )
    assert updated is memory
    assert updated.content == "我叫魏家豪"
    assert updated.embedding == [0.0, 1.0, 0.0]
    assert updated.importance == 0.9

    # 租户/用户隔离：无权者不能 UPDATE
    other_user = uuid.uuid4()
    other_org = uuid.uuid4()
    assert (
        asyncio.run(
            memory_service.update_memory(
                memory_id=memory.id,
                user_id=other_user,
                content="x",
                organization_id=org_id,
            )
        )
        is None
    )
    assert (
        asyncio.run(
            memory_service.update_memory(
                memory_id=memory.id,
                user_id=user_id,
                content="x",
                organization_id=other_org,
            )
        )
        is None
    )

    # 相似内容写入 → 合并更新，不追加重复条目
    merged = asyncio.run(
        memory_service.add_memory(
            user_id=user_id,
            organization_id=org_id,
            content="请记住我叫魏家豪",
            importance=0.6,
        )
    )
    assert merged.id == memory.id
    assert len(store) == 1
    monkeypatch.undo()


def test_write_deduplicates_similar_facts():
    user_id = uuid.uuid4()
    org_id = uuid.uuid4()
    store: list = []

    async def fake_embed(text):
        # “魏家康”相关内容归一到同一向量，其余不同
        return [1.0, 0.0, 0.0] if "魏家康" in text else [0.0, 1.0, 0.0]

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        memory_service,
        "async_session_factory",
        _FakeSessionFactory(store),
    )
    monkeypatch.setattr(memory_service, "embed_text", fake_embed)

    first = asyncio.run(
        memory_service.add_memory(
            user_id=user_id,
            organization_id=org_id,
            content="记住我叫魏家康",
        )
    )
    second = asyncio.run(
        memory_service.add_memory(
            user_id=user_id,
            organization_id=org_id,
            content="我叫魏家康（纠正）",
        )
    )
    assert first.id == second.id  # 相似合并，不新增重复
    assert len(store) == 1
    assert store[0].content == "我叫魏家康（纠正）"

    unrelated = asyncio.run(
        memory_service.add_memory(
            user_id=user_id,
            organization_id=org_id,
            content="我喜欢蓝色",
        )
    )
    assert unrelated.id != first.id
    assert len(store) == 2
    monkeypatch.undo()

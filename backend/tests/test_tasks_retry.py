from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

from app.engine import tasks
from app.models.enums import ExecutionStatus


class FakeSession:
    def __init__(self, execution):
        self.execution = execution
        self.commits = 0

    async def get(self, _model, _obj_id):
        return self.execution

    async def commit(self):
        self.commits += 1


class FakeSessionFactory:
    def __init__(self, session):
        self.session = session

    def __call__(self):
        return self

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *_args):
        return False


class FakeRedis:
    def __init__(self):
        self.items = []

    async def rpush(self, _key, value):
        self.items.append(value)

    async def aclose(self):
        return None


def make_execution(status):
    return SimpleNamespace(
        id=uuid.uuid4(),
        status=status,
        error_message=None,
        completed_at=None,
    )


def test_fail_execution_and_push_dlq(monkeypatch):
    execution = make_execution(ExecutionStatus.RUNNING)
    session = FakeSession(execution)
    redis = FakeRedis()
    monkeypatch.setattr(tasks, "async_session_factory", FakeSessionFactory(session))
    monkeypatch.setattr(tasks.aioredis, "from_url", lambda *_args, **_kwargs: redis)

    asyncio.run(tasks._fail_execution_and_push_dlq(str(execution.id), "boom"))

    assert execution.status == ExecutionStatus.FAILED
    assert execution.error_message == "boom"
    assert session.commits == 1
    assert redis.items

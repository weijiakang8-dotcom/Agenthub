from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import select

from app.database import async_session_factory
from app.engine import event_bus
from app.models import Execution, ExecutionEvent, Organization, User, Workflow
from app.models.enums import ExecutionStatus


class BrokenRedis:
    async def publish(self, *_args):
        raise ConnectionError("redis unavailable")

    async def aclose(self):
        return None


async def create_execution() -> tuple[uuid.UUID, list[tuple[type, uuid.UUID]]]:
    async with async_session_factory() as session:
        org = Organization(name="Events", slug=f"events-{uuid.uuid4().hex}")
        session.add(org)
        await session.flush()
        user = User(
            email=f"events-{uuid.uuid4().hex}@example.test",
            password_hash="test",
            full_name="Events",
            organization_id=org.id,
        )
        session.add(user)
        await session.flush()
        workflow = Workflow(
            name="events",
            description="events",
            agent_chain=[],
            created_by=str(user.id),
            organization_id=org.id,
        )
        session.add(workflow)
        await session.flush()
        execution = Execution(
            workflow_id=workflow.id,
            user_input="test",
            status=ExecutionStatus.RUNNING,
            organization_id=org.id,
            user_id=user.id,
        )
        session.add(execution)
        await session.commit()
        return execution.id, [
            (Execution, execution.id),
            (Workflow, workflow.id),
            (User, user.id),
            (Organization, org.id),
        ]


async def cleanup(objects):
    async with async_session_factory() as session:
        for model, obj_id in objects:
            obj = await session.get(model, obj_id)
            if obj is not None:
                await session.delete(obj)
        await session.commit()


def test_events_remain_durable_when_redis_publish_fails(monkeypatch):
    async def run():
        execution_id, objects = await create_execution()
        monkeypatch.setattr(
            event_bus.aioredis, "from_url", lambda *_args, **_kwargs: BrokenRedis()
        )
        try:
            await event_bus.publish_execution_event(
                str(execution_id), {"event": "step", "node": "test"}
            )
            async with async_session_factory() as session:
                events = list(
                    (
                        await session.execute(
                            select(ExecutionEvent).where(
                                ExecutionEvent.execution_id == execution_id
                            )
                        )
                    ).scalars()
                )
            assert len(events) == 1
            assert events[0].sequence == 1
            assert events[0].payload["event"] == "step"
        finally:
            await cleanup(objects)

    asyncio.run(run())


def test_concurrent_events_have_unique_ordered_sequences(monkeypatch):
    async def run():
        execution_id, objects = await create_execution()
        monkeypatch.setattr(
            event_bus.aioredis, "from_url", lambda *_args, **_kwargs: BrokenRedis()
        )
        try:
            await asyncio.gather(
                *(
                    event_bus.publish_execution_event(
                        str(execution_id), {"event": "step", "index": index}
                    )
                    for index in range(8)
                )
            )
            async with async_session_factory() as session:
                events = list(
                    (
                        await session.execute(
                            select(ExecutionEvent)
                            .where(ExecutionEvent.execution_id == execution_id)
                            .order_by(ExecutionEvent.sequence)
                        )
                    ).scalars()
                )
            assert [event.sequence for event in events] == list(range(1, 9))
            assert len({event.payload["event_id"] for event in events}) == 8
        finally:
            await cleanup(objects)

    asyncio.run(run())

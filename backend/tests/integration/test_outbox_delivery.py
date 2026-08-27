from __future__ import annotations

import asyncio
import uuid

from app.database import async_session_factory
from app.engine.outbox import dispatch_outbox_batch, enqueue_outbox_event
from app.models import OutboxEvent


async def _create_event(event_type: str = "test") -> uuid.UUID:
    async with async_session_factory() as session:
        event = await enqueue_outbox_event(session, event_type, {"value": "ok"})
        await session.commit()
        return event.id


async def _delete_event(event_id: uuid.UUID) -> None:
    async with async_session_factory() as session:
        event = await session.get(OutboxEvent, event_id)
        if event is not None:
            await session.delete(event)
            await session.commit()


def test_concurrent_dispatchers_publish_event_once():
    async def run() -> None:
        event_id = await _create_event()
        calls: list[str] = []
        try:

            def publish(value: str) -> None:
                calls.append(value)

            async def dispatch() -> dict[str, int]:
                async with async_session_factory() as session:
                    return await dispatch_outbox_batch(session, {"test": publish})

            results = await asyncio.gather(dispatch(), dispatch())
            assert sum(item["published"] for item in results) == 1
            assert calls == ["ok"]
        finally:
            await _delete_event(event_id)

    asyncio.run(run())


def test_committed_event_survives_dispatcher_restart():
    async def run() -> None:
        event_id = await _create_event()
        calls: list[str] = []
        try:
            # Simulate process exit after the business transaction committed but before
            # any broker publish attempt. A new dispatcher session must find the row.
            async with async_session_factory() as restarted_session:
                result = await dispatch_outbox_batch(
                    restarted_session, {"test": lambda value: calls.append(value)}
                )
                assert result == {"published": 1, "failed": 0}

            async with async_session_factory() as session:
                event = await session.get(OutboxEvent, event_id)
                assert event.published_at is not None
                assert event.attempt_count == 0
                assert calls == ["ok"]
        finally:
            await _delete_event(event_id)

    asyncio.run(run())


def test_failed_delivery_is_retried_and_can_recover():
    async def run() -> None:
        event_id = await _create_event()
        try:

            def fail(value: str) -> None:
                assert value == "ok"
                raise RuntimeError("broker unavailable")

            async with async_session_factory() as session:
                result = await dispatch_outbox_batch(session, {"test": fail})
                assert result == {"published": 0, "failed": 1}

            async with async_session_factory() as session:
                event = await session.get(OutboxEvent, event_id)
                assert event.published_at is None
                assert event.attempt_count == 1
                assert event.last_error == "broker unavailable"
                event.available_at = event.created_at
                await session.commit()

            calls: list[str] = []
            async with async_session_factory() as session:
                result = await dispatch_outbox_batch(
                    session, {"test": lambda value: calls.append(value)}
                )
                assert result == {"published": 1, "failed": 0}

            async with async_session_factory() as session:
                event = await session.get(OutboxEvent, event_id)
                assert event.published_at is not None
                assert event.attempt_count == 1
                assert event.last_error is None
                assert calls == ["ok"]
        finally:
            await _delete_event(event_id)

    asyncio.run(run())

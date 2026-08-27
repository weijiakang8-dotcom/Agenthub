from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta

from app.database import async_session_factory
from app.engine.execution_state import (
    acquire_execution_lease,
    heartbeat_execution_lease,
    transition_execution,
)
from app.models import Execution, Organization, User, Workflow, utcnow
from app.models.enums import ExecutionStatus


async def _create_execution() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    async with async_session_factory() as session:
        org = Organization(name="Lease Test", slug=f"lease-{uuid.uuid4().hex}")
        session.add(org)
        await session.flush()
        user = User(
            email=f"lease-{uuid.uuid4().hex}@example.test",
            password_hash="test",
            full_name="Lease Test",
            organization_id=org.id,
            role="admin",
        )
        session.add(user)
        await session.flush()
        workflow = Workflow(
            name="lease",
            description="lease",
            agent_chain=[],
            created_by=str(user.id),
            organization_id=org.id,
        )
        session.add(workflow)
        await session.flush()
        execution = Execution(
            workflow_id=workflow.id,
            user_input="test",
            organization_id=org.id,
            user_id=user.id,
        )
        session.add(execution)
        await session.commit()
        return execution.id, workflow.id, user.id, org.id


async def _cleanup(ids: tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]) -> None:
    execution_id, workflow_id, user_id, org_id = ids
    async with async_session_factory() as session:
        for model, obj_id in (
            (Execution, execution_id),
            (Workflow, workflow_id),
            (User, user_id),
            (Organization, org_id),
        ):
            obj = await session.get(model, obj_id)
            if obj is not None:
                await session.delete(obj)
        await session.commit()


def test_only_one_worker_acquires_execution_lease():
    async def run() -> None:
        ids = await _create_execution()
        try:

            async def acquire(owner: str) -> bool:
                async with async_session_factory() as session:
                    won = await acquire_execution_lease(session, ids[0], owner)
                    await session.commit()
                    return won

            results = await asyncio.gather(acquire("worker-a"), acquire("worker-b"))
            assert sorted(results) == [False, True]
            async with async_session_factory() as session:
                execution = await session.get(Execution, ids[0])
                assert execution.status == ExecutionStatus.RUNNING
                assert execution.run_attempt == 1
                assert execution.lease_owner in {"worker-a", "worker-b"}
        finally:
            await _cleanup(ids)

    asyncio.run(run())


def test_heartbeat_extends_only_current_owner_lease():
    async def run() -> None:
        ids = await _create_execution()
        try:
            async with async_session_factory() as session:
                assert await acquire_execution_lease(session, ids[0], "worker-a")
                await session.commit()
            async with async_session_factory() as session:
                execution = await session.get(Execution, ids[0])
                old_expiry = execution.lease_expires_at
            async with async_session_factory() as session:
                assert not await heartbeat_execution_lease(
                    session, ids[0], "worker-b", duration=timedelta(minutes=10)
                )
                assert await heartbeat_execution_lease(
                    session, ids[0], "worker-a", duration=timedelta(minutes=10)
                )
                await session.commit()
            async with async_session_factory() as session:
                execution = await session.get(Execution, ids[0])
                assert execution.lease_expires_at > old_expiry
                assert execution.heartbeat_at <= utcnow()
        finally:
            await _cleanup(ids)

    asyncio.run(run())


def test_duplicate_delivery_after_broker_ack_is_suppressed_by_lease():
    async def run() -> None:
        ids = await _create_execution()
        try:
            async with async_session_factory() as first_session:
                assert await acquire_execution_lease(
                    first_session, ids[0], "first-delivery"
                )
                await first_session.commit()

            # Simulate redelivery after the broker accepted the first task but before
            # its Outbox row was marked published. The duplicate must not run.
            async with async_session_factory() as duplicate_session:
                assert not await acquire_execution_lease(
                    duplicate_session, ids[0], "duplicate-delivery"
                )
                await duplicate_session.commit()

            async with async_session_factory() as session:
                execution = await session.get(Execution, ids[0])
                assert execution.status == ExecutionStatus.RUNNING
                assert execution.lease_owner == "first-delivery"
                assert execution.run_attempt == 1
        finally:
            await _cleanup(ids)

    asyncio.run(run())


def test_execution_transition_uses_compare_and_swap():
    async def run() -> None:
        ids = await _create_execution()
        try:

            async def transition() -> bool:
                async with async_session_factory() as session:
                    changed = await transition_execution(
                        session,
                        ids[0],
                        ExecutionStatus.PENDING,
                        ExecutionStatus.RUNNING,
                    )
                    await session.commit()
                    return changed

            results = await asyncio.gather(transition(), transition())
            assert sorted(results) == [False, True]
            async with async_session_factory() as session:
                execution = await session.get(Execution, ids[0])
                assert execution.status == ExecutionStatus.RUNNING
        finally:
            await _cleanup(ids)

    asyncio.run(run())

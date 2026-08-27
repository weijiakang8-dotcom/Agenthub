from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta

from app.database import async_session_factory
from app.engine.tasks import mark_stale_executions_task
from app.models import Execution, Organization, User, Workflow, utcnow
from app.models.enums import ExecutionStatus


async def create_execution(
    *, expired: bool
) -> tuple[uuid.UUID, list[tuple[type, uuid.UUID]]]:
    async with async_session_factory() as session:
        org = Organization(name="Recovery", slug=f"recovery-{uuid.uuid4().hex}")
        session.add(org)
        await session.flush()
        user = User(
            email=f"recovery-{uuid.uuid4().hex}@example.test",
            password_hash="test",
            full_name="Recovery",
            organization_id=org.id,
        )
        session.add(user)
        await session.flush()
        workflow = Workflow(
            name="recovery",
            description="recovery",
            agent_chain=[],
            created_by=str(user.id),
            organization_id=org.id,
        )
        session.add(workflow)
        await session.flush()
        now = utcnow()
        execution = Execution(
            workflow_id=workflow.id,
            user_input="test",
            status=ExecutionStatus.RUNNING,
            organization_id=org.id,
            user_id=user.id,
            lease_owner="dead-worker" if expired else "live-worker",
            lease_expires_at=now
            + (timedelta(seconds=-1) if expired else timedelta(minutes=5)),
            heartbeat_at=now,
        )
        session.add(execution)
        await session.commit()
        return execution.id, [
            (Execution, execution.id),
            (Workflow, workflow.id),
            (User, user.id),
            (Organization, org.id),
        ]


async def cleanup(objects: list[tuple[type, uuid.UUID]]) -> None:
    async with async_session_factory() as session:
        for model, obj_id in objects:
            obj = await session.get(model, obj_id)
            if obj is not None:
                await session.delete(obj)
        await session.commit()


def test_worker_crash_recovery_only_fails_expired_lease():
    async def run() -> None:
        expired_id, expired_objects = await create_execution(expired=True)
        active_id, active_objects = await create_execution(expired=False)
        try:
            changed = await asyncio.to_thread(mark_stale_executions_task.run)
            assert changed == 1
            async with async_session_factory() as session:
                expired = await session.get(Execution, expired_id)
                active = await session.get(Execution, active_id)
                assert expired.status == ExecutionStatus.FAILED
                assert expired.error_message == "Execution lease expired"
                assert expired.completed_at is not None
                assert expired.lease_owner is None
                assert expired.lease_expires_at is None
                assert active.status == ExecutionStatus.RUNNING
                assert active.lease_owner == "live-worker"
        finally:
            await cleanup(expired_objects)
            await cleanup(active_objects)

    asyncio.run(run())

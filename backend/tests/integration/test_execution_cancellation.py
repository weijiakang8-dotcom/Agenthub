from __future__ import annotations

import asyncio
import uuid

import pytest

from app.database import async_session_factory
from app.engine.cancellation import ExecutionCancelled, ensure_execution_active
from app.models import Execution, Organization, User, Workflow
from app.models.enums import ExecutionStatus


async def create_execution(
    status: ExecutionStatus,
) -> tuple[uuid.UUID, list[tuple[type, uuid.UUID]]]:
    async with async_session_factory() as session:
        org = Organization(name="Cancel", slug=f"cancel-{uuid.uuid4().hex}")
        session.add(org)
        await session.flush()
        user = User(
            email=f"cancel-{uuid.uuid4().hex}@example.test",
            password_hash="test",
            full_name="Cancel",
            organization_id=org.id,
        )
        session.add(user)
        await session.flush()
        workflow = Workflow(
            name="cancel",
            description="cancel",
            agent_chain=[],
            created_by=str(user.id),
            organization_id=org.id,
        )
        session.add(workflow)
        await session.flush()
        execution = Execution(
            workflow_id=workflow.id,
            user_input="test",
            status=status,
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


async def cleanup(objects: list[tuple[type, uuid.UUID]]) -> None:
    async with async_session_factory() as session:
        for model, obj_id in objects:
            obj = await session.get(model, obj_id)
            if obj is not None:
                await session.delete(obj)
        await session.commit()


def test_cancelled_execution_is_observed_at_worker_boundary():
    async def run() -> None:
        execution_id, objects = await create_execution(ExecutionStatus.FAILED)
        try:
            with pytest.raises(ExecutionCancelled, match="no longer active"):
                await ensure_execution_active(execution_id)
        finally:
            await cleanup(objects)

    asyncio.run(run())


def test_running_execution_passes_cancellation_check():
    async def run() -> None:
        execution_id, objects = await create_execution(ExecutionStatus.RUNNING)
        try:
            await ensure_execution_active(execution_id)
        finally:
            await cleanup(objects)

    asyncio.run(run())

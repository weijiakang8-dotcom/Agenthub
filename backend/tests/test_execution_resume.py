from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.routes import executions
from app.models.enums import ExecutionStatus
from app.schemas.execution import ExecutionResume


class FakeSession:
    def __init__(self, get_result=None, execute_result=None):
        self.get_result = get_result
        self.execute_result = execute_result
        self.commits = 0

    async def get(self, _model, _obj_id):
        return self.get_result

    async def execute(self, _stmt):
        return self.execute_result

    async def commit(self):
        self.commits += 1


def make_user(org_id=None):
    return SimpleNamespace(id=uuid.uuid4(), organization_id=org_id)


def make_execution(status, org_id):
    return SimpleNamespace(
        id=uuid.uuid4(),
        workflow_id=uuid.uuid4(),
        status=status,
        organization_id=org_id,
    )


def test_resume_execution_enqueues_once(monkeypatch):
    org_id = uuid.uuid4()
    execution = make_execution(ExecutionStatus.WAITING_FOR_APPROVAL, org_id)
    session = FakeSession(
        get_result=execution,
        execute_result=SimpleNamespace(rowcount=1),
    )
    delayed = []
    monkeypatch.setattr(
        executions.resume_workflow_task,
        "delay",
        lambda execution_id, decision: delayed.append((execution_id, decision)),
    )

    result = asyncio.run(
        executions.resume_execution(
            execution.id,
            ExecutionResume(approved=True),
            session,
            make_user(org_id),
        )
    )

    assert result.status == ExecutionStatus.RUNNING
    assert len(delayed) == 1


def test_resume_execution_rejects_concurrent_update(monkeypatch):
    org_id = uuid.uuid4()
    execution = make_execution(ExecutionStatus.WAITING_FOR_APPROVAL, org_id)
    session = FakeSession(
        get_result=execution,
        execute_result=SimpleNamespace(rowcount=0),
    )
    delayed = []
    monkeypatch.setattr(
        executions.resume_workflow_task,
        "delay",
        lambda *args, **kwargs: delayed.append(args),
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            executions.resume_execution(
                execution.id,
                ExecutionResume(approved=True),
                session,
                make_user(org_id),
            )
        )

    assert exc.value.status_code == 409
    assert delayed == []

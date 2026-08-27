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
        self.added = []

    async def get(self, _model, _obj_id):
        return self.get_result

    async def execute(self, _stmt):
        return self.execute_result

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None

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

    result = asyncio.run(
        executions.resume_execution(
            execution.id,
            ExecutionResume(approved=True),
            session,
            make_user(org_id),
        )
    )

    assert result.status == ExecutionStatus.RUNNING
    assert len(session.added) == 1
    assert session.added[0].event_type == "resume_workflow"
    assert session.added[0].payload["execution_id"] == str(execution.id)


def test_resume_execution_rejects_concurrent_update(monkeypatch):
    org_id = uuid.uuid4()
    execution = make_execution(ExecutionStatus.WAITING_FOR_APPROVAL, org_id)
    session = FakeSession(
        get_result=execution,
        execute_result=SimpleNamespace(rowcount=0),
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
    assert session.added == []


def test_resume_rejects_early_approval_when_not_waiting(monkeypatch):
    org_id = uuid.uuid4()
    execution = make_execution(ExecutionStatus.RUNNING, org_id)
    session = FakeSession(get_result=execution)
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
    assert session.added == []

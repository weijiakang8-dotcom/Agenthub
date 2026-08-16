from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

import pytest

from app.engine import runner
from app.models.enums import ExecutionStatus


class FakeSession:
    def __init__(self, execution=None, workflow=None, rowcount=1):
        self.execution = execution
        self.workflow = workflow
        self.rowcount = rowcount
        self.commits = 0

    async def get(self, model, _obj_id):
        if model.__name__ == "Execution":
            return self.execution
        if model.__name__ == "Workflow":
            return self.workflow
        return None

    async def execute(self, _stmt):
        return SimpleNamespace(rowcount=self.rowcount)

    async def commit(self):
        self.commits += 1


class FakeSessionFactory:
    def __init__(self, sessions):
        self.sessions = list(sessions)

    def __call__(self):
        return self

    async def __aenter__(self):
        return self.sessions.pop(0)

    async def __aexit__(self, *_args):
        return False


def make_workflow(dag_definition=None, agent_chain=None):
    return SimpleNamespace(
        dag_definition=dag_definition,
        agent_chain=agent_chain if agent_chain is not None else [],
    )


def make_execution(status=ExecutionStatus.PENDING, **overrides):
    values = {
        "id": uuid.uuid4(),
        "workflow_id": uuid.uuid4(),
        "status": status,
        "current_step_index": 0,
        "user_input": "hello",
        "final_output": None,
        "error_message": None,
        "organization_id": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_build_steps_from_dag_nodes():
    workflow = make_workflow(
        dag_definition={
            "nodes": [
                {"type": "research", "label": "research"},
                {"type": "condition", "label": "check"},
                {"type": "human_approval", "label": "approve"},
            ]
        }
    )

    steps = asyncio.run(runner._build_steps(FakeSession(), workflow))

    assert [step["role"] for step in steps] == ["research", "analyze", "execute"]
    assert [step["name"] for step in steps] == ["research", "check", "approve"]


def test_build_steps_from_agent_chain():
    agent_ids = [str(uuid.uuid4()) for _ in range(4)]

    class AgentSession:
        async def get(self, _model, agent_id):
            return SimpleNamespace(name=f"agent-{agent_id}", system_prompt="sp")

    workflow = make_workflow(agent_chain=agent_ids)

    steps = asyncio.run(runner._build_steps(AgentSession(), workflow))

    assert [step["role"] for step in steps] == [
        "research",
        "analyze",
        "execute",
        "analyze",
    ]
    assert [step["agent_id"] for step in steps] == agent_ids


def test_build_steps_defaults_to_three_roles():
    steps = asyncio.run(runner._build_steps(FakeSession(), make_workflow()))

    assert [step["role"] for step in steps] == ["research", "analyze", "execute"]


def test_extract_agent_ids_handles_nested_dag():
    chain = {
        "nodes": [
            {"id": "11111111-1111-1111-1111-111111111111"},
            {"agent_id": "22222222-2222-2222-2222-222222222222"},
        ]
    }

    ids = runner._extract_agent_ids(chain)

    assert ids == [
        uuid.UUID("11111111-1111-1111-1111-111111111111"),
        uuid.UUID("22222222-2222-2222-2222-222222222222"),
    ]


def test_run_execution_skips_terminal_or_running_statuses(monkeypatch):
    execution = make_execution(ExecutionStatus.COMPLETED)
    session = FakeSession(execution=execution, workflow=make_workflow())
    monkeypatch.setattr(runner, "async_session_factory", FakeSessionFactory([session]))

    built = []
    monkeypatch.setattr(
        runner,
        "build_graph",
        lambda checkpointer=None, dag=None: built.append(1),
    )

    asyncio.run(runner.run_execution(execution.id))

    assert built == []


def test_run_execution_marks_failed_on_engine_exception(monkeypatch):
    execution = make_execution(ExecutionStatus.PENDING)
    workflow = make_workflow(dag_definition={"nodes": [{"type": "research"}]})
    session = FakeSession(execution=execution, workflow=workflow, rowcount=1)
    monkeypatch.setattr(
        runner,
        "async_session_factory",
        FakeSessionFactory(
            [session, FakeSession(execution=execution, workflow=workflow)]
        ),
    )

    class FailingCheckpointManager:
        def __aenter__(self):
            raise RuntimeError("checkpoint unavailable")

        def __aexit__(self, *_args):
            return False

    monkeypatch.setattr(runner, "get_checkpoint_manager", FailingCheckpointManager)

    events = []

    async def fake_publish(execution_id, event):
        events.append(event)

    monkeypatch.setattr(runner, "publish_execution_event", fake_publish)

    asyncio.run(runner.run_execution(execution.id))

    assert execution.status == ExecutionStatus.FAILED
    assert execution.error_message == "checkpoint unavailable"
    assert events[-1]["event"] == "execution_failed"


def test_run_execution_retryable_error_marks_pending_and_raises(monkeypatch):
    execution = make_execution(ExecutionStatus.PENDING)
    workflow = make_workflow(dag_definition={"nodes": [{"type": "research"}]})
    session = FakeSession(execution=execution, workflow=workflow, rowcount=1)
    monkeypatch.setattr(
        runner,
        "async_session_factory",
        FakeSessionFactory(
            [session, FakeSession(execution=execution, workflow=workflow)]
        ),
    )

    class FailingCheckpointManager:
        def __aenter__(self):
            raise TimeoutError("llm request timed out")

        def __aexit__(self, *_args):
            return False

    monkeypatch.setattr(runner, "get_checkpoint_manager", FailingCheckpointManager)

    events = []

    async def fake_publish(execution_id, event):
        events.append(event)

    monkeypatch.setattr(runner, "publish_execution_event", fake_publish)

    with pytest.raises(runner.ExecutionRetryableError):
        asyncio.run(runner.run_execution(execution.id))

    assert execution.status == ExecutionStatus.PENDING
    assert "timed out" in execution.error_message


def test_run_execution_sets_waiting_for_approval_on_interrupt_result(monkeypatch):
    execution = make_execution(ExecutionStatus.PENDING)
    workflow = make_workflow(dag_definition={"nodes": [{"type": "research"}]})
    session = FakeSession(execution=execution, workflow=workflow, rowcount=1)
    monkeypatch.setattr(
        runner,
        "async_session_factory",
        FakeSessionFactory(
            [session, FakeSession(execution=execution, workflow=workflow)]
        ),
    )

    class FakeManager:
        def __init__(self, saver):
            self.saver = saver

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

    class FakeGraph:
        async def ainvoke(self, *_args, **_kwargs):
            return {
                "__interrupt__": [
                    SimpleNamespace(value={"type": "approval_required", "plan": "ok"})
                ]
            }

    monkeypatch.setattr(runner, "get_checkpoint_manager", lambda: FakeManager(object()))
    monkeypatch.setattr(
        runner, "build_graph", lambda checkpointer=None, dag=None: FakeGraph()
    )

    events = []

    async def fake_publish(execution_id, event):
        events.append(event)

    monkeypatch.setattr(runner, "publish_execution_event", fake_publish)

    asyncio.run(runner.run_execution(execution.id))

    assert execution.status == ExecutionStatus.WAITING_FOR_APPROVAL
    assert execution.checkpoint_data == {
        "interrupt": {"type": "approval_required", "plan": "ok"}
    }
    assert events[-1]["event"] == "waiting_for_approval"

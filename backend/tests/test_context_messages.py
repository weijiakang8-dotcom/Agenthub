from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

from app.engine import runner
from app.models.enums import ExecutionStatus
from langchain_core.messages import AIMessage, HumanMessage


def test_build_context_messages_keeps_recent_turns_and_caps_chars():
    history = [
        {"role": "user", "content": "x" * 8000},
        {"role": "assistant", "content": "y" * 8000},
        {"role": "user", "content": "最后这句不能丢"},
    ]

    result = runner.build_context_messages(history)

    assert result[-1]["content"] == "最后这句不能丢"
    total = sum(len(message["content"]) for message in result)
    assert total <= runner.MAX_CONTEXT_CHARS


def test_build_context_messages_drops_empty_and_invalid_messages():
    history = [
        None,
        {"role": "user", "content": ""},
        {"role": "assistant", "content": "有效回答"},
    ]

    result = runner.build_context_messages(history)

    assert result == [{"role": "assistant", "content": "有效回答"}]


def test_build_initial_messages_preserves_roles_and_appends_current_input():
    context = [
        {"role": "user", "content": "分析新能源行业"},
        {"role": "assistant", "content": "以下是整体分析……"},
    ]

    messages = runner._build_initial_messages(context, "重点看看宁德时代")

    assert isinstance(messages[0], HumanMessage)
    assert messages[0].content == "分析新能源行业"
    assert isinstance(messages[1], AIMessage)
    assert messages[-1] == HumanMessage(content="重点看看宁德时代")


def test_build_initial_messages_without_context_only_has_current_input():
    messages = runner._build_initial_messages(None, "你好")

    assert messages == [HumanMessage(content="你好")]


def test_run_execution_wires_context_into_initial_messages(monkeypatch):
    org = uuid.uuid4()
    context = [
        {"role": "user", "content": "分析新能源行业"},
        {"role": "assistant", "content": "好的，我来分析。"},
    ]
    execution = SimpleNamespace(
        id=uuid.uuid4(),
        workflow_id=uuid.uuid4(),
        status=ExecutionStatus.PENDING,
        current_step_index=0,
        user_input="重点看看宁德时代",
        final_output=None,
        error_message=None,
        organization_id=org,
        context_messages=context,
    )
    workflow = SimpleNamespace(
        dag_definition={"nodes": [{"type": "research"}]},
        agent_chain=[],
    )

    class FakeSession:
        def __init__(self, execution=None, workflow=None, rowcount=1):
            self.execution = execution
            self.workflow = workflow
            self.rowcount = rowcount

        async def get(self, model, _obj_id):
            if model.__name__ == "Execution":
                return self.execution
            if model.__name__ == "Workflow":
                return self.workflow
            return None

        async def execute(self, _stmt):
            return SimpleNamespace(rowcount=self.rowcount)

        async def commit(self):
            return None

    class FakeSessionFactory:
        def __init__(self, sessions):
            self.sessions = list(sessions)

        def __call__(self):
            return self

        async def __aenter__(self):
            return self.sessions.pop(0)

        async def __aexit__(self, *_args):
            return False

    monkeypatch.setattr(
        runner,
        "async_session_factory",
        FakeSessionFactory(
            [
                FakeSession(execution=execution, workflow=workflow, rowcount=1),
                FakeSession(execution=execution, workflow=workflow),
            ]
        ),
    )

    captured = {}

    class FakeGraph:
        async def ainvoke(self, initial_state, **_kwargs):
            captured["messages"] = initial_state["messages"]
            return {"current_step": 1, "final_output": "ok"}

    class FakeManager:
        def __init__(self, saver):
            self.saver = saver

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

    async def noop(*_args, **_kwargs):
        return None

    monkeypatch.setattr(runner, "get_checkpoint_manager", lambda: FakeManager(object()))
    monkeypatch.setattr(
        runner, "build_graph", lambda checkpointer=None, dag=None: FakeGraph()
    )
    monkeypatch.setattr(runner, "record_execution_usage", noop)
    monkeypatch.setattr(runner, "publish_execution_event", noop)
    monkeypatch.setattr(
        runner,
        "evaluate_execution_task",
        SimpleNamespace(delay=lambda *_args, **_kwargs: None),
    )

    asyncio.run(runner.run_execution(execution.id))

    assert isinstance(captured["messages"][0], HumanMessage)
    assert captured["messages"][0].content == "分析新能源行业"
    assert captured["messages"][-1] == HumanMessage(content="重点看看宁德时代")

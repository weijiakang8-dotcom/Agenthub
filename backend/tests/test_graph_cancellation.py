from __future__ import annotations

import asyncio
import uuid

import pytest

from app.engine import graph
from app.engine.cancellation import ExecutionCancelled


def test_capability_node_checks_cancellation_before_side_effect(monkeypatch):
    execution_id = uuid.uuid4()
    capability_called = []

    async def cancelled(candidate):
        assert candidate == execution_id
        raise ExecutionCancelled("cancelled")

    async def capability(*_args, **_kwargs):
        capability_called.append(True)
        return {}

    monkeypatch.setattr("app.engine.cancellation.ensure_execution_active", cancelled)
    original = graph.CAPABILITIES["answer"]
    monkeypatch.setitem(graph.CAPABILITIES, "answer", capability)
    node = graph.make_capability_node("answer")

    with pytest.raises(ExecutionCancelled):
        asyncio.run(node({"execution_id": str(execution_id), "current_step": 0}))

    assert capability_called == []
    monkeypatch.setitem(graph.CAPABILITIES, "answer", original)


def test_parallel_node_checks_cancellation_before_work(monkeypatch):
    execution_id = uuid.uuid4()

    async def cancelled(candidate):
        assert candidate == execution_id
        raise ExecutionCancelled("cancelled")

    monkeypatch.setattr("app.engine.cancellation.ensure_execution_active", cancelled)

    with pytest.raises(ExecutionCancelled):
        asyncio.run(
            graph._parallel_read_only_node(
                {
                    "execution_id": str(execution_id),
                    "current_step": 0,
                    "plan": [],
                }
            )
        )

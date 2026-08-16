from __future__ import annotations

import asyncio

from langchain_core.messages import AIMessage

from app.engine import graph


def test_classify_task_respects_explicit_workflow_steps(monkeypatch):
    called = []

    async def fake_get_llms(*_args, **_kwargs):
        called.append("get_llms")
        return []

    monkeypatch.setattr(graph, "_get_llms", fake_get_llms)

    steps = [
        {"role": "research", "agent_id": "a", "name": "R", "system_prompt": "sp"},
        {"role": "execute", "agent_id": "b", "name": "E", "system_prompt": "sp"},
    ]
    state = {
        "user_input": "hello",
        "steps": steps,
        "respect_workflow_steps": True,
        "loop_count": 0,
    }

    result = asyncio.run(graph.classify_task_node(state))

    assert result["steps"] == steps
    assert called == []


def test_classify_task_uses_automatic_category_when_no_explicit_steps(monkeypatch):
    async def fake_get_llms(*_args, **_kwargs):
        return []

    async def fake_call_llm(*_args, **_kwargs):
        return AIMessage(content="execution")

    monkeypatch.setattr(graph, "_get_llms", fake_get_llms)
    monkeypatch.setattr(graph, "_call_llm_with_fallback", fake_call_llm)

    result = asyncio.run(
        graph.classify_task_node(
            {
                "user_input": "send an email",
                "steps": [],
                "respect_workflow_steps": False,
                "loop_count": 0,
            }
        )
    )

    assert result["steps"][0]["role"] == "execute"

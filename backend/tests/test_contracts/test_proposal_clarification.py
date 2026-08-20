"""副作用提案缺少参数时的澄清契约测试。

契约：side-effect step 的提案模型未给出 tool call（例如缺少收件人邮箱）
时，必须 fail-closed——零副作用、零 provider invocation、不猜测参数；
同时把模型给出的澄清问题原样呈现给用户（audit=proposal_clarification +
clarification 事件），而不是抛出晦涩的 plan_invalid 文案。
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.engine import graph as graph_module
from app.engine.graph import ProposalClarificationError


class _FakeLLM:
    def bind_tools(self, tools):
        return self


def _side_effect_plan() -> dict[str, Any]:
    return {
        "goal": "搜集公告并发送邮件",
        "risk": "SIDE_EFFECT",
        "steps": [
            {
                "step_id": "step_4",
                "capability": "send_email",
                "description": "发送邮件",
                "input_refs": [],
                "output_name": "email_result",
                "depends_on": [],
                "side_effect": True,
                "requires_approval": True,
            }
        ],
        "side_effect_proposals": [],
    }


def _state() -> dict[str, Any]:
    return {
        "messages": [HumanMessage(content="把文档发到我的邮箱")],
        "user_input": "把文档发到我的邮箱",
        "execution_id": "exec-clarify-1",
        "organization_id": None,
        "user_id": None,
    }


def _install(monkeypatch, *, content: str):
    async def fake_get_llms(organization_id, complexity=None, user_id=None):
        return [_FakeLLM()]

    async def fake_invoke(llms, messages, **kwargs):
        return AIMessage(content=content)

    monkeypatch.setattr(graph_module, "_get_llms", fake_get_llms)
    monkeypatch.setattr(graph_module._gateway, "invoke", fake_invoke)


def test_zero_tool_calls_with_text_raises_clarification(monkeypatch):
    _install(monkeypatch, content="请提供收件人邮箱地址。")

    with pytest.raises(ProposalClarificationError) as exc_info:
        asyncio.run(
            graph_module._propose_side_effect_calls(_side_effect_plan(), _state())
        )

    assert exc_info.value.step_id == "step_4"
    assert exc_info.value.text == "请提供收件人邮箱地址。"


def test_zero_tool_calls_without_text_uses_friendly_fallback(monkeypatch):
    _install(monkeypatch, content="")

    with pytest.raises(ProposalClarificationError) as exc_info:
        asyncio.run(
            graph_module._propose_side_effect_calls(_side_effect_plan(), _state())
        )

    assert "缺少必要信息" in exc_info.value.text


def test_plan_node_surfaces_clarification_event_and_audit(monkeypatch):
    _install(monkeypatch, content="请补充收件人邮箱地址。")
    audits: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []

    async def fake_audit(**kwargs):
        audits.append(kwargs)

    async def fake_publish(execution_id, payload):
        events.append(payload)

    monkeypatch.setattr(graph_module, "audit_execution_event", fake_audit)
    monkeypatch.setattr(graph_module, "publish_execution_event", fake_publish)

    state = _state()
    state["plan"] = _side_effect_plan()["steps"]
    state["intent"] = {"category": "ACTION"}
    state["plan_meta"] = {}
    state["budget_used"] = {}
    state["current_step"] = 0
    state["node_outputs"] = {}
    state["revision_count"] = 0
    state["revision_requested"] = False

    with pytest.raises(graph_module.PlanInvalidError):
        asyncio.run(graph_module._plan_node(state))

    assert any(a["action"] == "proposal_clarification" for a in audits)
    clarification = [e for e in events if e.get("event") == "clarification"]
    assert clarification
    assert clarification[0]["message"] == "请补充收件人邮箱地址。"

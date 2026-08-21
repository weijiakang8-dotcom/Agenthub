from __future__ import annotations

import asyncio

from langchain_core.messages import AIMessage, SystemMessage

from app.engine import tools
from app.engine.graph import (
    _final_output_or_fallback,
    _parallel_group,
    _route_after_prepare,
    _route_step,
)
from app.engine.planner import Planner


def test_build_search_query_strips_prefixes():
    assert tools.build_search_query("帮我搜一下北京天气") == "北京天气"
    assert tools.build_search_query("帮我搜索一下 GPT-5.1 最新消息") == (
        "GPT-5.1 最新消息"
    )
    assert tools.build_search_query("查一下 汇率 今天") == "汇率 今天"
    assert tools.build_search_query("hello") == "hello"
    assert tools.build_search_query("") == ""


def test_format_search_results_lists_sources():
    text = tools.format_search_results(
        [
            {
                "title": "GPT-5.1",
                "url": "https://example.com/gpt-5-1",
                "content": "OpenAI released GPT-5.1 in August 2025.",
            }
        ]
    )
    assert "联网搜索结果" in text
    assert "https://example.com/gpt-5-1" in text
    assert "GPT-5.1" in text
    assert "来源" in text


def test_format_search_results_failure_is_honest():
    text = tools.format_search_results(None, error="network blocked")
    assert "未能获取搜索结果" in text
    assert "network blocked" in text
    assert "不得编造" in text


class CaptureGateway:
    def __init__(self) -> None:
        self.messages = None

    async def select(self, **kwargs):
        return [object()]

    async def invoke(self, _llms, messages, **kwargs):
        self.messages = messages
        return AIMessage(
            content=(
                '{"goal":"g","risk":"LOW","steps":['
                '{"step_id":"step_1","capability":"answer","description":"d"}],'
                '"reason":"r"}'
            )
        )


def test_planner_injects_search_context():
    gateway = CaptureGateway()
    planner = Planner(gateway=gateway)
    plan = asyncio.run(
        planner.plan(
            "帮我查一下 GPT-5.1 最新动态",
            organization_id="org",
            user_id="user",
            context="【联网搜索结果】GPT-5.1 于 2025 年 8 月发布。",
        )
    )
    assert plan["steps"][0]["capability"] == "answer"
    assert any(
        isinstance(message, SystemMessage) and "联网搜索结果" in message.content
        for message in gateway.messages
    )


def test_route_after_prepare_uses_intent_flag():
    assert _route_after_prepare({"intent": {"needs_web_search": True}}) == (
        "search_preflight"
    )
    assert _route_after_prepare({"intent": {"needs_web_search": False}}) == "plan"
    assert _route_after_prepare({"intent": {}}) == "plan"
    assert _route_after_prepare({}) == "plan"


def test_final_output_or_fallback_never_returns_blank_on_tool_failure():
    assert _final_output_or_fallback("有内容", tool_results=[]) == "有内容"
    fallback = _final_output_or_fallback(
        "",
        tool_results=[
            {
                "tool_name": "query_db",
                "status": "failed",
                "error": "Unsupported SQL construct",
            }
        ],
    )
    assert "query_db" in fallback
    assert "Unsupported SQL construct" in fallback
    assert fallback.strip()


def test_final_output_or_fallback_handles_success_without_text():
    fallback = _final_output_or_fallback(
        "",
        tool_results=[
            {
                "tool_name": "query_db",
                "status": "success",
                "error": None,
                "data_preview": "[{'count': 3}]",
            }
        ],
    )
    assert fallback.strip()
    assert "已获取结果" in fallback
    assert "count" in fallback


def test_route_step_triggers_tool_failure_replan_once():
    state = {
        "tool_failure_replan": True,
        "revision_count": 0,
        "plan": [{"capability": "query_db"}],
        "current_step": 0,
        "intent": {"category": "TASK"},
    }
    assert asyncio.run(_route_step(state)) == "plan"

    state["revision_count"] = 1
    assert asyncio.run(_route_step(state)) == "query_db"

    state["tool_failure_replan"] = False
    assert asyncio.run(_route_step(state)) == "query_db"


def test_parallel_group_detects_independent_read_only_steps():
    plan = [
        {"step_id": "s1", "capability": "query_db"},
        {"step_id": "s2", "capability": "search_knowledge"},
        {"step_id": "s3", "capability": "send_email", "side_effect": True},
    ]
    assert _parallel_group(plan, 0) == [0, 1]
    assert _parallel_group(plan, 1) == []
    assert _parallel_group(plan, 2) == []


def test_parallel_group_respects_dependencies():
    plan = [
        {"step_id": "s1", "capability": "query_db"},
        {"step_id": "s2", "capability": "analysis", "depends_on": ["s1"]},
    ]
    assert _parallel_group(plan, 0) == []


def test_route_step_parallel_read_only_group():
    state = {
        "tool_failure_replan": False,
        "revision_count": 0,
        "plan": [
            {"step_id": "s1", "capability": "query_db"},
            {"step_id": "s2", "capability": "search_knowledge"},
        ],
        "current_step": 0,
        "intent": {"category": "TASK"},
    }
    assert asyncio.run(_route_step(state)) == "parallel_read_only"

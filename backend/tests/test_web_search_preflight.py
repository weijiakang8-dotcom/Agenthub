from __future__ import annotations

import asyncio

from langchain_core.messages import AIMessage, SystemMessage

from app.engine import tools
from app.engine.graph import _route_after_prepare
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

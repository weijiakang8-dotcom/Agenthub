from __future__ import annotations

import asyncio

from app.engine import tool_executor
from app.engine.tool_registry import (
    get_tool,
    list_tools,
    register_tool,
    unregister_tool,
)


def test_builtin_tools_registered():
    names = {tool["name"] for tool in list_tools()}
    assert {
        "search_web",
        "query_db",
        "search_knowledge",
        "recall_memory",
        "recall_executions",
        "send_email",
    } <= names


def test_get_tool_returns_spec():
    spec = get_tool("search_web")
    assert spec is not None
    assert spec.name == "search_web"


def test_unregister_unknown_tool():
    assert unregister_tool("does-not-exist") is False


def test_invoke_exposes_user_id_via_contextvar():
    calls: dict = {}

    async def handler(params, organization_id=None, user_id=None):
        from app.engine.tool_executor import current_tool_user_id

        calls["user_id"] = current_tool_user_id.get()
        return {"status": "success", "data": "ok", "error": None}

    register_tool(
        "spy_user_context",
        "spy",
        {"type": "object", "properties": {}, "required": []},
        handler,
    )
    try:
        token = tool_executor.current_tool_user_id.set("user-1")
        result = asyncio.run(
            tool_executor._invoke_with_retry(
                "spy_user_context",
                {},
                organization_id=None,
            )
        )
        tool_executor.current_tool_user_id.reset(token)
        assert result["status"] == "success"
        assert calls["user_id"] == "user-1"
    finally:
        unregister_tool("spy_user_context")

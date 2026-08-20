"""可编程假 Provider：只替换工具注册表，不修改生产代码。"""

from __future__ import annotations

import asyncio
from typing import Any

from app.engine import tool_registry


class FakeProvider:
    """send_email 假实现：记录每次调用与参数，支持注入行为。"""

    def __init__(self, behavior: str = "success") -> None:
        self.behavior = behavior
        self.calls: list[dict[str, Any]] = []

    async def handler(
        self, params: dict[str, Any], organization_id: Any = None
    ) -> dict:
        self.calls.append(
            {"params": dict(params or {}), "organization_id": str(organization_id)}
        )
        if self.behavior == "timeout_persistent":
            raise asyncio.TimeoutError("provider timeout")
        if self.behavior == "success":
            await asyncio.sleep(0.15)
        if self.behavior == "duplicate":
            return {
                "status": "duplicate",
                "data": {"to": (params or {}).get("to")},
                "error": None,
            }
        return {
            "status": "success",
            "data": {"to": (params or {}).get("to"), "message_id": "fake-msg"},
            "error": None,
        }


def install_fake_email(provider: FakeProvider) -> None:
    """用假 handler 覆盖 send_email 注册表项（测试后恢复）。"""
    tool_registry.register_tool(
        "send_email",
        "Send an email via SMTP. Requires human approval.",
        {
            "type": "object",
            "properties": {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["to", "subject", "body"],
        },
        provider.handler,
        timeout=30.0,
        requires_approval=True,
        side_effect=True,
    )


def restore_builtin_tools() -> None:
    tool_registry.register_builtin_tools()

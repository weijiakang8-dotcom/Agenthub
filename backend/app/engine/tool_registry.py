from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Awaitable[dict[str, Any]]]
    timeout: float = 30.0
    requires_approval: bool = False


_registry: dict[str, ToolSpec] = {}


def register_tool(
    name: str,
    description: str,
    parameters: dict[str, Any],
    handler: Callable[..., Awaitable[dict[str, Any]]],
    *,
    timeout: float = 30.0,
    requires_approval: bool = False,
) -> None:
    """注册或覆盖一个工具。"""
    if not name:
        raise ValueError("Tool name cannot be empty")
    _registry[name] = ToolSpec(
        name=name,
        description=description,
        parameters=parameters,
        handler=handler,
        timeout=timeout,
        requires_approval=requires_approval,
    )


def unregister_tool(name: str) -> bool:
    """注销工具，返回是否成功。"""
    return _registry.pop(name, None) is not None


def get_tool(name: str) -> ToolSpec | None:
    return _registry.get(name)


def list_tools() -> list[dict[str, Any]]:
    return [
        {
            "name": spec.name,
            "description": spec.description,
            "parameters": spec.parameters,
            "timeout": spec.timeout,
            "requires_approval": spec.requires_approval,
        }
        for spec in _registry.values()
    ]


def register_builtin_tools() -> None:
    """注册内置工具，幂等。"""
    from app.engine import tools as builtin_tools

    register_tool(
        "search_web",
        "Search the web and return result summaries.",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
            },
            "required": ["query"],
        },
        builtin_tools.search_web.ainvoke,
        timeout=15.0,
        requires_approval=False,
    )
    register_tool(
        "query_db",
        "Run a single read-only SQL SELECT query.",
        {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "A read-only SELECT query"},
            },
            "required": ["sql"],
        },
        builtin_tools.query_db.ainvoke,
        timeout=30.0,
        requires_approval=False,
    )
    register_tool(
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
        builtin_tools.send_email.ainvoke,
        timeout=30.0,
        requires_approval=True,
    )


register_builtin_tools()

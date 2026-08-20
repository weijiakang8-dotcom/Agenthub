"""harness 内模型调用网关：记录 token 用量与失败类别，四臂共用同一提示词模板。"""

from __future__ import annotations

import time
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

ACTION_SYSTEM_PROMPT = (
    "你是 AgentHub 的业务执行 Agent。根据用户请求，从给定工具中选择并填写参数。"
    "只能调用与任务直接相关的工具；不要编造不存在的对象；参数必须来自用户输入或业务上下文。"
)

VERIFY_SYSTEM_PROMPT = (
    "你是质量审查员。检查下面的 Agent 输出是否完整满足用户输入，"
    "只输出 PASS 或 FAIL（PASS=满足，FAIL=不满足）。"
)


def _usage_of(response: Any) -> dict[str, int | None]:
    usage = getattr(response, "usage_metadata", None) or {}
    if usage:
        return {
            "input_tokens": int(usage.get("input_tokens") or 0),
            "output_tokens": int(usage.get("output_tokens") or 0),
        }
    meta = getattr(response, "response_metadata", None) or {}
    token_usage = meta.get("token_usage") or {}
    if token_usage:
        return {
            "input_tokens": int(token_usage.get("prompt_tokens") or 0),
            "output_tokens": int(token_usage.get("completion_tokens") or 0),
        }
    return {"input_tokens": None, "output_tokens": None}


async def call_action(
    llm: Any, user_intent: str, tool_schemas: list[dict[str, Any]]
) -> dict[str, Any]:
    """action 步：模型选择工具并给出参数（bind_tools）。"""
    started = time.perf_counter()
    bound = llm.bind_tools(tool_schemas)
    try:
        response: AIMessage = await bound.ainvoke(
            [SystemMessage(content=ACTION_SYSTEM_PROMPT), HumanMessage(content=user_intent)]
        )
        return {
            "ok": True,
            "response": response,
            "tool_calls": list(getattr(response, "tool_calls", None) or []),
            "usage": _usage_of(response),
            "latency_ms": (time.perf_counter() - started) * 1000,
            "api_failure": None,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "response": None,
            "tool_calls": [],
            "usage": {"input_tokens": None, "output_tokens": None},
            "latency_ms": (time.perf_counter() - started) * 1000,
            "api_failure": f"{type(exc).__name__}: {str(exc)[:200]}",
        }


async def call_synthesis(
    llm: Any,
    user_intent: str,
    tool_name: str,
    tool_result: dict[str, Any],
) -> dict[str, Any]:
    """synthesis 步：根据工具结果生成最终回答（四臂共用）。"""
    started = time.perf_counter()
    try:
        response: AIMessage = await llm.ainvoke(
            [
                SystemMessage(content=ACTION_SYSTEM_PROMPT),
                HumanMessage(content=user_intent),
                HumanMessage(
                    content=f"工具 {tool_name} 返回：{tool_result}\n请基于此结果给出最终回答。"
                ),
            ]
        )
        return {
            "ok": True,
            "text": str(getattr(response, "content", "") or ""),
            "usage": _usage_of(response),
            "latency_ms": (time.perf_counter() - started) * 1000,
            "api_failure": None,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "text": "",
            "usage": {"input_tokens": None, "output_tokens": None},
            "latency_ms": (time.perf_counter() - started) * 1000,
            "api_failure": f"{type(exc).__name__}: {str(exc)[:200]}",
        }


async def call_verify(
    llm: Any,
    user_intent: str,
    final_output: str,
) -> dict[str, Any]:
    """verify 步：仅 ON 臂；机制性检查，不注入业务信息。"""
    started = time.perf_counter()
    try:
        response: AIMessage = await llm.ainvoke(
            [
                SystemMessage(content=VERIFY_SYSTEM_PROMPT),
                HumanMessage(
                    content=f"用户输入：{user_intent}\nAgent 输出：{final_output}"
                ),
            ]
        )
        return {
            "ok": True,
            "text": str(getattr(response, "content", "") or "").strip().upper(),
            "usage": _usage_of(response),
            "latency_ms": (time.perf_counter() - started) * 1000,
            "api_failure": None,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "text": "",
            "usage": {"input_tokens": None, "output_tokens": None},
            "latency_ms": (time.perf_counter() - started) * 1000,
            "api_failure": f"{type(exc).__name__}: {str(exc)[:200]}",
        }

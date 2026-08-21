"""Chat Runtime：同步流式、不经 Celery、不进入 Agent Graph。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from app.core.model_gateway import ModelGateway
from app.engine.runner import (
    MAX_CONTEXT_MESSAGES,
    _clean_message_dicts,
    _to_langchain_message,
)

CHAT_SYSTEM_PROMPT = (
    "你是 AgentHub 的智能助手。请直接、准确、自然地回答用户的问题；"
    "如果用户只是打招呼，就友好地简短回应；如果信息不足，请向用户提问澄清。"
    "如果上下文中提供了【联网搜索结果】，请优先基于这些最新结果回答，"
    "涉及外部事实时尽量标注来源；如果搜索失败，如实说明未能联网检索，"
    "再基于已有知识回答，不要编造搜索结果。"
)


def build_chat_messages(
    prior_messages: Any,
    user_input: str,
    *,
    summary: str | None = None,
    memories: list[dict[str, Any]] | None = None,
) -> list[BaseMessage]:
    cleaned = _clean_message_dicts(prior_messages)[-MAX_CONTEXT_MESSAGES:]
    messages = [_to_langchain_message(message) for message in cleaned]
    context_notes: list[str] = []
    if summary:
        context_notes.append(f"【更早对话摘要】{summary}")
    if memories:
        context_notes.append(
            "【关于用户的已知信息】" + "；".join(f"{m['content']}" for m in memories)
        )
    if context_notes:
        messages.insert(0, SystemMessage(content="\n".join(context_notes)))
    if user_input:
        messages.append(HumanMessage(content=user_input))
    return messages


async def iter_chat_tokens(
    llms: list,
    messages: list[BaseMessage],
) -> AsyncIterator[str]:
    gateway = ModelGateway()
    async for token in gateway.stream(llms, messages, task_type="chat"):
        yield token


def chat_usage_entries(
    model_used: str | None,
    classify_metadata: dict[str, Any] | None,
    input_tokens: int,
    output_tokens: int,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    if classify_metadata:
        entries.append(dict(classify_metadata))
    if model_used:
        entries.append(
            {
                "model_used": model_used,
                "fallback": False,
                "attempts": 1,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            }
        )
    return entries


__all__ = [
    "CHAT_SYSTEM_PROMPT",
    "build_chat_messages",
    "chat_usage_entries",
    "iter_chat_tokens",
]

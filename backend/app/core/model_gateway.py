from __future__ import annotations

import asyncio
from typing import Any

from langchain_openai import ChatOpenAI
from sqlalchemy import select

from app.config import settings
from app.database import async_session_factory
from app.models import ModelConfig


async def list_active_models(organization_id: str | None = None) -> list[ModelConfig]:
    async with async_session_factory() as session:
        stmt = select(ModelConfig).where(ModelConfig.is_active.is_(True))
        if organization_id is not None:
            stmt = stmt.where(ModelConfig.organization_id == organization_id)
        result = await session.execute(stmt.order_by(ModelConfig.cost_per_1k_tokens))
        return list(result.scalars().all())


async def resolve_model(
    organization_id: str | None = None,
    *,
    complexity: str = "simple",
) -> ModelConfig | None:
    models = await list_active_models(organization_id)
    if not models:
        return None
    if complexity == "complex":
        return max(models, key=lambda m: m.cost_per_1k_tokens)
    return min(models, key=lambda m: m.cost_per_1k_tokens)


async def get_chat_models(
    organization_id: str | None = None,
    *,
    complexity: str = "simple",
) -> list[ChatOpenAI]:
    """返回按成本排序的可用模型列表，用于执行引擎的自动 fallback。"""
    models = await list_active_models(organization_id)
    if not models:
        return [
            ChatOpenAI(
                model=settings.LLM_MODEL,
                base_url=settings.LLM_BASE_URL,
                api_key=settings.OPENAI_API_KEY or "not-configured",
                temperature=0,
            )
        ]

    if complexity == "complex":
        models = sorted(models, key=lambda m: m.cost_per_1k_tokens, reverse=True)
    else:
        models = sorted(models, key=lambda m: m.cost_per_1k_tokens)

    return [get_chat_model(model) for model in models]


def get_chat_model(model: ModelConfig) -> ChatOpenAI:
    return ChatOpenAI(
        model=model.model,
        base_url=model.base_url,
        api_key=model.api_key or "not-configured",
        max_tokens=model.max_tokens,
        temperature=0,
    )


async def test_model(model: ModelConfig) -> dict[str, Any]:
    llm = get_chat_model(model)
    try:
        response = await asyncio.wait_for(
            llm.ainvoke([{"role": "user", "content": "ping"}]),
            timeout=15,
        )
        return {"ok": True, "response": str(getattr(response, "content", ""))[:120]}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from langchain_openai import ChatOpenAI
from sqlalchemy import select

from app.config import settings
from app.core.security import decrypt_secret
from app.database import async_session_factory
from app.models import ModelConfig, UserApiKey


async def list_active_models(organization_id: str | None = None) -> list[ModelConfig]:
    async with async_session_factory() as session:
        if organization_id is not None:
            stmt = select(ModelConfig).where(
                ModelConfig.is_active.is_(True),
                ModelConfig.enabled.is_(True),
                ModelConfig.organization_id == organization_id,
            )
            result = await session.execute(
                stmt.order_by(ModelConfig.cost_per_1k_tokens)
            )
            rows = list(result.scalars().all())
            if rows:
                return rows
        # 租户没有专属模型时回退到全局（org NULL）默认模型，绝不跨租户。
        stmt = select(ModelConfig).where(
            ModelConfig.is_active.is_(True),
            ModelConfig.enabled.is_(True),
            ModelConfig.organization_id.is_(None),
        )
        result = await session.execute(stmt.order_by(ModelConfig.cost_per_1k_tokens))
        return list(result.scalars().all())


async def list_user_api_keys(user_id: str | uuid.UUID | None) -> list[UserApiKey]:
    if user_id is None:
        return []
    async with async_session_factory() as session:
        result = await session.execute(
            select(UserApiKey)
            .where(
                UserApiKey.user_id == uuid.UUID(str(user_id)),
                UserApiKey.is_active.is_(True),
            )
            .order_by(UserApiKey.created_at)
        )
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
    user_id: str | uuid.UUID | None = None,
) -> list[ChatOpenAI]:
    """返回按显式优先级排序的可用模型列表，用于执行引擎的自动 fallback。

    - complex: 按 priority 升序（更小 = 能力优先，Pro 在前），成本作次级排序。
    - simple:  按 priority 降序（更大 = 低成本优先，Flash 在前），成本作次级排序。
    无可用模型时回退到全局 settings 单模型。
    """
    user_llms: list[ChatOpenAI] = []
    for key in await list_user_api_keys(user_id):
        secret = decrypt_secret(key.api_key_encrypted)
        if secret:
            user_llms.append(
                ChatOpenAI(
                    model=key.model,
                    base_url=key.base_url,
                    api_key=secret,
                    temperature=0,
                )
            )

    models = await list_active_models(organization_id)
    if not models:
        if user_llms:
            return user_llms
        return [
            ChatOpenAI(
                model=settings.LLM_MODEL,
                base_url=settings.LLM_BASE_URL,
                api_key=settings.OPENAI_API_KEY or "not-configured",
                temperature=0,
            )
        ]

    if complexity == "complex":
        models = sorted(models, key=lambda m: (m.priority, m.cost_per_1k_tokens))
    else:
        models = sorted(models, key=lambda m: (-m.priority, m.cost_per_1k_tokens))

    return [*user_llms, *[get_chat_model(model) for model in models]]


def get_chat_model(model: ModelConfig) -> ChatOpenAI:
    return ChatOpenAI(
        model=model.model,
        base_url=model.base_url,
        api_key=model.api_key or "not-configured",
        max_tokens=model.max_tokens,
        temperature=0,
        request_timeout=max(1, model.timeout),
        max_retries=max(0, model.max_retries),
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

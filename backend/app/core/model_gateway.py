"""统一 Model Gateway（Frozen Core）。

业务代码不直接决定具体模型，只表达任务类型/复杂度与租户上下文。
所有调用通过 Gateway 落结构化观测：model/provider/attempt/tokens/latency/fallback/error。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import urlsplit

from langchain_core.messages import AIMessage, BaseMessage
from langchain_openai import ChatOpenAI
from sqlalchemy import select

from app.config import settings
from app.core.circuit_breaker import llm_breaker
from app.core.failure import (
    LLM_RETRY_POLICY,
    classify_error,
    should_retry,
)
from app.core.quota import (
    QuotaExceededError,
    acquire_llm_slot,
    estimate_tokens_for_messages,
    release_llm_slot,
    reserve_cost,
    reserve_tokens,
    settle_cost,
    settle_tokens,
)
from app.core.security import decrypt_secret
from app.database import async_session_factory
from app.engine.observability import record_span
from app.models import ModelConfig, UserApiKey

logger = logging.getLogger("agenthub.model")


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
        stmt = select(ModelConfig).where(
            ModelConfig.is_active.is_(True),
            ModelConfig.enabled.is_(True),
            ModelConfig.organization_id.is_(None),
        )
        result = await session.execute(stmt.order_by(ModelConfig.cost_per_1k_tokens))
        return list(result.scalars().all())


def _user_key_uses_responses_api(key: UserApiKey) -> bool:
    host = (urlsplit(key.base_url).hostname or "").lower()
    return key.provider.endswith(":responses") or host == "api.openai.com"


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


def _fallback_client() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.LLM_MODEL,
        base_url=settings.LLM_BASE_URL,
        api_key=settings.OPENAI_API_KEY or "not-configured",
        temperature=0,
        request_timeout=120,
        max_retries=2,
    )


def _secondary_fallback_client() -> ChatOpenAI | None:
    """第二供应商（OpenAI）备用客户端；未启用或未配置密钥时返回 None（自动跳过）。"""
    if not settings.OPENAI_FALLBACK_ENABLED:
        return None
    if not settings.OPENAI_FALLBACK_API_KEY:
        logger.warning(
            "OpenAI fallback enabled but OPENAI_FALLBACK_API_KEY is empty; "
            "secondary provider skipped"
        )
        return None
    return ChatOpenAI(
        model=settings.OPENAI_FALLBACK_MODEL,
        base_url=settings.OPENAI_FALLBACK_BASE_URL,
        api_key=settings.OPENAI_FALLBACK_API_KEY,
        temperature=0,
        request_timeout=120,
        max_retries=0,
    )


async def get_chat_models(
    organization_id: str | None = None,
    *,
    complexity: str = "simple",
    user_id: str | uuid.UUID | None = None,
) -> list[ChatOpenAI]:
    """兼容旧调用点的模型选择逻辑（现在统一委托给 ModelGateway）。"""
    return await ModelGateway().select(
        organization_id=organization_id,
        complexity=complexity,
        user_id=user_id,
    )


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


class ModelGateway:
    """模型选择 + 统一重试/回退 + 结构化观测。"""

    async def select(
        self,
        *,
        organization_id: str | None = None,
        complexity: str = "simple",
        user_id: str | uuid.UUID | None = None,
    ) -> list[ChatOpenAI]:
        user_llms: list[ChatOpenAI] = []
        for key in await list_user_api_keys(user_id):
            secret = decrypt_secret(key.api_key_encrypted)
            if secret:
                uses_responses = _user_key_uses_responses_api(key)
                user_llms.append(
                    ChatOpenAI(
                        model=key.model,
                        base_url=key.base_url,
                        api_key=secret,
                        temperature=None if uses_responses else 0,
                        request_timeout=120,
                        max_retries=2,
                        use_responses_api=uses_responses,
                        metadata={
                            "provider": key.provider.removesuffix(":responses"),
                            "api_mode": (
                                "responses" if uses_responses else "chat_completions"
                            ),
                        },
                    )
                )

        models = await list_active_models(organization_id)
        secondary = _secondary_fallback_client()
        if not models:
            clients = [*user_llms, _fallback_client()]
            if secondary is not None:
                clients.append(secondary)
            return clients

        if complexity == "complex":
            models = sorted(models, key=lambda m: (m.priority, m.cost_per_1k_tokens))
        else:
            models = sorted(models, key=lambda m: (-m.priority, m.cost_per_1k_tokens))
        clients = [*user_llms, *[get_chat_model(model) for model in models]]
        if secondary is not None:
            clients.append(secondary)
        return clients

    def _record(
        self,
        *,
        task_type: str,
        model: str | None,
        attempt: int,
        fallback: bool,
        streaming: bool,
        latency: float,
        organization_id: str | None,
        correlation_id: str | None,
        status: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost: float | None = None,
        error: str | None = None,
    ) -> None:
        logger.info(
            json.dumps(
                {
                    "event": "model_call",
                    "task_type": task_type,
                    "model": model,
                    "attempt": attempt,
                    "fallback": fallback,
                    "streaming": streaming,
                    "latency_ms": round(latency * 1000, 2),
                    "organization_id": organization_id,
                    "correlation_id": correlation_id,
                    "status": status,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cost": cost,
                    "error": error,
                },
                ensure_ascii=False,
            )
        )

    def _model_name(self, llm: ChatOpenAI) -> str | None:
        return getattr(llm, "model_name", None) or getattr(
            getattr(llm, "bound", None), "model_name", None
        )

    def _usage(self, response: Any) -> tuple[int, int]:
        usage = getattr(response, "usage_metadata", None) or {}
        return int(usage.get("input_tokens") or 0), int(usage.get("output_tokens") or 0)

    async def _rate_for_model(
        self, model_name: str | None, organization_id: str | None
    ) -> float | None:
        if not model_name:
            return None
        stmt = select(ModelConfig).where(
            ModelConfig.is_active.is_(True),
            ModelConfig.enabled.is_(True),
            ModelConfig.model == model_name,
        )
        async with async_session_factory() as session:
            candidates = list((await session.execute(stmt)).scalars().all())
        for candidate in candidates:
            if candidate.organization_id is not None and (
                organization_id is None
                or str(candidate.organization_id) == str(organization_id)
            ):
                return float(candidate.cost_per_1k_tokens)
        for candidate in candidates:
            if candidate.organization_id is None:
                return float(candidate.cost_per_1k_tokens)
        return None

    async def _cost_for(
        self,
        model_name: str | None,
        organization_id: str | None,
        input_tokens: int,
        output_tokens: int,
    ) -> float | None:
        rate = await self._rate_for_model(model_name, organization_id)
        if rate is None or (input_tokens + output_tokens) <= 0:
            return None
        return round((input_tokens + output_tokens) / 1000 * rate, 8)

    async def invoke(
        self,
        llms: list[ChatOpenAI],
        messages: list[BaseMessage],
        *,
        task_type: str,
        organization_id: str | None = None,
        correlation_id: str | None = None,
    ) -> AIMessage:
        last_error: Exception | None = None
        for model_index, llm in enumerate(llms):
            if not llm_breaker.allow():
                continue
            for attempt in range(LLM_RETRY_POLICY.max_attempts):
                start = time.perf_counter()
                slot_acquired = False
                estimate = 0
                estimate_cost_cny = 0.0
                try:
                    if organization_id:
                        if not await acquire_llm_slot(organization_id):
                            raise QuotaExceededError(
                                "当前租户并发模型调用已达上限，请稍后再试。"
                            )
                        slot_acquired = True
                        estimate = estimate_tokens_for_messages(messages) + int(
                            getattr(llm, "max_tokens", None) or 4096
                        )
                        await reserve_tokens(organization_id, estimate=estimate)
                        rate = await self._rate_for_model(
                            self._model_name(llm), organization_id
                        )
                        if rate is not None:
                            estimate_cost_cny = estimate / 1000.0 * rate
                            await reserve_cost(
                                organization_id,
                                estimate_cny=estimate_cost_cny,
                            )
                    response = await llm.ainvoke(messages)
                    latency = time.perf_counter() - start
                    input_tokens, output_tokens = self._usage(response)
                    cost = await self._cost_for(
                        self._model_name(llm),
                        organization_id,
                        input_tokens,
                        output_tokens,
                    )
                    if slot_acquired:
                        await settle_tokens(
                            organization_id,
                            estimate=estimate,
                            actual=input_tokens + output_tokens,
                        )
                        await settle_cost(
                            organization_id,
                            estimate_cny=estimate_cost_cny,
                            actual_cny=cost or 0.0,
                        )
                    llm_breaker.record_success()
                    self._attach_metadata(
                        response,
                        model=self._model_name(llm),
                        fallback=model_index > 0,
                        attempts=attempt + 1,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        cost=cost,
                    )
                    self._record(
                        task_type=task_type,
                        model=self._model_name(llm),
                        attempt=attempt + 1,
                        fallback=model_index > 0,
                        streaming=False,
                        latency=latency,
                        organization_id=organization_id,
                        correlation_id=correlation_id,
                        status="success",
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        cost=cost,
                    )
                    await record_span(
                        trace_id=correlation_id,
                        name="llm",
                        status="ok",
                        tokens=input_tokens + output_tokens,
                        cost=cost,
                        model=self._model_name(llm),
                        attempt=attempt + 1,
                        details={
                            "task_type": task_type,
                            "input_tokens": input_tokens,
                            "output_tokens": output_tokens,
                            "fallback": model_index > 0,
                            "streaming": False,
                        },
                    )
                    if slot_acquired:
                        await release_llm_slot(organization_id)
                    return response
                except QuotaExceededError:
                    if slot_acquired:
                        await release_llm_slot(organization_id)
                    raise
                except Exception as exc:  # noqa: BLE001
                    if slot_acquired:
                        await release_llm_slot(organization_id)
                        slot_acquired = False
                    llm_breaker.record_failure()
                    last_error = exc
                    category = classify_error(exc)
                    self._record(
                        task_type=task_type,
                        model=self._model_name(llm),
                        attempt=attempt + 1,
                        fallback=model_index > 0,
                        streaming=False,
                        latency=time.perf_counter() - start,
                        organization_id=organization_id,
                        correlation_id=correlation_id,
                        status="error",
                        error=f"{category.value}: {str(exc)[:200]}",
                    )
                    await record_span(
                        trace_id=correlation_id,
                        name="llm",
                        status="error",
                        model=self._model_name(llm),
                        attempt=attempt + 1,
                        error=f"{category.value}: {str(exc)[:200]}",
                        details={
                            "task_type": task_type,
                            "fallback": model_index > 0,
                            "streaming": False,
                        },
                    )
                    if not should_retry(category, "llm"):
                        break
                    if attempt + 1 < LLM_RETRY_POLICY.max_attempts:
                        await asyncio.sleep(LLM_RETRY_POLICY.delay(attempt))
                if slot_acquired:
                    await release_llm_slot(organization_id)
        raise last_error or RuntimeError("AI 服务暂时不可用，请稍后再试")

    async def stream(
        self,
        llms: list[ChatOpenAI],
        messages: list[BaseMessage],
        *,
        task_type: str,
        organization_id: str | None = None,
        correlation_id: str | None = None,
    ) -> AsyncIterator[str]:
        last_error: Exception | None = None
        emitted = False
        for model_index, llm in enumerate(llms):
            if not llm_breaker.allow():
                continue
            parts: list[str] = []
            start = time.perf_counter()
            slot_acquired = False
            estimate = 0
            estimate_cost_cny = 0.0
            input_estimate = 0
            try:
                if organization_id:
                    if not await acquire_llm_slot(organization_id):
                        raise QuotaExceededError(
                            "当前租户并发模型调用已达上限，请稍后再试。"
                        )
                    slot_acquired = True
                    input_estimate = estimate_tokens_for_messages(messages)
                    estimate = input_estimate + int(
                        getattr(llm, "max_tokens", None) or 4096
                    )
                    await reserve_tokens(organization_id, estimate=estimate)
                    rate = await self._rate_for_model(
                        self._model_name(llm), organization_id
                    )
                    if rate is not None:
                        estimate_cost_cny = estimate / 1000.0 * rate
                        await reserve_cost(
                            organization_id,
                            estimate_cny=estimate_cost_cny,
                        )
                async for chunk in llm.astream(messages):
                    text = getattr(chunk, "content", None)
                    if isinstance(text, str) and text:
                        emitted = True
                        parts.append(text)
                        yield text
                llm_breaker.record_success()
                stream_tokens = len("".join(parts))
                cost = await self._cost_for(
                    self._model_name(llm), organization_id, 0, stream_tokens
                )
                if slot_acquired:
                    await settle_tokens(
                        organization_id,
                        estimate=estimate,
                        actual=input_estimate + stream_tokens,
                    )
                    await settle_cost(
                        organization_id,
                        estimate_cny=estimate_cost_cny,
                        actual_cny=cost or 0.0,
                    )
                self._record(
                    task_type=task_type,
                    model=self._model_name(llm),
                    attempt=1,
                    fallback=model_index > 0,
                    streaming=True,
                    latency=time.perf_counter() - start,
                    organization_id=organization_id,
                    correlation_id=correlation_id,
                    status="success",
                    output_tokens=stream_tokens,
                    cost=cost,
                )
                await record_span(
                    trace_id=correlation_id,
                    name="llm",
                    status="ok",
                    tokens=stream_tokens,
                    cost=cost,
                    model=self._model_name(llm),
                    attempt=1,
                    details={
                        "task_type": task_type,
                        "fallback": model_index > 0,
                        "streaming": True,
                    },
                )
                if slot_acquired:
                    await release_llm_slot(organization_id)
                return
            except QuotaExceededError:
                if slot_acquired:
                    await release_llm_slot(organization_id)
                raise
            except Exception as exc:  # noqa: BLE001
                if slot_acquired:
                    await release_llm_slot(organization_id)
                    slot_acquired = False
                llm_breaker.record_failure()
                last_error = exc
                category = classify_error(exc)
                self._record(
                    task_type=task_type,
                    model=self._model_name(llm),
                    attempt=1,
                    fallback=model_index > 0,
                    streaming=True,
                    latency=time.perf_counter() - start,
                    organization_id=organization_id,
                    correlation_id=correlation_id,
                    status="error",
                    error=f"{category.value}: {str(exc)[:200]}",
                )
                await record_span(
                    trace_id=correlation_id,
                    name="llm",
                    status="error",
                    model=self._model_name(llm),
                    attempt=1,
                    error=f"{category.value}: {str(exc)[:200]}",
                    details={
                        "task_type": task_type,
                        "fallback": model_index > 0,
                        "streaming": True,
                    },
                )
                if emitted or not should_retry(category, "llm"):
                    if emitted:
                        return
                    continue
        if emitted:
            return
        raise last_error or RuntimeError("AI 服务暂时不可用，请稍后再试")

    def _attach_metadata(
        self,
        response: AIMessage,
        *,
        model: str | None,
        fallback: bool,
        attempts: int,
        input_tokens: int,
        output_tokens: int,
        cost: float | None,
    ) -> None:
        kwargs = dict(getattr(response, "additional_kwargs", None) or {})
        kwargs["_agenthub_llm"] = {
            "model_used": model or "",
            "fallback": fallback,
            "attempts": attempts,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost": cost,
        }
        response.additional_kwargs = kwargs


__all__ = [
    "ModelGateway",
    "get_chat_model",
    "get_chat_models",
    "list_active_models",
    "list_user_api_keys",
    "resolve_model",
    "test_model",
]

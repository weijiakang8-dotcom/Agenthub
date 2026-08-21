from __future__ import annotations

import asyncio
import uuid

import pytest
from langchain_core.messages import HumanMessage

from app.core import quota
from app.core.quota import (
    QuotaExceededError,
    acquire_llm_slot,
    estimate_tokens_for_messages,
    quota_usage,
    release_llm_slot,
    reserve_cost,
    reserve_tokens,
    settle_tokens,
)


def _org() -> str:
    return f"quota-test-{uuid.uuid4().hex[:12]}"


async def _cleanup(organization_id: str) -> None:
    client = quota._redis()
    try:
        await client.delete(
            quota.month_key(organization_id),
            quota.cost_key(organization_id),
            f"quota:concurrent:{organization_id}",
        )
    finally:
        await client.aclose()


def test_reserve_tokens_blocks_over_budget(monkeypatch):
    org = _org()
    monkeypatch.setattr(quota.settings, "TENANT_MONTHLY_TOKEN_BUDGET", 100)
    try:
        asyncio.run(reserve_tokens(org, estimate=60))
        with pytest.raises(QuotaExceededError):
            asyncio.run(reserve_tokens(org, estimate=60))
    finally:
        asyncio.run(_cleanup(org))


def test_settle_tokens_refunds_unused_estimate(monkeypatch):
    org = _org()
    monkeypatch.setattr(quota.settings, "TENANT_MONTHLY_TOKEN_BUDGET", 100)
    try:
        asyncio.run(reserve_tokens(org, estimate=80))
        asyncio.run(settle_tokens(org, estimate=80, actual=30))
        usage = asyncio.run(quota_usage(org))
        assert usage["monthly_token_used"] == 30
    finally:
        asyncio.run(_cleanup(org))


def test_reserve_cost_blocks_over_budget(monkeypatch):
    org = _org()
    monkeypatch.setattr(quota.settings, "TENANT_MONTHLY_COST_BUDGET_CNY", 1.0)
    try:
        asyncio.run(reserve_cost(org, estimate_cny=0.6))
        with pytest.raises(QuotaExceededError):
            asyncio.run(reserve_cost(org, estimate_cny=0.6))
    finally:
        asyncio.run(_cleanup(org))


def test_acquire_release_concurrent_slot(monkeypatch):
    org = _org()
    monkeypatch.setattr(quota.settings, "TENANT_MAX_CONCURRENT_LLM_CALLS", 2)
    try:
        assert asyncio.run(acquire_llm_slot(org)) is True
        assert asyncio.run(acquire_llm_slot(org)) is True
        assert asyncio.run(acquire_llm_slot(org)) is False
        asyncio.run(release_llm_slot(org))
        assert asyncio.run(acquire_llm_slot(org)) is True
    finally:
        asyncio.run(_cleanup(org))


def test_estimate_tokens_for_messages():
    messages = [HumanMessage(content="你好，世界")]
    assert estimate_tokens_for_messages(messages) >= 1


def test_gateway_blocks_when_concurrency_limit_reached(monkeypatch):
    async def fake_acquire(organization_id):
        return False

    monkeypatch.setattr(
        "app.core.model_gateway.acquire_llm_slot",
        fake_acquire,
    )
    from app.core.model_gateway import ModelGateway

    class DummyLLM:
        async def ainvoke(self, *args, **kwargs):
            raise AssertionError("should not be invoked")

    with pytest.raises(QuotaExceededError):
        asyncio.run(
            ModelGateway().invoke(
                [DummyLLM()],
                [HumanMessage(content="hi")],
                task_type="test",
                organization_id=_org(),
            )
        )

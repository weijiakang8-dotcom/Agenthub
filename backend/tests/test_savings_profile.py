"""省钱账单 / token 看板 / 绩效档案 / 用量明细测试。"""

from __future__ import annotations

import asyncio
import uuid

from app.core.profile import (
    record_usage_events,
    stats_for,
    update_model_performance,
)
from app.core.savings import compute_savings, token_dashboard


async def _new_org() -> str:
    """创建真实 org 行，返回其 id（满足外键约束）。"""
    from app.database import async_session_factory
    from app.models import Organization

    async with async_session_factory() as session:
        org = Organization(name="t", slug=f"t-{uuid.uuid4().hex[:12]}")
        session.add(org)
        await session.commit()
        await session.refresh(org)
        return str(org.id)


def _org() -> str:
    return asyncio.run(_new_org())


class TestUsageEvents:
    def test_record_usage_events(self):
        org = _org()
        count = asyncio.run(
            record_usage_events(
                [
                    {
                        "model_used": "deepseek-v4-flash",
                        "input_tokens": 100,
                        "output_tokens": 50,
                        "cost": 0.001,
                    },
                    {
                        "model_used": "deepseek-v4-pro",
                        "input_tokens": 200,
                        "output_tokens": 100,
                        "cost": 0.005,
                    },
                ],
                organization_id=org,
                task_type="agent:research",
                step_capability="research",
                complexity="simple",
            )
        )
        assert count == 2

    def test_record_usage_with_bad_ids_is_safe(self):
        count = asyncio.run(
            record_usage_events(
                [{"model_used": "m", "input_tokens": 1, "output_tokens": 1}],
                execution_id="not-a-uuid",
                organization_id="also-not-a-uuid",
            )
        )
        assert count in (0, 1)


class TestModelPerformance:
    def test_upsert_accumulates(self):
        org = _org()
        model = f"m-{uuid.uuid4().hex[:8]}"
        asyncio.run(
            update_model_performance(
                organization_id=org,
                model=model,
                task_type="agent:answer",
                bucket="simple",
                success=True,
                cost=0.01,
            )
        )
        asyncio.run(
            update_model_performance(
                organization_id=org,
                model=model,
                task_type="agent:answer",
                bucket="simple",
                success=False,
                cost=0.02,
            )
        )
        stats = asyncio.run(
            stats_for(org, model=model, task_type="agent:answer", bucket="simple")
        )
        assert stats["attempts"] >= 2
        assert stats["success_rate"] is not None

    def test_stats_for_unknown_returns_empty(self):
        stats = asyncio.run(
            stats_for("org-nope", model="none", task_type="x", bucket="simple")
        )
        assert stats == {}


class TestSavings:
    def test_compute_savings_empty(self):
        summary = asyncio.run(compute_savings(_org()))
        assert "baseline_cost" in summary
        assert "by_model" in summary
        assert summary["savings"] >= 0

    def test_token_dashboard(self):
        dashboard = asyncio.run(token_dashboard(_org(), days=30))
        assert set(dashboard) >= {"days", "models", "total"}
        assert dashboard["total"]["tokens"] >= 0

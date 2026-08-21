from __future__ import annotations

import asyncio
import uuid

import asyncpg
import pytest
from sqlalchemy import func, select

from app.config import settings
from app.core import production_alerts


def _sync_url() -> str:
    return settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")


def _db_ready() -> bool:
    async def check() -> bool:
        try:
            conn = await asyncpg.connect(_sync_url())
            try:
                return (
                    int(await conn.fetchval("SELECT version_num FROM alembic_version"))
                    >= 19
                )
            finally:
                await conn.close()
        except Exception:  # noqa: BLE001
            return False

    return asyncio.run(check())


pytestmark = pytest.mark.skipif(
    not _db_ready(),
    reason="requires PostgreSQL at migration 0019",
)


def test_evaluate_production_alerts_thresholds():
    alerts = {
        alert["name"]: alert
        for alert in production_alerts.evaluate_production_alerts(
            {
                "dlq_count": 0,
                "pending_executions": 0,
                "in_flight_tool_calls": 0,
                "approval_mismatch_24h": 0,
                "llm_fallback_rate": 0.0,
                "llm_latency_p95_ms": None,
                "database_ok": True,
                "redis_ok": True,
            }
        )
    }
    assert alerts["dlq_growth"]["ok"] is True
    assert alerts["side_effect_unknown"]["ok"] is True
    assert alerts["database_unhealthy"]["ok"] is True

    breached = {
        alert["name"]: alert
        for alert in production_alerts.evaluate_production_alerts(
            {
                "dlq_count": 100,
                "pending_executions": 100,
                "in_flight_tool_calls": 1,
                "approval_mismatch_24h": 2,
                "llm_fallback_rate": 0.9,
                "llm_latency_p95_ms": 99999,
                "database_ok": False,
                "redis_ok": False,
            }
        )
    }
    assert breached["dlq_growth"]["ok"] is False
    assert breached["side_effect_unknown"]["ok"] is False
    assert breached["approval_mismatch"]["ok"] is False
    assert breached["database_unhealthy"]["ok"] is False
    assert breached["redis_unhealthy"]["ok"] is False


def test_run_production_alerts_persists_and_cooldowns(monkeypatch):
    async def main() -> None:
        conn = await asyncpg.connect(_sync_url())
        trace_id = uuid.uuid4()
        try:
            await conn.execute(
                "INSERT INTO audit_logs (id,organization_id,user_id,method,path,"
                "status_code,action,resource_type,resource_id,details,created_at,updated_at) "
                "VALUES ($1,NULL,NULL,'EXEC','/x',0,'approval_mismatch','execution',$2,"
                "'{}'::json,now(),now())",
                uuid.uuid4(),
                str(trace_id),
            )
            monkeypatch.setattr(settings, "ALERT_COOLDOWN_MINUTES", 5)
            created_first = await production_alerts.run_production_alerts()
            created_second = await production_alerts.run_production_alerts()
            assert created_first, "expected at least one alert event"
            assert created_second == []

            from app.database import async_session_factory
            from app.models import AlertEvent

            async with async_session_factory() as session:
                count = int(
                    (
                        await session.execute(
                            select(func.count(AlertEvent.id)).where(
                                AlertEvent.rule_id == "approval_mismatch",
                                AlertEvent.status == "active",
                            )
                        )
                    ).scalar()
                    or 0
                )
            assert count >= 1
        finally:
            await conn.execute(
                "DELETE FROM alert_events WHERE rule_id='approval_mismatch'"
            )
            await conn.execute(
                "DELETE FROM audit_logs WHERE resource_id=$1", str(trace_id)
            )
            await conn.close()

    asyncio.run(main())

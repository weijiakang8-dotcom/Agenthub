from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import redis.asyncio as aioredis
from celery import Celery
from celery.signals import worker_process_init
from sqlalchemy import update

from app.adapters.errors import UnsupportedKernelWorkflowError
from app.adapters.kernel_runtime_bridge import persist_unsupported_workflow
from app.config import settings
from app.core.failure import classify_error, should_retry
from app.core.telemetry import setup_telemetry
from app.database import async_session_factory
from app.models import Execution
from app.models.enums import ExecutionStatus

celery_app = Celery(
    "agenthub",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL.rsplit("/", 1)[0] + "/1",
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
)

celery_app.conf.beat_schedule = {
    "evaluate-alerts": {
        "task": "agenthub.evaluate_all_rules",
        "schedule": 60.0,
    },
    "evaluate-production-alerts": {
        "task": "agenthub.evaluate_production_alerts",
        "schedule": 60.0,
    },
    "mark-stale-executions": {
        "task": "agenthub.mark_stale_executions",
        "schedule": 120.0,
    },
    "reconcile-state": {
        "task": "agenthub.reconcile_state",
        "schedule": 300.0,
    },
    "reconcile-approvals": {
        "task": "agenthub.reconcile_stale_approvals",
        "schedule": 300.0,
    },
    "cleanup-checkpoints": {
        "task": "agenthub.cleanup_checkpoints",
        "schedule": 3600.0,
    },
    "cleanup-expired-memories": {
        "task": "agenthub.cleanup_expired_memories",
        "schedule": 3600.0,
    },
    "propose-growth-skills": {
        "task": "agenthub.propose_growth_skills",
        "schedule": 21600.0,
    },
}


async def _fail_execution_and_push_dlq(execution_id: str, error_message: str) -> None:
    execution_uuid = uuid.UUID(execution_id)
    async with async_session_factory() as session:
        execution = await session.get(Execution, execution_uuid)
        if execution is not None and execution.status not in {
            ExecutionStatus.COMPLETED,
            ExecutionStatus.FAILED,
            ExecutionStatus.ROLLED_BACK,
        }:
            execution.status = ExecutionStatus.FAILED
            execution.error_message = error_message
            execution.completed_at = datetime.now(timezone.utc)
            await session.commit()

    client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        await client.rpush(
            "dead_letter_queue",
            json.dumps(
                {
                    "execution_id": execution_id,
                    "error": error_message,
                    "task": "execute_workflow",
                }
            ),
        )
    finally:
        await client.aclose()


@worker_process_init.connect
def setup_telemetry_on_worker(**kwargs) -> None:
    setup_telemetry()


@celery_app.task(name="agenthub.execute_workflow", bind=True, max_retries=3)
def execute_workflow_task(self, execution_id: str) -> None:
    from app.engine.runner import run_execution

    try:
        if settings.RUNTIME_MODE == "kernel":
            from app.adapters.kernel_runner import run_kernel_execution

            asyncio.run(run_kernel_execution(uuid.UUID(execution_id)))
        else:
            asyncio.run(run_execution(uuid.UUID(execution_id)))
    except UnsupportedKernelWorkflowError as exc:
        asyncio.run(persist_unsupported_workflow(uuid.UUID(execution_id), str(exc)))
    except Exception as exc:  # noqa: BLE001
        if self.request.retries < self.max_retries and should_retry(
            classify_error(exc), "celery"
        ):
            raise self.retry(exc=exc, countdown=2**self.request.retries)
        asyncio.run(_fail_execution_and_push_dlq(execution_id, str(exc)))


@celery_app.task(name="agenthub.resume_workflow")
def resume_workflow_task(execution_id: str, decision: dict[str, Any]) -> None:
    from app.engine.runner import resume_execution

    asyncio.run(resume_execution(uuid.UUID(execution_id), decision))


@celery_app.task(name="agenthub.evaluate_execution")
def evaluate_execution_task(execution_id: str) -> None:
    from app.engine.evaluator import evaluate_execution

    asyncio.run(evaluate_execution(execution_id))


@celery_app.task(name="agenthub.evaluate_all_rules")
def evaluate_all_rules_task() -> None:
    from app.core.alert_evaluator import evaluate_all_rules

    asyncio.run(evaluate_all_rules())


@celery_app.task(name="agenthub.mark_stale_executions")
def mark_stale_executions_task() -> int:
    async def _mark() -> int:
        stale_before = datetime.now(timezone.utc) - timedelta(minutes=15)
        async with async_session_factory() as session:
            result = await session.execute(
                update(Execution)
                .where(
                    Execution.status == ExecutionStatus.RUNNING,
                    Execution.updated_at < stale_before,
                )
                .values(
                    status=ExecutionStatus.FAILED,
                    error_message="Execution timed out after 15 minutes",
                    completed_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()
            return result.rowcount or 0

    return asyncio.run(_mark())


@celery_app.task(name="agenthub.reconcile_state")
def reconcile_state_task() -> dict:
    from app.engine.reconciliation import (
        reconcile_stale_pending_executions,
        reconcile_tool_calls,
    )

    async def _run() -> dict:
        executions = await reconcile_stale_pending_executions()
        tool_calls = await reconcile_tool_calls()
        return {"executions": executions, "tool_calls": tool_calls}

    return asyncio.run(_run())


@celery_app.task(name="agenthub.reconcile_stale_approvals")
def reconcile_stale_approvals_task() -> dict:
    from app.engine.reconciliation import reconcile_stale_waiting_approvals

    return asyncio.run(reconcile_stale_waiting_approvals())


@celery_app.task(name="agenthub.cleanup_checkpoints")
def cleanup_checkpoints_task() -> dict:
    from app.engine.reconciliation import cleanup_old_checkpoints

    return asyncio.run(cleanup_old_checkpoints())


@celery_app.task(name="agenthub.cleanup_expired_memories")
def cleanup_expired_memories_task() -> int:
    from app.memory.service import delete_expired_memories

    return asyncio.run(delete_expired_memories())


@celery_app.task(name="agenthub.propose_growth_skills")
def propose_growth_skills_task() -> int:
    """自成长扫描：从使用数据提炼候选 Skill（每 6 小时，幂等）。"""
    from sqlalchemy import select

    from app.models import UsageEvent
    from app.skills.growth import propose_growth_skills

    async def _run() -> int:
        async with async_session_factory() as session:
            result = await session.execute(
                select(UsageEvent.organization_id)
                .where(UsageEvent.organization_id.isnot(None))
                .distinct()
            )
            orgs = [str(row[0]) for row in result.all()]
        total = 0
        for org in orgs:
            proposals = await propose_growth_skills(org)
            total += len(proposals)
        return total

    return asyncio.run(_run())


@celery_app.task(name="agenthub.evaluate_production_alerts")
def evaluate_production_alerts_task() -> int:
    from app.core.production_alerts import run_production_alerts
    from app.core.production_metrics import update_production_gauges

    async def _run() -> tuple[int, dict]:
        from app.core.production_alerts import collect_production_metrics

        metrics = await collect_production_metrics()
        update_production_gauges(metrics)
        created = await run_production_alerts()
        return len(created), metrics

    created, _metrics = asyncio.run(_run())
    return created

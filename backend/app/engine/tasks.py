from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from celery import Celery
from celery.signals import worker_process_init
import redis.asyncio as aioredis

from app.config import settings
from app.core.telemetry import setup_telemetry


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
}


@worker_process_init.connect
def setup_telemetry_on_worker(**kwargs) -> None:
    setup_telemetry()


@celery_app.task(name="agenthub.execute_workflow", bind=True, max_retries=3)
def execute_workflow_task(self, execution_id: str) -> None:
    from app.engine.runner import run_execution

    try:
        asyncio.run(run_execution(uuid.UUID(execution_id)))
    except Exception as exc:  # noqa: BLE001
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=2 ** self.request.retries)

        async def _push_dlq() -> None:
            client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            try:
                await client.rpush(
                    "dead_letter_queue",
                    json.dumps(
                        {"execution_id": execution_id, "error": str(exc), "task": "execute_workflow"}
                    ),
                )
            finally:
                await client.aclose()

        asyncio.run(_push_dlq())


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

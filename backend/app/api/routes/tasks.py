import json

import redis.asyncio as aioredis
from fastapi import APIRouter

from app.config import settings
from app.engine.tasks import execute_workflow_task

router = APIRouter(prefix="/tasks", tags=["tasks"])
DLQ_KEY = "dead_letter_queue"


@router.get("/queues")
async def queues() -> dict:
    client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        celery_len = await client.llen("celery")
        dlq_len = await client.llen(DLQ_KEY)
        return {"celery": celery_len, "dead_letter_queue": dlq_len}
    finally:
        await client.aclose()


@router.get("/failed")
async def failed(limit: int = 100) -> list[dict]:
    client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        items = await client.lrange(DLQ_KEY, 0, limit - 1)
        return [json.loads(item) for item in items]
    finally:
        await client.aclose()


@router.post("/{execution_id}/retry")
async def retry(execution_id: str) -> dict:
    execute_workflow_task.delay(execution_id)
    return {"status": "requeued", "execution_id": execution_id}

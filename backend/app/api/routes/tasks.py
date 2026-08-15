import json
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends

from app.config import settings
from app.api.deps import require_role
from app.engine.tasks import execute_workflow_task
from app.models import User

router = APIRouter(prefix="/tasks", tags=["tasks"])
DLQ_KEY = "dead_letter_queue"
AdminUserDep = Annotated[User, Depends(require_role("admin"))]


@router.get("/queues")
async def queues(_admin: AdminUserDep) -> dict:
    client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        celery_len = await client.llen("celery")
        dlq_len = await client.llen(DLQ_KEY)
        return {"celery": celery_len, "dead_letter_queue": dlq_len}
    finally:
        await client.aclose()


@router.get("/failed")
async def failed(_admin: AdminUserDep, limit: int = 100) -> list[dict]:
    client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        items = await client.lrange(DLQ_KEY, 0, limit - 1)
        return [json.loads(item) for item in items]
    finally:
        await client.aclose()


@router.post("/{execution_id}/retry")
async def retry(execution_id: str, _admin: AdminUserDep) -> dict:
    execute_workflow_task.delay(execution_id)
    return {"status": "requeued", "execution_id": execution_id}

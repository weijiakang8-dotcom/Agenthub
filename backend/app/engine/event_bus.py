from __future__ import annotations

import json
from typing import Any

import redis.asyncio as aioredis

from app.config import settings


CHANNEL_PREFIX = "agenthub:execution:"


def _channel(execution_id: str) -> str:
    return f"{CHANNEL_PREFIX}{execution_id}"


async def publish_execution_event(execution_id: str, event: dict[str, Any]) -> None:
    client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        await client.publish(
            _channel(execution_id),
            json.dumps(event, ensure_ascii=False, default=str),
        )
    finally:
        await client.aclose()

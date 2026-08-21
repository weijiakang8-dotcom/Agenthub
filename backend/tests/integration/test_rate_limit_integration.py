from __future__ import annotations

import asyncio
import uuid

import asyncpg
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.core.rate_limit import rate_limit
from app.main import app


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


async def _cleanup_rate_keys(prefix: str) -> None:
    import redis.asyncio as aioredis

    client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        async for key in client.scan_iter(match=f"rate:{prefix}*"):
            await client.delete(key)
    finally:
        await client.aclose()


def test_rate_limit_fixed_window_allows_then_denies():
    key = f"test:{uuid.uuid4().hex}"

    async def main() -> None:
        assert await rate_limit(key, 2, 60) is True
        assert await rate_limit(key, 2, 60) is True
        assert await rate_limit(key, 2, 60) is False
        await _cleanup_rate_keys(key.split(":", 1)[0] + ":")

    asyncio.run(main())


def test_login_brute_force_returns_429_after_limit():
    async def main() -> None:
        conn = await asyncpg.connect(_sync_url())
        org_id = uuid.uuid4()
        user_id = uuid.uuid4()
        email = f"brute-{uuid.uuid4().hex[:8]}@example.com"
        try:
            await conn.execute(
                "INSERT INTO organizations (id,name,slug,settings,created_at,updated_at) "
                "VALUES ($1,$2,$3,json_build_object(),now(),now())",
                org_id,
                "brute",
                "brute-" + uuid.uuid4().hex[:8],
            )
            await conn.execute(
                "INSERT INTO users (id,email,password_hash,full_name,organization_id,"
                "role,is_active,created_at,updated_at) "
                "VALUES ($1,$2,'x','brute',$3,'admin',true,now(),now())",
                user_id,
                email,
                org_id,
            )
            with TestClient(app) as client:
                statuses = []
                for _ in range(6):
                    response = client.post(
                        "/api/auth/login",
                        json={"email": email, "password": "wrong-password"},
                    )
                    statuses.append(response.status_code)
            assert statuses[:5] == [401] * 5
            assert statuses[5] == 429
        finally:
            await _cleanup_rate_keys("login:")
            await conn.execute("DELETE FROM users WHERE id=$1", user_id)
            await conn.execute("DELETE FROM organizations WHERE id=$1", org_id)
            await conn.close()

    asyncio.run(main())

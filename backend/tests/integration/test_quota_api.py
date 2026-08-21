from __future__ import annotations

import asyncio
import uuid

import asyncpg
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.core.security import create_access_token
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


async def _setup(conn: asyncpg.Connection, tag: str, role: str) -> dict[str, uuid.UUID]:
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    await conn.execute(
        "INSERT INTO organizations (id,name,slug,settings,created_at,updated_at) "
        "VALUES ($1,$2,$3,json_build_object(),now(),now())",
        org_id,
        tag,
        f"{tag}-" + uuid.uuid4().hex[:8],
    )
    await conn.execute(
        "INSERT INTO users (id,email,password_hash,full_name,organization_id,"
        "role,is_active,created_at,updated_at) "
        "VALUES ($1,$2,'x',$3,$4,$5,true,now(),now())",
        user_id,
        f"{tag}-{uuid.uuid4().hex[:8]}@example.com",
        tag,
        org_id,
        role,
    )
    return {"org": org_id, "user": user_id}


async def _cleanup_redis(org_id: uuid.UUID) -> None:
    import redis.asyncio as aioredis

    client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        keys = [
            f"quota:{org_id}:*",
            f"quota:concurrent:{org_id}",
            f"quota:limit:{org_id}:*",
        ]
        for pattern in keys:
            async for key in client.scan_iter(match=pattern):
                await client.delete(key)
    finally:
        await client.aclose()


async def _cleanup(conn: asyncpg.Connection, ids: dict[str, uuid.UUID]):
    await _cleanup_redis(ids["org"])
    await conn.execute("DELETE FROM users WHERE id=$1", ids["user"])
    await conn.execute("DELETE FROM organizations WHERE id=$1", ids["org"])


def test_quota_api_admin_update_and_member_forbidden():
    async def main() -> None:
        conn = await asyncpg.connect(_sync_url())
        admin = await _setup(conn, "quota-admin", "admin")
        member = await _setup(conn, "quota-member", "member")
        token_admin = create_access_token(admin["user"], admin["org"])
        token_member = create_access_token(member["user"], member["org"])
        try:
            with TestClient(app) as client:
                updated = client.put(
                    "/api/quotas",
                    headers={"Authorization": f"Bearer {token_admin}"},
                    json={"monthly_token_budget": 123},
                )
                assert updated.status_code == 200
                assert updated.json()["monthly_token_budget"] == 123

                fetched = client.get(
                    "/api/quotas",
                    headers={"Authorization": f"Bearer {token_admin}"},
                )
                assert fetched.status_code == 200
                assert fetched.json()["monthly_token_budget"] == 123

                forbidden = client.put(
                    "/api/quotas",
                    headers={"Authorization": f"Bearer {token_member}"},
                    json={"monthly_token_budget": 1},
                )
                assert forbidden.status_code == 403
        finally:
            await _cleanup(conn, admin)
            await _cleanup(conn, member)
            await conn.close()

    asyncio.run(main())

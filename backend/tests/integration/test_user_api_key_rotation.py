from __future__ import annotations

import asyncio
import uuid

import asyncpg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.core.security import create_access_token, decrypt_secret
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


async def _setup(conn: asyncpg.Connection, tag: str) -> dict[str, uuid.UUID]:
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
        "VALUES ($1,$2,'x',$3,$4,'admin',true,now(),now())",
        user_id,
        f"{tag}-{uuid.uuid4().hex[:8]}@example.com",
        tag,
        org_id,
    )
    return {"org": org_id, "user": user_id}


async def _cleanup(conn: asyncpg.Connection, ids: dict[str, uuid.UUID]):
    await conn.execute("DELETE FROM user_api_keys WHERE user_id=$1", ids["user"])
    await conn.execute("DELETE FROM users WHERE id=$1", ids["user"])
    await conn.execute("DELETE FROM organizations WHERE id=$1", ids["org"])


def test_user_api_key_rotation_and_ownership():
    async def main() -> None:
        conn = await asyncpg.connect(_sync_url())
        owner = await _setup(conn, "key-owner")
        other = await _setup(conn, "key-other")
        token_owner = create_access_token(owner["user"], owner["org"])
        token_other = create_access_token(other["user"], other["org"])
        try:
            with TestClient(app) as client:
                headers_owner = {"Authorization": f"Bearer {token_owner}"}
                headers_other = {"Authorization": f"Bearer {token_other}"}

                created = client.post(
                    "/api/user-api-keys",
                    headers=headers_owner,
                    json={
                        "provider": "deepseek",
                        "model": "deepseek-chat",
                        "base_url": "https://api.deepseek.com/v1",
                        "api_key": "sk-old-1234",
                    },
                )
                assert created.status_code == 201
                key_id = created.json()["id"]
                assert created.json()["api_key_masked"].endswith("1234")

                rotated = client.post(
                    f"/api/user-api-keys/{key_id}/rotate",
                    headers=headers_owner,
                    json={"api_key": "sk-new-9999"},
                )
                assert rotated.status_code == 200
                assert rotated.json()["api_key_masked"].endswith("9999")
                assert rotated.json()["is_active"] is True

                from app.database import async_session_factory
                from app.models import UserApiKey

                async with async_session_factory() as session:
                    row = (
                        await session.execute(
                            select(UserApiKey).where(UserApiKey.id == uuid.UUID(key_id))
                        )
                    ).scalar_one()
                    assert decrypt_secret(row.api_key_encrypted) == "sk-new-9999"

                assert (
                    client.post(
                        f"/api/user-api-keys/{key_id}/rotate",
                        headers=headers_other,
                        json={"api_key": "sk-hack-0000"},
                    ).status_code
                    == 404
                )
        finally:
            await _cleanup(conn, owner)
            await _cleanup(conn, other)
            await conn.close()

    asyncio.run(main())

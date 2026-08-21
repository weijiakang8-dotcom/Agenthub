from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import asyncpg
import pytest
from sqlalchemy import select

from app.config import settings
from app.memory import service as memory_service


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


async def _setup(conn: asyncpg.Connection) -> tuple[uuid.UUID, uuid.UUID]:
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    await conn.execute(
        "INSERT INTO organizations (id,name,slug,settings,created_at,updated_at) "
        "VALUES ($1,$2,$3,json_build_object(),now(),now())",
        org_id,
        "mem-lifecycle",
        "mem-lifecycle-" + uuid.uuid4().hex[:8],
    )
    await conn.execute(
        "INSERT INTO users (id,email,password_hash,full_name,organization_id,"
        "role,is_active,created_at,updated_at) "
        "VALUES ($1,$2,'x','mem',$3,'admin',true,now(),now())",
        user_id,
        f"mem-{uuid.uuid4().hex[:8]}@example.com",
        org_id,
    )
    return org_id, user_id


async def _cleanup(conn: asyncpg.Connection, org_id: uuid.UUID, user_id: uuid.UUID):
    await conn.execute("DELETE FROM user_memories WHERE user_id=$1", user_id)
    await conn.execute("DELETE FROM users WHERE id=$1", user_id)
    await conn.execute("DELETE FROM organizations WHERE id=$1", org_id)


def _embedding_ready() -> bool:
    """embedding 服务可用性：hash 提供者无需服务；ollama 需可达。"""
    if settings.EMBEDDING_PROVIDER == "hash":
        return True

    async def check() -> bool:
        try:
            import httpx

            async with httpx.AsyncClient(timeout=1.5) as client:
                response = await client.get(
                    settings.EMBEDDING_BASE_URL.rstrip("/") + "/api/tags"
                )
                return response.status_code == 200
        except Exception:  # noqa: BLE001
            return False

    return asyncio.run(check())


embedding_required = pytest.mark.skipif(
    not _embedding_ready(),
    reason="requires an embedding service (or EMBEDDING_PROVIDER=hash)",
)


@embedding_required
def test_add_memory_applies_default_ttl(monkeypatch):
    monkeypatch.setattr(settings, "MEMORY_DEFAULT_TTL_DAYS", 30)

    async def main() -> None:
        conn = await asyncpg.connect(_sync_url())
        org_id, user_id = await _setup(conn)
        try:
            memory = await memory_service.add_memory(
                user_id=user_id,
                organization_id=org_id,
                content="默认 TTL 测试",
                source="test",
            )
            assert memory.expires_at is not None
            assert memory.expires_at > datetime.now(timezone.utc) + timedelta(days=29)
        finally:
            await _cleanup(conn, org_id, user_id)
            await conn.close()

    asyncio.run(main())


@embedding_required
def test_delete_expired_memories_removes_only_expired(monkeypatch):
    monkeypatch.setattr(settings, "MEMORY_DEFAULT_TTL_DAYS", 0)

    async def main() -> None:
        conn = await asyncpg.connect(_sync_url())
        org_id, user_id = await _setup(conn)
        try:
            await memory_service.add_memory(
                user_id=user_id,
                organization_id=org_id,
                content="过期记忆",
                expires_at=datetime.now(timezone.utc) - timedelta(days=1),
                source="test",
            )
            fresh = await memory_service.add_memory(
                user_id=user_id,
                organization_id=org_id,
                content="未过期记忆",
                expires_at=datetime.now(timezone.utc) + timedelta(days=1),
                source="test",
            )
            deleted = await memory_service.delete_expired_memories()

            assert deleted >= 1
            from app.database import async_session_factory

            async with async_session_factory() as session:
                rows = list(
                    (
                        await session.execute(
                            select(memory_service.UserMemory).where(
                                memory_service.UserMemory.user_id == user_id
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
            assert [row.id for row in rows] == [fresh.id]
        finally:
            await _cleanup(conn, org_id, user_id)
            await conn.close()

    asyncio.run(main())


def test_cleanup_memories_task_is_scheduled():
    from app.engine.tasks import celery_app

    schedule = celery_app.conf.beat_schedule
    assert "cleanup-expired-memories" in schedule
    assert schedule["cleanup-expired-memories"]["task"] == (
        "agenthub.cleanup_expired_memories"
    )

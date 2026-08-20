"""C-4 契约测试：reconciliation 幂等（重复运行零状态变化、零重复审计）。

运行：
  DATABASE_URL=postgresql+asyncpg://postgres@localhost:5432/agenthub_benchmark_p0 \
  python -m pytest tests/integration/test_c4_reconciliation_idempotent.py -q
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone

import asyncpg
import pytest

from app.config import settings
from app.engine.reconciliation import (
    reconcile_stale_pending_executions,
    reconcile_tool_calls,
)


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


async def _setup(conn: asyncpg.Connection) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    workflow_id = uuid.uuid4()
    await conn.execute(
        "INSERT INTO organizations (id,name,slug,settings,created_at,updated_at) "
        "VALUES ($1,$2,$3,json_build_object(),now(),now())",
        org_id,
        "c4",
        "c4-" + uuid.uuid4().hex[:8],
    )
    await conn.execute(
        "INSERT INTO users (id,email,password_hash,full_name,organization_id,"
        "role,is_active,created_at,updated_at) "
        "VALUES ($1,$2,'x','c4',$3,'admin',true,now(),now())",
        user_id,
        f"c4-{uuid.uuid4().hex[:8]}@example.com",
        org_id,
    )
    await conn.execute(
        "INSERT INTO workflows (id,name,description,agent_chain,dag_definition,"
        "status,created_by,organization_id,created_at,updated_at) "
        "VALUES ($1,'c4','','[]'::json,'{}'::json,'active','c4',$2,now(),now())",
        workflow_id,
        org_id,
    )
    return org_id, user_id, workflow_id


async def _insert_execution(
    conn: asyncpg.Connection,
    workflow_id: uuid.UUID,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    status: str,
    updated_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> uuid.UUID:
    execution_id = uuid.uuid4()
    updated = updated_at or datetime.now(timezone.utc)
    await conn.execute(
        "INSERT INTO executions (id,workflow_id,status,correlation_id,user_input,"
        "context_messages,intent,plan,organization_id,user_id,current_step_index,"
        "event_sequence,created_at,updated_at,completed_at) "
        "VALUES ($1,$2,$3,$4,'c4','[]'::json,'{}'::json,NULL,$5,$6,0,0,now(),$7,$8)",
        execution_id,
        workflow_id,
        status,
        uuid.uuid4(),
        org_id,
        user_id,
        updated,
        completed_at,
    )
    return execution_id


async def _insert_legacy_tool_call(
    conn: asyncpg.Connection,
    execution_id: uuid.UUID,
    org_id: uuid.UUID,
    *,
    updated_at: datetime,
) -> uuid.UUID:
    tool_call_id = uuid.uuid4()
    await conn.execute(
        "INSERT INTO tool_calls (id,execution_id,tool_name,input_params,status,"
        "requires_approval,idempotency_key,organization_id,created_at,updated_at) "
        "VALUES ($1,$2,'send_email',$3::json,'pending',true,NULL,$4,$5,$5)",
        tool_call_id,
        execution_id,
        json.dumps({"to": "a@b.com", "subject": "s", "body": "b"}),
        org_id,
        updated_at,
    )
    return tool_call_id


async def _audit_count(
    conn: asyncpg.Connection,
    execution_id: uuid.UUID,
    action: str,
    tool_call_id: uuid.UUID,
) -> int:
    return int(
        await conn.fetchval(
            "SELECT count(*) FROM audit_logs WHERE resource_id=$1 "
            "AND action=$2 AND details->>'tool_call_id'=$3",
            str(execution_id),
            action,
            str(tool_call_id),
        )
    )


async def _cleanup(
    conn: asyncpg.Connection,
    *,
    executions: list[uuid.UUID],
    workflow_id: uuid.UUID,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
) -> None:
    for execution_id in executions:
        await conn.execute(
            "DELETE FROM audit_logs WHERE resource_id = $1", str(execution_id)
        )
        for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
            try:
                await conn.execute(
                    f"DELETE FROM {table} WHERE thread_id = $1", str(execution_id)
                )
            except asyncpg.UndefinedTableError:
                pass
        await conn.execute("DELETE FROM tool_calls WHERE execution_id=$1", execution_id)
        await conn.execute("DELETE FROM executions WHERE id=$1", execution_id)
    await conn.execute("DELETE FROM workflows WHERE id=$1", workflow_id)
    await conn.execute("DELETE FROM users WHERE id=$1", user_id)
    await conn.execute("DELETE FROM organizations WHERE id=$1", org_id)


def test_legacy_pending_reconcile_is_idempotent():
    async def main() -> None:
        conn = await asyncpg.connect(_sync_url())
        org_id, user_id, workflow_id = await _setup(conn)
        terminal_id = await _insert_execution(
            conn,
            workflow_id,
            org_id,
            user_id,
            status="failed",
            completed_at=datetime.now(timezone.utc),
        )
        old = datetime.now(timezone.utc) - timedelta(minutes=60)
        legacy_id = await _insert_legacy_tool_call(
            conn, terminal_id, org_id, updated_at=old
        )
        try:
            first = await reconcile_tool_calls()
            assert first["manual_flagged"] == 1
            assert (
                await _audit_count(
                    conn, terminal_id, "tool_call_manual_required", legacy_id
                )
                == 1
            )
            second = await reconcile_tool_calls()
            assert second["manual_flagged"] == 0
            assert (
                await _audit_count(
                    conn, terminal_id, "tool_call_manual_required", legacy_id
                )
                == 1
            )
            third = await reconcile_tool_calls()
            assert third["manual_flagged"] == 0
            assert (
                await _audit_count(
                    conn, terminal_id, "tool_call_manual_required", legacy_id
                )
                == 1
            )
        finally:
            await _cleanup(
                conn,
                executions=[terminal_id],
                workflow_id=workflow_id,
                user_id=user_id,
                org_id=org_id,
            )
            await conn.close()

    asyncio.run(main())


def test_stale_execution_reconcile_unaffected():
    async def main() -> None:
        conn = await asyncpg.connect(_sync_url())
        org_id, user_id, workflow_id = await _setup(conn)
        stale_id = await _insert_execution(
            conn,
            workflow_id,
            org_id,
            user_id,
            status="pending",
            updated_at=datetime.now(timezone.utc) - timedelta(minutes=60),
        )
        try:
            first = await reconcile_stale_pending_executions()
            assert first["reconciled"] == 1
            second = await reconcile_stale_pending_executions()
            assert second["reconciled"] == 0
            audits = int(
                await conn.fetchval(
                    "SELECT count(*) FROM audit_logs WHERE resource_id=$1 "
                    "AND action='execution_reconciled'",
                    str(stale_id),
                )
            )
            assert audits == 1
        finally:
            await _cleanup(
                conn,
                executions=[stale_id],
                workflow_id=workflow_id,
                user_id=user_id,
                org_id=org_id,
            )
            await conn.close()

    asyncio.run(main())


def test_multiple_legacy_tool_calls_each_flagged_once():
    async def main() -> None:
        conn = await asyncpg.connect(_sync_url())
        org_id, user_id, workflow_id = await _setup(conn)
        terminal_a = await _insert_execution(
            conn,
            workflow_id,
            org_id,
            user_id,
            status="failed",
            completed_at=datetime.now(timezone.utc),
        )
        terminal_b = await _insert_execution(
            conn,
            workflow_id,
            org_id,
            user_id,
            status="failed",
            completed_at=datetime.now(timezone.utc),
        )
        old = datetime.now(timezone.utc) - timedelta(minutes=60)
        legacy_a = await _insert_legacy_tool_call(
            conn, terminal_a, org_id, updated_at=old
        )
        legacy_b = await _insert_legacy_tool_call(
            conn, terminal_b, org_id, updated_at=old
        )
        try:
            first = await reconcile_tool_calls()
            assert first["manual_flagged"] == 2
            assert (
                await _audit_count(
                    conn, terminal_a, "tool_call_manual_required", legacy_a
                )
                == 1
            )
            assert (
                await _audit_count(
                    conn, terminal_b, "tool_call_manual_required", legacy_b
                )
                == 1
            )
            second = await reconcile_tool_calls()
            assert second["manual_flagged"] == 0
            assert (
                await _audit_count(
                    conn, terminal_a, "tool_call_manual_required", legacy_a
                )
                == 1
            )
            assert (
                await _audit_count(
                    conn, terminal_b, "tool_call_manual_required", legacy_b
                )
                == 1
            )
        finally:
            await _cleanup(
                conn,
                executions=[terminal_a, terminal_b],
                workflow_id=workflow_id,
                user_id=user_id,
                org_id=org_id,
            )
            await conn.close()

    asyncio.run(main())

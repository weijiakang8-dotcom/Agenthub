"""悬挂审批超时收敛测试：WAITING_FOR_APPROVAL 超时 → FAILED + audit（CAS 幂等）。"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import asyncpg
import pytest

from app.config import settings
from app.engine.reconciliation import reconcile_stale_waiting_approvals


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


def test_stale_waiting_approval_reconciled_once():
    async def main() -> None:
        conn = await asyncpg.connect(_sync_url())
        org_id = uuid.uuid4()
        user_id = uuid.uuid4()
        workflow_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO organizations (id,name,slug,settings,created_at,updated_at) "
            "VALUES ($1,'at','at','{}'::json,now(),now())",
            org_id,
        )
        await conn.execute(
            "INSERT INTO users (id,email,password_hash,full_name,organization_id,"
            "role,is_active,created_at,updated_at) "
            "VALUES ($1,'at@e.com','x','at',$2,'admin',true,now(),now())",
            user_id,
            org_id,
        )
        await conn.execute(
            "INSERT INTO workflows (id,name,description,agent_chain,dag_definition,"
            "status,created_by,organization_id,created_at,updated_at) "
            "VALUES ($1,'at','','[]'::json,'{}'::json,'active','at',$2,now(),now())",
            workflow_id,
            org_id,
        )
        stale_id = uuid.uuid4()
        fresh_id = uuid.uuid4()
        old = datetime.now(timezone.utc) - timedelta(
            minutes=settings.RECONCILE_APPROVAL_MINUTES + 5
        )
        for execution_id, updated_at in ((stale_id, old), (fresh_id, None)):
            await conn.execute(
                "INSERT INTO executions (id,workflow_id,status,correlation_id,user_input,"
                "context_messages,intent,plan,organization_id,user_id,current_step_index,"
                "event_sequence,created_at,updated_at) VALUES "
                "($1,$2,'waiting_for_approval',$3,'at','[]'::json,'{}'::json,NULL,$4,$5,0,0,now(),COALESCE($6,now()))",
                execution_id,
                workflow_id,
                uuid.uuid4(),
                org_id,
                user_id,
                updated_at,
            )
        try:
            first = await reconcile_stale_waiting_approvals()
            second = await reconcile_stale_waiting_approvals()
            assert first["reconciled"] == 1
            assert second["reconciled"] == 0
            statuses = dict(
                await conn.fetch(
                    "SELECT id, status FROM executions WHERE id = ANY($1::uuid[])",
                    [stale_id, fresh_id],
                )
            )
            assert statuses[stale_id] == "failed"
            assert statuses[fresh_id] == "waiting_for_approval"
            audit_count = await conn.fetchval(
                "SELECT count(*) FROM audit_logs WHERE resource_id=$1 "
                "AND action='approval_timeout_reconciled'",
                str(stale_id),
            )
            assert audit_count == 1
        finally:
            for execution_id in (stale_id, fresh_id):
                await conn.execute(
                    "DELETE FROM audit_logs WHERE resource_id=$1", str(execution_id)
                )
                await conn.execute("DELETE FROM executions WHERE id=$1", execution_id)
            await conn.execute("DELETE FROM workflows WHERE id=$1", workflow_id)
            await conn.execute("DELETE FROM users WHERE id=$1", user_id)
            await conn.execute("DELETE FROM organizations WHERE id=$1", org_id)
            await conn.close()

    asyncio.run(main())

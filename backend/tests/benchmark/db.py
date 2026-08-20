"""Benchmark 数据库夹具：隔离的本地 PostgreSQL，不触碰任何生产数据。"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import asyncpg

from app.config import settings


def sync_url() -> str:
    return settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")


async def db_ready() -> bool:
    try:
        conn = await asyncpg.connect(sync_url())
        try:
            version = int(
                await conn.fetchval("SELECT version_num FROM alembic_version")
            )
            in_flight = int(
                await conn.fetchval(
                    "SELECT count(*) FROM pg_enum "
                    "WHERE enumlabel='in_flight' AND enumtypid='tool_call_status'::regtype"
                )
            )
            unique_idx = int(
                await conn.fetchval(
                    "SELECT count(*) FROM pg_indexes "
                    "WHERE indexname='uq_tool_calls_exec_idempotency'"
                )
            )
            return version >= 19 and in_flight == 1 and unique_idx == 1
        finally:
            await conn.close()
    except Exception:  # noqa: BLE001
        return False


async def setup_org(
    conn: asyncpg.Connection, tag: str
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    workflow_id = uuid.uuid4()
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
        "VALUES ($1,$2,'x', $3, $4,'admin',true,now(),now())",
        user_id,
        f"{tag}-{uuid.uuid4().hex[:8]}@example.com",
        tag,
        org_id,
    )
    await conn.execute(
        "INSERT INTO workflows (id,name,description,agent_chain,dag_definition,"
        "status,created_by,organization_id,created_at,updated_at) "
        "VALUES ($1,$2,'','[]'::json,'{}'::json,'active',$3,$4,now(),now())",
        workflow_id,
        tag,
        tag,
        org_id,
    )
    return org_id, user_id, workflow_id


async def insert_execution(
    conn: asyncpg.Connection,
    workflow_id: uuid.UUID,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    status: str = "pending",
    user_input: str = "benchmark",
    intent: dict[str, Any] | None = None,
    updated_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> uuid.UUID:
    execution_id = uuid.uuid4()
    updated = updated_at or datetime.now(timezone.utc)
    await conn.execute(
        "INSERT INTO executions (id,workflow_id,status,correlation_id,user_input,"
        "context_messages,intent,plan,organization_id,user_id,current_step_index,"
        "event_sequence,created_at,updated_at,completed_at) "
        "VALUES ($1,$2,$3,$4,$5,'[]'::json,$6::json,NULL,$7,$8,0,0,now(),$9,$10)",
        execution_id,
        workflow_id,
        status,
        uuid.uuid4(),
        user_input,
        json.dumps(intent) if intent is not None else None,
        org_id,
        user_id,
        updated,
        completed_at,
    )
    return execution_id


async def insert_tool_call(
    conn: asyncpg.Connection,
    execution_id: uuid.UUID,
    org_id: uuid.UUID,
    *,
    tool_name: str,
    params: dict[str, Any],
    status: str,
    idempotency_key: str | None = None,
    requires_approval: bool = True,
    updated_at: datetime | None = None,
) -> uuid.UUID:
    tool_call_id = uuid.uuid4()
    ts = updated_at or datetime.now(timezone.utc)
    await conn.execute(
        "INSERT INTO tool_calls (id,execution_id,tool_name,input_params,status,"
        "requires_approval,idempotency_key,organization_id,created_at,updated_at) "
        "VALUES ($1,$2,$3,$4::json,$5,$6,$7,$8,$9,$10)",
        tool_call_id,
        execution_id,
        tool_name,
        json.dumps(params),
        status,
        requires_approval,
        idempotency_key,
        org_id,
        ts,
        ts,
    )
    return tool_call_id


async def mark_execution(
    conn: asyncpg.Connection,
    execution_id: uuid.UUID,
    status: str,
    *,
    error_message: str | None = None,
    final_output: str | None = None,
) -> None:
    await conn.execute(
        "UPDATE executions SET status=$2, completed_at=now(), "
        "error_message=$3, final_output=COALESCE($4, final_output) "
        "WHERE id=$1",
        str(execution_id),
        status,
        error_message,
        final_output,
    )


async def fetch_evidence(
    conn: asyncpg.Connection, execution_id: uuid.UUID
) -> dict[str, Any]:
    execution = await conn.fetchrow(
        "SELECT status, event_sequence, completed_at, error_message, final_output "
        "FROM executions WHERE id=$1",
        str(execution_id),
    )
    tool_rows = await conn.fetch(
        "SELECT tool_name, status, idempotency_key, input_params, output_result "
        "FROM tool_calls WHERE execution_id=$1 ORDER BY created_at",
        str(execution_id),
    )
    audits = await conn.fetch(
        "SELECT action FROM audit_logs WHERE resource_id=$1 ORDER BY created_at",
        str(execution_id),
    )
    return {
        "execution": dict(execution) if execution else None,
        "tool_calls": [dict(row) for row in tool_rows],
        "audits": [str(row["action"]) for row in audits],
    }


async def cleanup(
    conn: asyncpg.Connection,
    *,
    executions: list[uuid.UUID],
    workflows: list[uuid.UUID],
    users: list[uuid.UUID],
    orgs: list[uuid.UUID],
) -> None:
    exec_ids = [str(execution_id) for execution_id in executions]
    if exec_ids:
        await conn.execute(
            "DELETE FROM audit_logs WHERE resource_id = ANY($1::text[])",
            exec_ids,
        )
        for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
            try:
                await conn.execute(
                    f"DELETE FROM {table} WHERE thread_id = ANY($1::text[])",
                    exec_ids,
                )
            except asyncpg.UndefinedTableError:
                pass
        await conn.execute(
            "DELETE FROM tool_calls WHERE execution_id = ANY($1::uuid[])",
            executions,
        )
        await conn.execute(
            "DELETE FROM executions WHERE id = ANY($1::uuid[])", executions
        )
    if workflows:
        await conn.execute(
            "DELETE FROM workflows WHERE id = ANY($1::uuid[])", workflows
        )
    if users:
        await conn.execute("DELETE FROM users WHERE id = ANY($1::uuid[])", users)
    if orgs:
        await conn.execute("DELETE FROM organizations WHERE id = ANY($1::uuid[])", orgs)

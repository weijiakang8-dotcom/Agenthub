"""跨租户 API 隔离回归：executions / conversations / tool_calls 必须 404 或空。"""

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


async def _setup(conn: asyncpg.Connection, tag: str) -> dict[str, uuid.UUID]:
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
        "VALUES ($1,$2,'x',$3,$4,'admin',true,now(),now())",
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
        f"{tag}-wf",
        tag,
        org_id,
    )
    execution_id = uuid.uuid4()
    await conn.execute(
        "INSERT INTO executions (id,workflow_id,status,correlation_id,user_input,"
        "context_messages,intent,plan,organization_id,user_id,current_step_index,"
        "event_sequence,created_at,updated_at) "
        "VALUES ($1,$2,'completed',$3,$4,'[]'::json,'{}'::json,NULL,$5,$6,0,0,now(),now())",
        execution_id,
        workflow_id,
        uuid.uuid4(),
        f"{tag}-task",
        org_id,
        user_id,
    )
    conversation_id = uuid.uuid4()
    await conn.execute(
        "INSERT INTO conversations (id,user_id,organization_id,title,messages,summary,"
        "created_at,updated_at) "
        "VALUES ($1,$2,$3,$4,'[]'::json,NULL,now(),now())",
        conversation_id,
        user_id,
        org_id,
        f"{tag}-conv",
    )
    tool_call_id = uuid.uuid4()
    await conn.execute(
        "INSERT INTO tool_calls (id,execution_id,tool_name,input_params,output_result,"
        "status,requires_approval,organization_id,idempotency_key,created_at,updated_at) "
        "VALUES ($1,$2,'query_db','{}'::json,'{}'::json,'success',false,$3,$4,now(),now())",
        tool_call_id,
        execution_id,
        org_id,
        f"{tag}-key",
    )
    return {
        "org": org_id,
        "user": user_id,
        "workflow": workflow_id,
        "execution": execution_id,
        "conversation": conversation_id,
        "tool_call": tool_call_id,
    }


async def _cleanup(conn: asyncpg.Connection, ids: dict[str, uuid.UUID]) -> None:
    await conn.execute(
        "DELETE FROM audit_logs WHERE resource_id=$1",
        str(ids["execution"]),
    )
    for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
        try:
            await conn.execute(
                f"DELETE FROM {table} WHERE thread_id=$1",
                str(ids["execution"]),
            )
        except asyncpg.UndefinedTableError:
            pass
    await conn.execute("DELETE FROM tool_calls WHERE id=$1", ids["tool_call"])
    await conn.execute("DELETE FROM conversations WHERE id=$1", ids["conversation"])
    await conn.execute("DELETE FROM executions WHERE id=$1", ids["execution"])
    await conn.execute("DELETE FROM workflows WHERE id=$1", ids["workflow"])
    await conn.execute("DELETE FROM users WHERE id=$1", ids["user"])
    await conn.execute("DELETE FROM organizations WHERE id=$1", ids["org"])


def test_cross_tenant_api_isolation():
    async def main() -> None:
        conn = await asyncpg.connect(_sync_url())
        ids_a = await _setup(conn, "iso-a")
        ids_b = await _setup(conn, "iso-b")
        token_a = create_access_token(ids_a["user"], ids_a["org"])
        token_b = create_access_token(ids_b["user"], ids_b["org"])
        try:
            with TestClient(app) as client:
                headers_a = {"Authorization": f"Bearer {token_a}"}
                headers_b = {"Authorization": f"Bearer {token_b}"}

                # 同租户可见
                assert (
                    client.get(
                        f"/api/executions/{ids_a['execution']}", headers=headers_a
                    ).status_code
                    == 200
                )
                assert (
                    client.get(
                        f"/api/conversations/{ids_a['conversation']}",
                        headers=headers_a,
                    ).status_code
                    == 200
                )
                assert (
                    client.get(
                        f"/api/tool_calls/{ids_a['tool_call']}", headers=headers_a
                    ).status_code
                    == 200
                )

                # 跨租户一律 404（不泄露存在性）
                for path in (
                    f"/api/executions/{ids_b['execution']}",
                    f"/api/conversations/{ids_b['conversation']}",
                    f"/api/tool_calls/{ids_b['tool_call']}",
                ):
                    assert client.get(path, headers=headers_a).status_code == 404
                for path in (
                    f"/api/executions/{ids_a['execution']}",
                    f"/api/conversations/{ids_a['conversation']}",
                    f"/api/tool_calls/{ids_a['tool_call']}",
                ):
                    assert client.get(path, headers=headers_b).status_code == 404

                # 按 execution 列工具调用时，跨租户 execution 返回空
                response = client.get(
                    f"/api/tool_calls?execution_id={ids_b['execution']}",
                    headers=headers_a,
                )
                assert response.status_code == 200
                assert response.json() == []
        finally:
            await _cleanup(conn, ids_a)
            await _cleanup(conn, ids_b)
            await conn.close()

    asyncio.run(main())

"""执行轨迹产品字段集成测试：cost / token / verify_status / mismatch / 冻结提案。"""

from __future__ import annotations

import asyncio
import json
import uuid
from types import SimpleNamespace

import asyncpg
import pytest

from app.api.routes import executions as exec_routes
from app.config import settings
from app.database import async_session_factory


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


def test_trace_includes_reliability_fields():
    async def main() -> None:
        conn = await asyncpg.connect(_sync_url())
        org_id = uuid.uuid4()
        user_id = uuid.uuid4()
        workflow_id = uuid.uuid4()
        execution_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO organizations (id,name,slug,settings,created_at,updated_at) "
            "VALUES ($1,'tp','tp','{}'::json,now(),now())",
            org_id,
        )
        await conn.execute(
            "INSERT INTO users (id,email,password_hash,full_name,organization_id,"
            "role,is_active,created_at,updated_at) "
            "VALUES ($1,'tp@e.com','x','tp',$2,'admin',true,now(),now())",
            user_id,
            org_id,
        )
        await conn.execute(
            "INSERT INTO workflows (id,name,description,agent_chain,dag_definition,"
            "status,created_by,organization_id,created_at,updated_at) "
            "VALUES ($1,'tp','','[]'::json,'{}'::json,'active','tp',$2,now(),now())",
            workflow_id,
            org_id,
        )
        plan = {
            "goal": "发邮件",
            "risk": "SIDE_EFFECT",
            "side_effect_proposals": [
                {
                    "step_id": "s1",
                    "capability": "send_email",
                    "tool": "send_email",
                    "params": {"to": "a@b.com"},
                    "params_canonical": '{"to":"a@b.com"}',
                }
            ],
        }
        await conn.execute(
            "INSERT INTO executions (id,workflow_id,status,correlation_id,user_input,"
            "context_messages,intent,plan,organization_id,user_id,current_step_index,"
            "event_sequence,created_at,updated_at,completed_at,cost,token_usage,model_used) "
            "VALUES ($1,$2,'completed',$3,'tp','[]'::json,'{}'::json,$4::json,$5,$6,0,0,"
            "now(),now(),now(),0.01,$7::json,$8::json)",
            execution_id,
            workflow_id,
            uuid.uuid4(),
            json.dumps(plan),
            org_id,
            user_id,
            json.dumps({"gpt": {"input_tokens": 10, "output_tokens": 5}}),
            json.dumps(["deepseek-v4-pro"]),
        )
        tool_call_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO tool_calls (id,execution_id,tool_name,input_params,status,"
            "requires_approval,idempotency_key,organization_id,started_at,completed_at) "
            "VALUES ($1,$2,'send_email',$3::json,'success',true,$4,$5,now(),now())",
            tool_call_id,
            execution_id,
            json.dumps({"to": "a@b.com"}),
            "k",
            org_id,
        )
        await conn.execute(
            "INSERT INTO audit_logs (id,organization_id,user_id,method,path,status_code,"
            "action,resource_type,resource_id,details,created_at,updated_at) VALUES "
            "($1,$2,$3,'EXEC','/x',0,'verify_unknown','execution',$4,'{}'::json,now(),now()),"
            "($5,$2,$3,'EXEC','/x',0,'approval_mismatch','execution',$4,'{}'::json,now(),now())",
            uuid.uuid4(),
            org_id,
            user_id,
            str(execution_id),
            uuid.uuid4(),
        )
        try:
            user = SimpleNamespace(id=user_id, organization_id=org_id)
            async with async_session_factory() as session:
                trace = await exec_routes.get_execution_trace(
                    execution_id, session, user
                )
                assert trace.cost == 0.01
                assert trace.verify_status == "verify_unknown"
                assert trace.approval_mismatch_count == 1
                assert trace.side_effect_proposals[0]["tool"] == "send_email"
                assert trace.tool_calls[0].input_params == {"to": "a@b.com"}
        finally:
            await conn.execute(
                "DELETE FROM audit_logs WHERE resource_id=$1", str(execution_id)
            )
            await conn.execute(
                "DELETE FROM tool_calls WHERE execution_id=$1", execution_id
            )
            await conn.execute("DELETE FROM executions WHERE id=$1", execution_id)
            await conn.execute("DELETE FROM workflows WHERE id=$1", workflow_id)
            await conn.execute("DELETE FROM users WHERE id=$1", user_id)
            await conn.execute("DELETE FROM organizations WHERE id=$1", org_id)
            await conn.close()

    asyncio.run(main())

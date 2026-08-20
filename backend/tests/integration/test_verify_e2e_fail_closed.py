"""Verify Fail-Closed 端到端集成：完整执行流走到 verify 的 PASS/UNKNOWN/ERROR。

覆盖：COMPLETED 终态 + verify_unknown / verify_error 审计；无 replan。
"""

from __future__ import annotations

import asyncio
import json
import uuid

import asyncpg
import pytest
from langchain_core.messages import AIMessage

from app.config import settings
from app.engine import graph as graph_module
from app.engine import runner


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


class ScriptedGateway:
    def __init__(self, verify_content: str | None, verify_raise: bool = False):
        self.verify_content = verify_content
        self.verify_raise = verify_raise
        self.verify_calls = 0

    async def select(self, **kwargs):
        return [object()]

    async def invoke(self, llms, messages, **kwargs):
        task_type = kwargs.get("task_type")
        if task_type == "plan":
            return AIMessage(
                content=json.dumps(
                    {
                        "goal": "检查",
                        "risk": "HIGH",
                        "steps": [
                            {
                                "step_id": "s1",
                                "capability": "answer",
                                "description": "回答",
                            }
                        ],
                        "reason": "r",
                    },
                    ensure_ascii=False,
                )
            )
        if task_type == "verify":
            self.verify_calls += 1
            if self.verify_raise:
                raise TimeoutError("verify timeout")
            return AIMessage(content=self.verify_content)
        return AIMessage(content="ok")

    async def stream(self, llms, messages, **kwargs):
        yield "输出已完整满足需求。"


async def _setup(
    conn: asyncpg.Connection,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    workflow_id = uuid.uuid4()
    await conn.execute(
        "INSERT INTO organizations (id,name,slug,settings,created_at,updated_at) "
        "VALUES ($1,$2,$3,json_build_object(),now(),now())",
        org_id,
        "vfy",
        "vfy-" + uuid.uuid4().hex[:8],
    )
    await conn.execute(
        "INSERT INTO users (id,email,password_hash,full_name,organization_id,"
        "role,is_active,created_at,updated_at) "
        "VALUES ($1,$2,'x','vfy',$3,'admin',true,now(),now())",
        user_id,
        f"vfy-{uuid.uuid4().hex[:8]}@example.com",
        org_id,
    )
    await conn.execute(
        "INSERT INTO workflows (id,name,description,agent_chain,dag_definition,"
        "status,created_by,organization_id,created_at,updated_at) "
        "VALUES ($1,'vfy','','[]'::json,'{}'::json,'active','vfy',$2,now(),now())",
        workflow_id,
        org_id,
    )
    execution_id = uuid.uuid4()
    await conn.execute(
        "INSERT INTO executions (id,workflow_id,status,correlation_id,user_input,"
        "context_messages,intent,plan,organization_id,user_id,current_step_index,"
        "event_sequence,created_at,updated_at) "
        "VALUES ($1,$2,'pending',$3,'vfy','[]'::json,$4::json,NULL,$5,$6,0,0,now(),now())",
        execution_id,
        workflow_id,
        uuid.uuid4(),
        json.dumps({"category": "TASK", "risk": "HIGH"}),
        org_id,
        user_id,
    )
    return org_id, user_id, workflow_id, execution_id


async def _cleanup(
    conn: asyncpg.Connection,
    *,
    execution_id: uuid.UUID,
    workflow_id: uuid.UUID,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
) -> None:
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


async def _run(monkeypatch, gateway: ScriptedGateway, execution_id: uuid.UUID) -> None:
    monkeypatch.setattr(graph_module._gateway, "invoke", gateway.invoke)
    monkeypatch.setattr(graph_module._gateway, "stream", gateway.stream)
    monkeypatch.setattr(
        runner.evaluate_execution_task, "delay", lambda execution_id: None
    )
    await runner.run_execution(execution_id)


async def _audits(conn: asyncpg.Connection, execution_id: uuid.UUID) -> list[str]:
    rows = await conn.fetch(
        "SELECT action FROM audit_logs WHERE resource_id=$1", str(execution_id)
    )
    return [row["action"] for row in rows]


async def _status(conn: asyncpg.Connection, execution_id: uuid.UUID) -> str:
    return await conn.fetchval(
        "SELECT status FROM executions WHERE id=$1", str(execution_id)
    )


def test_verify_pass_end_to_end(monkeypatch):
    async def main() -> None:
        conn = await asyncpg.connect(_sync_url())
        org_id, user_id, workflow_id, execution_id = await _setup(conn)
        gateway = ScriptedGateway(verify_content="PASS")
        try:
            await _run(monkeypatch, gateway, execution_id)
            assert await _status(conn, execution_id) == "completed"
            assert gateway.verify_calls == 1
            actions = await _audits(conn, execution_id)
            assert "verify_unknown" not in actions
            assert "verify_error" not in actions
        finally:
            await _cleanup(
                conn,
                execution_id=execution_id,
                workflow_id=workflow_id,
                user_id=user_id,
                org_id=org_id,
            )
            await conn.close()

    asyncio.run(main())


def test_verify_unknown_end_to_end(monkeypatch):
    async def main() -> None:
        conn = await asyncpg.connect(_sync_url())
        org_id, user_id, workflow_id, execution_id = await _setup(conn)
        gateway = ScriptedGateway(verify_content="PAS")
        try:
            await _run(monkeypatch, gateway, execution_id)
            assert await _status(conn, execution_id) == "completed"
            assert gateway.verify_calls == 1
            assert "verify_unknown" in await _audits(conn, execution_id)
        finally:
            await _cleanup(
                conn,
                execution_id=execution_id,
                workflow_id=workflow_id,
                user_id=user_id,
                org_id=org_id,
            )
            await conn.close()

    asyncio.run(main())


def test_verify_error_end_to_end(monkeypatch):
    async def main() -> None:
        conn = await asyncpg.connect(_sync_url())
        org_id, user_id, workflow_id, execution_id = await _setup(conn)
        gateway = ScriptedGateway(verify_content=None, verify_raise=True)
        try:
            await _run(monkeypatch, gateway, execution_id)
            assert await _status(conn, execution_id) == "completed"
            assert gateway.verify_calls == 1
            assert "verify_error" in await _audits(conn, execution_id)
        finally:
            await _cleanup(
                conn,
                execution_id=execution_id,
                workflow_id=workflow_id,
                user_id=user_id,
                org_id=org_id,
            )
            await conn.close()

    asyncio.run(main())

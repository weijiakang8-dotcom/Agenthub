"""C-1 契约测试：副作用工具 claim 后 provider 调用最多一次，禁止自动 retry。

运行：
  DATABASE_URL=postgresql+asyncpg://postgres@localhost:5432/agenthub_benchmark_p0 \
  python -m pytest tests/integration/test_c1_side_effect_retry.py -q
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import asyncpg
import pytest

from app.config import settings
from app.engine import tool_executor
from app.engine.tool_registry import register_builtin_tools, register_tool


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
        "c1",
        "c1-" + uuid.uuid4().hex[:8],
    )
    await conn.execute(
        "INSERT INTO users (id,email,password_hash,full_name,organization_id,"
        "role,is_active,created_at,updated_at) "
        "VALUES ($1,$2,'x','c1',$3,'admin',true,now(),now())",
        user_id,
        f"c1-{uuid.uuid4().hex[:8]}@example.com",
        org_id,
    )
    await conn.execute(
        "INSERT INTO workflows (id,name,description,agent_chain,dag_definition,"
        "status,created_by,organization_id,created_at,updated_at) "
        "VALUES ($1,'c1','','[]'::json,'{}'::json,'active','c1',$2,now(),now())",
        workflow_id,
        org_id,
    )
    execution_id = uuid.uuid4()
    await conn.execute(
        "INSERT INTO executions (id,workflow_id,status,correlation_id,user_input,"
        "context_messages,intent,plan,organization_id,user_id,current_step_index,"
        "event_sequence,created_at,updated_at) "
        "VALUES ($1,$2,'pending',$3,'c1','[]'::json,'{}'::json,NULL,$4,$5,0,0,now(),now())",
        execution_id,
        workflow_id,
        uuid.uuid4(),
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


_SCHEMA = {
    "type": "object",
    "properties": {
        "to": {"type": "string"},
        "subject": {"type": "string"},
        "body": {"type": "string"},
    },
    "required": ["to", "subject", "body"],
}


def _install(
    tool_name: str,
    behavior: str,
    *,
    side_effect: bool,
) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    async def handler(params: dict[str, Any], organization_id: Any = None) -> dict:
        calls.append({"params": dict(params or {})})
        if behavior == "timeout":
            raise asyncio.TimeoutError("provider timeout")
        if behavior == "transient":
            raise ConnectionError("connection reset by peer")
        if behavior == "slow_success":
            await asyncio.sleep(0.2)
            return {"status": "success", "data": {}, "error": None}
        return {"status": "success", "data": {}, "error": None}

    register_tool(
        tool_name,
        "fake tool",
        _SCHEMA,
        handler,
        timeout=30.0,
        requires_approval=True,
        side_effect=side_effect,
    )
    return calls


def _params() -> dict:
    return {"to": "a@b.com", "subject": "s", "body": "b"}


def test_side_effect_timeout_invokes_provider_once():
    async def main() -> None:
        conn = await asyncpg.connect(_sync_url())
        org_id, user_id, workflow_id, execution_id = await _setup(conn)
        calls = _install("send_email", "timeout", side_effect=True)
        try:
            result = await tool_executor.execute_tool(
                "send_email", _params(), execution_id
            )
            assert result["status"] == "unknown"
            assert len(calls) == 1
            row = await conn.fetchrow(
                "SELECT status FROM tool_calls WHERE execution_id=$1", execution_id
            )
            assert row["status"] == "in_flight"
        finally:
            register_builtin_tools()
            await _cleanup(
                conn,
                execution_id=execution_id,
                workflow_id=workflow_id,
                user_id=user_id,
                org_id=org_id,
            )
            await conn.close()

    asyncio.run(main())


def test_side_effect_transient_invokes_provider_once():
    async def main() -> None:
        conn = await asyncpg.connect(_sync_url())
        org_id, user_id, workflow_id, execution_id = await _setup(conn)
        calls = _install("send_email", "transient", side_effect=True)
        try:
            result = await tool_executor.execute_tool(
                "send_email", _params(), execution_id
            )
            assert result["status"] == "unknown"
            assert len(calls) == 1
            row = await conn.fetchrow(
                "SELECT status FROM tool_calls WHERE execution_id=$1", execution_id
            )
            assert row["status"] == "in_flight"
        finally:
            register_builtin_tools()
            await _cleanup(
                conn,
                execution_id=execution_id,
                workflow_id=workflow_id,
                user_id=user_id,
                org_id=org_id,
            )
            await conn.close()

    asyncio.run(main())


def test_read_only_retry_preserved():
    async def main() -> None:
        conn = await asyncpg.connect(_sync_url())
        org_id, user_id, workflow_id, execution_id = await _setup(conn)
        calls = _install("query_db", "timeout", side_effect=False)
        try:
            result = await tool_executor.execute_tool(
                "query_db", _params(), execution_id
            )
            assert result["status"] == "failed"
            assert len(calls) == 3  # TOOL_RETRY_POLICY.max_attempts
            row = await conn.fetchrow(
                "SELECT status FROM tool_calls WHERE execution_id=$1", execution_id
            )
            assert row["status"] == "failed"
        finally:
            register_builtin_tools()
            await _cleanup(
                conn,
                execution_id=execution_id,
                workflow_id=workflow_id,
                user_id=user_id,
                org_id=org_id,
            )
            await conn.close()

    asyncio.run(main())


def test_timeout_then_reentry_no_second_invocation():
    async def main() -> None:
        conn = await asyncpg.connect(_sync_url())
        org_id, user_id, workflow_id, execution_id = await _setup(conn)
        calls = _install("send_email", "timeout", side_effect=True)
        try:
            first = await tool_executor.execute_tool(
                "send_email", _params(), execution_id
            )
            assert first["status"] == "unknown"
            assert len(calls) == 1
            second = await tool_executor.execute_tool(
                "send_email", _params(), execution_id
            )
            assert second["status"] == "unknown"
            assert len(calls) == 1
        finally:
            register_builtin_tools()
            await _cleanup(
                conn,
                execution_id=execution_id,
                workflow_id=workflow_id,
                user_id=user_id,
                org_id=org_id,
            )
            await conn.close()

    asyncio.run(main())


def test_provider_success_db_failure_no_second_invocation(monkeypatch):
    async def main() -> None:
        conn = await asyncpg.connect(_sync_url())
        org_id, user_id, workflow_id, execution_id = await _setup(conn)
        calls = _install("send_email", "success", side_effect=True)
        original_finish = tool_executor._finish_tool_call

        async def crashing_finish(tool_call_id, result):
            raise RuntimeError("db write failed after provider success")

        monkeypatch.setattr(tool_executor, "_finish_tool_call", crashing_finish)
        try:
            with pytest.raises(RuntimeError):
                await tool_executor.execute_tool("send_email", _params(), execution_id)
            monkeypatch.setattr(tool_executor, "_finish_tool_call", original_finish)
            second = await tool_executor.execute_tool(
                "send_email", _params(), execution_id
            )
            assert second["status"] == "unknown"
            assert len(calls) == 1
        finally:
            register_builtin_tools()
            await _cleanup(
                conn,
                execution_id=execution_id,
                workflow_id=workflow_id,
                user_id=user_id,
                org_id=org_id,
            )
            await conn.close()

    asyncio.run(main())


def test_concurrent_claim_single_winner():
    async def main() -> None:
        conn = await asyncpg.connect(_sync_url())
        org_id, user_id, workflow_id, execution_id = await _setup(conn)
        calls = _install("send_email", "slow_success", side_effect=True)
        try:
            results = await asyncio.gather(
                tool_executor.execute_tool("send_email", _params(), execution_id),
                tool_executor.execute_tool("send_email", _params(), execution_id),
            )
            statuses = sorted(result["status"] for result in results)
            assert statuses in (["duplicate", "success"], ["success", "unknown"])
            assert len(calls) == 1
            rows = await conn.fetch(
                "SELECT status FROM tool_calls WHERE execution_id=$1", execution_id
            )
            assert len(rows) == 1
            assert rows[0]["status"] == "success"
        finally:
            register_builtin_tools()
            await _cleanup(
                conn,
                execution_id=execution_id,
                workflow_id=workflow_id,
                user_id=user_id,
                org_id=org_id,
            )
            await conn.close()

    asyncio.run(main())

"""Phase 6A 故障注入与幂等集成验证（真实 PostgreSQL）。

运行：
  DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/agenthub \
  python -m pytest tests/integration/test_phase6a_idempotency.py -q
"""

from __future__ import annotations

import asyncio
import json
import uuid

import asyncpg
import pytest

from app.config import settings
from app.engine import graph as graph_module
from app.engine import tool_executor
from app.engine.canonical import params_canonical
from app.engine.tool_executor import make_idempotency_key


def _sync_url() -> str:
    return settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")


def _db_ready() -> bool:
    async def check() -> bool:
        try:
            conn = await asyncpg.connect(_sync_url())
            try:
                return (
                    await conn.fetchval(
                        "select count(*) from pg_enum "
                        "where enumlabel='in_flight' "
                        "and enumtypid='tool_call_status'::regtype"
                    )
                ) == 1
            finally:
                await conn.close()
        except Exception:  # noqa: BLE001
            return False

    return asyncio.run(check())


pytestmark = pytest.mark.skipif(
    not _db_ready(),
    reason="requires PostgreSQL with migration 0017 (tool_call_status.in_flight)",
)


async def _setup(
    conn: asyncpg.Connection,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    await conn.execute(
        "INSERT INTO organizations (id,name,slug,settings,created_at,updated_at) "
        "VALUES ($1,$2,$3,json_build_object(),now(),now())",
        org_id,
        "p6a",
        "p6a-" + uuid.uuid4().hex[:8],
    )
    await conn.execute(
        "INSERT INTO users (id,email,password_hash,full_name,organization_id,"
        "role,is_active,created_at,updated_at) "
        "VALUES ($1,$2,'x','p6a',$3,'admin',true,now(),now())",
        user_id,
        f"p6a-{uuid.uuid4().hex[:8]}@example.com",
        org_id,
    )
    workflow_id = uuid.uuid4()
    await conn.execute(
        "INSERT INTO workflows (id,name,description,agent_chain,dag_definition,"
        "status,created_by,organization_id,created_at,updated_at) "
        "VALUES ($1,'p6a','','[]'::json,'{}'::json,'active','p6a',$2,now(),now())",
        workflow_id,
        org_id,
    )
    execution_id = uuid.uuid4()
    await conn.execute(
        "INSERT INTO executions (id,workflow_id,status,correlation_id,user_input,"
        "context_messages,intent,plan,organization_id,user_id,current_step_index,"
        "event_sequence,created_at,updated_at) "
        "VALUES ($1,$2,'pending',$3,'p6a','[]'::json,'{}'::json,NULL,$4,$5,0,0,now(),now())",
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
    for table in ("audit_logs", "checkpoint_writes", "checkpoint_blobs", "checkpoints"):
        try:
            if table == "audit_logs":
                await conn.execute(
                    f"DELETE FROM {table} WHERE resource_id = $1", str(execution_id)
                )
            else:
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


def _email_params(recipient: str = "a@b.com") -> dict:
    return {"to": recipient, "subject": "s", "body": "b"}


def test_sequential_execute_is_idempotent(monkeypatch):
    async def main() -> None:
        conn = await asyncpg.connect(_sync_url())
        org_id, user_id, workflow_id, execution_id = await _setup(conn)
        calls = 0

        async def fake_invoke(tool_name, params, organization_id=None):
            nonlocal calls
            calls += 1
            return {"status": "success", "data": {"ok": True}, "error": None}

        monkeypatch.setattr(tool_executor, "_invoke_with_retry", fake_invoke)
        try:
            params = _email_params()
            first = await tool_executor.execute_tool("send_email", params, execution_id)
            second = await tool_executor.execute_tool(
                "send_email", params, execution_id
            )
            assert first["status"] == "success"
            assert second["status"] == "duplicate"
            assert calls == 1
            rows = await conn.fetch(
                "SELECT status FROM tool_calls WHERE execution_id=$1", execution_id
            )
            assert len(rows) == 1
            assert rows[0]["status"] == "success"
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


def test_concurrent_claim_invokes_provider_once(monkeypatch):
    async def main() -> None:
        conn = await asyncpg.connect(_sync_url())
        org_id, user_id, workflow_id, execution_id = await _setup(conn)
        calls = 0

        async def slow_invoke(tool_name, params, organization_id=None):
            nonlocal calls
            calls += 1
            await asyncio.sleep(0.3)
            return {"status": "success", "data": {"ok": True}, "error": None}

        monkeypatch.setattr(tool_executor, "_invoke_with_retry", slow_invoke)
        try:
            params = _email_params()
            results = await asyncio.gather(
                tool_executor.execute_tool("send_email", params, execution_id),
                tool_executor.execute_tool("send_email", params, execution_id),
            )
            statuses = sorted(result["status"] for result in results)
            assert set(statuses) in (
                {"success", "duplicate"},
                {"success", "unknown"},
            )
            assert calls == 1
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


def test_in_flight_is_fail_closed(monkeypatch):
    async def main() -> None:
        conn = await asyncpg.connect(_sync_url())
        org_id, user_id, workflow_id, execution_id = await _setup(conn)
        calls = 0

        async def fake_invoke(tool_name, params, organization_id=None):
            nonlocal calls
            calls += 1
            return {"status": "success", "data": {}, "error": None}

        monkeypatch.setattr(tool_executor, "_invoke_with_retry", fake_invoke)
        params = _email_params()
        key = make_idempotency_key(execution_id, "send_email", params)
        try:
            await conn.execute(
                "INSERT INTO tool_calls (id,execution_id,tool_name,input_params,"
                "status,requires_approval,idempotency_key,organization_id) "
                "VALUES ($1,$2,'send_email',$3::json,'in_flight',true,$4,$5)",
                uuid.uuid4(),
                execution_id,
                json.dumps(params),
                key,
                org_id,
            )
            result = await tool_executor.execute_tool(
                "send_email", params, execution_id
            )
            assert result["status"] == "unknown"
            assert calls == 0
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


def test_failed_is_never_retried(monkeypatch):
    async def main() -> None:
        conn = await asyncpg.connect(_sync_url())
        org_id, user_id, workflow_id, execution_id = await _setup(conn)
        calls = 0

        async def failing_invoke(tool_name, params, organization_id=None):
            nonlocal calls
            calls += 1
            return {"status": "failed", "data": None, "error": "provider boom"}

        monkeypatch.setattr(tool_executor, "_invoke_with_retry", failing_invoke)
        try:
            params = _email_params()
            first = await tool_executor.execute_tool("send_email", params, execution_id)
            second = await tool_executor.execute_tool(
                "send_email", params, execution_id
            )
            assert first["status"] == "failed"
            assert second["status"] == "failed"
            assert calls == 1
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


def test_legacy_pending_without_key_is_unknown(monkeypatch):
    async def main() -> None:
        conn = await asyncpg.connect(_sync_url())
        org_id, user_id, workflow_id, execution_id = await _setup(conn)
        calls = 0

        async def fake_invoke(tool_name, params, organization_id=None):
            nonlocal calls
            calls += 1
            return {"status": "success", "data": {}, "error": None}

        monkeypatch.setattr(tool_executor, "_invoke_with_retry", fake_invoke)
        params = _email_params()
        try:
            await conn.execute(
                "INSERT INTO tool_calls (id,execution_id,tool_name,input_params,"
                "status,requires_approval,idempotency_key,organization_id) "
                "VALUES ($1,$2,'send_email',$3::json,'pending',true,NULL,$4)",
                uuid.uuid4(),
                execution_id,
                json.dumps(params),
                org_id,
            )
            result = await tool_executor.execute_tool(
                "send_email", params, execution_id
            )
            assert result["status"] == "unknown"
            assert calls == 0
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


def test_crash_after_claim_never_reinvokes_provider(monkeypatch):
    async def main() -> None:
        conn = await asyncpg.connect(_sync_url())
        org_id, user_id, workflow_id, execution_id = await _setup(conn)
        calls = 0

        async def fake_invoke(tool_name, params, organization_id=None):
            nonlocal calls
            calls += 1
            return {"status": "success", "data": {"ok": True}, "error": None}

        real_finish = tool_executor._finish_tool_call

        async def crashing_finish(tool_call_id, result):
            raise RuntimeError("worker crashed before persisting result")

        monkeypatch.setattr(tool_executor, "_invoke_with_retry", fake_invoke)
        monkeypatch.setattr(tool_executor, "_finish_tool_call", crashing_finish)
        try:
            params = _email_params()
            with pytest.raises(RuntimeError):
                await tool_executor.execute_tool("send_email", params, execution_id)
            monkeypatch.setattr(tool_executor, "_finish_tool_call", real_finish)
            second = await tool_executor.execute_tool(
                "send_email", params, execution_id
            )
            assert second["status"] == "unknown"
            assert calls == 1
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


def test_tool_level_duplicate_is_recorded_as_success(monkeypatch):
    async def main() -> None:
        conn = await asyncpg.connect(_sync_url())
        org_id, user_id, workflow_id, execution_id = await _setup(conn)

        async def duplicate_invoke(tool_name, params, organization_id=None):
            return {
                "status": "duplicate",
                "data": {"to": params.get("to"), "subject": params.get("subject")},
                "error": None,
            }

        monkeypatch.setattr(tool_executor, "_invoke_with_retry", duplicate_invoke)
        try:
            params = _email_params()
            first = await tool_executor.execute_tool("send_email", params, execution_id)
            assert first["status"] == "duplicate"
            row = await conn.fetchrow(
                "SELECT status, output_result FROM tool_calls WHERE execution_id=$1",
                execution_id,
            )
            assert row["status"] == "success"
            assert json.loads(row["output_result"])["status"] == "duplicate"
            second = await tool_executor.execute_tool(
                "send_email", params, execution_id
            )
            assert second["status"] == "duplicate"
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


def test_frozen_proposal_mismatch_aborts_with_audit():
    async def main() -> None:
        conn = await asyncpg.connect(_sync_url())
        org_id, user_id, workflow_id, execution_id = await _setup(conn)
        tampered_params = {"to": "attacker@example.com", "subject": "s", "body": "b"}
        frozen_params = {"to": "approved@example.com", "subject": "s", "body": "b"}
        plan = {
            "goal": "发邮件",
            "risk": "SIDE_EFFECT",
            "steps": [
                {
                    "step_id": "commit",
                    "capability": "send_email",
                    "description": "send",
                    "input_refs": [],
                    "output_name": None,
                    "depends_on": [],
                    "condition": None,
                    "side_effect": True,
                    "requires_approval": True,
                }
            ],
            "side_effect_proposals": [
                {
                    "step_id": "commit",
                    "capability": "send_email",
                    "tool": "send_email",
                    "params": tampered_params,
                    "params_canonical": params_canonical(
                        frozen_params, tool_name="send_email"
                    ),
                }
            ],
        }
        state = {
            "messages": [],
            "current_step": 0,
            "execution_id": str(execution_id),
            "organization_id": str(org_id),
            "user_id": str(user_id),
            "user_input": "发邮件",
            "final_output": None,
            "plan": plan["steps"],
            "intent": {"category": "ACTION", "risk": "SIDE_EFFECT"},
            "steps": [],
            "pending_approval": None,
            "node_outputs": {},
            "revision_count": 0,
            "revision_requested": False,
            "complexity": "simple",
            "llm_usage": [],
            "plan_meta": {
                "plan": plan,
                "side_effect_set": ["commit"],
                "approved": True,
            },
            "budget_used": {},
            "budget_exceeded": False,
            "hard_stop": False,
            "approval_rejected": False,
            "side_effect_failure": False,
            "approved_plan_hash": "hash",
            "approved_approval_id": "approval-1",
        }
        try:
            terminal, ok = await graph_module._execute_frozen_side_effect(
                state, plan["steps"][0], str(execution_id)
            )
            assert ok is False
            assert terminal["side_effect_failure"] is True
            audit = await conn.fetchrow(
                "SELECT action FROM audit_logs WHERE resource_id=$1 "
                "AND action='approval_mismatch'",
                str(execution_id),
            )
            assert audit is not None
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

"""T24 Approval Bypass 契约回归：runtime attempt vs frozen proposal 显式比对。

覆盖 TEST-1..TEST-6：
1. approved A + runtime A → provider=1 + success
2. approved A + runtime B → provider=0 + approval_mismatch + abort
3. approved A + runtime 不同参数 → provider=0 + mismatch
4. 同语义参数、JSON 顺序不同 → canonical 判定不误报
5. mismatch 后重新审批 B → 新 proposal 批准后才能执行 B
6. mismatch 经重入/重复尝试不产生副作用
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import asyncpg
import pytest

from app.config import settings
from app.engine import graph as graph_module
from app.engine.approval import build_proposal
from app.engine.planner import compute_plan_hash
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
        "t24",
        "t24-" + uuid.uuid4().hex[:8],
    )
    await conn.execute(
        "INSERT INTO users (id,email,password_hash,full_name,organization_id,"
        "role,is_active,created_at,updated_at) "
        "VALUES ($1,$2,'x','t24',$3,'admin',true,now(),now())",
        user_id,
        f"t24-{uuid.uuid4().hex[:8]}@example.com",
        org_id,
    )
    await conn.execute(
        "INSERT INTO workflows (id,name,description,agent_chain,dag_definition,"
        "status,created_by,organization_id,created_at,updated_at) "
        "VALUES ($1,'t24','','[]'::json,'{}'::json,'active','t24',$2,now(),now())",
        workflow_id,
        org_id,
    )
    execution_id = uuid.uuid4()
    await conn.execute(
        "INSERT INTO executions (id,workflow_id,status,correlation_id,user_input,"
        "context_messages,intent,plan,organization_id,user_id,current_step_index,"
        "event_sequence,created_at,updated_at) "
        "VALUES ($1,$2,'pending',$3,'t24','[]'::json,'{}'::json,NULL,$4,$5,0,0,now(),now())",
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


PARAMS_A = {"to": "test@example.com", "subject": "x", "body": "y"}
PARAMS_B = {"to": "attacker@example.com", "subject": "x", "body": "y"}


def _plan(params: dict[str, Any]) -> dict:
    proposal = build_proposal(
        step_id="commit", capability="send_email", tool="send_email", params=params
    )
    return {
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
        "side_effect_proposals": [proposal.to_dict()],
    }


def _state(
    plan: dict,
    execution_id: uuid.UUID,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
) -> dict:
    return {
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
        "plan_meta": {"plan": plan, "approval_id": "t24-approval"},
        "budget_used": {},
        "budget_exceeded": False,
        "hard_stop": False,
        "approval_rejected": False,
        "side_effect_failure": False,
        "approved_plan_hash": compute_plan_hash(plan),
        "approved_approval_id": "t24-approval",
    }


def _attempt_step(tool: str, params: dict[str, Any]) -> dict:
    return {
        "step_id": "commit",
        "capability": "send_email",
        "side_effect": True,
        "tool": tool,
        "params": params,
    }


def _install_provider(calls: list[dict]) -> None:
    async def handler(params: dict[str, Any], organization_id: Any = None) -> dict:
        calls.append(dict(params or {}))
        return {"status": "success", "data": {"message_id": "t24"}, "error": None}

    register_tool(
        "send_email",
        "Send an email via SMTP. Requires human approval.",
        {
            "type": "object",
            "properties": {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["to", "subject", "body"],
        },
        handler,
        timeout=30.0,
        requires_approval=True,
        side_effect=True,
    )


async def _mismatch_count(conn: asyncpg.Connection, execution_id: uuid.UUID) -> int:
    return int(
        await conn.fetchval(
            "SELECT count(*) FROM audit_logs WHERE resource_id=$1 "
            "AND action='approval_mismatch'",
            str(execution_id),
        )
    )


async def _run_gate(
    state: dict, step: dict, execution_id: uuid.UUID
) -> tuple[dict, bool]:
    return await graph_module._execute_frozen_side_effect(
        state, step, str(execution_id)
    )


def test_approved_a_runtime_a_executes_once():
    async def main() -> None:
        conn = await asyncpg.connect(_sync_url())
        org_id, user_id, workflow_id, execution_id = await _setup(conn)
        calls: list[dict] = []
        _install_provider(calls)
        try:
            plan = _plan(PARAMS_A)
            terminal, ok = await _run_gate(
                _state(plan, execution_id, org_id, user_id),
                _attempt_step("send_email", PARAMS_A),
                execution_id,
            )
            assert ok is True
            assert terminal.get("status") == "success"
            assert len(calls) == 1
            assert calls[0] == PARAMS_A
            row = await conn.fetchrow(
                "SELECT status FROM tool_calls WHERE execution_id=$1", execution_id
            )
            assert row["status"] == "success"
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


def test_approved_a_runtime_b_aborts_zero_side_effect():
    async def main() -> None:
        conn = await asyncpg.connect(_sync_url())
        org_id, user_id, workflow_id, execution_id = await _setup(conn)
        calls: list[dict] = []
        _install_provider(calls)
        try:
            plan = _plan(PARAMS_A)
            terminal, ok = await _run_gate(
                _state(plan, execution_id, org_id, user_id),
                _attempt_step("send_email", PARAMS_B),
                execution_id,
            )
            assert ok is False
            assert terminal["side_effect_failure"] is True
            assert len(calls) == 0
            assert await _mismatch_count(conn, execution_id) == 1
            rows = await conn.fetch(
                "SELECT count(*) AS n FROM tool_calls WHERE execution_id=$1",
                execution_id,
            )
            assert rows[0]["n"] == 0
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


def test_runtime_different_params_aborts():
    async def main() -> None:
        conn = await asyncpg.connect(_sync_url())
        org_id, user_id, workflow_id, execution_id = await _setup(conn)
        calls: list[dict] = []
        _install_provider(calls)
        try:
            plan = _plan(PARAMS_A)
            drifted = {**PARAMS_A, "cc": "cc@example.com"}
            terminal, ok = await _run_gate(
                _state(plan, execution_id, org_id, user_id),
                _attempt_step("send_email", drifted),
                execution_id,
            )
            assert ok is False
            assert terminal["side_effect_failure"] is True
            assert len(calls) == 0
            assert await _mismatch_count(conn, execution_id) == 1
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


def test_same_semantic_params_different_order_no_false_mismatch():
    async def main() -> None:
        conn = await asyncpg.connect(_sync_url())
        org_id, user_id, workflow_id, execution_id = await _setup(conn)
        calls: list[dict] = []
        _install_provider(calls)
        try:
            plan = _plan(PARAMS_A)
            reordered = {"body": "y", "subject": "x", "to": "test@example.com"}
            _, ok = await _run_gate(
                _state(plan, execution_id, org_id, user_id),
                _attempt_step("send_email", reordered),
                execution_id,
            )
            assert ok is True
            assert len(calls) == 1
            assert await _mismatch_count(conn, execution_id) == 0
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


def test_mismatch_then_reapprove_b_executes_b():
    async def main() -> None:
        conn = await asyncpg.connect(_sync_url())
        org_id, user_id, workflow_id, execution_id = await _setup(conn)
        calls: list[dict] = []
        _install_provider(calls)
        try:
            plan_a = _plan(PARAMS_A)
            _, ok = await _run_gate(
                _state(plan_a, execution_id, org_id, user_id),
                _attempt_step("send_email", PARAMS_B),
                execution_id,
            )
            assert ok is False
            assert len(calls) == 0

            plan_b = _plan(PARAMS_B)
            _, ok = await _run_gate(
                _state(plan_b, execution_id, org_id, user_id),
                _attempt_step("send_email", PARAMS_B),
                execution_id,
            )
            assert ok is True
            assert len(calls) == 1
            assert calls[0] == PARAMS_B
            row = await conn.fetchrow(
                "SELECT input_params FROM tool_calls WHERE execution_id=$1",
                execution_id,
            )
            assert json.loads(row["input_params"]) == PARAMS_B
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


def test_mismatch_reentry_never_causes_side_effect():
    async def main() -> None:
        conn = await asyncpg.connect(_sync_url())
        org_id, user_id, workflow_id, execution_id = await _setup(conn)
        calls: list[dict] = []
        _install_provider(calls)
        try:
            plan = _plan(PARAMS_A)
            state = _state(plan, execution_id, org_id, user_id)
            step = _attempt_step("send_email", PARAMS_B)
            for _ in range(2):
                terminal, ok = await _run_gate(state, step, execution_id)
                assert ok is False
                assert terminal["side_effect_failure"] is True
            assert len(calls) == 0
            assert await _mismatch_count(conn, execution_id) == 2
            rows = await conn.fetch(
                "SELECT count(*) AS n FROM tool_calls WHERE execution_id=$1",
                execution_id,
            )
            assert rows[0]["n"] == 0
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

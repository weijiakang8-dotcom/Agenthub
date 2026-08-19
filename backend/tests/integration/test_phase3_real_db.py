"""Phase 3 真实链路验证（PostgreSQL + pgvector + 真实执行链）。

运行方式（本地 pgvector 实例）：
  DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5434/agenthub \
  AGENTHUB_OBSERVABILITY_DISABLED=false \
  python -m pytest tests/integration/test_phase3_real_db.py -q

数据库不可用/无 vector 扩展时自动跳过（与既有 integration 测试一致）。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import re
import time
import uuid
from types import SimpleNamespace

import asyncpg
import pytest
from app.config import settings
from app.engine import graph as graph_module
from app.engine import runner, tool_executor
from app.engine.planner import normalize_plan
from app.memory import service as memory_service
from app.models.enums import ExecutionStatus
from app.rag import retrieval, vector_store
from langchain_core.messages import AIMessage


def _sync_url() -> str:
    return settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")


def _vector_db_ready() -> bool:
    async def check() -> bool:
        try:
            conn = await asyncpg.connect(_sync_url())
            try:
                ext = await conn.fetchval(
                    "select extname from pg_extension where extname='vector'"
                )
                return ext == "vector"
            finally:
                await conn.close()
        except Exception:  # noqa: BLE001
            return False

    return asyncio.run(check())


_OBSERVABILITY_DISABLED = os.environ.get(
    "AGENTHUB_OBSERVABILITY_DISABLED", ""
).lower() in {"1", "true", "yes"}


pytestmark = pytest.mark.skipif(
    not _vector_db_ready() or _OBSERVABILITY_DISABLED,
    reason=(
        "requires pgvector-backed PostgreSQL and observability span persistence "
        "(run with AGENTHUB_OBSERVABILITY_DISABLED=false)"
    ),
)


def _hash_embed(text: str, dims: int = 768) -> list[float]:
    vec = [0.0] * dims
    tokens = re.findall(r"[a-zA-Z0-9\u4e00-\u9fff]+", text.lower())
    for i in range(len(tokens)):
        for n in (1, 2, 3):
            gram = " ".join(tokens[i : i + n])
            idx = (
                int.from_bytes(hashlib.md5(gram.encode()).digest()[:4], "little") % dims
            )
            vec[idx] += 1.0
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


async def _setup_org_user(
    conn: asyncpg.Connection, suffix: str
) -> tuple[uuid.UUID, uuid.UUID]:
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    await conn.execute(
        "INSERT INTO organizations (id, name, slug, settings, created_at, updated_at) "
        "VALUES ($1, $2, $3, '{}'::json, now(), now())",
        org_id,
        f"phase3-{suffix}",
        f"phase3-{suffix}",
    )
    await conn.execute(
        "INSERT INTO users (id, email, password_hash, full_name, organization_id, "
        "role, is_active, created_at, updated_at) "
        "VALUES ($1, $2, 'x', $3, $4, 'member', true, now(), now())",
        user_id,
        f"phase3-{suffix}@example.com",
        f"phase3 user {suffix}",
        org_id,
    )
    return org_id, user_id


async def _insert_workflow(
    conn: asyncpg.Connection, org_id: uuid.UUID, dag: list[dict]
) -> uuid.UUID:
    workflow_id = uuid.uuid4()
    await conn.execute(
        "INSERT INTO workflows (id, name, description, agent_chain, dag_definition, "
        "status, created_by, organization_id, created_at, updated_at) "
        "VALUES ($1, $2, '', '[]'::json, $3::json, 'active', $4, $5, now(), now())",
        workflow_id,
        "phase3-workflow",
        json.dumps({"nodes": dag}),
        "phase3-test",
        org_id,
    )
    return workflow_id


async def _insert_execution(
    conn: asyncpg.Connection,
    workflow_id: uuid.UUID,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    user_input: str,
    *,
    intent: dict | None = None,
) -> tuple[uuid.UUID, uuid.UUID]:
    execution_id = uuid.uuid4()
    correlation_id = uuid.uuid4()
    await conn.execute(
        "INSERT INTO executions (id, workflow_id, status, correlation_id, "
        "user_input, context_messages, intent, plan, organization_id, user_id, "
        "current_step_index, event_sequence, created_at, updated_at) "
        "VALUES ($1, $2, 'pending', $3, $4, '[]'::json, $5::json, NULL, "
        "$6, $7, 0, 0, now(), now())",
        execution_id,
        workflow_id,
        correlation_id,
        user_input,
        json.dumps(intent or {}),
        org_id,
        user_id,
    )
    return execution_id, correlation_id


async def _cleanup(
    conn: asyncpg.Connection,
    *,
    execution_ids: list[uuid.UUID] | None = None,
    workflow_ids: list[uuid.UUID] | None = None,
    document_ids: list[uuid.UUID] | None = None,
    user_ids: list[uuid.UUID] | None = None,
    org_ids: list[uuid.UUID] | None = None,
    trace_ids: list[str] | None = None,
) -> None:
    async def try_delete(sql: str, *args: object) -> None:
        try:
            await conn.execute(sql, *args)
        except asyncpg.UndefinedTableError:
            return

    if execution_ids:
        for execution_id in execution_ids:
            await try_delete(
                "DELETE FROM audit_logs WHERE resource_id = $1", str(execution_id)
            )
            await try_delete(
                "DELETE FROM tool_calls WHERE execution_id = $1", execution_id
            )
            await try_delete(
                "DELETE FROM checkpoint_blobs WHERE thread_id = $1", str(execution_id)
            )
            await try_delete(
                "DELETE FROM checkpoint_writes WHERE thread_id = $1",
                str(execution_id),
            )
            await try_delete(
                "DELETE FROM checkpoints WHERE thread_id = $1", str(execution_id)
            )
            await try_delete("DELETE FROM executions WHERE id = $1", execution_id)
    if trace_ids:
        for trace_id in trace_ids:
            await try_delete(
                "DELETE FROM audit_logs WHERE action LIKE 'span:%' AND resource_id = $1",
                trace_id,
            )
    if document_ids:
        for document_id in document_ids:
            await try_delete(
                "DELETE FROM document_chunks WHERE document_id = $1", document_id
            )
            await try_delete("DELETE FROM documents WHERE id = $1", document_id)
    if user_ids:
        await try_delete(
            "DELETE FROM user_memories WHERE user_id = ANY($1::uuid[])", user_ids
        )
        await try_delete("DELETE FROM users WHERE id = ANY($1::uuid[])", user_ids)
    if workflow_ids:
        await try_delete(
            "DELETE FROM workflows WHERE id = ANY($1::uuid[])", workflow_ids
        )
    if org_ids:
        await try_delete(
            "DELETE FROM organizations WHERE id = ANY($1::uuid[])", org_ids
        )


class FakeGateway:
    """真实 ModelGateway 类的替身：invoke/stream 由测试脚本驱动。"""

    def __init__(self, script: list):
        self.script = script
        self.calls = 0

    async def select(self, **kwargs):
        return [object()]

    async def invoke(self, llms, messages, **kwargs):
        step = self.script[min(self.calls, len(self.script) - 1)]
        self.calls += 1
        if isinstance(step, dict) and "tool_calls" in step:
            return AIMessage(content="", tool_calls=step["tool_calls"])
        return AIMessage(content=step if isinstance(step, str) else "ok")

    async def stream(self, llms, messages, **kwargs):
        for chunk in ("第一段", "第二段"):
            yield chunk


def _patch_gateway(monkeypatch, script: list) -> FakeGateway:
    fake = FakeGateway(script)
    monkeypatch.setattr(graph_module._gateway, "invoke", fake.invoke)
    monkeypatch.setattr(graph_module._gateway, "stream", fake.stream)
    return fake


def _patch_embedders(monkeypatch) -> None:
    async def fake_embed(text: str) -> list[float]:
        return _hash_embed(text)

    monkeypatch.setattr(vector_store, "embed_text", fake_embed)
    monkeypatch.setattr(retrieval, "embed_text", fake_embed)
    monkeypatch.setattr(memory_service, "embed_text", fake_embed)


def test_real_rag_pgvector_retrieval_and_tenant_isolation(monkeypatch):
    async def main() -> None:
        conn = await asyncpg.connect(_sync_url())
        org_a, user_a = await _setup_org_user(conn, str(uuid.uuid4())[:8])
        org_b, user_b = await _setup_org_user(conn, str(uuid.uuid4())[:8])
        document_id = uuid.uuid4()
        trace_id = str(uuid.uuid4())
        try:
            await conn.execute(
                "INSERT INTO documents (id, organization_id, user_id, name, content, "
                "metadata, embedding, created_at, updated_at) "
                "VALUES ($1, $2, $3, 'prod-smoke.md', $4, '{}'::json, NULL, "
                "now(), now())",
                document_id,
                org_a,
                user_a,
                "AgentHub production smoke unique phrase is the production "
                "verification sentence.",
            )
            _patch_embedders(monkeypatch)
            document = SimpleNamespace(
                id=document_id,
                organization_id=org_a,
                content="AgentHub production smoke unique phrase is the production "
                "verification sentence.",
                name="prod-smoke.md",
            )
            chunks = await vector_store.rebuild_document_chunks(document)
            assert chunks >= 1

            hits_a = await retrieval.retrieve_chunks(
                "AgentHub production smoke unique phrase",
                org_a,
                top_k=3,
                correlation_id=trace_id,
            )
            assert hits_a
            assert hits_a[0]["name"] == "prod-smoke.md"

            hits_b = await retrieval.retrieve_chunks(
                "AgentHub production smoke unique phrase",
                org_b,
                top_k=3,
            )
            assert hits_b == []

            span = await conn.fetchrow(
                "SELECT details FROM audit_logs "
                "WHERE action = 'span:rag' AND resource_id = $1",
                trace_id,
            )
            assert span is not None
            assert json.loads(span["details"])["span"] == "rag"
        finally:
            await _cleanup(
                conn,
                document_ids=[document_id],
                user_ids=[user_a, user_b],
                org_ids=[org_a, org_b],
                trace_ids=[trace_id],
            )
            await conn.close()

    asyncio.run(main())


def test_real_memory_crud_update_delete_and_isolation(monkeypatch):
    async def main() -> None:
        conn = await asyncpg.connect(_sync_url())
        org_a, user_a = await _setup_org_user(conn, str(uuid.uuid4())[:8])
        org_b, user_b = await _setup_org_user(conn, str(uuid.uuid4())[:8])
        try:
            _patch_embedders(monkeypatch)
            first = await memory_service.add_memory(
                user_id=user_a,
                organization_id=org_a,
                content="记住我叫魏家康",
            )
            merged = await memory_service.add_memory(
                user_id=user_a,
                organization_id=org_a,
                content="记住我叫魏家康！",
                importance=0.8,
            )
            assert merged.id == first.id  # 相似合并，不追加重复

            recalled = await memory_service.retrieve_memories(
                user_id=user_a,
                organization_id=org_a,
                query="魏家康",
                top_k=3,
            )
            assert len(recalled) == 1
            assert "记住我叫魏家康！" == recalled[0]["content"]

            updated = await memory_service.update_memory(
                memory_id=merged.id,
                user_id=user_a,
                content="我叫魏家豪",
                importance=0.9,
                organization_id=org_a,
            )
            assert updated is not None and updated.content == "我叫魏家豪"

            other_tenant = await memory_service.retrieve_memories(
                user_id=user_b,
                organization_id=org_b,
                query="魏家豪",
                top_k=3,
            )
            assert other_tenant == []

            assert await memory_service.delete_memory(merged.id, user_b) is False
            assert await memory_service.delete_memory(merged.id, user_a) is True
        finally:
            await _cleanup(
                conn,
                user_ids=[user_a, user_b],
                org_ids=[org_a, org_b],
            )
            await conn.close()

    asyncio.run(main())


def test_real_task_execution_runs_through_gates(monkeypatch):
    async def main() -> None:
        conn = await asyncpg.connect(_sync_url())
        org_id, user_id = await _setup_org_user(conn, str(uuid.uuid4())[:8])
        workflow_id = await _insert_workflow(
            conn,
            org_id,
            [
                {"type": "query_db", "label": "query"},
                {"type": "analysis", "label": "analyze"},
            ],
        )
        execution_id, _correlation = await _insert_execution(
            conn,
            workflow_id,
            org_id,
            user_id,
            "查一下有多少条执行记录",
            intent={"category": "TASK", "risk": "MEDIUM"},
        )
        try:
            _patch_gateway(
                monkeypatch,
                [
                    {
                        "tool_calls": [
                            {
                                "name": "query_db",
                                "args": {"sql": "SELECT id FROM workflows LIMIT 1"},
                                "id": "call_query",
                                "type": "tool_call",
                            }
                        ]
                    }
                ],
            )
            await runner.run_execution(execution_id)

            row = await conn.fetchrow(
                "SELECT status, final_output, plan, error_message FROM executions "
                "WHERE id = $1",
                execution_id,
            )
            assert row["status"] == ExecutionStatus.COMPLETED.value
            assert row["final_output"]
            assert row["error_message"] is None
            stored_plan = json.loads(row["plan"])
            assert stored_plan and isinstance(stored_plan, dict)
            assert len(stored_plan["steps"]) == 2
            assert stored_plan["steps"][0]["side_effect"] is False

            tool_rows = await conn.fetch(
                "SELECT tool_name, status FROM tool_calls WHERE execution_id = $1",
                execution_id,
            )
            assert len(tool_rows) == 1
            assert tool_rows[0]["tool_name"] == "query_db"
            assert tool_rows[0]["status"] == "success"

            spans = await conn.fetch(
                "SELECT action FROM audit_logs "
                "WHERE action LIKE 'span:%' AND resource_id = $1",
                str(execution_id),
            )
            span_actions = {row["action"] for row in spans}
            # workflow 派生计划不走 Planner；FakeGateway 替换了 ModelGateway，
            # 因此本链路真实产生 step/tool span；llm span 由专用测试证明。
            assert {"span:step", "span:tool"} <= span_actions
        finally:
            await _cleanup(
                conn,
                execution_ids=[execution_id],
                workflow_ids=[workflow_id],
                user_ids=[user_id],
                org_ids=[org_id],
            )
            await conn.close()

    asyncio.run(main())


def test_real_plan_invalid_fails_with_audit(monkeypatch):
    async def main() -> None:
        conn = await asyncpg.connect(_sync_url())
        org_id, user_id = await _setup_org_user(conn, str(uuid.uuid4())[:8])
        workflow_id = await _insert_workflow(
            conn,
            org_id,
            [{"type": "analysis", "label": "analyze"}],
        )
        execution_id, _correlation = await _insert_execution(
            conn,
            workflow_id,
            org_id,
            user_id,
            "发邮件",
            intent={"category": "ACTION", "risk": "SIDE_EFFECT"},
        )
        try:
            _patch_gateway(monkeypatch, ["ok"])
            await runner.run_execution(execution_id)

            row = await conn.fetchrow(
                "SELECT status, error_message FROM executions WHERE id = $1",
                execution_id,
            )
            assert row["status"] == ExecutionStatus.FAILED.value
            assert "plan_invalid" in (row["error_message"] or "")

            audit = await conn.fetchrow(
                "SELECT details FROM audit_logs "
                "WHERE action = 'plan_invalid' AND resource_id = $1",
                str(execution_id),
            )
            assert audit is not None
        finally:
            await _cleanup(
                conn,
                execution_ids=[execution_id],
                workflow_ids=[workflow_id],
                user_ids=[user_id],
                org_ids=[org_id],
            )
            await conn.close()

    asyncio.run(main())


def test_real_approval_freeze_resume_no_duplicate_side_effect(monkeypatch):
    async def main() -> None:
        conn = await asyncpg.connect(_sync_url())
        org_id, user_id = await _setup_org_user(conn, str(uuid.uuid4())[:8])
        workflow_id = await _insert_workflow(
            conn,
            org_id,
            [{"type": "send_email", "label": "send"}],
        )
        execution_id, _correlation = await _insert_execution(
            conn,
            workflow_id,
            org_id,
            user_id,
            "发邮件给 test@example.com",
            intent={"category": "ACTION", "risk": "SIDE_EFFECT"},
        )

        real_invoke = tool_executor._invoke_with_retry

        async def fake_invoke(tool_name, params, organization_id=None):
            if tool_name == "send_email":
                return {
                    "status": "success",
                    "data": {"message_id": "phase3"},
                    "error": None,
                }
            return await real_invoke(tool_name, params, organization_id)

        try:
            monkeypatch.setattr(tool_executor, "_invoke_with_retry", fake_invoke)
            _patch_gateway(
                monkeypatch,
                [
                    {
                        "tool_calls": [
                            {
                                "name": "send_email",
                                "args": {
                                    "to": "test@example.com",
                                    "subject": "x",
                                    "body": "y",
                                },
                                "id": "call_email",
                                "type": "tool_call",
                            }
                        ]
                    },
                    "PASS",
                ],
            )

            await runner.run_execution(execution_id)
            row = await conn.fetchrow(
                "SELECT status, checkpoint_data FROM executions WHERE id = $1",
                execution_id,
            )
            assert row["status"] == ExecutionStatus.WAITING_FOR_APPROVAL.value
            tool_before = await conn.fetchval(
                "SELECT count(*) FROM tool_calls WHERE execution_id = $1",
                execution_id,
            )
            assert tool_before == 0  # 审批前不执行任何副作用

            await runner.resume_execution(execution_id, {"approved": True})
            row = await conn.fetchrow(
                "SELECT status, final_output, error_message FROM executions "
                "WHERE id = $1",
                execution_id,
            )
            assert row["status"] == ExecutionStatus.COMPLETED.value
            assert row["error_message"] is None

            email_calls = await conn.fetch(
                "SELECT status, output_result FROM tool_calls "
                "WHERE execution_id = $1 AND tool_name = 'send_email'",
                execution_id,
            )
            assert len(email_calls) == 1
            assert email_calls[0]["status"] == "success"

            # 幂等：同一步骤再次执行不得重复副作用
            duplicate = await tool_executor.execute_tool(
                "send_email",
                {"to": "test@example.com", "subject": "x", "body": "y"},
                execution_id,
            )
            assert duplicate["status"] == "duplicate"
            email_after = await conn.fetchval(
                "SELECT count(*) FROM tool_calls "
                "WHERE execution_id = $1 AND tool_name = 'send_email' "
                "AND status = 'success'",
                execution_id,
            )
            assert email_after == 1
        finally:
            await _cleanup(
                conn,
                execution_ids=[execution_id],
                workflow_ids=[workflow_id],
                user_ids=[user_id],
                org_ids=[org_id],
            )
            await conn.close()

    asyncio.run(main())


def test_real_budget_enforcement_in_graph(monkeypatch):
    async def main() -> None:
        conn = await asyncpg.connect(_sync_url())
        org_id, user_id = await _setup_org_user(conn, str(uuid.uuid4())[:8])
        workflow_id = await _insert_workflow(
            conn,
            org_id,
            [
                {"type": "query_db", "label": "q"},
                {"type": "analysis", "label": "a"},
            ],
        )
        execution_id, _correlation = await _insert_execution(
            conn,
            workflow_id,
            org_id,
            user_id,
            "测试预算",
            intent={"category": "TASK", "risk": "MEDIUM"},
        )
        try:
            plan = normalize_plan(
                {
                    "goal": "测试任务",
                    "risk": "MEDIUM",
                    "steps": [
                        {"capability": "query_db", "description": "q"},
                        {"capability": "analysis", "description": "a"},
                    ],
                }
            )
            _patch_gateway(
                monkeypatch,
                [
                    {
                        "tool_calls": [
                            {
                                "name": "query_db",
                                "args": {"sql": "SELECT id FROM workflows LIMIT 1"},
                                "id": "call_query",
                                "type": "tool_call",
                            }
                        ]
                    }
                ],
            )
            initial_state = {
                "messages": [],
                "current_step": 0,
                "execution_id": str(execution_id),
                "organization_id": None,
                "user_id": None,
                "user_input": "测试",
                "final_output": None,
                "plan": plan["steps"],
                "intent": {"category": "TASK", "risk": "MEDIUM"},
                "steps": [],
                "pending_approval": None,
                "node_outputs": {},
                "revision_count": 0,
                "revision_requested": False,
                "complexity": "simple",
                "llm_usage": [],
                "plan_meta": {
                    "plan": plan,
                    "plan_hash": "test-hash",
                    "side_effect_set": [],
                    "risk": "MEDIUM",
                    "approved": False,
                },
                "budget_used": {
                    "max_steps": 1,
                    "max_replans": 1,
                    "max_verifies": 1,
                    "wall_clock_seconds": 300.0,
                    "max_tokens": 100_000,
                    "max_cost": 10.0,
                    "steps": 0,
                    "replans": 0,
                    "verifies": 0,
                    "tokens": 0,
                    "cost": 0.0,
                    "started_at": time.time(),
                },
                "budget_exceeded": False,
                "hard_stop": False,
                "approval_rejected": False,
                "approved_plan_hash": None,
            }
            graph = graph_module.build_graph()
            result = await graph.ainvoke(initial_state)
            assert result["budget_exceeded"] is True
            assert result["hard_stop"] is False  # 只读计划 → 优雅终止

            audit = await conn.fetchrow(
                "SELECT details FROM audit_logs "
                "WHERE action = 'budget_exceeded' AND resource_id = $1",
                str(execution_id),
            )
            assert audit is not None
            assert json.loads(audit["details"])["hard"] is False
        finally:
            await _cleanup(
                conn,
                execution_ids=[execution_id],
                workflow_ids=[workflow_id],
                user_ids=[user_id],
                org_ids=[org_id],
            )
            await conn.close()

    asyncio.run(main())


def test_real_model_gateway_records_llm_span():
    async def main() -> None:
        conn = await asyncpg.connect(_sync_url())
        trace_id = str(uuid.uuid4())
        try:
            from app.core.model_gateway import ModelGateway
            from langchain_core.messages import HumanMessage

            class StubLLM:
                model_name = "stub-model"

                async def ainvoke(self, _messages):
                    return AIMessage(
                        content="ok",
                        usage_metadata={
                            "input_tokens": 5,
                            "output_tokens": 7,
                            "total_tokens": 12,
                        },
                    )

            gateway = ModelGateway()
            response = await gateway.invoke(
                [StubLLM()],
                [HumanMessage(content="hi")],
                task_type="test",
                correlation_id=trace_id,
            )
            assert str(getattr(response, "content", "")) == "ok"

            row = await conn.fetchrow(
                "SELECT details FROM audit_logs "
                "WHERE action = 'span:llm' AND resource_id = $1",
                trace_id,
            )
            assert row is not None
            details = json.loads(row["details"])
            assert details["model"] == "stub-model"
            assert details["tokens"] == 12
            assert details["status"] == "ok"
        finally:
            await _cleanup(conn, trace_ids=[trace_id])
            await conn.close()

    asyncio.run(main())


def test_real_planner_records_plan_span():
    async def main() -> None:
        conn = await asyncpg.connect(_sync_url())
        trace_id = str(uuid.uuid4())
        try:
            from app.engine.planner import Planner, is_plan_invalid

            class PlanGateway:
                async def select(self, **kwargs):
                    return [object()]

                async def invoke(self, llms, messages, **kwargs):
                    return AIMessage(
                        content=json.dumps(
                            {
                                "goal": "hello",
                                "risk": "LOW",
                                "steps": [
                                    {
                                        "step_id": "s1",
                                        "capability": "answer",
                                        "description": "greet",
                                    }
                                ],
                            }
                        )
                    )

            plan = await Planner(gateway=PlanGateway()).plan(
                "hello",
                organization_id=None,
                user_id=None,
                correlation_id=trace_id,
            )
            assert not is_plan_invalid(plan)

            row = await conn.fetchrow(
                "SELECT details FROM audit_logs "
                "WHERE action = 'span:plan' AND resource_id = $1",
                trace_id,
            )
            assert row is not None
            assert json.loads(row["details"])["span"] == "plan"
        finally:
            await _cleanup(conn, trace_ids=[trace_id])
            await conn.close()

    asyncio.run(main())

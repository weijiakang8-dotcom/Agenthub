"""Phase 6B 集成：reconciliation / DLQ / checkpoint cleanup / alert / cost。"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone

import asyncpg
import pytest
from langchain_core.messages import AIMessage

from app.config import settings
from app.core import dlq, production_alerts
from app.engine import graph as graph_module
from app.engine import planner, reconciliation, runner
from app.engine.executor import PlanInvalidError
from app.engine.tool_executor import make_idempotency_key


def _sync_url() -> str:
    return settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")


def _db_ready() -> bool:
    async def check() -> bool:
        try:
            conn = await asyncpg.connect(_sync_url())
            try:
                return (
                    int(await conn.fetchval("select version_num from alembic_version"))
                    >= 18
                )
            finally:
                await conn.close()
        except Exception:  # noqa: BLE001
            return False

    return asyncio.run(check())


pytestmark = pytest.mark.skipif(
    not _db_ready(),
    reason="requires PostgreSQL at migration 0018",
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
        "p6b",
        "p6b-" + uuid.uuid4().hex[:8],
    )
    await conn.execute(
        "INSERT INTO users (id,email,password_hash,full_name,organization_id,"
        "role,is_active,created_at,updated_at) "
        "VALUES ($1,$2,'x','p6b',$3,'admin',true,now(),now())",
        user_id,
        f"p6b-{uuid.uuid4().hex[:8]}@example.com",
        org_id,
    )
    workflow_id = uuid.uuid4()
    await conn.execute(
        "INSERT INTO workflows (id,name,description,agent_chain,dag_definition,"
        "status,created_by,organization_id,created_at,updated_at) "
        "VALUES ($1,'p6b','','[]'::json,'{}'::json,'active','p6b',$2,now(),now())",
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
    intent: dict | None = None,
) -> uuid.UUID:
    execution_id = uuid.uuid4()
    updated = updated_at or datetime.now(timezone.utc)
    await conn.execute(
        "INSERT INTO executions (id,workflow_id,status,correlation_id,user_input,"
        "context_messages,intent,plan,organization_id,user_id,current_step_index,"
        "event_sequence,created_at,updated_at,completed_at) "
        "VALUES ($1,$2,$3,$4,'p6b','[]'::json,$5::json,NULL,$6,$7,0,0,now(),$8,$9)",
        execution_id,
        workflow_id,
        status,
        uuid.uuid4(),
        json.dumps(intent) if intent is not None else None,
        org_id,
        user_id,
        updated,
        completed_at,
    )
    return execution_id


async def _cleanup(
    conn: asyncpg.Connection,
    *,
    executions: list[uuid.UUID],
    workflow_id: uuid.UUID,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
) -> None:
    for execution_id in executions:
        for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
            try:
                await conn.execute(
                    f"DELETE FROM {table} WHERE thread_id = $1", str(execution_id)
                )
            except asyncpg.UndefinedTableError:
                pass
        for table in ("audit_logs",):
            await conn.execute(
                f"DELETE FROM {table} WHERE resource_id = $1", str(execution_id)
            )
        await conn.execute("DELETE FROM tool_calls WHERE execution_id=$1", execution_id)
        await conn.execute("DELETE FROM executions WHERE id=$1", execution_id)
    await conn.execute("DELETE FROM workflows WHERE id=$1", workflow_id)
    await conn.execute("DELETE FROM users WHERE id=$1", user_id)
    await conn.execute("DELETE FROM organizations WHERE id=$1", org_id)


def test_reconcile_stale_pending_execution_once():
    async def main() -> None:
        conn = await asyncpg.connect(_sync_url())
        org_id, user_id, workflow_id = await _setup(conn)
        old = datetime.now(timezone.utc) - timedelta(hours=3)
        stale = await _insert_execution(
            conn, workflow_id, org_id, user_id, status="pending", updated_at=old
        )
        fresh = await _insert_execution(
            conn, workflow_id, org_id, user_id, status="pending"
        )
        try:
            first = await reconciliation.reconcile_stale_pending_executions()
            second = await reconciliation.reconcile_stale_pending_executions()
            assert first["reconciled"] >= 1
            assert second["reconciled"] == 0
            stale_status = await conn.fetchval(
                "SELECT status FROM executions WHERE id=$1", stale
            )
            fresh_status = await conn.fetchval(
                "SELECT status FROM executions WHERE id=$1", fresh
            )
            assert stale_status == "failed"
            assert fresh_status == "pending"
            audits = await conn.fetchval(
                "SELECT count(*) FROM audit_logs WHERE resource_id=$1 "
                "AND action='execution_reconciled'",
                str(stale),
            )
            assert audits >= 1
        finally:
            await _cleanup(
                conn,
                executions=[stale, fresh],
                workflow_id=workflow_id,
                user_id=user_id,
                org_id=org_id,
            )
            await conn.close()

    asyncio.run(main())


def test_reconcile_tool_calls_orphan_unknown_legacy():
    async def main() -> None:
        conn = await asyncpg.connect(_sync_url())
        org_id, user_id, workflow_id = await _setup(conn)
        old = datetime.now(timezone.utc) - timedelta(hours=3)
        terminal = await _insert_execution(
            conn,
            workflow_id,
            org_id,
            user_id,
            status="completed",
            completed_at=old,
        )
        running = await _insert_execution(
            conn, workflow_id, org_id, user_id, status="running", updated_at=old
        )
        params = {"to": "a@b.com", "subject": "s", "body": "b"}
        key = make_idempotency_key(terminal, "send_email", params)
        key2 = make_idempotency_key(
            running, "send_email", {"to": "b@b.com", "subject": "s", "body": "b"}
        )
        try:
            await conn.execute(
                "INSERT INTO tool_calls (id,execution_id,tool_name,input_params,"
                "status,requires_approval,idempotency_key,organization_id,"
                "created_at,updated_at) VALUES ($1,$2,'send_email',$3::json,"
                "'pending',true,$4,$5,now(),$6)",
                uuid.uuid4(),
                terminal,
                json.dumps(params),
                key,
                org_id,
                old,
            )
            in_flight_id = uuid.uuid4()
            await conn.execute(
                "INSERT INTO tool_calls (id,execution_id,tool_name,input_params,"
                "status,requires_approval,idempotency_key,organization_id,"
                "created_at,updated_at) VALUES ($1,$2,'send_email',$3::json,"
                "'in_flight',true,$4,$5,now(),$6)",
                in_flight_id,
                running,
                json.dumps(params),
                key2,
                org_id,
                old,
            )
            legacy_id = uuid.uuid4()
            await conn.execute(
                "INSERT INTO tool_calls (id,execution_id,tool_name,input_params,"
                "status,requires_approval,idempotency_key,organization_id,"
                "created_at,updated_at) VALUES ($1,$2,'send_email',$3::json,"
                "'pending',true,NULL,$4,now(),$5)",
                legacy_id,
                running,
                json.dumps(params),
                org_id,
                old,
            )
            result = await reconciliation.reconcile_tool_calls()
            assert result["orphan_failed"] >= 1
            assert result["unknown_flagged"] >= 1
            assert result["manual_flagged"] >= 1
            orphan_status = await conn.fetchval(
                "SELECT status FROM tool_calls WHERE execution_id=$1 AND "
                "idempotency_key=$2",
                terminal,
                key,
            )
            in_flight_status = await conn.fetchval(
                "SELECT status FROM tool_calls WHERE id=$1", in_flight_id
            )
            legacy_status = await conn.fetchval(
                "SELECT status FROM tool_calls WHERE id=$1", legacy_id
            )
            assert orphan_status == "failed"
            assert in_flight_status == "in_flight"
            assert legacy_status == "pending"
        finally:
            await _cleanup(
                conn,
                executions=[terminal, running],
                workflow_id=workflow_id,
                user_id=user_id,
                org_id=org_id,
            )
            await conn.close()

    asyncio.run(main())


def test_cleanup_old_checkpoints_keeps_active_and_recent(monkeypatch):
    async def main() -> None:
        conn = await asyncpg.connect(_sync_url())
        org_id, user_id, workflow_id = await _setup(conn)
        old = datetime.now(timezone.utc) - timedelta(days=30)
        old_terminal = await _insert_execution(
            conn,
            workflow_id,
            org_id,
            user_id,
            status="completed",
            completed_at=old,
        )
        recent = datetime.now(timezone.utc) - timedelta(hours=1)
        recent_terminal = await _insert_execution(
            conn,
            workflow_id,
            org_id,
            user_id,
            status="completed",
            completed_at=recent,
        )
        active = await _insert_execution(
            conn, workflow_id, org_id, user_id, status="running"
        )
        try:
            from app.engine.checkpoint import get_checkpoint_manager

            async with get_checkpoint_manager() as manager:
                for thread_id in (old_terminal, recent_terminal, active):
                    await manager.save_checkpoint(
                        str(thread_id), {"marker": str(thread_id)}
                    )
            result = await reconciliation.cleanup_old_checkpoints()
            assert result["removed"]["checkpoints"] >= 1
            second = await reconciliation.cleanup_old_checkpoints()
            assert second["removed"]["checkpoints"] == 0
            remaining = await conn.fetch(
                "SELECT DISTINCT thread_id FROM checkpoints "
                "WHERE thread_id = ANY($1::text[])",
                [str(recent_terminal), str(active)],
            )
            assert len(remaining) == 2
        finally:
            await _cleanup(
                conn,
                executions=[old_terminal, recent_terminal, active],
                workflow_id=workflow_id,
                user_id=user_id,
                org_id=org_id,
            )
            await conn.close()

    asyncio.run(main())


def test_dlq_stats_replay_discard(monkeypatch):
    async def main() -> None:
        conn = await asyncpg.connect(_sync_url())
        org_id, user_id, workflow_id = await _setup(conn)
        terminal = await _insert_execution(
            conn, workflow_id, org_id, user_id, status="completed"
        )
        replayable = await _insert_execution(
            conn, workflow_id, org_id, user_id, status="pending"
        )
        test_key = f"test-dlq-{uuid.uuid4().hex}"
        monkeypatch.setattr(dlq, "DLQ_KEY", test_key)
        enqueued: list[str] = []
        fake_task = type("FakeTask", (), {})()
        fake_task.delay = lambda execution_id: enqueued.append(execution_id)
        monkeypatch.setattr("app.engine.tasks.execute_workflow_task", fake_task)
        import redis.asyncio as aioredis

        client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        await client.delete(test_key)
        try:
            await client.rpush(
                test_key,
                json.dumps(
                    {
                        "execution_id": str(terminal),
                        "error": "boom",
                        "task": "execute_workflow",
                    }
                ),
                json.dumps(
                    {
                        "execution_id": str(replayable),
                        "error": "boom",
                        "task": "execute_workflow",
                    }
                ),
            )
            stats = await dlq.dlq_stats()
            assert stats["count"] == 2
            terminal_replay = await dlq.dlq_replay(0, actor="test")
            assert terminal_replay["ok"] is False
            assert enqueued == []
            replayable_replay = await dlq.dlq_replay(1, actor="test")
            assert replayable_replay["ok"] is True
            assert enqueued == [str(replayable)]
            discard = await dlq.dlq_discard(0, actor="test")
            assert discard["ok"] is True
            stats_after = await dlq.dlq_stats()
            assert stats_after["count"] == 1
            audits = await conn.fetchval(
                "SELECT count(*) FROM audit_logs WHERE action LIKE 'dlq_%' "
                "AND resource_id IN ($1,$2)",
                str(terminal),
                str(replayable),
            )
            assert audits >= 3
        finally:
            await client.delete(test_key)
            await client.aclose()
            await _cleanup(
                conn,
                executions=[terminal, replayable],
                workflow_id=workflow_id,
                user_id=user_id,
                org_id=org_id,
            )
            await conn.close()

    asyncio.run(main())


def test_production_alerts_thresholds_and_cooldown(monkeypatch):
    async def main() -> None:
        conn = await asyncpg.connect(_sync_url())
        metrics = {
            "dlq_count": 99,
            "pending_executions": 0,
            "in_flight_tool_calls": 0,
            "approval_mismatch_24h": 0,
            "side_effect_unknown_24h": 0,
            "llm_calls_24h": 0,
            "llm_fallback_rate": 0.0,
            "llm_latency_p95_ms": None,
            "database_ok": False,
            "redis_ok": True,
        }
        monkeypatch.setattr(
            production_alerts,
            "collect_production_metrics",
            lambda: _fake_collect(metrics),
        )
        try:
            alerts = production_alerts.evaluate_production_alerts(metrics)
            by_name = {alert["name"]: alert for alert in alerts}
            assert by_name["dlq_growth"]["ok"] is False
            assert by_name["database_unhealthy"]["ok"] is False
            assert by_name["redis_unhealthy"]["ok"] is True
            first = await production_alerts.run_production_alerts()
            second = await production_alerts.run_production_alerts()
            assert len(first) >= 2
            assert len(second) == 0  # cooldown 抑制噪声
            # cooldown 过期后允许再次触发
            await conn.execute(
                "UPDATE alert_events SET triggered_at = now() - interval '30 minutes' "
                "WHERE rule_id IN ('dlq_growth','database_unhealthy')"
            )
            third = await production_alerts.run_production_alerts()
            assert len(third) >= 2
        finally:
            await conn.execute(
                "DELETE FROM alert_events WHERE rule_id IN "
                "('dlq_growth','database_unhealthy')"
            )
            await conn.close()

    asyncio.run(main())


async def _fake_collect(metrics):
    return metrics


def test_cost_metering_and_unknown_semantics(monkeypatch):
    async def main() -> None:
        from app.core import billing

        conn = await asyncpg.connect(_sync_url())
        org_id, user_id, workflow_id = await _setup(conn)
        known = await _insert_execution(
            conn, workflow_id, org_id, user_id, status="completed"
        )
        unknown = await _insert_execution(
            conn, workflow_id, org_id, user_id, status="completed"
        )
        try:
            db = await asyncpg.connect(_sync_url())
            await db.execute(
                "UPDATE executions SET checkpoint_data = $2::json WHERE id=$1",
                known,
                json.dumps(
                    {
                        "llm_usage": [
                            {
                                "model_used": "deepseek-chat",
                                "input_tokens": 1000,
                                "output_tokens": 500,
                                "cost": 0.0015,
                            },
                            {
                                "model_used": "deepseek-chat",
                                "input_tokens": 2000,
                                "output_tokens": 1000,
                                "cost": 0.003,
                            },
                        ]
                    }
                ),
            )
            await db.execute(
                "UPDATE executions SET checkpoint_data = $2::json WHERE id=$1",
                unknown,
                json.dumps(
                    {
                        "llm_usage": [
                            {
                                "model_used": "no-such-model",
                                "input_tokens": 1000,
                                "output_tokens": 500,
                            }
                        ]
                    }
                ),
            )
            await db.close()
            await billing.record_execution_usage(known)
            await billing.record_execution_usage(unknown)
            known_cost = await conn.fetchval(
                "SELECT cost FROM executions WHERE id=$1", known
            )
            unknown_cost = await conn.fetchval(
                "SELECT cost FROM executions WHERE id=$1", unknown
            )
            assert known_cost == pytest.approx(0.0045)
            assert unknown_cost is None
        finally:
            await _cleanup(
                conn,
                executions=[known, unknown],
                workflow_id=workflow_id,
                user_id=user_id,
                org_id=org_id,
            )
            await conn.close()

    asyncio.run(main())


def test_gateway_cross_provider_fallback_control_flow():
    async def main() -> None:
        from langchain_core.messages import HumanMessage

        from app.core.model_gateway import ModelGateway

        class FailingLLM:
            model_name = "deepseek-v4-flash"

            async def ainvoke(self, _messages):
                raise TimeoutError("provider A timeout")

        class WorkingLLM:
            model_name = "deepseek-v4-flash"

            async def ainvoke(self, _messages):
                from langchain_core.messages import AIMessage

                return AIMessage(
                    content="ok",
                    usage_metadata={
                        "input_tokens": 1000,
                        "output_tokens": 500,
                        "total_tokens": 1500,
                    },
                )

        gateway = ModelGateway()
        response = await gateway.invoke(
            [FailingLLM(), WorkingLLM()],
            [HumanMessage(content="hi")],
            task_type="fallback-test",
            correlation_id=str(uuid.uuid4()),
        )
        metadata = (getattr(response, "additional_kwargs", None) or {}).get(
            "_agenthub_llm"
        ) or {}
        assert str(getattr(response, "content", "")) == "ok"
        assert metadata["fallback"] is True
        assert metadata["attempts"] == 1
        assert metadata["input_tokens"] == 1000
        assert metadata["output_tokens"] == 500
        # 真实 rate（deepseek-chat）存在时 cost 必须可计算
        assert metadata.get("cost") is not None

    asyncio.run(main())


def test_metrics_endpoint_exposes_production_gauges(monkeypatch):
    async def main() -> None:
        from fastapi.testclient import TestClient

        from app.main import app

        metrics = {
            "dlq_count": 7,
            "pending_executions": 2,
            "in_flight_tool_calls": 0,
            "approval_mismatch_24h": 0,
            "side_effect_unknown_24h": 0,
            "llm_calls_24h": 10,
            "llm_fallback_rate": 0.0,
            "llm_latency_p95_ms": None,
            "database_ok": True,
            "redis_ok": True,
        }
        monkeypatch.setattr(
            "app.api.routes.metrics.collect_production_metrics",
            lambda: _fake_collect(metrics),
        )
        client = TestClient(app)
        body = client.get("/metrics").text
        assert "agenthub_dlq_count 7.0" in body
        assert "agenthub_pending_executions 2.0" in body

    asyncio.run(main())


def test_baseline_report_is_read_only_and_derivable():
    async def main() -> None:
        from app.core import baseline_report

        conn = await asyncpg.connect(_sync_url())
        org_id, user_id, workflow_id = await _setup(conn)
        ok = await _insert_execution(
            conn, workflow_id, org_id, user_id, status="completed"
        )
        bad = await _insert_execution(
            conn, workflow_id, org_id, user_id, status="failed"
        )
        try:
            db = await asyncpg.connect(_sync_url())
            await db.execute(
                "UPDATE executions SET intent=$2::json WHERE id=$1",
                ok,
                json.dumps({"category": "CHAT"}),
            )
            await db.execute(
                "UPDATE executions SET intent=$2::json, error_message='x' "
                "WHERE id=$1",
                bad,
                json.dumps({"category": "KNOWLEDGE"}),
            )
            await db.close()
            start = datetime.now(timezone.utc) - timedelta(minutes=5)
            report = await baseline_report.build_baseline_report(
                start_time=start, end_time=datetime.now(timezone.utc)
            )
            assert report["requests"]["total"] >= 2
            assert report["requests"]["chat"] >= 1
            assert report["requests"]["knowledge"] >= 1
            assert report["error"]["execution_failed"] >= 1
            assert isinstance(report["tokens"], dict)
            assert "POST_DEPLOY_BASELINE" in baseline_report.render_baseline_report(
                report
            )
        finally:
            await _cleanup(
                conn,
                executions=[ok, bad],
                workflow_id=workflow_id,
                user_id=user_id,
                org_id=org_id,
            )
            await conn.close()

    asyncio.run(main())


def test_approval_event_emitted_after_state_commit(monkeypatch):
    async def main() -> None:
        conn = await asyncpg.connect(_sync_url())
        org_id, user_id, workflow_id = await _setup(conn)
        await conn.execute(
            "UPDATE workflows SET dag_definition = $1::json WHERE id = $2",
            json.dumps({"nodes": [{"type": "send_email", "label": "send"}]}),
            workflow_id,
        )
        execution_id = await _insert_execution(
            conn,
            workflow_id,
            org_id,
            user_id,
            status="pending",
            intent={"category": "ACTION", "risk": "SIDE_EFFECT"},
        )
        observed: list[tuple[str | None, str]] = []
        real_publish = runner.publish_execution_event

        async def wrapped_publish(execution_id, event):
            if event.get("event") == "approval_required":
                status = await conn.fetchval(
                    "SELECT status FROM executions WHERE id=$1", str(execution_id)
                )
                observed.append((event.get("approval_id"), status))
            await real_publish(str(execution_id), event)

        class ProposalGateway:
            async def select(self, **kwargs):
                return [object()]

            async def invoke(self, llms, messages, **kwargs):
                return AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "send_email",
                            "args": {"to": "a@b.com", "subject": "s", "body": "b"},
                            "id": "call_proposal",
                            "type": "tool_call",
                        }
                    ],
                )

            async def stream(self, llms, messages, **kwargs):
                yield "x"

        monkeypatch.setattr(runner, "publish_execution_event", wrapped_publish)
        monkeypatch.setattr(graph_module._gateway, "invoke", ProposalGateway().invoke)
        monkeypatch.setattr(graph_module._gateway, "stream", ProposalGateway().stream)
        try:
            await runner.run_execution(execution_id)
            assert observed, "approval_required event was not emitted"
            for approval_id, status in observed:
                assert approval_id
                assert status == "waiting_for_approval"
        finally:
            await _cleanup(
                conn,
                executions=[execution_id],
                workflow_id=workflow_id,
                user_id=user_id,
                org_id=org_id,
            )
            await conn.close()

    asyncio.run(main())


def test_concurrent_resume_only_one_wins(monkeypatch):
    async def main() -> None:
        from types import SimpleNamespace

        from app.api.routes import executions as exec_routes
        from app.database import async_session_factory
        from app.schemas.execution import ExecutionResume

        conn = await asyncpg.connect(_sync_url())
        org_id, user_id, workflow_id = await _setup(conn)
        execution_id = await _insert_execution(
            conn, workflow_id, org_id, user_id, status="waiting_for_approval"
        )
        delayed: list[str] = []
        monkeypatch.setattr(
            exec_routes.resume_workflow_task,
            "delay",
            lambda execution_id, decision: delayed.append(execution_id),
        )
        user = SimpleNamespace(id=user_id, organization_id=org_id)
        codes: list[int] = []

        async def resume_once():
            async with async_session_factory() as session:
                try:
                    await exec_routes.resume_execution(
                        execution_id,
                        ExecutionResume(approved=True),
                        session,
                        user,
                    )
                    codes.append(202)
                except Exception as exc:  # noqa: BLE001
                    codes.append(getattr(exc, "status_code", 500))

        try:
            await asyncio.gather(resume_once(), resume_once())
            assert sorted(codes) == [202, 409]
            assert len(delayed) == 1
        finally:
            await _cleanup(
                conn,
                executions=[execution_id],
                workflow_id=workflow_id,
                user_id=user_id,
                org_id=org_id,
            )
            await conn.close()

    asyncio.run(main())


def test_approval_id_mismatch_aborts_with_audit():
    async def main() -> None:
        from app.engine.canonical import params_canonical

        conn = await asyncpg.connect(_sync_url())
        org_id, user_id, workflow_id = await _setup(conn)
        execution_id = await _insert_execution(
            conn, workflow_id, org_id, user_id, status="pending"
        )
        email_params = {"to": "a@b.com", "subject": "s", "body": "b"}
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
                    "params": email_params,
                    "params_canonical": params_canonical(
                        email_params, tool_name="send_email"
                    ),
                }
            ],
        }
        initial_state = {
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
            "plan_meta": {"plan": plan, "approval_id": "expected"},
            "budget_used": {},
            "budget_exceeded": False,
            "hard_stop": False,
            "approval_rejected": False,
            "side_effect_failure": False,
            "approved_plan_hash": planner.compute_plan_hash(plan),
            "approved_approval_id": "different",
        }
        try:
            graph = graph_module.build_graph()
            with pytest.raises(PlanInvalidError):
                await graph.ainvoke(initial_state)
            audit = await conn.fetchrow(
                "SELECT action FROM audit_logs WHERE resource_id=$1 "
                "AND action='approval_mismatch'",
                str(execution_id),
            )
            assert audit is not None
        finally:
            await _cleanup(
                conn,
                executions=[execution_id],
                workflow_id=workflow_id,
                user_id=user_id,
                org_id=org_id,
            )
            await conn.close()

    asyncio.run(main())

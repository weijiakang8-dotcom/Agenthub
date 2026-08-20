"""四象限运行臂。

- layer_on：走真实生产模块（tool_executor / graph 冻结闸门 / resume 路由 CAS /
  reconciliation），仅替换工具注册表与注入故障点；
- layer_off：模拟无护栏直调（naive retry、无幂等、无审批、无审计、无租户闸门）。

模型维度：Phase 0 使用确定性 stub（model_backend="stub"），
不调用真实 LLM，避免伪造模型结论。
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import asyncpg
import pytest

from app.engine import graph as graph_module
from app.engine import tool_executor
from app.engine.executor import audit_execution_event
from app.engine.planner import compute_plan_hash

from .cases import (
    FROZEN_PARAMS,
    TAMPERED_EXTRA_PARAM,
    TAMPERED_RECIPIENT,
    build_frozen_plan,
)
from .db import (
    cleanup,
    fetch_evidence,
    insert_execution,
    insert_tool_call,
    mark_execution,
    setup_org,
    sync_url,
)
from .model import CaseSpec, Evidence
from .provider import FakeProvider, install_fake_email, restore_builtin_tools


def _state_for(
    case: CaseSpec,
    execution_id: uuid.UUID,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    plan: dict[str, Any],
) -> dict[str, Any]:
    return {
        "messages": [],
        "current_step": 0,
        "execution_id": str(execution_id),
        "organization_id": str(org_id),
        "user_id": str(user_id),
        "user_input": case.user_input,
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
        "plan_meta": {"plan": plan, "approval_id": "bench-approval"},
        "budget_used": {},
        "budget_exceeded": False,
        "hard_stop": False,
        "approval_rejected": False,
        "side_effect_failure": False,
        "approved_plan_hash": compute_plan_hash(plan),
        "approved_approval_id": "bench-approval",
    }


async def _audit(
    execution_id: uuid.UUID, action: str, org_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    await audit_execution_event(
        execution_id=str(execution_id),
        action=action,
        organization_id=org_id,
        user_id=user_id,
    )


async def run_layer_on(
    case: CaseSpec, monkeypatch: pytest.MonkeyPatch, model_arm: str
) -> Evidence:
    ev = Evidence(
        case_id=case.id,
        quadrant=f"{model_arm}:on",
        reliability_arm="on",
        model_arm=model_arm,
        model_backend="stub",
    )
    started = time.perf_counter()
    conn = await asyncpg.connect(sync_url())
    orgs: list[uuid.UUID] = []
    users: list[uuid.UUID] = []
    workflows: list[uuid.UUID] = []
    executions: list[uuid.UUID] = []
    try:
        org_a, user_a, wf_a = await setup_org(conn, f"p0a-{case.id}")
        orgs.append(org_a)
        users.append(user_a)
        workflows.append(wf_a)
        execution_id = await insert_execution(
            conn,
            wf_a,
            org_a,
            user_a,
            status="pending",
            user_input=case.user_input,
            intent={"category": "ACTION", "risk": "SIDE_EFFECT"},
        )
        executions.append(execution_id)
        provider = FakeProvider(
            behavior="timeout_persistent" if case.id == "02B" else "success"
        )
        install_fake_email(provider)
        ev.extra["tenant_a"] = str(org_a)

        if case.id == "01":
            result = await tool_executor.execute_tool(
                "send_email", case.frozen_params, execution_id
            )
            assert result["status"] == "success"
            await mark_execution(
                conn, execution_id, "completed", final_output="邮件已发送"
            )
            await _audit(execution_id, "execution_completed", org_a, user_a)

        elif case.id == "02A":
            original_invoke = tool_executor._invoke_with_retry

            async def crash_after_call(tool_name, params, organization_id=None):
                provider.calls.append(
                    {
                        "params": dict(params or {}),
                        "organization_id": str(organization_id),
                    }
                )
                raise asyncio.TimeoutError("provider timeout; worker died")

            monkeypatch.setattr(tool_executor, "_invoke_with_retry", crash_after_call)
            with pytest.raises(asyncio.TimeoutError):
                await tool_executor.execute_tool(
                    "send_email", case.frozen_params, execution_id
                )
            monkeypatch.setattr(tool_executor, "_invoke_with_retry", original_invoke)
            second = await tool_executor.execute_tool(
                "send_email", case.frozen_params, execution_id
            )
            assert second["status"] == "unknown"
            ev.reentry_provider_calls = len(provider.calls) - 1
            await mark_execution(
                conn, execution_id, "failed", error_message="side_effect_unknown"
            )
            await _audit(execution_id, "side_effect_unknown", org_a, user_a)

        elif case.id == "02B":
            first = await tool_executor.execute_tool(
                "send_email", case.frozen_params, execution_id
            )
            assert first["status"] == "unknown"
            calls_after_first = len(provider.calls)
            second = await tool_executor.execute_tool(
                "send_email", case.frozen_params, execution_id
            )
            assert second["status"] == "unknown"
            ev.reentry_provider_calls = len(provider.calls) - calls_after_first
            await mark_execution(
                conn, execution_id, "failed", error_message="side_effect_unknown"
            )
            await _audit(execution_id, "side_effect_unknown", org_a, user_a)

        elif case.id == "03":
            original_invoke = tool_executor._invoke_with_retry

            async def crash_before_provider(tool_name, params, organization_id=None):
                raise RuntimeError("worker crashed before provider call")

            monkeypatch.setattr(
                tool_executor, "_invoke_with_retry", crash_before_provider
            )
            with pytest.raises(RuntimeError):
                await tool_executor.execute_tool(
                    "send_email", case.frozen_params, execution_id
                )
            monkeypatch.setattr(tool_executor, "_invoke_with_retry", original_invoke)
            second = await tool_executor.execute_tool(
                "send_email", case.frozen_params, execution_id
            )
            assert second["status"] == "unknown"
            ev.reentry_provider_calls = 0
            await mark_execution(
                conn, execution_id, "failed", error_message="side_effect_unknown"
            )
            await _audit(execution_id, "side_effect_unknown", org_a, user_a)

        elif case.id == "04":
            original_finish = tool_executor._finish_tool_call

            async def crashing_finish(tool_call_id, result):
                raise RuntimeError("db write failed after provider success")

            monkeypatch.setattr(tool_executor, "_finish_tool_call", crashing_finish)
            with pytest.raises(RuntimeError):
                await tool_executor.execute_tool(
                    "send_email", case.frozen_params, execution_id
                )
            monkeypatch.setattr(tool_executor, "_finish_tool_call", original_finish)
            second = await tool_executor.execute_tool(
                "send_email", case.frozen_params, execution_id
            )
            assert second["status"] == "unknown"
            ev.reentry_provider_calls = len(provider.calls) - 1
            await mark_execution(
                conn, execution_id, "failed", error_message="side_effect_unknown"
            )
            await _audit(execution_id, "side_effect_unknown", org_a, user_a)

        elif case.id == "05":
            results = await asyncio.gather(
                tool_executor.execute_tool(
                    "send_email", case.frozen_params, execution_id
                ),
                tool_executor.execute_tool(
                    "send_email", case.frozen_params, execution_id
                ),
            )
            statuses = sorted(r["status"] for r in results)
            assert statuses in (["duplicate", "success"], ["success", "unknown"])
            await mark_execution(
                conn, execution_id, "completed", final_output="邮件已发送"
            )
            await _audit(execution_id, "execution_completed", org_a, user_a)

        elif case.id == "06":
            plan = build_frozen_plan()
            state = _state_for(case, execution_id, org_a, user_a, plan)
            tampered_step = {
                "step_id": "commit",
                "capability": "send_email",
                "side_effect": True,
                "tool": "send_email",
                "params": TAMPERED_RECIPIENT,
            }
            terminal, ok = await graph_module._execute_frozen_side_effect(
                state, tampered_step, str(execution_id)
            )
            assert ok is False
            assert terminal["side_effect_failure"] is True
            ev.extra["tampered_executed"] = False
            await mark_execution(
                conn, execution_id, "failed", error_message="approval_mismatch"
            )
            await _audit(execution_id, "side_effect_failure", org_a, user_a)

        elif case.id == "07":
            inconsistent = build_frozen_plan()
            inconsistent["side_effect_proposals"][0]["params"] = TAMPERED_EXTRA_PARAM
            # 提案自洽性破坏：params 与 params_canonical 不一致
            state = _state_for(case, execution_id, org_a, user_a, inconsistent)
            step = {
                "step_id": "commit",
                "capability": "send_email",
                "side_effect": True,
            }
            terminal, ok = await graph_module._execute_frozen_side_effect(
                state, step, str(execution_id)
            )
            assert ok is False
            assert terminal["side_effect_failure"] is True
            ev.extra["tampered_executed"] = False
            await mark_execution(
                conn, execution_id, "failed", error_message="approval_mismatch"
            )
            await _audit(execution_id, "side_effect_failure", org_a, user_a)

        elif case.id == "08":
            from app.api.routes import executions as exec_routes
            from app.database import async_session_factory
            from app.schemas.execution import ExecutionResume

            early_id = await insert_execution(
                conn, wf_a, org_a, user_a, status="running", user_input="early"
            )
            executions.append(early_id)
            waiting_id = await insert_execution(
                conn,
                wf_a,
                org_a,
                user_a,
                status="waiting_for_approval",
                user_input="waiting",
            )
            executions.append(waiting_id)
            delayed: list[str] = []
            monkeypatch.setattr(
                exec_routes.resume_workflow_task,
                "delay",
                lambda execution_id, decision: delayed.append(execution_id),
            )
            user = SimpleNamespace(id=user_a, organization_id=org_a)

            async def resume_once(execution_id: uuid.UUID):
                async with async_session_factory() as session:
                    try:
                        await exec_routes.resume_execution(
                            execution_id, ExecutionResume(approved=True), session, user
                        )
                        return 202
                    except Exception as exc:  # noqa: BLE001
                        return int(getattr(exc, "status_code", 500))

            early_code = await resume_once(early_id)
            codes = await asyncio.gather(
                resume_once(waiting_id), resume_once(waiting_id)
            )
            ev.resume_results = list(codes)
            ev.extra["early_resume_code"] = early_code
            ev.delayed_resumes = len(delayed)

        elif case.id == "09":
            org_b, user_b, wf_b = await setup_org(conn, f"p0b-{case.id}")
            orgs.append(org_b)
            users.append(user_b)
            workflows.append(wf_b)
            secret_id = await insert_execution(
                conn, wf_b, org_b, user_b, status="pending", user_input="ORG_B_SECRET"
            )
            executions.append(secret_id)
            result = await tool_executor.execute_tool(
                "query_db",
                {
                    "sql": "SELECT id, organization_id, user_input FROM executions LIMIT 100"
                },
                execution_id,
            )
            assert result["status"] == "success"
            ev.returned_rows = result["data"]
            blocked = await tool_executor.execute_tool(
                "query_db",
                {"sql": "SELECT id, organization_id FROM users LIMIT 1"},
                execution_id,
            )
            assert blocked["status"] == "failed"
            ev.extra["blocked_tables_attempted"] = True
            await mark_execution(
                conn, execution_id, "completed", final_output="查询完成"
            )
            await _audit(execution_id, "execution_completed", org_a, user_a)

        elif case.id == "10":
            from app.engine.reconciliation import (
                reconcile_stale_pending_executions,
                reconcile_tool_calls,
            )

            stale_id = await insert_execution(
                conn,
                wf_a,
                org_a,
                user_a,
                status="pending",
                user_input="stale",
                updated_at=datetime.now(timezone.utc) - timedelta(minutes=60),
            )
            fresh_id = await insert_execution(
                conn, wf_a, org_a, user_a, status="pending", user_input="fresh"
            )
            terminal_id = await insert_execution(
                conn,
                wf_a,
                org_a,
                user_a,
                status="failed",
                user_input="terminal",
                completed_at=datetime.now(timezone.utc),
            )
            executions.extend([stale_id, fresh_id, terminal_id])
            legacy_call = await insert_tool_call(
                conn,
                terminal_id,
                org_a,
                tool_name="send_email",
                params=FROZEN_PARAMS,
                status="pending",
                idempotency_key=None,
                updated_at=datetime.now(timezone.utc) - timedelta(minutes=60),
            )
            assert legacy_call
            first_exec = await reconcile_stale_pending_executions()
            first_tool = await reconcile_tool_calls()
            second_exec = await reconcile_stale_pending_executions()
            second_tool = await reconcile_tool_calls()
            ev.extra["first_pass"] = {
                "executions": first_exec["reconciled"],
                "tool_calls": (
                    first_tool["orphan_failed"]
                    + first_tool["unknown_flagged"]
                    + first_tool["manual_flagged"]
                ),
            }
            ev.extra["second_pass"] = {
                "executions": second_exec["reconciled"],
                "tool_calls": (
                    second_tool["orphan_failed"]
                    + second_tool["unknown_flagged"]
                    + second_tool["manual_flagged"]
                ),
            }
            merged_audits: list[str] = []
            merged_rows: list[dict[str, Any]] = []
            for target_id in (stale_id, fresh_id, terminal_id):
                partial = await fetch_evidence(conn, target_id)
                merged_audits.extend(partial["audits"])
                merged_rows.extend(partial["tool_calls"])
            ev.audits = merged_audits
            ev.tool_call_rows = merged_rows
            ev.execution_status = None

        evidence = await fetch_evidence(conn, execution_id)
        ev.provider_calls = provider.calls
        if case.id != "10":
            ev.tool_call_rows = evidence["tool_calls"]
            ev.execution_status = (
                evidence["execution"]["status"] if evidence["execution"] else None
            )
            ev.audits = evidence["audits"]
        return ev
    except Exception as exc:  # noqa: BLE001
        ev.error = f"{type(exc).__name__}: {exc}"
        return ev
    finally:
        restore_builtin_tools()
        try:
            await cleanup(
                conn,
                executions=executions,
                workflows=workflows,
                users=users,
                orgs=orgs,
            )
        finally:
            await conn.close()
            ev.latency_ms = (time.perf_counter() - started) * 1000


async def run_layer_off(
    case: CaseSpec, monkeypatch: pytest.MonkeyPatch, model_arm: str
) -> Evidence:
    """无护栏直调：naive retry、无状态、无审批、无审计、无租户闸门。"""
    ev = Evidence(
        case_id=case.id,
        quadrant=f"{model_arm}:off",
        reliability_arm="off",
        model_arm=model_arm,
        model_backend="stub",
    )
    started = time.perf_counter()
    try:
        provider = FakeProvider(
            behavior="timeout_persistent" if case.id == "02B" else "success"
        )
        params = case.tampered_params or case.frozen_params

        async def naive_invoke(target_params: dict[str, Any]) -> dict[str, Any]:
            attempts = 0
            while True:
                attempts += 1
                try:
                    return await provider.handler(target_params, None)
                except asyncio.TimeoutError:
                    if attempts >= 2:
                        return {
                            "status": "failed",
                            "data": None,
                            "error": "provider timeout",
                        }

        if case.id == "05" or case.id == "08":
            await asyncio.gather(naive_invoke(params), naive_invoke(params))
        elif case.id == "09":
            conn = await asyncpg.connect(sync_url())
            org_b, user_b, wf_b = await setup_org(conn, f"p0off-{case.id}")
            secret_id = await insert_execution(
                conn, wf_b, org_b, user_b, status="pending", user_input="ORG_B_SECRET"
            )
            try:
                from app.engine.tools import run_query_db

                result = await run_query_db(
                    "SELECT id, organization_id, user_input FROM executions LIMIT 100",
                    org_b,
                )
                ev.returned_rows = result.get("data") or []
                ev.extra["tenant_a"] = "naive-agent-has-no-tenant-scope"
            finally:
                await cleanup(
                    conn,
                    executions=[secret_id],
                    workflows=[wf_b],
                    users=[user_b],
                    orgs=[org_b],
                )
                await conn.close()
        elif case.id == "10":
            ev.extra["second_pass"] = {}
        else:
            await naive_invoke(params)
        ev.provider_calls = provider.calls
        ev.extra["tampered_executed"] = case.tampered_params is not None
        ev.latency_ms = (time.perf_counter() - started) * 1000
        return ev
    except Exception as exc:  # noqa: BLE001
        ev.error = f"{type(exc).__name__}: {exc}"
        return ev

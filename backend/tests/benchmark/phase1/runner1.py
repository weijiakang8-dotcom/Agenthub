"""Phase 1A trial 流水线。

ON 臂使用生产可靠性模块（tool_executor.execute_tool / approval.build_proposal /
audit_execution_event）；OFF 臂用同一 agent loop 直接调 handler，无任何可靠性机制。
"""

from __future__ import annotations

import time
import uuid
from typing import Any

import asyncpg

from app.engine import tool_executor
from app.engine.approval import build_proposal
from app.engine.executor import audit_execution_event
from app.engine.tool_registry import get_tool, register_builtin_tools

from tests.benchmark import db as bench_db
from tests.benchmark.phase1.fixtures import BusinessFixture, register_phase1_tools
from tests.benchmark.phase1.gateway import call_action, call_synthesis, call_verify
from tests.benchmark.phase1.model_matrix import build_llm, cost_cny, is_peak_hour
from tests.benchmark.phase1.oracle1 import TASKS, evaluate_trial, param_equivalent


def _tool_schema(name: str) -> dict[str, Any]:
    spec = get_tool(name)
    if spec is None:
        raise RuntimeError(f"tool not registered: {name}")
    return {
        "type": "function",
        "function": {
            "name": spec.name,
            "description": spec.description,
            "parameters": spec.parameters,
        },
    }


def _classify_api_failure(message: str) -> str:
    text = str(message).lower()
    if "timeout" in text or "timed out" in text:
        return "timeout"
    if "429" in text or "rate limit" in text or "too many requests" in text:
        return "rate_limit"
    if "5" in text and ("server error" in text or "internal" in text):
        return "5xx"
    return "other"


def _param_equivalent(task_id: str, actual: dict[str, Any], canonical: dict[str, Any]) -> bool:
    return param_equivalent(task_id, actual, canonical)


async def run_trial(task_id: str, arm: str, trial: int) -> dict[str, Any]:
    from tests.benchmark.phase1.model_matrix import ARMS

    arm_cfg = ARMS[arm]
    model = arm_cfg["model"]
    reliability = arm_cfg["reliability"]
    task = TASKS[task_id]
    started = time.perf_counter()
    fx = BusinessFixture()
    register_phase1_tools(fx)
    llm = build_llm(model)

    record: dict[str, Any] = {
        "task_id": task_id,
        "arm": arm,
        "model": model,
        "reliability": reliability,
        "trial": trial,
        "success": False,
        "safe_success": False,
        "semantic_score": 0.0,
        "safety_failure": True,
        "serious_unsafe_event": [],
        "provider_calls": 0,
        "tool_calls": [],
        "execution_terminal_state": None,
        "recovery_converged": None,
        "input_tokens": 0,
        "output_tokens": 0,
        "cost_cny": None,
        "cost_usd": None,
        "latency_ms": 0.0,
        "audit_evidence": [],
        "failure_reason": None,
        "verify_pass": None,
        "model_calls": [],
    }

    conn: asyncpg.Connection | None = None
    org_id = user_id = workflow_id = execution_id = None
    usage_list: list[dict[str, Any]] = []
    executed_tool: str | None = None
    executed_params: dict[str, Any] = {}
    final_output = ""
    try:
        schemas = [_tool_schema(name) for name in task["available_tools"]]
        action = await call_action(llm, task["user_intent"], schemas)
        usage_list.append({"step": "action", **action["usage"]})
        record["model_calls"].append(
            {
                "step": "action",
                "latency_ms": round(action["latency_ms"], 2),
                "usage": action["usage"],
                "api_failure": action["api_failure"],
            }
        )
        if not action["ok"]:
            record["failure_reason"] = f"api_failure:{_classify_api_failure(action['api_failure'])}"
            record["execution_terminal_state"] = "failed"
            return _finalize(record, task, reliability, fx, usage_list, started, executed_tool, executed_params, final_output)

        tool_calls = action["tool_calls"]
        if len(tool_calls) != 1:
            record["failure_reason"] = "no_tool_call" if not tool_calls else "multiple_tool_calls"
            record["execution_terminal_state"] = "failed"
            return _finalize(record, task, reliability, fx, usage_list, started, executed_tool, executed_params, final_output)

        call = tool_calls[0]
        executed_tool = str(call.get("name") or "")
        executed_params = dict(call.get("args") or {})
        record["tool_calls"] = [executed_tool]
        tool_result: dict[str, Any] | None = None

        if reliability == "ON":
            if conn is None:
                conn = await asyncpg.connect(bench_db.sync_url())
            org_id, user_id, workflow_id = await bench_db.setup_org(conn, f"p1-{task_id}-{arm}-{trial}")
            execution_id = await bench_db.insert_execution(
                conn, workflow_id, org_id, user_id, status="pending", user_input=task["user_intent"]
            )
            if task["risk"] == "R2":
                proposal = build_proposal(
                    step_id="s1",
                    capability=executed_tool,
                    tool=executed_tool,
                    params=executed_params,
                )
                record["frozen_proposal"] = proposal.to_dict()
                result = await tool_executor.execute_tool(proposal.tool, proposal.params, execution_id)
            else:
                record["frozen_proposal"] = None
                result = await tool_executor.execute_tool(executed_tool, executed_params, execution_id)
            tool_result = result
        else:
            spec = get_tool(executed_tool)
            if spec is None:
                record["failure_reason"] = "unknown_tool"
                record["execution_terminal_state"] = "failed"
                return _finalize(record, task, reliability, fx, usage_list, started, executed_tool, executed_params, final_output)
            tool_result = await spec.handler(executed_params, None)

        if tool_result is None or tool_result.get("status") != "success":
            record["failure_reason"] = f"tool_failed:{str(tool_result or {})[:120]}"

        synthesis = await call_synthesis(llm, task["user_intent"], executed_tool, tool_result or {})
        usage_list.append({"step": "synthesis", **synthesis["usage"]})
        record["model_calls"].append(
            {
                "step": "synthesis",
                "latency_ms": round(synthesis["latency_ms"], 2),
                "usage": synthesis["usage"],
                "api_failure": synthesis["api_failure"],
            }
        )
        final_output = synthesis["text"]
        if not synthesis["ok"]:
            record["failure_reason"] = f"api_failure:{_classify_api_failure(synthesis['api_failure'])}"

        if reliability == "ON":
            verify = await call_verify(llm, task["user_intent"], final_output)
            usage_list.append({"step": "verify", **verify["usage"]})
            record["verify_pass"] = verify["text"] == "PASS" if verify["ok"] else None
            record["model_calls"].append(
                {
                    "step": "verify",
                    "latency_ms": round(verify["latency_ms"], 2),
                    "usage": verify["usage"],
                    "api_failure": verify["api_failure"],
                }
            )
            await bench_db.mark_execution(conn, execution_id, "completed", final_output=final_output or None)
            await audit_execution_event(
                execution_id=str(execution_id),
                action="execution_completed",
                organization_id=org_id,
                user_id=user_id,
            )
            evidence = await bench_db.fetch_evidence(conn, execution_id)
            record["audit_evidence"] = evidence["audits"]
            record["execution_terminal_state"] = evidence["execution"]["status"] if evidence["execution"] else "missing"
        else:
            record["execution_terminal_state"] = "completed" if synthesis["ok"] else "failed"

        record["success"] = True
        return _finalize(record, task, reliability, fx, usage_list, started, executed_tool, executed_params, final_output)
    except Exception as exc:  # noqa: BLE001
        record["failure_reason"] = f"harness_error:{type(exc).__name__}:{str(exc)[:200]}"
        record["execution_terminal_state"] = "failed"
        return _finalize(record, task, reliability, fx, usage_list, started, executed_tool, executed_params, final_output)
    finally:
        if conn is not None:
            try:
                if execution_id is not None:
                    await bench_db.cleanup(
                        conn,
                        executions=[execution_id],
                        workflows=[workflow_id] if workflow_id else [],
                        users=[user_id] if user_id else [],
                        orgs=[org_id] if org_id else [],
                    )
            finally:
                await conn.close()
        register_builtin_tools()


def _finalize(
    record: dict[str, Any],
    task: dict[str, Any],
    reliability: str,
    fx: BusinessFixture,
    usage_list: list[dict[str, Any]],
    started: float,
    executed_tool: str | None,
    executed_params: dict[str, Any],
    final_output: str,
) -> dict[str, Any]:
    total_input = sum(int(u.get("input_tokens") or 0) for u in usage_list if u.get("input_tokens") is not None)
    total_output = sum(int(u.get("output_tokens") or 0) for u in usage_list if u.get("output_tokens") is not None)
    any_unknown = any(u.get("input_tokens") is None or u.get("output_tokens") is None for u in usage_list)
    record["input_tokens"] = total_input
    record["output_tokens"] = total_output
    peak = is_peak_hour()
    record["price_tier"] = "peak" if peak else "offpeak"
    record["cost_cny"] = None if any_unknown else cost_cny(record["model"], total_input, total_output, peak)
    record["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
    if task["risk"] == "R2":
        record["provider_calls"] = len(fx.sent_emails) + len(fx.finalized_invoices)
    else:
        record["provider_calls"] = 0
    record["recovery_converged"] = None

    evidence = {
        "executed_tool": executed_tool,
        "executed_params": executed_params,
        "tool_calls": record["tool_calls"],
        "side_effect_calls": record["provider_calls"],
        "terminal_state": record["execution_terminal_state"],
        "audit_evidence": record["audit_evidence"],
        "frozen_proposal": record.get("frozen_proposal"),
        "final_output": final_output,
    }
    verdict = evaluate_trial(task["task_id"], evidence, reliability)
    record["safe_success"] = verdict["safe_success"]
    record["semantic_score"] = 1.0 if verdict["semantic_pass"] else 0.0
    record["safety_failure"] = not verdict["safety_pass"]
    record["serious_unsafe_event"] = verdict["serious_unsafe_events"]
    record["safety_checks"] = verdict["safety_checks"]
    record["semantic_checks"] = verdict["semantic_checks"]
    record["executed_params"] = executed_params
    record["final_output"] = final_output[:400]
    if record["failure_reason"] is None and not verdict["safe_success"]:
        record["failure_reason"] = "safety_failure" if not verdict["safety_pass"] else "semantic_failure"
    return record

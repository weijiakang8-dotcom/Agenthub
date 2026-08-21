from __future__ import annotations

import logging
import uuid
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.errors import GraphInterrupt
from langgraph.types import Command
from sqlalchemy import select, update

from app.config import settings
from app.core.billing import record_execution_usage
from app.core.failure import classify_error, should_retry
from app.database import async_session_factory
from app.engine.checkpoint import get_checkpoint_manager
from app.engine.event_bus import publish_execution_event
from app.engine.executor import PlanInvalidError, audit_execution_event
from app.engine.graph import build_graph
from app.engine.planner import is_plan_invalid, normalize_plan
from app.engine.tasks import evaluate_execution_task
from app.models import Agent, Execution, ToolCall, Workflow, utcnow
from app.models.enums import ExecutionStatus

ROLES = ["research", "analyze", "execute"]
_NO_INTERRUPT = object()
logger = logging.getLogger(__name__)

MAX_CONTEXT_MESSAGES = 20
MAX_CONTEXT_CHARS = 12000


async def _collect_shadow_tool_calls(execution_id: str) -> list[dict]:
    try:
        async with async_session_factory() as session:
            result = await session.execute(
                select(ToolCall).where(ToolCall.execution_id == uuid.UUID(execution_id))
            )
            calls = result.scalars().all()
            return [
                {
                    "tool_name": call.tool_name,
                    "input_params": call.input_params or {},
                    "output_result": call.output_result or {},
                    "status": (
                        call.status.value
                        if hasattr(call.status, "value")
                        else str(call.status)
                    ),
                }
                for call in calls
            ]
    except Exception:  # noqa: BLE001
        return []


async def run_shadow_hook(execution, workflow, final_output) -> Any | None:
    """真实 Legacy Shadow Hook：Legacy 结果确定后、COMPLETED 持久化前调用。

    - 默认关闭（settings.SHADOW_MODE=False）。
    - 任何异常都被吞掉，绝不改变 Legacy 主链路。
    """
    if not settings.SHADOW_MODE:
        return None
    try:
        from app.adapters.runtime_bridge import run_shadow_after_execution
        from app.adapters.shadow_audit import persist_shadow_audit

        tool_calls = await _collect_shadow_tool_calls(str(execution.id))
        result = run_shadow_after_execution(
            execution_id=str(execution.id),
            user_input=execution.user_input or "",
            final_output=final_output,
            status="completed",
            workflow_name=getattr(workflow, "name", "workflow"),
            agent_chain=getattr(workflow, "agent_chain", []) or [],
            tool_calls=tool_calls,
            enabled=True,
        )
        if result is not None:
            try:
                await persist_shadow_audit(
                    result,
                    execution_id=str(execution.id),
                    workflow_id=(
                        str(workflow.id)
                        if getattr(workflow, "id", None) is not None
                        else None
                    ),
                    organization_id=(
                        str(execution.organization_id)
                        if getattr(execution, "organization_id", None) is not None
                        else None
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                # Shadow audit 失败不得影响 Shadow 结果，更不得影响 Legacy。
                logger.warning("shadow audit persistence failed: %s", exc)
        return result
    except Exception:  # noqa: BLE001
        return None


def _clean_message_dicts(messages: Any) -> list[dict]:
    return [
        message
        for message in (messages or [])
        if isinstance(message, dict) and str(message.get("content", "")).strip()
    ]


def build_context_messages(prior_messages: Any) -> list[dict]:
    """把历史消息清洗并按长度截断，得到可入库的 conversation context。"""
    cleaned = _clean_message_dicts(prior_messages)[-MAX_CONTEXT_MESSAGES:]
    total = sum(len(str(message.get("content", ""))) for message in cleaned)
    while total > MAX_CONTEXT_CHARS and len(cleaned) > 1:
        total -= len(str(cleaned[0].get("content", "")))
        cleaned = cleaned[1:]
    return cleaned


def _to_langchain_message(message: dict) -> HumanMessage | AIMessage:
    content = str(message.get("content", ""))
    if message.get("role") == "assistant":
        return AIMessage(content=content)
    return HumanMessage(content=content)


def _build_initial_messages(context_messages: Any, user_input: str | None) -> list:
    messages = [
        _to_langchain_message(message)
        for message in _clean_message_dicts(context_messages)
    ]
    messages = messages[-MAX_CONTEXT_MESSAGES:]
    total = sum(len(str(message.content)) for message in messages)
    while total > MAX_CONTEXT_CHARS and len(messages) > 1:
        total -= len(str(messages[0].content))
        messages = messages[1:]
    if user_input:
        messages.append(HumanMessage(content=user_input))
    return messages


class ExecutionRetryableError(Exception):
    """可重试的执行错误，应由 Celery 层根据重试策略重新入队。"""


def _is_retryable_exception(exc: Exception) -> bool:
    return should_retry(classify_error(exc), "celery")


def _interrupt_value(result: dict[str, Any]) -> Any:
    interrupts = result.get("__interrupt__") or []
    if not interrupts:
        return _NO_INTERRUPT
    first = interrupts[0]
    return getattr(first, "value", first)


async def _publish_approval_event(
    execution_id: uuid.UUID,
    interrupt_value: Any,
    result: dict[str, Any],
) -> None:
    """在状态已提交后发射 approval_required / clarification_required（不领先持久化状态）。"""
    payload = interrupt_value
    if isinstance(payload, dict):
        pending = (
            payload.get("tool_call")
            if isinstance(payload.get("tool_call"), dict)
            else {}
        )
    else:
        pending = {}
    if isinstance(payload, dict) and payload.get("type") == "clarification":
        await publish_execution_event(
            str(execution_id),
            {
                "event": "clarification_required",
                "clarification": payload.get("clarification") or {},
            },
        )
        return
    if pending.get("type") == "plan_approval":
        event = {
            "event": "approval_required",
            "approval_id": pending.get("approval_id"),
            "plan_hash": pending.get("plan_hash"),
            "side_effect_set": pending.get("side_effect_set"),
            "side_effect_proposals": pending.get("side_effect_proposals") or [],
            "plan": result.get("plan"),
        }
    else:
        event = {
            "event": "approval_required",
            "tool_call_id": pending.get("tool_call_id"),
            "tool": pending.get("tool_name"),
            "params": pending.get("tool_args"),
        }
    await publish_execution_event(str(execution_id), event)


def _extract_agent_ids(agent_chain) -> list[uuid.UUID]:
    ids: list[uuid.UUID] = []

    def visit(value) -> None:
        if isinstance(value, str):
            try:
                ids.append(uuid.UUID(value))
            except ValueError:
                pass
        elif isinstance(value, dict):
            for key in ("agent_id", "id"):
                if key in value:
                    visit(value[key])
            if "nodes" in value:
                visit(value["nodes"])
        elif isinstance(value, (list, tuple)):
            for item in value:
                visit(item)

    visit(agent_chain)
    return ids


async def _build_steps(session, workflow: Workflow) -> list[dict[str, Any]]:
    dag = workflow.dag_definition or {}
    nodes = dag.get("nodes")
    if nodes:
        role_map = {
            "research": "research",
            "analyze": "analyze",
            "execute": "execute",
            "condition": "analyze",
            "human_approval": "execute",
            "approval": "execute",
        }
        steps = []
        for node in nodes:
            node_type = (
                (node or {}).get("type", "analyze")
                if isinstance(node, dict)
                else "analyze"
            )
            steps.append(
                {
                    "role": role_map.get(node_type, "analyze"),
                    "agent_id": None,
                    "name": (
                        (node or {}).get("label", node_type)
                        if isinstance(node, dict)
                        else node_type
                    ),
                    "system_prompt": (
                        (node or {}).get("system_prompt", "")
                        if isinstance(node, dict)
                        else ""
                    ),
                }
            )
        if steps:
            return steps

    agent_ids = _extract_agent_ids(workflow.agent_chain)
    steps: list[dict[str, Any]] = []
    for index, agent_id in enumerate(agent_ids):
        agent = await session.get(Agent, agent_id)
        role = ROLES[index] if index < len(ROLES) else "analyze"
        steps.append(
            {
                "role": role,
                "agent_id": str(agent_id),
                "name": agent.name if agent else "agent",
                "system_prompt": agent.system_prompt if agent else "",
            }
        )

    if not steps:
        steps = [
            {"role": role, "agent_id": None, "name": role, "system_prompt": ""}
            for role in ROLES
        ]
    return steps


def build_plan_from_workflow(workflow: Workflow) -> list[dict[str, Any]] | None:
    """把显式 workflow 定义映射为能力计划；无显式定义时由 Planner 动态规划。"""
    dag = workflow.dag_definition or {}
    nodes = dag.get("nodes")
    if nodes:
        capability_map = {
            "research": "research",
            "web_search": "web_search",
            "knowledge": "knowledge",
            "query_db": "query_db",
            "analyze": "analysis",
            "condition": "analysis",
            "execute": "execute",
            "send_email": "send_email",
            "answer": "answer",
            "human_approval": "send_email",
            "approval": "send_email",
        }
        plan = []
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_type = node.get("type", "analysis")
            plan.append(
                {
                    "capability": capability_map.get(node_type, "answer"),
                    "description": node.get("label", node_type),
                }
            )
        return plan or None

    agent_ids = _extract_agent_ids(workflow.agent_chain)
    if agent_ids:
        roles = ["research", "analysis", "execute"]
        plan = []
        for index, _agent_id in enumerate(agent_ids):
            role = roles[index] if index < len(roles) else "analysis"
            plan.append({"capability": role, "description": role})
        return plan
    return None


async def _update_status(
    execution_id: uuid.UUID,
    status: ExecutionStatus,
    *,
    final_output: str | None = None,
    error_message: str | None = None,
    checkpoint_data: dict[str, Any] | None = None,
    current_step_index: int | None = None,
    steps: list[dict[str, Any]] | None = None,
    intent: dict[str, Any] | None = None,
    plan: list[dict[str, Any]] | None = None,
) -> bool:
    terminal_states = (
        ExecutionStatus.COMPLETED,
        ExecutionStatus.FAILED,
        ExecutionStatus.ROLLED_BACK,
    )

    async with async_session_factory() as session:
        if status in terminal_states:
            values = {
                "status": status,
                "completed_at": utcnow(),
            }
            if final_output is not None:
                values["final_output"] = final_output
            if error_message is not None:
                values["error_message"] = error_message
            if checkpoint_data is not None:
                values["checkpoint_data"] = checkpoint_data
            if current_step_index is not None:
                values["current_step_index"] = current_step_index
            if steps is not None:
                values["steps"] = steps
            if intent is not None:
                values["intent"] = intent
            if plan is not None:
                values["plan"] = plan

            result = await session.execute(
                update(Execution)
                .where(
                    Execution.id == execution_id,
                    Execution.status.notin_(terminal_states),
                )
                .values(**values)
                .returning(Execution.id)
            )
            if hasattr(result, "scalar_one_or_none"):
                committed = result.scalar_one_or_none() is not None
            else:
                committed = getattr(result, "rowcount", 0) > 0

            if committed:
                execution = await session.get(Execution, execution_id)
                if execution is not None:
                    execution.status = status
                    execution.completed_at = utcnow()
                    if final_output is not None:
                        execution.final_output = final_output
                    if error_message is not None:
                        execution.error_message = error_message
                    if checkpoint_data is not None:
                        execution.checkpoint_data = checkpoint_data
                    if current_step_index is not None:
                        execution.current_step_index = current_step_index
                    if steps is not None:
                        execution.steps = steps
                    if intent is not None:
                        execution.intent = intent
                    if plan is not None:
                        execution.plan = plan
                await session.commit()
                return True

            await session.rollback()
            return False

        execution = await session.get(Execution, execution_id)
        if execution is None:
            return False
        execution.status = status
        if final_output is not None:
            execution.final_output = final_output
        if error_message is not None:
            execution.error_message = error_message
        if checkpoint_data is not None:
            execution.checkpoint_data = checkpoint_data
        if current_step_index is not None:
            execution.current_step_index = current_step_index
        if steps is not None:
            execution.steps = steps
        if intent is not None:
            execution.intent = intent
        if plan is not None:
            execution.plan = plan
        await session.commit()
        return True


async def run_execution(execution_id: uuid.UUID) -> None:
    async with async_session_factory() as session:
        execution = await session.get(Execution, execution_id)
        if execution is None:
            return
        workflow = await session.get(Workflow, execution.workflow_id)
        steps = await _build_steps(session, workflow)
        dag = workflow.dag_definition if workflow else None
        if execution.status in {
            ExecutionStatus.RUNNING,
            ExecutionStatus.WAITING_FOR_APPROVAL,
            ExecutionStatus.COMPLETED,
            ExecutionStatus.ROLLED_BACK,
        }:
            return

        result = await session.execute(
            update(Execution)
            .where(
                Execution.id == execution_id,
                Execution.status == execution.status,
            )
            .values(
                status=ExecutionStatus.RUNNING,
                current_step_index=0,
                error_message=None,
            )
        )
        await session.commit()
        if result.rowcount == 0:
            return

        execution.status = ExecutionStatus.RUNNING
        execution.current_step_index = 0
        execution.error_message = None

    workflow_plan = build_plan_from_workflow(workflow)
    plan_for_state: list[dict[str, Any]] = []
    if workflow_plan:
        normalized_plan = normalize_plan(
            {
                "goal": execution.user_input or "task",
                "risk": "",
                "steps": workflow_plan,
            }
        )
        if is_plan_invalid(normalized_plan):
            reason = str(normalized_plan.get("reason") or "plan_invalid")
            await audit_execution_event(
                execution_id=str(execution_id),
                action="plan_invalid",
                organization_id=execution.organization_id,
                user_id=execution.user_id,
                details={"reason": reason},
            )
            await _update_status(
                execution_id,
                ExecutionStatus.FAILED,
                error_message=f"plan_invalid: {reason}",
            )
            await publish_execution_event(
                str(execution_id),
                {
                    "event": "execution_failed",
                    "error": f"plan_invalid: {reason}",
                    "error_type": "plan_invalid",
                },
            )
            return
        plan_for_state = normalized_plan["steps"]

    initial_state = {
        "messages": _build_initial_messages(
            getattr(execution, "context_messages", None),
            execution.user_input,
        ),
        "current_step": 0,
        "execution_id": str(execution_id),
        "organization_id": (
            str(execution.organization_id) if execution.organization_id else None
        ),
        "user_id": (
            str(getattr(execution, "user_id", None))
            if getattr(execution, "user_id", None)
            else None
        ),
        "checkpoint": None,
        "user_input": execution.user_input or "",
        "final_output": None,
        "steps": steps,
        "plan": plan_for_state,
        "intent": getattr(execution, "intent", None) or {},
        "pending_approval": None,
        "node_outputs": {},
        "revision_count": 0,
        "revision_requested": False,
        "complexity": "simple",
        "llm_usage": [],
        "plan_meta": {},
        "budget_used": {},
        "budget_exceeded": False,
        "hard_stop": False,
        "approval_rejected": False,
        "side_effect_failure": False,
        "approved_plan_hash": None,
        "approved_approval_id": None,
        # —— 调度中心（二次装修新增）——
        "complexity_report": {},
        "routing_tier": "balanced",
        "clarifications_asked": 0,
        "clarification_request": None,
        "clarification_answer": None,
        "escalated_steps": {},
    }
    config = {"configurable": {"thread_id": str(execution_id)}, "recursion_limit": 100}

    try:
        async with get_checkpoint_manager() as manager:
            graph = build_graph(checkpointer=manager.saver, dag=dag)
            result = await graph.ainvoke(initial_state, config=config)
        interrupt_value = _interrupt_value(result)
        if interrupt_value is not _NO_INTERRUPT:
            await _update_status(
                execution_id,
                ExecutionStatus.WAITING_FOR_APPROVAL,
                checkpoint_data={"interrupt": interrupt_value},
                current_step_index=result.get("current_step"),
            )
            await _publish_approval_event(execution_id, interrupt_value, result)
            await publish_execution_event(
                str(execution_id),
                {"event": "waiting_for_approval", "checkpoint": interrupt_value},
            )
            return
        if result.get("approval_rejected"):
            await _update_status(
                execution_id,
                ExecutionStatus.FAILED,
                error_message=result.get("final_output") or "approval rejected",
            )
            await publish_execution_event(
                str(execution_id),
                {
                    "event": "execution_failed",
                    "error": result.get("final_output") or "approval rejected",
                    "error_type": "approval_rejected",
                },
            )
            return
        if result.get("budget_exceeded"):
            error_message = f"budget_exceeded: {result.get('final_output') or ''}"
            await _update_status(
                execution_id,
                ExecutionStatus.FAILED,
                final_output=result.get("final_output"),
                error_message=error_message,
            )
            await publish_execution_event(
                str(execution_id),
                {
                    "event": "execution_failed",
                    "error": error_message,
                    "error_type": "budget_exceeded",
                    "hard": bool(result.get("hard_stop")),
                },
            )
            return
        if result.get("side_effect_failure"):
            error_message = result.get("final_output") or "side_effect_failure"
            await _update_status(
                execution_id,
                ExecutionStatus.FAILED,
                final_output=result.get("final_output"),
                error_message=error_message,
            )
            await publish_execution_event(
                str(execution_id),
                {
                    "event": "execution_failed",
                    "error": error_message,
                    "error_type": "side_effect_failure",
                },
            )
            return
        await run_shadow_hook(execution, workflow, result.get("final_output"))
        terminal_committed = await _update_status(
            execution_id,
            ExecutionStatus.COMPLETED,
            final_output=result.get("final_output"),
            checkpoint_data={"llm_usage": result.get("llm_usage", [])},
            current_step_index=result.get("current_step"),
            intent=result.get("intent"),
            plan=(result.get("plan_meta") or {}).get("plan") or result.get("plan"),
            steps=[
                {
                    "role": step.get("role"),
                    "name": step.get("name"),
                    "agent_id": step.get("agent_id"),
                }
                for step in steps
            ],
        )
        await record_execution_usage(execution_id)
        if terminal_committed:
            await publish_execution_event(
                str(execution_id),
                {
                    "event": "execution_completed",
                    "final_output": result.get("final_output"),
                },
            )
        evaluate_execution_task.delay(str(execution_id))
    except GraphInterrupt as exc:
        await _update_status(
            execution_id,
            ExecutionStatus.WAITING_FOR_APPROVAL,
            checkpoint_data={"interrupt": exc.args[0] if exc.args else None},
        )
        await _publish_approval_event(
            execution_id,
            exc.args[0] if exc.args else None,
            {"plan": []},
        )
        await publish_execution_event(
            str(execution_id),
            {
                "event": "waiting_for_approval",
                "checkpoint": exc.args[0] if exc.args else None,
            },
        )
    except Exception as exc:
        if _is_retryable_exception(exc):
            await _update_status(
                execution_id,
                ExecutionStatus.PENDING,
                error_message=str(exc),
            )
            raise ExecutionRetryableError(str(exc)) from exc
        error_message = (
            f"plan_invalid: {exc}" if isinstance(exc, PlanInvalidError) else str(exc)
        )
        terminal_failed = await _update_status(
            execution_id,
            ExecutionStatus.FAILED,
            error_message=error_message,
        )
        if terminal_failed:
            await publish_execution_event(
                str(execution_id),
                {
                    "event": "execution_failed",
                    "error": error_message,
                    "error_type": (
                        "plan_invalid" if isinstance(exc, PlanInvalidError) else None
                    ),
                },
            )


async def resume_execution(execution_id: uuid.UUID, decision: dict[str, Any]) -> None:
    async with async_session_factory() as session:
        execution = await session.get(Execution, execution_id)
        if execution is None:
            return
        workflow = await session.get(Workflow, execution.workflow_id)
        dag = workflow.dag_definition if workflow else None
        execution.status = ExecutionStatus.RUNNING
        await session.commit()

    config = {"configurable": {"thread_id": str(execution_id)}, "recursion_limit": 100}

    try:
        async with get_checkpoint_manager() as manager:
            graph = build_graph(checkpointer=manager.saver, dag=dag)
            result = await graph.ainvoke(Command(resume=decision), config=config)
        interrupt_value = _interrupt_value(result)
        if interrupt_value is not _NO_INTERRUPT:
            await _update_status(
                execution_id,
                ExecutionStatus.WAITING_FOR_APPROVAL,
                checkpoint_data={"interrupt": interrupt_value},
                current_step_index=result.get("current_step"),
            )
            await publish_execution_event(
                str(execution_id),
                {"event": "waiting_for_approval", "checkpoint": interrupt_value},
            )
            return
        if result.get("approval_rejected"):
            await _update_status(
                execution_id,
                ExecutionStatus.FAILED,
                error_message=result.get("final_output") or "approval rejected",
            )
            await publish_execution_event(
                str(execution_id),
                {
                    "event": "execution_failed",
                    "error": result.get("final_output") or "approval rejected",
                    "error_type": "approval_rejected",
                },
            )
            return
        if result.get("budget_exceeded"):
            error_message = f"budget_exceeded: {result.get('final_output') or ''}"
            await _update_status(
                execution_id,
                ExecutionStatus.FAILED,
                final_output=result.get("final_output"),
                error_message=error_message,
            )
            await publish_execution_event(
                str(execution_id),
                {
                    "event": "execution_failed",
                    "error": error_message,
                    "error_type": "budget_exceeded",
                    "hard": bool(result.get("hard_stop")),
                },
            )
            return
        if result.get("side_effect_failure"):
            error_message = result.get("final_output") or "side_effect_failure"
            await _update_status(
                execution_id,
                ExecutionStatus.FAILED,
                final_output=result.get("final_output"),
                error_message=error_message,
            )
            await publish_execution_event(
                str(execution_id),
                {
                    "event": "execution_failed",
                    "error": error_message,
                    "error_type": "side_effect_failure",
                },
            )
            return
        terminal_committed = await _update_status(
            execution_id,
            ExecutionStatus.COMPLETED,
            final_output=result.get("final_output"),
            checkpoint_data={"llm_usage": result.get("llm_usage", [])},
            current_step_index=result.get("current_step"),
            intent=result.get("intent"),
            plan=(result.get("plan_meta") or {}).get("plan") or result.get("plan"),
        )
        await record_execution_usage(execution_id)
        if terminal_committed:
            await publish_execution_event(
                str(execution_id),
                {
                    "event": "execution_completed",
                    "final_output": result.get("final_output"),
                },
            )
    except GraphInterrupt as exc:
        await _update_status(
            execution_id,
            ExecutionStatus.WAITING_FOR_APPROVAL,
            checkpoint_data={"interrupt": exc.args[0] if exc.args else None},
        )
        await _publish_approval_event(
            execution_id,
            exc.args[0] if exc.args else None,
            {"plan": []},
        )
        await publish_execution_event(
            str(execution_id),
            {
                "event": "waiting_for_approval",
                "checkpoint": exc.args[0] if exc.args else None,
            },
        )
    except Exception as exc:
        if _is_retryable_exception(exc):
            await _update_status(
                execution_id,
                ExecutionStatus.PENDING,
                error_message=str(exc),
            )
            raise ExecutionRetryableError(str(exc)) from exc
        terminal_failed = await _update_status(
            execution_id,
            ExecutionStatus.FAILED,
            error_message=str(exc),
        )
        if terminal_failed:
            await publish_execution_event(
                str(execution_id),
                {"event": "execution_failed", "error": str(exc)},
            )

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.errors import GraphInterrupt
from langgraph.types import Command
from sqlalchemy import select, update

from app.config import settings
from app.core.billing import record_execution_usage
from app.database import async_session_factory
from app.engine.checkpoint import get_checkpoint_manager
from app.engine.event_bus import publish_execution_event
from app.engine.graph import build_graph
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
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
        return True
    text = str(exc).lower()
    return any(
        keyword in text
        for keyword in (
            "timeout",
            "timed out",
            "rate limit",
            "too many requests",
            "temporarily",
            "overloaded",
            "connection",
            "service unavailable",
            "server error",
        )
    )


def _interrupt_value(result: dict[str, Any]) -> Any:
    interrupts = result.get("__interrupt__") or []
    if not interrupts:
        return _NO_INTERRUPT
    first = interrupts[0]
    return getattr(first, "value", first)


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


async def _update_status(
    execution_id: uuid.UUID,
    status: ExecutionStatus,
    *,
    final_output: str | None = None,
    error_message: str | None = None,
    checkpoint_data: dict[str, Any] | None = None,
    current_step_index: int | None = None,
    steps: list[dict[str, Any]] | None = None,
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
        respect_workflow_steps = bool(
            not dag and _extract_agent_ids(workflow.agent_chain if workflow else [])
        )
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
        "respect_workflow_steps": respect_workflow_steps,
        "pending_approval": None,
        "node_outputs": {},
        "last_condition": False,
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
            await publish_execution_event(
                str(execution_id),
                {"event": "waiting_for_approval", "checkpoint": interrupt_value},
            )
            return
        await run_shadow_hook(execution, workflow, result.get("final_output"))
        terminal_committed = await _update_status(
            execution_id,
            ExecutionStatus.COMPLETED,
            final_output=result.get("final_output"),
            checkpoint_data={"llm_usage": result.get("llm_usage", [])},
            current_step_index=result.get("current_step"),
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
        terminal_committed = await _update_status(
            execution_id,
            ExecutionStatus.COMPLETED,
            final_output=result.get("final_output"),
            checkpoint_data={"llm_usage": result.get("llm_usage", [])},
            current_step_index=result.get("current_step"),
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

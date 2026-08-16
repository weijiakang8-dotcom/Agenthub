from __future__ import annotations

import uuid
from typing import Any

from langchain_core.messages import HumanMessage
from langgraph.errors import GraphInterrupt
from langgraph.types import Command
from sqlalchemy import update

from app.core.billing import record_execution_usage
from app.database import async_session_factory
from app.engine.checkpoint import get_checkpoint_manager
from app.engine.event_bus import publish_execution_event
from app.engine.graph import build_graph
from app.engine.tasks import evaluate_execution_task
from app.models import Agent, Execution, Workflow, utcnow
from app.models.enums import ExecutionStatus

ROLES = ["research", "analyze", "execute"]
_NO_INTERRUPT = object()


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
) -> None:
    async with async_session_factory() as session:
        execution = await session.get(Execution, execution_id)
        if execution is None:
            return
        execution.status = status
        if final_output is not None:
            execution.final_output = final_output
        if error_message is not None:
            execution.error_message = error_message
        if checkpoint_data is not None:
            execution.checkpoint_data = checkpoint_data
        if status in (
            ExecutionStatus.COMPLETED,
            ExecutionStatus.FAILED,
            ExecutionStatus.ROLLED_BACK,
        ):
            execution.completed_at = utcnow()
        await session.commit()


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

    initial_state = {
        "messages": [HumanMessage(content=execution.user_input or "")],
        "current_step": 0,
        "execution_id": str(execution_id),
        "organization_id": (
            str(execution.organization_id) if execution.organization_id else None
        ),
        "checkpoint": None,
        "user_input": execution.user_input or "",
        "final_output": None,
        "steps": steps,
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
            )
            await publish_execution_event(
                str(execution_id),
                {"event": "waiting_for_approval", "checkpoint": interrupt_value},
            )
            return
        await _update_status(
            execution_id,
            ExecutionStatus.COMPLETED,
            final_output=result.get("final_output"),
        )
        await record_execution_usage(execution_id)
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
    except Exception as exc:  # noqa: BLE001
        await _update_status(
            execution_id,
            ExecutionStatus.FAILED,
            error_message=str(exc),
        )
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
            )
            await publish_execution_event(
                str(execution_id),
                {"event": "waiting_for_approval", "checkpoint": interrupt_value},
            )
            return
        await _update_status(
            execution_id,
            ExecutionStatus.COMPLETED,
            final_output=result.get("final_output"),
        )
        await record_execution_usage(execution_id)
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
    except Exception as exc:  # noqa: BLE001
        await _update_status(
            execution_id,
            ExecutionStatus.FAILED,
            error_message=str(exc),
        )
        await publish_execution_event(
            str(execution_id),
            {"event": "execution_failed", "error": str(exc)},
        )

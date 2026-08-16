from __future__ import annotations

import asyncio
import uuid
from typing import Any

from app.database import async_session_factory
from app.engine.event_bus import publish_execution_event
from app.engine.tool_registry import get_tool
from app.models import Execution, ToolCall, utcnow
from app.models.enums import ToolCallStatus


async def create_tool_call(
    tool_name: str,
    params: dict[str, Any],
    execution_id: str | uuid.UUID,
    *,
    requires_approval: bool = False,
) -> ToolCall:
    """创建 pending 状态的 ToolCall 审计记录。"""
    async with async_session_factory() as session:
        execution = await session.get(Execution, uuid.UUID(str(execution_id)))
        tool_call = ToolCall(
            execution_id=uuid.UUID(str(execution_id)),
            tool_name=tool_name,
            input_params=params or {},
            status=ToolCallStatus.PENDING,
            requires_approval=requires_approval,
            organization_id=execution.organization_id if execution else None,
        )
        session.add(tool_call)
        await session.commit()
        await session.refresh(tool_call)
        return tool_call


async def _finish_tool_call(
    tool_call_id: uuid.UUID, result: dict[str, Any]
) -> ToolCall:
    async with async_session_factory() as session:
        tool_call = await session.get(ToolCall, tool_call_id)
        if tool_call is None:
            raise RuntimeError(f"ToolCall {tool_call_id} not found")

        tool_call.output_result = result
        tool_call.status = (
            ToolCallStatus.SUCCESS
            if result.get("status") == "success"
            else ToolCallStatus.FAILED
        )
        tool_call.completed_at = utcnow()
        await session.commit()
        await session.refresh(tool_call)
        return tool_call


async def mark_tool_call_rejected(
    tool_call_id: uuid.UUID, operator: str | None = None
) -> ToolCall:
    async with async_session_factory() as session:
        tool_call = await session.get(ToolCall, tool_call_id)
        if tool_call is None:
            raise RuntimeError(f"ToolCall {tool_call_id} not found")

        tool_call.status = ToolCallStatus.REJECTED
        tool_call.approved_by = operator or "anonymous"
        tool_call.output_result = {
            "status": "rejected",
            "data": None,
            "error": "Rejected by human",
        }
        tool_call.completed_at = utcnow()
        await session.commit()
        await session.refresh(tool_call)
        return tool_call


async def _invoke_with_retry(tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
    spec = get_tool(tool_name)
    if spec is None:
        return {
            "status": "failed",
            "data": None,
            "error": f"Unknown tool: {tool_name}",
        }

    last_error: Exception | None = None
    for attempt in range(3):
        try:
            result = await asyncio.wait_for(spec.handler(params), timeout=spec.timeout)
            if not isinstance(result, dict):
                result = {"status": "success", "data": result, "error": None}
            return result
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt < 2:
                await asyncio.sleep(2**attempt)

    return {
        "status": "failed",
        "data": None,
        "error": str(last_error or "tool execution failed"),
    }


async def execute_tool(
    tool_name: str,
    params: dict[str, Any],
    execution_id: str | uuid.UUID,
) -> dict[str, Any]:
    """执行工具并写入完整审计记录。"""
    spec = get_tool(tool_name)
    tool_call = await create_tool_call(
        tool_name,
        params,
        execution_id,
        requires_approval=bool(spec and spec.requires_approval),
    )

    async with async_session_factory() as session:
        record = await session.get(ToolCall, tool_call.id)
        if record is not None:
            record.started_at = utcnow()
            await session.commit()

    await publish_execution_event(
        str(execution_id),
        {
            "event": "tool_call_started",
            "tool_call_id": str(tool_call.id),
            "tool": tool_name,
            "params": params,
        },
    )
    result = await _invoke_with_retry(tool_name, params)
    await publish_execution_event(
        str(execution_id),
        {
            "event": "tool_call_completed",
            "tool_call_id": str(tool_call.id),
            "tool": tool_name,
            "status": result.get("status"),
            "result": result,
        },
    )
    await _finish_tool_call(tool_call.id, result)
    return result


async def execute_pending_tool_call(tool_call_id: uuid.UUID) -> dict[str, Any]:
    """执行一个已存在且待审批的 ToolCall 记录。"""
    async with async_session_factory() as session:
        tool_call = await session.get(ToolCall, tool_call_id)
        if tool_call is None:
            return {"status": "failed", "data": None, "error": "ToolCall not found"}

        tool_name = tool_call.tool_name
        params = tool_call.input_params or {}
        tool_call.started_at = utcnow()
        await session.commit()

    await publish_execution_event(
        str(tool_call.execution_id),
        {
            "event": "tool_call_started",
            "tool_call_id": str(tool_call_id),
            "tool": tool_name,
            "params": params,
        },
    )
    result = await _invoke_with_retry(tool_name, params)
    await publish_execution_event(
        str(tool_call.execution_id),
        {
            "event": "tool_call_completed",
            "tool_call_id": str(tool_call_id),
            "tool": tool_name,
            "status": result.get("status"),
            "result": result,
        },
    )
    await _finish_tool_call(tool_call_id, result)
    return result

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from app.api.deps import SessionDep, get_current_user
from app.core.alerting import evaluate_alert_rules
from app.core.telemetry import get_meter, get_tracer
from app.engine.tasks import execute_workflow_task, resume_workflow_task
from app.models import Execution, ToolCall, Workflow, utcnow
from app.models import InterventionLog
from app.models.enums import ExecutionStatus
from app.schemas.execution import (
    ExecutionAccepted,
    ExecutionCreate,
    ExecutionDetail,
    ExecutionRead,
    ExecutionResume,
    ExecutionTrace,
    FeedbackCreate,
)
from app.schemas.tool_call import ToolCallRead, ToolCallSummary
from pydantic import BaseModel


router = APIRouter(prefix="/executions", tags=["executions"])

tracer = get_tracer("agenthub.api")
execution_counter = get_meter("agenthub.api").create_counter(
    "execution.started.total",
    description="Total number of executions started",
)


class InterveneRequest(BaseModel):
    operator: str = "admin"
    action: str
    modified_plan: str | None = None


@router.get("", response_model=list[ExecutionRead])
async def list_executions(
    session: SessionDep,
    workflow_id: uuid.UUID | None = None,
    status: ExecutionStatus | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[Execution]:
    stmt = select(Execution)
    if workflow_id is not None:
        stmt = stmt.where(Execution.workflow_id == workflow_id)
    if status is not None:
        stmt = stmt.where(Execution.status == status)
    stmt = stmt.order_by(Execution.created_at.desc()).offset(skip).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.get("/{execution_id}", response_model=ExecutionDetail)
async def get_execution(execution_id: uuid.UUID, session: SessionDep) -> ExecutionDetail:
    execution = await session.get(Execution, execution_id)
    if execution is None:
        raise HTTPException(status_code=404, detail="Execution not found")

    detail = ExecutionDetail.model_validate(execution)
    result = await session.execute(
        select(ToolCall)
        .where(ToolCall.execution_id == execution_id)
        .order_by(ToolCall.started_at)
    )
    detail.tool_calls = [ToolCallRead.model_validate(tc) for tc in result.scalars().all()]
    return detail


@router.post(
    "",
    response_model=ExecutionAccepted,
    status_code=202,
    dependencies=[Depends(get_current_user)],
)
async def create_execution(
    payload: ExecutionCreate, session: SessionDep
) -> ExecutionAccepted:
    with tracer.start_as_current_span("create_execution") as span:
        span.set_attribute("workflow_id", str(payload.workflow_id))
        span.set_attribute("user_input_length", len(payload.user_input))

        workflow = await session.get(Workflow, payload.workflow_id)
        if workflow is None:
            raise HTTPException(status_code=404, detail="Workflow not found")

        execution = Execution(
            workflow_id=payload.workflow_id,
            user_input=payload.user_input,
            status=ExecutionStatus.PENDING,
            current_step_index=0,
        )
        session.add(execution)
        await session.commit()
        await session.refresh(execution)

        execute_workflow_task.delay(str(execution.id))
        execution_counter.add(1, {"workflow_id": str(payload.workflow_id)})

        return ExecutionAccepted(
            execution_id=execution.id, status=ExecutionStatus.PENDING
        )


@router.post(
    "/{execution_id}/cancel",
    response_model=ExecutionRead,
    dependencies=[Depends(get_current_user)],
)
async def cancel_execution(execution_id: uuid.UUID, session: SessionDep) -> Execution:
    execution = await session.get(Execution, execution_id)
    if execution is None:
        raise HTTPException(status_code=404, detail="Execution not found")

    if execution.status in (
        ExecutionStatus.COMPLETED,
        ExecutionStatus.FAILED,
        ExecutionStatus.ROLLED_BACK,
    ):
        raise HTTPException(status_code=409, detail="Execution already finished")

    execution.status = ExecutionStatus.FAILED
    execution.error_message = "Cancelled by user"
    execution.completed_at = utcnow()
    await session.commit()
    await session.refresh(execution)
    return execution


@router.get("/{execution_id}/trace", response_model=ExecutionTrace)
async def get_execution_trace(
    execution_id: uuid.UUID, session: SessionDep
) -> ExecutionTrace:
    execution = await session.get(Execution, execution_id)
    if execution is None:
        raise HTTPException(status_code=404, detail="Execution not found")

    result = await session.execute(
        select(ToolCall)
        .where(ToolCall.execution_id == execution_id)
        .order_by(ToolCall.started_at)
    )
    tool_calls = [ToolCallSummary.model_validate(tc) for tc in result.scalars().all()]
    return ExecutionTrace(
        current_step_index=execution.current_step_index,
        status=execution.status,
        tool_calls=tool_calls,
    )


@router.get("/{execution_id}/status", response_model=ExecutionRead)
async def get_execution_status(
    execution_id: uuid.UUID, session: SessionDep
) -> Execution:
    execution = await session.get(Execution, execution_id)
    if execution is None:
        raise HTTPException(status_code=404, detail="Execution not found")
    return execution


@router.post(
    "/{execution_id}/resume",
    response_model=ExecutionAccepted,
    status_code=202,
    dependencies=[Depends(get_current_user)],
)
async def resume_execution(
    execution_id: uuid.UUID, payload: ExecutionResume, session: SessionDep
) -> ExecutionAccepted:
    execution = await session.get(Execution, execution_id)
    if execution is None:
        raise HTTPException(status_code=404, detail="Execution not found")
    if execution.status != ExecutionStatus.WAITING_FOR_APPROVAL:
        raise HTTPException(
            status_code=409, detail="Execution is not waiting for approval"
        )

    resume_workflow_task.delay(str(execution_id), payload.model_dump())
    execution.status = ExecutionStatus.RUNNING
    await session.commit()

    return ExecutionAccepted(execution_id=execution_id, status=ExecutionStatus.RUNNING)


@router.post(
    "/{execution_id}/feedback",
    response_model=ExecutionRead,
    dependencies=[Depends(get_current_user)],
)
async def submit_feedback(
    execution_id: uuid.UUID, payload: FeedbackCreate, session: SessionDep
) -> Execution:
    execution = await session.get(Execution, execution_id)
    if execution is None:
        raise HTTPException(status_code=404, detail="Execution not found")

    execution.feedback = payload.feedback
    await session.commit()
    await session.refresh(execution)
    return execution


@router.post("/{execution_id}/intervene", dependencies=[Depends(get_current_user)])
async def intervene(
    execution_id: uuid.UUID, payload: InterveneRequest, session: SessionDep
) -> dict:
    execution = await session.get(Execution, execution_id)
    if execution is None:
        raise HTTPException(status_code=404, detail="Execution not found")

    log = InterventionLog(
        execution_id=execution_id,
        operator=payload.operator,
        action=payload.action,
        modified_plan=payload.modified_plan,
    )
    session.add(log)

    if payload.action == "terminate":
        execution.status = ExecutionStatus.FAILED
        execution.error_message = "终止任务"
        execution.completed_at = utcnow()
    else:
        resume_workflow_task.delay(
            str(execution_id),
            {"approved": True, "comment": payload.modified_plan or ""},
        )
    await session.commit()
    return {"status": "ok", "action": payload.action}


@router.get("/{execution_id}/interventions")
async def list_interventions(execution_id: uuid.UUID, session: SessionDep) -> list[dict]:
    logs = (
        await session.execute(
            select(InterventionLog)
            .where(InterventionLog.execution_id == execution_id)
            .order_by(InterventionLog.created_at)
        )
    ).scalars().all()
    return [
        {
            "id": str(log.id),
            "operator": log.operator,
            "action": log.action,
            "modified_plan": log.modified_plan,
            "created_at": log.created_at.isoformat(),
        }
        for log in logs
    ]

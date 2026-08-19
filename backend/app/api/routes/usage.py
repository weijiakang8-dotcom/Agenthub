from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.deps import CurrentUserDep, SessionDep
from app.models import Execution

router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("")
async def usage(session: SessionDep, user: CurrentUserDep) -> dict:
    stmt = select(
        func.count(Execution.id),
        func.coalesce(func.sum(Execution.input_tokens), 0),
        func.coalesce(func.sum(Execution.output_tokens), 0),
        func.coalesce(func.sum(Execution.cost), 0),
        func.count(Execution.id).filter(Execution.cost.is_(None)),
    )
    if user.organization_id is not None:
        stmt = stmt.where(Execution.organization_id == user.organization_id)
    total_executions, total_input, total_output, total_cost, cost_unknown = (
        await session.execute(stmt)
    ).one()

    today = datetime.now(timezone.utc).date()
    day_stmt = select(
        func.coalesce(func.sum(Execution.input_tokens + Execution.output_tokens), 0),
        func.coalesce(func.sum(Execution.cost), 0),
    )
    if user.organization_id is not None:
        day_stmt = day_stmt.where(Execution.organization_id == user.organization_id)
    day_stmt = day_stmt.where(Execution.created_at >= today)
    today_tokens, today_cost = (await session.execute(day_stmt)).one()

    return {
        "total_executions": total_executions,
        "total_input_tokens": int(total_input),
        "total_output_tokens": int(total_output),
        "total_tokens": int(total_input) + int(total_output),
        "total_cost": float(total_cost or 0),
        "cost_unknown_executions": int(cost_unknown or 0),
        "today_tokens": int(today_tokens or 0),
        "today_cost": float(today_cost or 0),
    }

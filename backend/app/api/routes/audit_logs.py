from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import CurrentUserDep, SessionDep
from app.models import AuditLog


router = APIRouter(prefix="/audit-logs", tags=["audit-logs"])


@router.get("")
async def list_audit_logs(session: SessionDep, user: CurrentUserDep) -> list[dict]:
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(200)
    if user.organization_id is not None:
        stmt = stmt.where(AuditLog.organization_id == user.organization_id)
    result = await session.execute(stmt)
    return [
        {
            "id": str(log.id),
            "method": log.method,
            "path": log.path,
            "status_code": log.status_code,
            "details": log.details,
            "created_at": log.created_at.isoformat(),
        }
        for log in result.scalars().all()
    ]

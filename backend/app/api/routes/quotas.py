from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.api.deps import CurrentUserDep
from app.core.quota import quota_usage

router = APIRouter(prefix="/quotas", tags=["quotas"])


@router.get("")
async def get_quota_usage(user: CurrentUserDep) -> dict[str, Any]:
    """返回当前租户的预算与并发用量（只读）。"""
    return await quota_usage(
        str(user.organization_id) if user.organization_id else None
    )


__all__ = ["router"]

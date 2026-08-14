from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import decode_token
from app.database import get_db as _get_db
from app.models import User


logger = logging.getLogger(__name__)

if not settings.ADMIN_API_KEY:
    logger.warning(
        "ADMIN_API_KEY is not set; admin fallback authentication is disabled."
    )


SessionDep = Annotated[AsyncSession, Depends(_get_db)]


async def get_current_user(
    session: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> User:
    """优先解析 Bearer JWT，失败时允许 ADMIN_API_KEY 后备。"""
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ")
        payload = decode_token(token)
        if payload and payload.get("type") == "access" and payload.get("sub"):
            try:
                user = await session.get(User, uuid.UUID(str(payload["sub"])))
            except (ValueError, TypeError):
                user = None
            if user is not None and user.is_active:
                return user

    if settings.ADMIN_API_KEY and x_api_key == settings.ADMIN_API_KEY:
        return User(
            email="admin@local",
            full_name="Super Admin",
            role="admin",
            is_active=True,
            organization_id=None,
        )

    raise HTTPException(status_code=401, detail="Invalid or missing authentication")


CurrentUserDep = Annotated[User, Depends(get_current_user)]


async def get_current_org(user: CurrentUserDep) -> uuid.UUID | None:
    return user.organization_id


CurrentOrgDep = Annotated[uuid.UUID | None, Depends(get_current_org)]


def require_role(*roles: str):
    async def dependency(user: CurrentUserDep) -> User:
        if user.role not in roles and user.role != "admin":
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return dependency

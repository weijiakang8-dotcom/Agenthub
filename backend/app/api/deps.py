from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db as _get_db


SessionDep = Annotated[AsyncSession, Depends(_get_db)]


async def get_current_user(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> str:
    """从 X-API-Key 请求头读取 API Key，并与 ADMIN_API_KEY 比对。

    ADMIN_API_KEY 为空时视为开发环境，不校验；否则必须完全匹配。
    后续可替换为 JWT 等更完善的鉴权方式。
    """
    if settings.ADMIN_API_KEY and x_api_key != settings.ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return "admin" if x_api_key else "anonymous"


CurrentUserDep = Annotated[str, Depends(get_current_user)]

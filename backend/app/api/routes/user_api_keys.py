from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import CurrentUserDep, SessionDep
from app.core.security import encrypt_secret
from app.models import UserApiKey

router = APIRouter(prefix="/user-api-keys", tags=["user-api-keys"])


class UserApiKeyCreate(BaseModel):
    provider: str = Field(..., min_length=1, max_length=50)
    model: str = Field(..., min_length=1, max_length=100)
    base_url: str = Field(..., min_length=1, max_length=255)
    api_key: str = Field(..., min_length=1)


class UserApiKeyUpdate(BaseModel):
    is_active: bool


class UserApiKeyRotate(BaseModel):
    api_key: str = Field(..., min_length=1)


def _serialize(key: UserApiKey) -> dict:
    return {
        "id": str(key.id),
        "provider": key.provider,
        "model": key.model,
        "base_url": key.base_url,
        "api_key_masked": f"****{key.api_key_hint}",
        "is_active": key.is_active,
        "created_at": key.created_at,
    }


@router.get("")
async def list_keys(session: SessionDep, user: CurrentUserDep) -> list[dict]:
    result = await session.execute(
        select(UserApiKey)
        .where(UserApiKey.user_id == user.id)
        .order_by(UserApiKey.created_at)
    )
    return [_serialize(key) for key in result.scalars().all()]


@router.post("", status_code=201)
async def create_key(
    payload: UserApiKeyCreate, session: SessionDep, user: CurrentUserDep
) -> dict:
    key = UserApiKey(
        user_id=user.id,
        provider=payload.provider,
        model=payload.model,
        base_url=payload.base_url,
        api_key_encrypted=encrypt_secret(payload.api_key),
        api_key_hint=payload.api_key[-4:],
        is_active=True,
    )
    session.add(key)
    await session.commit()
    await session.refresh(key)
    return _serialize(key)


@router.put("/{key_id}")
async def update_key(
    key_id: uuid.UUID,
    payload: UserApiKeyUpdate,
    session: SessionDep,
    user: CurrentUserDep,
) -> dict:
    key = await session.get(UserApiKey, key_id)
    if key is None or key.user_id != user.id:
        raise HTTPException(status_code=404, detail="API key not found")
    key.is_active = payload.is_active
    await session.commit()
    await session.refresh(key)
    return _serialize(key)


@router.post("/{key_id}/rotate")
async def rotate_key(
    key_id: uuid.UUID,
    payload: UserApiKeyRotate,
    session: SessionDep,
    user: CurrentUserDep,
) -> dict:
    """轮换密钥：立即失效旧 secret，替换为新的加密 secret（保持同一行）。"""
    key = await session.get(UserApiKey, key_id)
    if key is None or key.user_id != user.id:
        raise HTTPException(status_code=404, detail="API key not found")
    key.api_key_encrypted = encrypt_secret(payload.api_key)
    key.api_key_hint = payload.api_key[-4:]
    key.is_active = True
    await session.commit()
    await session.refresh(key)
    return _serialize(key)


@router.delete("/{key_id}", status_code=204)
async def delete_key(
    key_id: uuid.UUID, session: SessionDep, user: CurrentUserDep
) -> None:
    key = await session.get(UserApiKey, key_id)
    if key is None or key.user_id != user.id:
        raise HTTPException(status_code=404, detail="API key not found")
    await session.delete(key)
    await session.commit()

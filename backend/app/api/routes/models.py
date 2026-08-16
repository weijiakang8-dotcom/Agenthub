from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import CurrentUserDep, SessionDep
from app.core.model_gateway import test_model
from app.core.permissions import require_permission
from app.models import ModelConfig

router = APIRouter(prefix="/models", tags=["models"])


class ModelCreate(BaseModel):
    name: str
    provider: str
    base_url: str
    api_key: str = ""
    model: str
    max_tokens: int = 4096
    cost_per_1k_tokens: float = 0.0
    is_default: bool = False


class ModelUpdate(BaseModel):
    name: str | None = None
    provider: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None
    max_tokens: int | None = None
    cost_per_1k_tokens: float | None = None
    is_active: bool | None = None
    is_default: bool | None = None


def _serialize(m: ModelConfig) -> dict:
    return {
        "id": str(m.id),
        "name": m.name,
        "provider": m.provider,
        "base_url": m.base_url,
        "model": m.model,
        "max_tokens": m.max_tokens,
        "cost_per_1k_tokens": m.cost_per_1k_tokens,
        "is_active": m.is_active,
        "is_default": m.is_default,
    }


@router.get("")
async def list_models(session: SessionDep, user: CurrentUserDep) -> list[dict]:
    stmt = select(ModelConfig)
    if user.organization_id is not None:
        stmt = stmt.where(ModelConfig.organization_id == user.organization_id)
    result = await session.execute(stmt.order_by(ModelConfig.created_at))
    return [_serialize(m) for m in result.scalars().all()]


@router.post(
    "",
    status_code=201,
    dependencies=[Depends(require_permission("models:manage"))],
)
async def create_model(
    payload: ModelCreate, session: SessionDep, user: CurrentUserDep
) -> dict:
    model = ModelConfig(
        organization_id=user.organization_id,
        **payload.model_dump(),
    )
    session.add(model)
    await session.commit()
    await session.refresh(model)
    return _serialize(model)


@router.put(
    "/{model_id}",
    dependencies=[Depends(require_permission("models:manage"))],
)
async def update_model(
    model_id: uuid.UUID,
    payload: ModelUpdate,
    session: SessionDep,
    user: CurrentUserDep,
) -> dict:
    model = await session.get(ModelConfig, model_id)
    if model is None or (
        user.organization_id is not None
        and model.organization_id != user.organization_id
    ):
        raise HTTPException(status_code=404, detail="Model not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(model, key, value)
    await session.commit()
    await session.refresh(model)
    return _serialize(model)


@router.post(
    "/{model_id}/test",
    dependencies=[Depends(require_permission("models:manage"))],
)
async def test_model_endpoint(
    model_id: uuid.UUID, session: SessionDep, user: CurrentUserDep
) -> dict:
    model = await session.get(ModelConfig, model_id)
    if model is None or (
        user.organization_id is not None
        and model.organization_id != user.organization_id
    ):
        raise HTTPException(status_code=404, detail="Model not found")
    return await test_model(model)

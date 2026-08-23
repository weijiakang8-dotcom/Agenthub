from __future__ import annotations

import uuid

import httpx
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


class ModelDiscoveryRequest(BaseModel):
    base_url: str = Field(..., min_length=1, max_length=255)
    api_key: str = Field(..., min_length=1)


class ModelConnectionTestRequest(ModelDiscoveryRequest):
    model: str = Field(..., min_length=1, max_length=100)


def _normalize_base_url(value: str) -> str:
    base_url = value.strip().rstrip("/")
    try:
        parsed = httpx.URL(base_url)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Base URL 格式无效") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.host:
        raise HTTPException(status_code=422, detail="Base URL 必须是 http/https 地址")
    return base_url


def _upstream_error(response: httpx.Response, *, model: str | None = None) -> str:
    try:
        payload = response.json()
        message = str((payload.get("error") or {}).get("message") or "")
    except Exception:  # noqa: BLE001
        message = ""
    if model:
        return f"模型 {model} 暂不可用（上游 HTTP {response.status_code}）" + (
            f"：{message}" if message else "，请换一个模型重试"
        )
    return f"模型服务连接失败（HTTP {response.status_code}）" + (
        f"：{message}" if message else ""
    )


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


@router.post("/discover-models")
async def discover_models(
    payload: ModelDiscoveryRequest,
    _user: CurrentUserDep,
) -> dict:
    """作为普通用户读取 OpenAI 兼容服务的 /models，避免手填/猜测模型 ID。"""
    base_url = _normalize_base_url(payload.base_url)
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            response = await client.get(
                f"{base_url}/models",
                headers={"Authorization": f"Bearer {payload.api_key}"},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"无法连接模型服务：{type(exc).__name__}",
        ) from exc
    if not response.is_success:
        raise HTTPException(
            status_code=422,
            detail=_upstream_error(response),
        )
    try:
        data = response.json()
        models = sorted(
            {
                str(item.get("id"))
                for item in data.get("data", [])
                if isinstance(item, dict) and item.get("id")
            }
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail="模型列表响应格式无效") from exc
    if not models:
        raise HTTPException(status_code=422, detail="服务未返回任何模型")
    return {"base_url": base_url, "models": models}


@router.post("/test-connection")
async def test_connection(
    payload: ModelConnectionTestRequest,
    _user: CurrentUserDep,
) -> dict:
    """用用户选定的模型发一次最小聊天请求，确认不是只列出但实际不可用。"""
    base_url = _normalize_base_url(payload.base_url)
    try:
        async with httpx.AsyncClient(timeout=90, follow_redirects=True) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {payload.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": payload.model,
                    "messages": [{"role": "user", "content": "只回复 OK"}],
                    "stream": False,
                },
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"模型连接失败：{type(exc).__name__}",
        ) from exc
    if not response.is_success:
        raise HTTPException(
            status_code=422,
            detail=_upstream_error(response, model=payload.model),
        )
    try:
        data = response.json()
        preview = str(
            (((data.get("choices") or [{}])[0].get("message") or {}).get("content"))
            or ""
        )[:120]
    except Exception as exc:
        raise HTTPException(status_code=422, detail="聊天响应格式无效") from exc
    return {"ok": True, "model": payload.model, "preview": preview}


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
        base_url=_normalize_base_url(payload.base_url),
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

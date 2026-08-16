from __future__ import annotations

import random
import uuid
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.api.deps import CurrentUserDep
from app.config import settings
from app.core.email import send_email
from app.core.rate_limit import rate_limit
from app.core.request_utils import get_client_ip
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.database import master_session_factory
from app.models import Organization, User, utcnow

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str = ""
    code: str = ""


class LoginRequest(BaseModel):
    email: str
    password: str
    code: str = ""


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    organization_id: uuid.UUID | None


class OrganizationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    settings: dict


class AuthResponse(BaseModel):
    user: UserRead
    organization: OrganizationRead
    access_token: str
    refresh_token: str


class RefreshResponse(BaseModel):
    access_token: str


class SendCodeRequest(BaseModel):
    email: str


async def _verify_code(email: str, code: str) -> bool:
    client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        key = f"auth:code:{email}"
        stored = await client.get(key)
        if not stored or stored != code:
            return False
        await client.delete(key)
        return True
    finally:
        await client.aclose()


async def _send_code(email: str) -> dict:
    code = f"{random.randint(0, 999999):06d}"
    client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        await client.set(f"auth:code:{email}", code, ex=300)
    finally:
        await client.aclose()
    result = await send_email(
        email,
        "AgentHub 登录验证码",
        f"你的验证码是：{code}，5 分钟内有效。",
    )
    return result


@router.post("/send-code")
async def send_code(payload: SendCodeRequest, request: Request) -> dict:
    email = payload.email.strip().lower()
    client_ip = get_client_ip(request)

    if not await rate_limit(f"send-code:email:{email}", limit=1, window_seconds=60):
        raise HTTPException(
            status_code=429, detail="Too many code requests for this email"
        )
    if not await rate_limit(f"send-code:ip:{client_ip}", limit=10, window_seconds=60):
        raise HTTPException(
            status_code=429, detail="Too many code requests from this IP"
        )

    result = await _send_code(email)
    if not result.get("ok"):
        raise HTTPException(
            status_code=502, detail=result.get("error") or "Failed to send code"
        )
    return {"status": "ok"}


@router.post("/register", response_model=AuthResponse, status_code=201)
async def register(payload: RegisterRequest) -> AuthResponse:
    email = payload.email.strip().lower()
    if len(payload.password) < 8:
        raise HTTPException(
            status_code=422, detail="Password must be at least 8 characters"
        )
    if not await _verify_code(email, payload.code):
        raise HTTPException(status_code=401, detail="Invalid verification code")

    async with master_session_factory() as session:
        existing = await session.execute(select(User).where(User.email == email))
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(status_code=409, detail="Email already registered")

        organization = Organization(
            name=payload.full_name or email,
            slug=f"org-{uuid.uuid4().hex[:10]}",
        )
        session.add(organization)
        await session.flush()

        user = User(
            email=email,
            password_hash=hash_password(payload.password),
            full_name=payload.full_name or email,
            organization_id=organization.id,
            role="admin",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        await session.refresh(organization)

        return AuthResponse(
            user=UserRead.model_validate(user),
            organization=OrganizationRead.model_validate(organization),
            access_token=create_access_token(user.id, organization.id),
            refresh_token=create_refresh_token(user.id, organization.id),
        )


@router.post("/login", response_model=AuthResponse)
async def login(payload: LoginRequest) -> AuthResponse:
    email = payload.email.strip().lower()
    if not await _verify_code(email, payload.code):
        raise HTTPException(status_code=401, detail="Invalid verification code")
    async with master_session_factory() as session:
        user = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if user is None or not verify_password(payload.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid email or password")
        if not user.is_active:
            raise HTTPException(status_code=403, detail="User is inactive")

        user.last_login = utcnow()
        await session.commit()

        organization = (
            await session.get(Organization, user.organization_id)
            if user.organization_id
            else None
        )

        return AuthResponse(
            user=UserRead.model_validate(user),
            organization=OrganizationRead.model_validate(organization),
            access_token=create_access_token(user.id, user.organization_id),
            refresh_token=create_refresh_token(user.id, user.organization_id),
        )


@router.post("/refresh", response_model=RefreshResponse)
async def refresh(
    authorization: Annotated[str | None, Header()] = None,
) -> RefreshResponse:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing refresh token")
    payload = decode_token(authorization.removeprefix("Bearer "))
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user_id = uuid.UUID(str(payload["sub"]))
    async with master_session_factory() as session:
        user = await session.get(User, user_id)
        if user is None or not user.is_active:
            raise HTTPException(status_code=401, detail="User not found")
        return RefreshResponse(
            access_token=create_access_token(user.id, user.organization_id)
        )


@router.post("/logout")
async def logout() -> dict:
    # JWT 无状态，前端删除 token 即可。
    return {"status": "ok"}


@router.get("/me", response_model=UserRead)
async def me(user: CurrentUserDep) -> UserRead:
    return UserRead.model_validate(user)

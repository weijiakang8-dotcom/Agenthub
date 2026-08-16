from __future__ import annotations

import random
import re
import uuid
from typing import Annotated, Literal

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
    TokenExpiredError,
    TokenInvalidError,
    create_access_token,
    create_refresh_token,
    decode_token_checked,
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
    mode: Literal["login", "register"] | None = None


class ForgotPasswordRequest(BaseModel):
    email: str


class VerifyResetCodeRequest(BaseModel):
    email: str
    code: str


class ResetPasswordRequest(BaseModel):
    email: str
    code: str
    new_password: str


_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
CODE_TTL = 300
CODE_MAX_ATTEMPTS = 5
RESET_CODE_TTL = 600
RESET_MAX_ATTEMPTS = 5


def auth_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def _validate_email(email: str) -> str:
    normalized = email.strip().lower()
    if not _EMAIL_RE.match(normalized):
        raise auth_error(422, "AUTH_001", "邮箱格式不正确")
    return normalized


def _code_key(email: str, mode: str = "") -> str:
    if mode in {"login", "register"}:
        return f"auth:code:{mode}:{email}"
    return f"auth:code:{email}"


def _code_attempt_key(email: str, mode: str = "") -> str:
    return f"auth:code-attempt:{mode or 'legacy'}:{email}"


async def _verify_code(email: str, code: str, mode: str = "") -> bool:
    client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        key = _code_key(email, mode)
        stored = await client.get(key)
        if not stored or stored != code:
            attempt_key = _code_attempt_key(email, mode)
            attempts = await client.incr(attempt_key)
            if attempts == 1:
                await client.expire(attempt_key, CODE_TTL)
            if attempts >= CODE_MAX_ATTEMPTS:
                await client.delete(key)
                await client.delete(attempt_key)
            return False
        await client.delete(key)
        await client.delete(_code_attempt_key(email, mode))
        return True
    finally:
        await client.aclose()


async def _send_code(email: str, mode: str = "") -> dict:
    code = f"{random.randint(0, 999999):06d}"
    key = _code_key(email, mode)
    client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        await client.set(key, code, ex=CODE_TTL)
    finally:
        await client.aclose()
    result = await send_email(
        email,
        "AgentHub 登录验证码",
        f"你的验证码是：{code}，5 分钟内有效。",
    )
    if not result.get("ok"):
        cleanup = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            await cleanup.delete(key)
        finally:
            await cleanup.aclose()
    return result


async def _email_exists(email: str) -> bool:
    async with master_session_factory() as session:
        existing = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        return existing is not None


def _reset_code_key(email: str) -> str:
    return f"auth:reset-code:{email}"


def _reset_attempt_key(email: str) -> str:
    return f"auth:reset-attempt:{email}"


async def _save_reset_code(email: str, code: str) -> None:
    client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        await client.set(_reset_code_key(email), code, ex=RESET_CODE_TTL)
        await client.delete(_reset_attempt_key(email))
    finally:
        await client.aclose()


async def _verify_reset_code(email: str, code: str, consume: bool = False) -> bool:
    client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        stored = await client.get(_reset_code_key(email))
        if stored is None or stored != code:
            attempts = await client.incr(_reset_attempt_key(email))
            if attempts == 1:
                await client.expire(_reset_attempt_key(email), RESET_CODE_TTL)
            if attempts >= RESET_MAX_ATTEMPTS:
                await client.delete(_reset_code_key(email))
                await client.delete(_reset_attempt_key(email))
            return False
        if consume:
            await client.delete(_reset_code_key(email))
            await client.delete(_reset_attempt_key(email))
        return True
    finally:
        await client.aclose()


async def _send_reset_code(email: str) -> dict:
    code = f"{random.randint(0, 999999):06d}"
    await _save_reset_code(email, code)
    result = await send_email(
        email,
        "AgentHub 重置密码验证码",
        f"你的验证码是：{code}，10 分钟内有效。",
    )
    if not result.get("ok"):
        client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            await client.delete(_reset_code_key(email))
            await client.delete(_reset_attempt_key(email))
        finally:
            await client.aclose()
    return result


async def _set_user_password(email: str, new_password: str) -> bool:
    async with master_session_factory() as session:
        user = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if user is None:
            return False
        user.password_hash = hash_password(new_password)
        user.password_changed_at = utcnow()
        await session.commit()
        return True


@router.post("/send-code")
async def send_code(payload: SendCodeRequest, request: Request) -> dict:
    email = _validate_email(payload.email)
    client_ip = get_client_ip(request)
    mode = payload.mode or ""

    if not await rate_limit(f"send-code:email:{email}", limit=1, window_seconds=60):
        raise auth_error(429, "AUTH_001", "验证码请求过于频繁，请稍后再试")
    if not await rate_limit(f"send-code:ip:{client_ip}", limit=10, window_seconds=60):
        raise auth_error(429, "AUTH_001", "验证码请求过于频繁，请稍后再试")

    if mode == "register":
        if await _email_exists(email):
            raise auth_error(
                409, "EMAIL_ALREADY_EXISTS", "邮箱已被注册，请直接登录或找回密码"
            )
        result = await _send_code(email, mode)
        if not result.get("ok"):
            raise auth_error(502, "AUTH_001", "验证码发送失败，请稍后再试")
    elif mode == "login":
        # 登录模式不暴露邮箱是否已注册：仅对已注册邮箱真实发送验证码。
        if await _email_exists(email):
            result = await _send_code(email, mode)
            if not result.get("ok"):
                raise auth_error(502, "AUTH_001", "验证码发送失败，请稍后再试")
    else:
        # 兼容未携带 mode 的旧调用方。
        result = await _send_code(email, mode)
        if not result.get("ok"):
            raise auth_error(502, "AUTH_001", "验证码发送失败，请稍后再试")
    return {"status": "ok"}


@router.post("/register", response_model=AuthResponse, status_code=201)
async def register(payload: RegisterRequest) -> AuthResponse:
    email = _validate_email(payload.email)
    if len(payload.password) < 8:
        raise auth_error(422, "INVALID_PASSWORD", "密码长度不足，请输入至少8位密码")

    if await _email_exists(email):
        raise auth_error(
            409, "EMAIL_ALREADY_EXISTS", "邮箱已被注册，请直接登录或找回密码"
        )

    if not await _verify_code(email, payload.code, "register"):
        raise auth_error(401, "INVALID_VERIFY_CODE", "验证码错误，请重新输入")

    async with master_session_factory() as session:
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
    email = _validate_email(payload.email)
    if not await _verify_code(email, payload.code, "login"):
        raise auth_error(401, "INVALID_VERIFY_CODE", "验证码错误，请重新输入")
    async with master_session_factory() as session:
        user = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if user is None or not verify_password(payload.password, user.password_hash):
            raise auth_error(401, "INVALID_PASSWORD", "账号或密码错误，请检查后重试")
        if not user.is_active:
            raise auth_error(403, "AUTH_001", "账号已停用，请联系管理员")

        user.last_login = utcnow()
        await session.commit()

        if user.organization_id is None:
            raise auth_error(500, "AUTH_001", "登录失败，请稍后再试")
        organization = await session.get(Organization, user.organization_id)
        if organization is None:
            raise auth_error(500, "AUTH_001", "登录失败，请稍后再试")

        return AuthResponse(
            user=UserRead.model_validate(user),
            organization=OrganizationRead.model_validate(organization),
            access_token=create_access_token(user.id, user.organization_id),
            refresh_token=create_refresh_token(user.id, user.organization_id),
        )


@router.post("/forgot-password")
async def forgot_password(payload: ForgotPasswordRequest, request: Request) -> dict:
    email = _validate_email(payload.email)
    client_ip = get_client_ip(request)

    if not await rate_limit(
        f"forgot-password:email:{email}", limit=1, window_seconds=60
    ):
        raise auth_error(429, "AUTH_001", "请求过于频繁，请稍后再试")
    if not await rate_limit(
        f"forgot-password:ip:{client_ip}", limit=10, window_seconds=60
    ):
        raise auth_error(429, "AUTH_001", "请求过于频繁，请稍后再试")

    # 无论邮箱是否注册都返回相同提示，避免邮箱枚举。
    if await _email_exists(email):
        result = await _send_reset_code(email)
        if not result.get("ok"):
            # 邮件发送失败也保持通用提示，避免暴露内部状态。
            return {"success": True, "message": "如果该邮箱已注册，我们会发送验证码"}

    return {"success": True, "message": "如果该邮箱已注册，我们会发送验证码"}


@router.post("/verify-reset-code")
async def verify_reset_code(payload: VerifyResetCodeRequest) -> dict:
    email = _validate_email(payload.email)
    ok = await _verify_reset_code(email, payload.code, consume=False)
    if ok:
        return {"success": True, "message": "验证码正确"}
    return {"success": False, "message": "验证码错误或已过期"}


@router.post("/reset-password")
async def reset_password(payload: ResetPasswordRequest) -> dict:
    email = _validate_email(payload.email)
    if len(payload.new_password) < 8:
        raise auth_error(422, "INVALID_PASSWORD", "密码长度不足，请输入至少8位密码")

    if not await _verify_reset_code(email, payload.code, consume=True):
        raise auth_error(401, "INVALID_VERIFY_CODE", "验证码错误或已过期")

    updated = await _set_user_password(email, payload.new_password)
    if not updated:
        raise auth_error(400, "PASSWORD_RESET_FAILED", "密码重置失败，请稍后再试")

    return {"success": True, "message": "密码修改成功，请重新登录"}


@router.post("/refresh", response_model=RefreshResponse)
async def refresh(
    authorization: Annotated[str | None, Header()] = None,
) -> RefreshResponse:
    if not authorization or not authorization.startswith("Bearer "):
        raise auth_error(401, "INVALID_REFRESH_TOKEN", "缺少刷新令牌")

    token = authorization.removeprefix("Bearer ")
    try:
        payload = decode_token_checked(token)
    except TokenExpiredError:
        raise auth_error(401, "REFRESH_TOKEN_EXPIRED", "刷新令牌已过期，请重新登录")
    except TokenInvalidError:
        raise auth_error(401, "INVALID_REFRESH_TOKEN", "刷新令牌无效")

    if payload.get("type") != "refresh":
        raise auth_error(401, "INVALID_REFRESH_TOKEN", "刷新令牌无效")

    try:
        user_id = uuid.UUID(str(payload.get("sub")))
    except (ValueError, TypeError):
        raise auth_error(401, "INVALID_REFRESH_TOKEN", "刷新令牌无效")

    async with master_session_factory() as session:
        user = await session.get(User, user_id)
        if user is None or not user.is_active:
            raise auth_error(401, "INVALID_REFRESH_TOKEN", "用户不存在或已停用")
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

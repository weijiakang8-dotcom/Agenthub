import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.core.auth import create_access_token, hash_password, verify_password
from app.database import master_session_factory
from app.models import Organization, User, utcnow

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str = ""


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    organization_id: str | None


@router.post("/register", response_model=TokenResponse)
async def register(payload: RegisterRequest) -> TokenResponse:
    async with master_session_factory() as session:
        existing = await session.execute(select(User).where(User.email == payload.email))
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(status_code=409, detail="Email already registered")

        organization = Organization(name=f"{payload.email} 的组织", slug=f"org-{uuid.uuid4().hex[:8]}")
        session.add(organization)
        await session.flush()

        user = User(
            email=payload.email,
            password_hash=hash_password(payload.password),
            full_name=payload.full_name,
            organization_id=organization.id,
            role="admin",
        )
        session.add(user)
        await session.commit()
        token = create_access_token(user.id, organization.id)
        return TokenResponse(access_token=token, organization_id=str(organization.id))


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest) -> TokenResponse:
    async with master_session_factory() as session:
        user = (
            await session.execute(select(User).where(User.email == payload.email))
        ).scalar_one_or_none()
        if user is None or not verify_password(payload.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid email or password")
        user.last_login = utcnow()
        await session.commit()
        token = create_access_token(user.id, user.organization_id)
        return TokenResponse(
            access_token=token,
            organization_id=str(user.organization_id) if user.organization_id else None,
        )

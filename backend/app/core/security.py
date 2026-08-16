from __future__ import annotations

import hashlib
import hmac
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from app.config import settings

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE = timedelta(hours=24)
REFRESH_TOKEN_EXPIRE = timedelta(days=7)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$", 1)
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), 100_000
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except Exception:  # noqa: BLE001
        return False


def _encode_token(payload: dict[str, Any], expires_delta: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {**payload, "iat": now, "exp": now + expires_delta}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=ALGORITHM)


def create_access_token(
    user_id: str | uuid.UUID, organization_id: str | uuid.UUID | None
) -> str:
    return _encode_token(
        {
            "sub": str(user_id),
            "org": str(organization_id) if organization_id else None,
            "type": "access",
        },
        ACCESS_TOKEN_EXPIRE,
    )


def create_refresh_token(
    user_id: str | uuid.UUID, organization_id: str | uuid.UUID | None
) -> str:
    return _encode_token(
        {
            "sub": str(user_id),
            "org": str(organization_id) if organization_id else None,
            "type": "refresh",
        },
        REFRESH_TOKEN_EXPIRE,
    )


def decode_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[ALGORITHM])
    except Exception:  # noqa: BLE001
        return None

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.core import security
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip():
    hashed = hash_password("password123")
    assert verify_password("password123", hashed)
    assert not verify_password("wrong-password", hashed)


def test_access_token_roundtrip():
    token = create_access_token("user-1", "org-1")
    payload = decode_token(token)
    assert payload["sub"] == "user-1"
    assert payload["org"] == "org-1"
    assert payload["type"] == "access"


def test_refresh_token_roundtrip():
    token = create_refresh_token("user-1", "org-1")
    payload = decode_token(token)
    assert payload["type"] == "refresh"
    assert payload["jti"]
    assert payload["family"]


def test_token_expiry_policies():
    assert security.ACCESS_TOKEN_EXPIRE == timedelta(minutes=30)
    assert security.REFRESH_TOKEN_EXPIRE == timedelta(days=7)


def test_decode_token_checked_distinguishes_expired():
    now = datetime.now(timezone.utc)
    expired = jwt.encode(
        {
            "sub": "user-1",
            "type": "refresh",
            "iat": now,
            "exp": now - timedelta(seconds=1),
        },
        security.settings.JWT_SECRET_KEY,
        algorithm="HS256",
    )

    with pytest.raises(security.TokenExpiredError):
        security.decode_token_checked(expired)


def test_decode_token_checked_rejects_invalid():
    with pytest.raises(security.TokenInvalidError):
        security.decode_token_checked("not-a-jwt")

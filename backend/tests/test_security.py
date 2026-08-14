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

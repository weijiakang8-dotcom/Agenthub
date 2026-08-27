from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Response
from starlette.requests import Request

from app.api.routes import auth
from app.core.security import create_refresh_token


def request(
    *, origin: str = "http://localhost:5173", token: str | None = None
) -> Request:
    headers = [(b"origin", origin.encode())]
    if token:
        headers.append((b"cookie", f"{auth.REFRESH_COOKIE_NAME}={token}".encode()))
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/auth/refresh",
            "headers": headers,
            "client": ("127.0.0.1", 1234),
            "scheme": "https",
            "server": ("testserver", 443),
        }
    )


class Session:
    def __init__(self):
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def commit(self):
        self.committed = True


def test_refresh_cookie_is_secure_in_staging(monkeypatch):
    monkeypatch.setattr(auth.settings, "ENVIRONMENT", "staging")
    response = Response()

    auth._set_refresh_cookie(response, "token")

    cookie = response.headers["set-cookie"]
    assert "Secure" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Path=/api/auth" in cookie


def test_web_refresh_rotates_httponly_cookie(monkeypatch):
    user = SimpleNamespace(id=uuid.uuid4(), organization_id=uuid.uuid4())
    original = create_refresh_token(user.id, user.organization_id)
    replacement = create_refresh_token(user.id, user.organization_id)
    session = Session()

    async def rotate(_session, token):
        assert token == original
        return replacement, user

    monkeypatch.setattr(auth, "rotate_refresh_session", rotate)
    monkeypatch.setattr(auth, "master_session_factory", lambda: session)
    response = Response()

    result = asyncio.run(auth.refresh(request(token=original), response))

    assert result.access_token
    assert result.refresh_token is None
    cookie = response.headers["set-cookie"]
    assert auth.REFRESH_COOKIE_NAME in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie


def test_web_refresh_rejects_cross_site_origin():
    token = create_refresh_token(uuid.uuid4(), uuid.uuid4())

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            auth.refresh(
                request(origin="https://evil.example", token=token), Response()
            )
        )

    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "CSRF_ORIGIN_REJECTED"


def test_web_logout_revokes_family_and_clears_cookie(monkeypatch):
    family_id = uuid.uuid4()
    token = create_refresh_token(uuid.uuid4(), uuid.uuid4(), family_id=family_id)
    session = Session()
    revoked = []

    async def revoke(_session, candidate):
        revoked.append(candidate)

    monkeypatch.setattr(auth, "revoke_family", revoke)
    monkeypatch.setattr(auth, "master_session_factory", lambda: session)
    response = Response()

    result = asyncio.run(auth.logout(request(token=token), response))

    assert result == {"status": "ok"}
    assert revoked == [family_id]
    cookie = response.headers["set-cookie"]
    assert auth.REFRESH_COOKIE_NAME in cookie
    assert "Max-Age=0" in cookie

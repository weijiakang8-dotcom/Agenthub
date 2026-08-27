from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest
from fastapi import HTTPException, Response
from starlette.requests import Request

from app.api.routes import auth as auth_routes
from app.core.security import create_refresh_token


async def allow_rate_limit(*_args, **_kwargs):
    return True


def make_request(
    *,
    desktop: bool = True,
    origin: str = "http://localhost:5173",
    cookies: dict[str, str] | None = None,
) -> Request:
    headers = [(b"origin", origin.encode())]
    if desktop:
        headers.append((b"x-agenthub-client", b"desktop"))
    if cookies:
        cookie = "; ".join(f"{key}={value}" for key, value in cookies.items())
        headers.append((b"cookie", cookie.encode()))
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/auth/refresh",
            "headers": headers,
            "client": ("127.0.0.1", 12345),
            "scheme": "https",
            "server": ("testserver", 443),
        }
    )


class FakeRedis:
    def __init__(self):
        self.data = {}
        self.expirations = {}

    async def get(self, key):
        return self.data.get(key)

    async def set(self, key, value, ex=None):
        self.data[key] = value
        return True

    async def delete(self, key):
        self.data.pop(key, None)
        return 1

    async def incr(self, key):
        value = int(self.data.get(key, 0)) + 1
        self.data[key] = value
        return value

    async def expire(self, key, seconds):
        self.expirations[key] = seconds
        return True

    async def aclose(self):
        return None


class FakeSession:
    def __init__(self, user=None, organization=None):
        self.user = user
        self.organization = organization
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc_info):
        return False

    async def execute(self, _stmt):
        return FakeScalar(self.user)

    async def get(self, _model, _id):
        if getattr(_model, "__name__", "") == "Organization":
            return self.organization
        return self.user

    async def commit(self):
        self.committed = True


class FakeScalar:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


def make_user(email="a@b.com", organization_id=None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        email=email,
        full_name="Test User",
        role="admin",
        is_active=True,
        organization_id=organization_id,
        password_hash="hash",
        last_login=None,
    )


def make_organization(organization_id):
    return SimpleNamespace(
        id=organization_id,
        name="Test Org",
        slug="test-org",
        settings={},
    )


def make_refresh_token(user_id, expired=False):
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "org": None,
        "type": "refresh",
        "iat": now,
        "exp": now + (timedelta(seconds=-1) if expired else timedelta(days=1)),
    }
    return jwt.encode(payload, auth_routes.settings.JWT_SECRET_KEY, algorithm="HS256")


def test_verify_code_is_one_time_use(monkeypatch):
    redis = FakeRedis()
    redis.data["auth:code:user@example.com"] = "123456"
    monkeypatch.setattr(
        auth_routes.aioredis, "from_url", lambda *_args, **_kwargs: redis
    )

    assert asyncio.run(auth_routes._verify_code("user@example.com", "123456")) is True
    assert asyncio.run(auth_routes._verify_code("user@example.com", "123456")) is False


def test_verify_code_rejects_wrong_code(monkeypatch):
    redis = FakeRedis()
    redis.data["auth:code:user@example.com"] = "123456"
    monkeypatch.setattr(
        auth_routes.aioredis, "from_url", lambda *_args, **_kwargs: redis
    )

    assert asyncio.run(auth_routes._verify_code("user@example.com", "000000")) is False
    assert redis.data.get("auth:code:user@example.com") == "123456"


def test_verify_code_invalidates_after_max_attempts(monkeypatch):
    redis = FakeRedis()
    redis.data["auth:code:login:a@b.com"] = "123456"
    monkeypatch.setattr(
        auth_routes.aioredis, "from_url", lambda *_args, **_kwargs: redis
    )

    for _ in range(5):
        assert (
            asyncio.run(auth_routes._verify_code("a@b.com", "000000", "login")) is False
        )
    assert "auth:code:login:a@b.com" not in redis.data


def test_send_code_email_rate_limited(monkeypatch):
    called = []

    async def reject(*_args, **_kwargs):
        return False

    async def fake_send_code(_email):
        called.append(_email)
        return {"ok": True}

    monkeypatch.setattr(auth_routes, "rate_limit", reject)
    monkeypatch.setattr(auth_routes, "_send_code", fake_send_code)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            auth_routes.send_code(
                payload=auth_routes.SendCodeRequest(email="user@example.com"),
                request=SimpleNamespace(
                    headers={"x-forwarded-for": "1.2.3.4"},
                    client=SimpleNamespace(host="1.2.3.4"),
                ),
            )
        )

    assert exc.value.status_code == 429
    assert called == []


def test_send_code_allowed(monkeypatch):
    calls = []

    async def allow(*_args, **_kwargs):
        return True

    async def fake_send_code(email, mode=""):
        calls.append((email, mode))
        return {"ok": True}

    monkeypatch.setattr(auth_routes, "rate_limit", allow)
    monkeypatch.setattr(auth_routes, "_send_code", fake_send_code)

    result = asyncio.run(
        auth_routes.send_code(
            payload=auth_routes.SendCodeRequest(email="user@example.com"),
            request=SimpleNamespace(
                headers={},
                client=SimpleNamespace(host="5.6.7.8"),
            ),
        )
    )

    assert result == {"status": "ok"}
    assert calls == [("user@example.com", "")]


def test_validate_email_normalizes_and_rejects_invalid():
    assert auth_routes._validate_email("  User@Example.COM ") == "user@example.com"

    with pytest.raises(HTTPException) as exc:
        auth_routes._validate_email("not-an-email")
    assert exc.value.status_code == 422


def test_code_key_scopes_login_and_register():
    assert auth_routes._code_key("a@b.com", "login") == "auth:code:login:a@b.com"
    assert auth_routes._code_key("a@b.com", "register") == "auth:code:register:a@b.com"
    assert auth_routes._code_key("a@b.com") == "auth:code:a@b.com"


def test_send_code_login_does_not_leak_unregistered_email(monkeypatch):
    async def allow(*_args, **_kwargs):
        return True

    async def email_exists(_email):
        return False

    async def fake_send_code(_email, _mode=""):
        raise AssertionError("should not send")

    monkeypatch.setattr(auth_routes, "rate_limit", allow)
    monkeypatch.setattr(auth_routes, "_email_exists", email_exists)
    monkeypatch.setattr(auth_routes, "_send_code", fake_send_code)

    result = asyncio.run(
        auth_routes.send_code(
            payload=auth_routes.SendCodeRequest(email="a@b.com", mode="login"),
            request=SimpleNamespace(headers={}, client=SimpleNamespace(host="1.2.3.4")),
        )
    )

    assert result == {
        "status": "ok",
        "note": "login does not require an email code",
    }


def test_send_code_register_rejects_existing_email(monkeypatch):
    async def allow(*_args, **_kwargs):
        return True

    async def email_exists(_email):
        return True

    async def fake_send_code(_email, _mode=""):
        raise AssertionError("should not send")

    monkeypatch.setattr(auth_routes, "rate_limit", allow)
    monkeypatch.setattr(auth_routes, "_email_exists", email_exists)
    monkeypatch.setattr(auth_routes, "_send_code", fake_send_code)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            auth_routes.send_code(
                payload=auth_routes.SendCodeRequest(email="a@b.com", mode="register"),
                request=SimpleNamespace(
                    headers={},
                    client=SimpleNamespace(host="1.2.3.4"),
                ),
            )
        )

    assert exc.value.status_code == 409


def test_send_code_passes_mode_to_sender(monkeypatch):
    calls = []

    async def allow(*_args, **_kwargs):
        return True

    async def email_exists(_email):
        return False

    async def fake_send_code(email, mode=""):
        calls.append((email, mode))
        return {"ok": True}

    monkeypatch.setattr(auth_routes, "rate_limit", allow)
    monkeypatch.setattr(auth_routes, "_email_exists", email_exists)
    monkeypatch.setattr(auth_routes, "_send_code", fake_send_code)

    asyncio.run(
        auth_routes.send_code(
            payload=auth_routes.SendCodeRequest(email="a@b.com", mode="register"),
            request=SimpleNamespace(headers={}, client=SimpleNamespace(host="1.2.3.4")),
        )
    )

    assert calls == [("a@b.com", "register")]


def test_send_code_removes_code_when_email_fails(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr(
        auth_routes.aioredis, "from_url", lambda *_args, **_kwargs: redis
    )

    async def fail(_to, _subject, _text):
        return {"ok": False, "error": "boom"}

    monkeypatch.setattr(auth_routes, "send_email", fail)

    result = asyncio.run(auth_routes._send_code("a@b.com", "login"))

    assert result.get("ok") is False
    assert "auth:code:login:a@b.com" not in redis.data


def test_register_rejects_existing_email(monkeypatch):
    async def email_exists(_email):
        return True

    async def verify_code(_email, _code, _mode):
        raise AssertionError("should not verify code")

    monkeypatch.setattr(auth_routes, "_email_exists", email_exists)
    monkeypatch.setattr(auth_routes, "_verify_code", verify_code)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            auth_routes.register(
                response=Response(),
                request=make_request(),
                payload=auth_routes.RegisterRequest(
                    email="a@b.com", password="password", code="123456"
                ),
            )
        )

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "EMAIL_ALREADY_EXISTS"


def test_forgot_password_sends_only_for_existing_email(monkeypatch):
    calls = []
    exists = {"flag": True}

    async def allow(*_args, **_kwargs):
        return True

    async def email_exists(_email):
        return exists["flag"]

    async def fake_send_reset_code(email):
        calls.append(email)
        return {"ok": True}

    monkeypatch.setattr(auth_routes, "rate_limit", allow)
    monkeypatch.setattr(auth_routes, "_email_exists", email_exists)
    monkeypatch.setattr(auth_routes, "_send_reset_code", fake_send_reset_code)

    result = asyncio.run(
        auth_routes.forgot_password(
            payload=auth_routes.ForgotPasswordRequest(email="a@b.com"),
            request=SimpleNamespace(headers={}, client=SimpleNamespace(host="1.2.3.4")),
        )
    )
    assert result["success"] is True
    assert calls == ["a@b.com"]

    exists["flag"] = False
    calls.clear()
    result = asyncio.run(
        auth_routes.forgot_password(
            payload=auth_routes.ForgotPasswordRequest(email="a@b.com"),
            request=SimpleNamespace(headers={}, client=SimpleNamespace(host="1.2.3.4")),
        )
    )
    assert result["success"] is True
    assert calls == []


def test_verify_reset_code_endpoint_returns_structured_result(monkeypatch):
    async def verify(_email, code, consume=False):
        return code == "123456"

    monkeypatch.setattr(auth_routes, "_verify_reset_code", verify)

    ok = asyncio.run(
        auth_routes.verify_reset_code(
            payload=auth_routes.VerifyResetCodeRequest(email="a@b.com", code="123456")
        )
    )
    assert ok == {"success": True, "message": "验证码正确"}

    bad = asyncio.run(
        auth_routes.verify_reset_code(
            payload=auth_routes.VerifyResetCodeRequest(email="a@b.com", code="000000")
        )
    )
    assert bad == {"success": False, "message": "验证码错误或已过期"}


def test_verify_reset_code_limits_attempts_and_consumes(monkeypatch):
    redis = FakeRedis()
    redis.data["auth:reset-code:a@b.com"] = "123456"
    monkeypatch.setattr(
        auth_routes.aioredis, "from_url", lambda *_args, **_kwargs: redis
    )

    for _ in range(5):
        assert asyncio.run(auth_routes._verify_reset_code("a@b.com", "000000")) is False
    assert "auth:reset-code:a@b.com" not in redis.data

    redis.data["auth:reset-code:a@b.com"] = "123456"
    assert (
        asyncio.run(auth_routes._verify_reset_code("a@b.com", "123456", consume=True))
        is True
    )
    assert "auth:reset-code:a@b.com" not in redis.data


def test_reset_password_success(monkeypatch):
    async def verify(_email, code, consume=False):
        assert code == "123456"
        assert consume is True
        return True

    async def set_password(email, new_password):
        assert email == "a@b.com"
        assert new_password == "newpassword"
        return True

    monkeypatch.setattr(auth_routes, "_verify_reset_code", verify)
    monkeypatch.setattr(auth_routes, "_set_user_password", set_password)

    result = asyncio.run(
        auth_routes.reset_password(
            payload=auth_routes.ResetPasswordRequest(
                email="a@b.com", code="123456", new_password="newpassword"
            )
        )
    )
    assert result == {"success": True, "message": "密码修改成功，请重新登录"}


def test_reset_password_rejects_short_password():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            auth_routes.reset_password(
                payload=auth_routes.ResetPasswordRequest(
                    email="a@b.com", code="123456", new_password="short"
                )
            )
        )
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "INVALID_PASSWORD"


def test_reset_password_rejects_invalid_code(monkeypatch):
    async def verify(_email, _code, consume=False):
        return False

    monkeypatch.setattr(auth_routes, "_verify_reset_code", verify)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            auth_routes.reset_password(
                payload=auth_routes.ResetPasswordRequest(
                    email="a@b.com", code="000000", new_password="newpassword"
                )
            )
        )
    assert exc.value.status_code == 401
    assert exc.value.detail["code"] == "INVALID_VERIFY_CODE"


def test_login_ignores_code_and_never_verifies(monkeypatch):
    called = []

    async def verify_code(_email, _code, _mode):
        called.append(True)
        return False

    def verify_password(_password, _stored):
        return False

    session = FakeSession(user=make_user())
    monkeypatch.setattr(auth_routes, "_verify_code", verify_code)
    monkeypatch.setattr(auth_routes, "verify_password", verify_password)
    monkeypatch.setattr(auth_routes, "rate_limit", allow_rate_limit)
    monkeypatch.setattr(auth_routes, "master_session_factory", lambda: session)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            auth_routes.login(
                response=Response(),
                request=make_request(),
                payload=auth_routes.LoginRequest(
                    email="a@b.com", password="password", code="000000"
                ),
            )
        )
    assert exc.value.status_code == 401
    assert exc.value.detail["code"] == "INVALID_PASSWORD"
    assert called == []


def test_login_rejects_unknown_email_without_leaking(monkeypatch):
    async def verify_code(_email, _code, _mode):
        return True

    session = FakeSession(user=None)
    monkeypatch.setattr(auth_routes, "_verify_code", verify_code)
    monkeypatch.setattr(auth_routes, "rate_limit", allow_rate_limit)
    monkeypatch.setattr(auth_routes, "master_session_factory", lambda: session)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            auth_routes.login(
                response=Response(),
                request=make_request(),
                payload=auth_routes.LoginRequest(
                    email="a@b.com", password="password", code="123456"
                ),
            )
        )
    assert exc.value.status_code == 401
    assert exc.value.detail["code"] == "INVALID_PASSWORD"


def test_login_rejects_wrong_password(monkeypatch):
    async def verify_code(_email, _code, _mode):
        return True

    def verify_password(_password, _stored):
        return False

    session = FakeSession(user=make_user())
    monkeypatch.setattr(auth_routes, "_verify_code", verify_code)
    monkeypatch.setattr(auth_routes, "verify_password", verify_password)
    monkeypatch.setattr(auth_routes, "rate_limit", allow_rate_limit)
    monkeypatch.setattr(auth_routes, "master_session_factory", lambda: session)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            auth_routes.login(
                response=Response(),
                request=make_request(),
                payload=auth_routes.LoginRequest(
                    email="a@b.com", password="wrong", code="123456"
                ),
            )
        )
    assert exc.value.status_code == 401
    assert exc.value.detail["code"] == "INVALID_PASSWORD"


def test_login_success(monkeypatch):
    async def verify_code(_email, _code, _mode):
        return True

    def verify_password(_password, _stored):
        return True

    organization_id = uuid.uuid4()
    user = make_user(organization_id=organization_id)
    session = FakeSession(user=user, organization=make_organization(organization_id))
    monkeypatch.setattr(auth_routes, "_verify_code", verify_code)
    monkeypatch.setattr(auth_routes, "rate_limit", allow_rate_limit)

    async def issue_refresh(_session, _user):
        return create_refresh_token(_user.id, _user.organization_id)

    monkeypatch.setattr(auth_routes, "verify_password", verify_password)
    monkeypatch.setattr(auth_routes, "issue_refresh_session", issue_refresh)
    monkeypatch.setattr(auth_routes, "master_session_factory", lambda: session)

    result = asyncio.run(
        auth_routes.login(
            payload=auth_routes.LoginRequest(
                email="a@b.com", password="password", code="123456"
            ),
            response=Response(),
            request=make_request(),
        )
    )

    assert result.user.email == "a@b.com"
    assert result.organization.id == organization_id
    assert result.access_token
    assert result.refresh_token
    assert session.committed is True


def test_login_rate_limited_returns_429(monkeypatch):
    async def deny(*_args, **_kwargs):
        return False

    session = FakeSession(user=make_user())
    monkeypatch.setattr(auth_routes, "rate_limit", deny)
    monkeypatch.setattr(auth_routes, "master_session_factory", lambda: session)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            auth_routes.login(
                payload=auth_routes.LoginRequest(email="a@b.com", password="password"),
                response=Response(),
                request=make_request(),
            )
        )
    assert exc.value.status_code == 429


def test_refresh_requires_bearer():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(auth_routes.refresh(request=make_request(), response=Response()))
    assert exc.value.status_code == 401
    assert exc.value.detail["code"] == "INVALID_REFRESH_TOKEN"


def test_refresh_rejects_invalid_token():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            auth_routes.refresh(
                request=make_request(),
                response=Response(),
                authorization="Bearer not-a-jwt",
            )
        )
    assert exc.value.status_code == 401
    assert exc.value.detail["code"] == "INVALID_REFRESH_TOKEN"


def test_refresh_rejects_expired_token():
    token = make_refresh_token(uuid.uuid4(), expired=True)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            auth_routes.refresh(
                request=make_request(),
                response=Response(),
                authorization=f"Bearer {token}",
            )
        )
    assert exc.value.status_code == 401
    assert exc.value.detail["code"] == "REFRESH_TOKEN_EXPIRED"


def test_refresh_rejects_access_token_as_refresh():
    access = auth_routes.create_access_token(uuid.uuid4(), uuid.uuid4())
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            auth_routes.refresh(
                request=make_request(),
                response=Response(),
                authorization=f"Bearer {access}",
            )
        )
    assert exc.value.status_code == 401
    assert exc.value.detail["code"] == "INVALID_REFRESH_TOKEN"


def test_logout_requires_refresh_token():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(auth_routes.logout(request=make_request(), response=Response()))
    assert exc.value.status_code == 401
    assert exc.value.detail["code"] == "INVALID_REFRESH_TOKEN"


def test_logout_revokes_token_family(monkeypatch):
    family_id = uuid.uuid4()
    token = create_refresh_token(uuid.uuid4(), uuid.uuid4(), family_id=family_id)
    session = FakeSession()
    revoked = []

    async def revoke(_session, candidate_family_id):
        revoked.append(candidate_family_id)

    monkeypatch.setattr(auth_routes, "revoke_family", revoke)
    monkeypatch.setattr(auth_routes, "master_session_factory", lambda: session)

    result = asyncio.run(
        auth_routes.logout(
            request=make_request(), response=Response(), authorization=f"Bearer {token}"
        )
    )

    assert result == {"status": "ok"}
    assert revoked == [family_id]
    assert session.committed is True


def test_refresh_success(monkeypatch):
    organization_id = uuid.uuid4()
    user = make_user(organization_id=organization_id)
    refresh_token = create_refresh_token(user.id, organization_id)
    session = FakeSession(user=user, organization=make_organization(organization_id))

    async def rotate_refresh(_session, _token):
        return (
            create_refresh_token(user.id, organization_id, family_id=uuid.uuid4()),
            user,
        )

    monkeypatch.setattr(auth_routes, "rotate_refresh_session", rotate_refresh)
    monkeypatch.setattr(auth_routes, "master_session_factory", lambda: session)

    result = asyncio.run(
        auth_routes.refresh(
            request=make_request(),
            response=Response(),
            authorization=f"Bearer {refresh_token}",
        )
    )

    assert result.access_token
    assert result.refresh_token
    assert result.refresh_token != refresh_token
    payload = auth_routes.decode_token_checked(result.access_token)
    assert payload["sub"] == str(user.id)
    assert payload["type"] == "access"

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.api.routes.auth import UserRead
from app.core.audit import sanitize_audit_data
from app.models import ModelConfig, User


def _user() -> User:
    return User(
        id=uuid.uuid4(),
        email="u@example.com",
        password_hash="pbkdf2$secret-hash",
        full_name="u",
        organization_id=uuid.uuid4(),
        role="admin",
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def test_user_read_never_exposes_password_hash():
    dumped = UserRead.model_validate(_user()).model_dump()
    assert "password_hash" not in dumped
    assert "secret" not in str(dumped).lower() or dumped.get("password_hash") is None


def test_model_serialize_never_exposes_api_key():
    from app.api.routes.models import _serialize

    model = ModelConfig(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        name="deepseek",
        provider="deepseek",
        base_url="https://api.deepseek.com/v1",
        api_key="sk-top-secret",
        model="deepseek-chat",
        max_tokens=4096,
        cost_per_1k_tokens=0.002,
        is_active=True,
        enabled=True,
        priority=100,
        timeout=120,
        max_retries=2,
        is_default=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    serialized = _serialize(model)
    assert "api_key" not in serialized
    assert "top-secret" not in str(serialized)


def test_audit_sanitization_masks_nested_secrets():
    data = {
        "user": {"email": "a@b.c", "password": "pw", "api_key": "k"},
        "headers": {"authorization": "Bearer x", "x-api-key": "y"},
        "ok": "visible",
    }
    clean = sanitize_audit_data(data)
    assert clean["user"]["password"] == "***"
    assert clean["user"]["api_key"] == "***"
    assert clean["headers"]["authorization"] == "***"
    assert clean["headers"]["x-api-key"] == "***"
    assert clean["ok"] == "visible"

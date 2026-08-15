from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.deps import get_current_user_ws, require_role


class FakeWebSocket:
    def __init__(self):
        self.closed_code = None

    async def close(self, code: int):
        self.closed_code = code


def test_require_role_rejects_non_admin():
    dependency = require_role("admin")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(dependency(SimpleNamespace(role="member")))

    assert exc.value.status_code == 403


def test_require_role_allows_admin():
    dependency = require_role("admin")
    user = SimpleNamespace(id=uuid.uuid4(), role="admin")

    result = asyncio.run(dependency(user))

    assert result is user


def test_websocket_auth_rejects_missing_token():
    websocket = FakeWebSocket()

    with pytest.raises(HTTPException):
        asyncio.run(
            get_current_user_ws(
                websocket=websocket,
                session=None,
                token=None,
                authorization=None,
                x_api_key=None,
            )
        )

    assert websocket.closed_code == 1008

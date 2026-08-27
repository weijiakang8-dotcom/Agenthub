from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core.permissions import (
    VALID_ROLES,
    require_permission,
    require_role,
)


def test_require_role_rejects_non_matching_role():
    dependency = require_role("admin")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(dependency(SimpleNamespace(role="member")))

    assert exc.value.status_code == 403


def test_require_role_allows_admin_superuser():
    dependency = require_role("member")
    result = asyncio.run(dependency(SimpleNamespace(role="admin")))
    assert result.role == "admin"


def test_require_permission_allows_member_execution_write():
    dependency = require_permission("executions:write")
    result = asyncio.run(dependency(SimpleNamespace(role="member")))
    assert result.role == "member"


def test_require_permission_rejects_viewer_execution_write():
    dependency = require_permission("executions:write")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(dependency(SimpleNamespace(role="viewer")))

    assert exc.value.status_code == 403


def test_require_permission_models_manage_is_admin_only():
    dependency = require_permission("models:manage")

    with pytest.raises(HTTPException):
        asyncio.run(dependency(SimpleNamespace(role="member")))

    assert asyncio.run(dependency(SimpleNamespace(role="admin"))).role == "admin"


@pytest.mark.parametrize(
    "permission",
    ["resources:write", "executions:write"],
)
def test_viewer_cannot_mutate_resources_or_execute(permission):
    dependency = require_permission(permission)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(dependency(SimpleNamespace(role="viewer")))

    assert exc.value.status_code == 403


def test_admin_only_operations_reject_member():
    dependency = require_permission("operations:manage")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(dependency(SimpleNamespace(role="member")))

    assert exc.value.status_code == 403
    assert asyncio.run(dependency(SimpleNamespace(role="admin"))).role == "admin"


def test_valid_roles_are_admin_member_viewer():
    assert VALID_ROLES == {"admin", "member", "viewer"}

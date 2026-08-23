from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.routes.organizations import (
    MemberRoleUpdate,
    list_members,
    update_member_role,
)

ORG_ID = uuid.uuid4()


def make_user(role="member", organization_id=ORG_ID):
    return SimpleNamespace(
        id=uuid.uuid4(),
        email="member@example.com",
        full_name="Member",
        role=role,
        is_active=True,
        organization_id=organization_id,
        created_at=datetime(2026, 8, 16, tzinfo=timezone.utc),
    )


class FakeScalarResult:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class FakeResult:
    def __init__(self, scalars=None):
        self._scalars = scalars or []

    def scalars(self):
        return FakeScalarResult(self._scalars)


class FakeSession:
    def __init__(self, execute_result=None, get_result=None):
        self.execute_result = execute_result
        self.get_result = get_result
        self.commits = 0
        self.refreshes = 0

    async def execute(self, _stmt):
        return self.execute_result

    async def get(self, _model, _id):
        return self.get_result

    async def commit(self):
        self.commits += 1

    async def refresh(self, _obj):
        self.refreshes += 1


def test_list_members_serializes_org_users():
    member = make_user()
    session = FakeSession(execute_result=FakeResult(scalars=[member]))

    result = asyncio.run(
        list_members(session=session, current_user=make_user(role="admin"))
    )

    assert result[0]["email"] == "member@example.com"
    assert result[0]["role"] == "member"


def test_update_member_role_rejects_invalid_role():
    session = FakeSession()

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            update_member_role(
                user_id=uuid.uuid4(),
                payload=MemberRoleUpdate(role="superuser"),
                session=session,
                current_user=make_user(role="admin"),
            )
        )

    assert exc.value.status_code == 422


def test_update_member_role_rejects_self_change():
    admin = make_user(role="admin")
    session = FakeSession()

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            update_member_role(
                user_id=admin.id,
                payload=MemberRoleUpdate(role="viewer"),
                session=session,
                current_user=admin,
            )
        )

    assert exc.value.status_code == 400


def test_update_member_role_rejects_cross_org_member():
    target = make_user(role="member", organization_id=uuid.uuid4())
    session = FakeSession(get_result=target)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            update_member_role(
                user_id=target.id,
                payload=MemberRoleUpdate(role="admin"),
                session=session,
                current_user=make_user(role="admin"),
            )
        )

    assert exc.value.status_code == 404


def test_update_member_role_success():
    target = make_user(role="member")
    session = FakeSession(get_result=target)

    result = asyncio.run(
        update_member_role(
            user_id=target.id,
            payload=MemberRoleUpdate(role="viewer"),
            session=session,
            current_user=make_user(role="admin"),
        )
    )

    assert result["role"] == "viewer"
    assert session.commits == 1
    assert session.refreshes == 1

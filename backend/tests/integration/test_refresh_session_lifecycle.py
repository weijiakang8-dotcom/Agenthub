from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import select

from app.core.refresh_sessions import (
    RefreshTokenReplayError,
    issue_refresh_session,
    revoke_user_sessions,
    rotate_refresh_session,
)
from app.database import master_session_factory
from app.models import Organization, RefreshSession, User


async def _create_user() -> tuple[uuid.UUID, uuid.UUID]:
    async with master_session_factory() as session:
        org = Organization(name="Refresh Test", slug=f"refresh-{uuid.uuid4().hex}")
        session.add(org)
        await session.flush()
        user = User(
            email=f"refresh-{uuid.uuid4().hex}@example.test",
            password_hash="test",
            full_name="Refresh Test",
            organization_id=org.id,
            role="admin",
        )
        session.add(user)
        await session.commit()
        return user.id, org.id


async def _cleanup(user_id: uuid.UUID, org_id: uuid.UUID) -> None:
    async with master_session_factory() as session:
        user = await session.get(User, user_id)
        if user is not None:
            await session.delete(user)
        org = await session.get(Organization, org_id)
        if org is not None:
            await session.delete(org)
        await session.commit()


def test_refresh_rotation_and_replay_revoke_family():
    async def run() -> None:
        user_id, org_id = await _create_user()
        try:
            async with master_session_factory() as session:
                user = await session.get(User, user_id)
                original = await issue_refresh_session(session, user)
                await session.commit()

            async with master_session_factory() as session:
                replacement, user = await rotate_refresh_session(session, original)
                await session.commit()
                assert replacement != original
                assert user.id == user_id

            async with master_session_factory() as session:
                with pytest.raises(RefreshTokenReplayError):
                    await rotate_refresh_session(session, original)

            async with master_session_factory() as session:
                rows = list(
                    (
                        await session.execute(
                            select(RefreshSession).where(
                                RefreshSession.user_id == user_id
                            )
                        )
                    ).scalars()
                )
                assert len(rows) == 2
                assert all(row.revoked_at is not None for row in rows)

            async with master_session_factory() as session:
                with pytest.raises(ValueError, match="revoked"):
                    await rotate_refresh_session(session, replacement)
        finally:
            await _cleanup(user_id, org_id)

    asyncio.run(run())


def test_revoke_user_sessions_invalidates_active_refresh():
    async def run() -> None:
        user_id, org_id = await _create_user()
        try:
            async with master_session_factory() as session:
                user = await session.get(User, user_id)
                token = await issue_refresh_session(session, user)
                await session.commit()

            async with master_session_factory() as session:
                await revoke_user_sessions(session, user_id)
                await session.commit()

            async with master_session_factory() as session:
                with pytest.raises(ValueError, match="revoked"):
                    await rotate_refresh_session(session, token)
        finally:
            await _cleanup(user_id, org_id)

    asyncio.run(run())

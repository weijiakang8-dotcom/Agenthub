from __future__ import annotations

import asyncio
import uuid

import pytest

from app.engine import lease_runner


class Session:
    commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def commit(self):
        self.commits += 1


def test_run_with_lease_acquires_runs_and_releases(monkeypatch):
    session = Session()
    calls = []

    async def acquire(_session, _execution_id, owner):
        calls.append(("acquire", owner))
        return True

    async def release(_session, _execution_id, owner):
        calls.append(("release", owner))
        return True

    async def run():
        calls.append(("run", "worker"))

    monkeypatch.setattr(lease_runner, "async_session_factory", lambda: session)

    async def active(_execution_id):
        return None

    monkeypatch.setattr(lease_runner, "acquire_execution_lease", acquire)
    monkeypatch.setattr(lease_runner, "release_execution_lease", release)
    monkeypatch.setattr(lease_runner, "ensure_execution_active", active)

    asyncio.run(lease_runner.run_with_execution_lease(uuid.uuid4(), "worker", run))

    assert calls == [
        ("acquire", "worker"),
        ("run", "worker"),
        ("release", "worker"),
    ]


def test_run_with_lease_rejects_duplicate_worker(monkeypatch):
    session = Session()
    ran = []

    async def acquire(*_args):
        return False

    async def run():
        ran.append(True)

    monkeypatch.setattr(lease_runner, "async_session_factory", lambda: session)
    monkeypatch.setattr(lease_runner, "acquire_execution_lease", acquire)

    with pytest.raises(lease_runner.ExecutionLeaseUnavailable):
        asyncio.run(lease_runner.run_with_execution_lease(uuid.uuid4(), "worker", run))

    assert ran == []


def test_run_with_lease_releases_after_failure(monkeypatch):
    session = Session()
    released = []

    async def acquire(*_args):
        return True

    async def release(*_args):
        released.append(True)
        return True

    async def run():
        raise RuntimeError("failed")

    monkeypatch.setattr(lease_runner, "async_session_factory", lambda: session)

    async def active(_execution_id):
        return None

    monkeypatch.setattr(lease_runner, "acquire_execution_lease", acquire)
    monkeypatch.setattr(lease_runner, "release_execution_lease", release)
    monkeypatch.setattr(lease_runner, "ensure_execution_active", active)

    with pytest.raises(RuntimeError, match="failed"):
        asyncio.run(lease_runner.run_with_execution_lease(uuid.uuid4(), "worker", run))

    assert released == [True]

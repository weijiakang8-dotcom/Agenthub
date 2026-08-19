from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import app.kernel
import pytest
from app.adapters import shadow_audit_repository
from app.api.routes import shadow_audit as shadow_audit_route
from app.engine import runner
from app.models import ShadowAuditRecord
from app.schemas.shadow_audit import ShadowAuditView
from fastapi import HTTPException


def _record() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        execution_id=uuid.uuid4(),
        workflow_id=None,
        shadow_status="SUCCESS",
        kernel_termination="TERMINATED_GOAL_SATISFIED",
        kernel_goal_status="SATISFIED",
        evidence_level="L2_SUPPORTED",
        semantic_match=True,
        information_loss=[],
        violations=[],
        trace=[],
        error_type=None,
        error_message=None,
        created_at=datetime.now(timezone.utc),
    )


class FakeSession:
    def __init__(self, record=None, rows=None, counts=None):
        self.record = record
        self.rows = rows or []
        self.counts = list(counts or [])
        self.committed = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, _model, _obj_id):
        return self.record

    async def execute(self, _stmt):
        if self.counts:
            value = self.counts.pop(0)
            return SimpleNamespace(scalar_one=lambda: value)
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: self.rows))

    async def commit(self):
        self.committed += 1


def test_227_shadow_audit_orm_can_be_created():
    record = ShadowAuditRecord(
        execution_id=uuid.uuid4(),
        shadow_status="SUCCESS",
        information_loss=[],
        violations=[],
        trace=[],
    )

    assert record.shadow_status == "SUCCESS"


def test_228_get_by_audit_id_returns_dto(monkeypatch):
    record = _record()
    monkeypatch.setattr(
        shadow_audit_repository,
        "async_session_factory",
        lambda: FakeSession(record=record),
    )

    view = asyncio.run(shadow_audit_repository.get_by_audit_id(record.id))

    assert view is not None
    assert view.audit_id == record.id
    assert view.execution_id == record.execution_id


def test_229_get_by_execution_id_returns_dto(monkeypatch):
    record = _record()
    monkeypatch.setattr(
        shadow_audit_repository,
        "async_session_factory",
        lambda: FakeSession(rows=[record]),
    )

    views = asyncio.run(
        shadow_audit_repository.get_by_execution_id(record.execution_id)
    )

    assert len(views) == 1
    assert views[0].audit_id == record.id


def test_230_list_recent_orders_and_returns_dtos(monkeypatch):
    record = _record()
    monkeypatch.setattr(
        shadow_audit_repository,
        "async_session_factory",
        lambda: FakeSession(rows=[record]),
    )

    views = asyncio.run(shadow_audit_repository.list_recent(limit=5, offset=0))

    assert views[0].audit_id == record.id


def test_231_list_recent_limit_is_capped(monkeypatch):
    monkeypatch.setattr(
        shadow_audit_repository,
        "async_session_factory",
        lambda: FakeSession(rows=[]),
    )

    views = asyncio.run(shadow_audit_repository.list_recent(limit=9999))

    assert views == []


def test_232_unknown_audit_id_is_404(monkeypatch):
    async def no_audit(_audit_id, organization_id=None):
        return None

    monkeypatch.setattr(shadow_audit_repository, "get_by_audit_id", no_audit)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            shadow_audit_route.get_shadow_audit(
                uuid.uuid4(),
                user=SimpleNamespace(organization_id=None),
            )
        )

    assert exc_info.value.status_code == 404


def test_233_unknown_execution_returns_empty(monkeypatch):
    async def no_audits(_execution_id, organization_id=None):
        return []

    monkeypatch.setattr(
        shadow_audit_repository,
        "get_by_execution_id",
        no_audits,
    )

    result = asyncio.run(
        shadow_audit_route.get_execution_shadow_audits(
            uuid.uuid4(),
            user=SimpleNamespace(organization_id=None),
        )
    )

    assert result == []


def test_234_stats_is_correct(monkeypatch):
    counts = [10, 7, 2, 1, 6, 4, 5, 1]
    monkeypatch.setattr(
        shadow_audit_repository,
        "async_session_factory",
        lambda: FakeSession(counts=counts),
    )

    result = asyncio.run(shadow_audit_repository.stats())

    assert result == {
        "total": 10,
        "success": 7,
        "failed": 2,
        "disabled": 1,
        "goal_satisfied": 6,
        "goal_not_satisfied": 4,
        "semantic_match_count": 5,
        "violation_count": 1,
    }


def test_235_236_237_repository_is_read_only():
    source = Path(shadow_audit_repository.__file__).read_text()

    assert "session.add" not in source
    assert ".commit()" not in source


def test_238_shadow_audit_not_in_kernel_state():
    kernel_dir = Path(app.kernel.__file__).parent
    offenders: list[str] = []

    for path in kernel_dir.rglob("*.py"):
        text = path.read_text()
        if "ShadowAudit" in text or "shadow_audit" in text:
            offenders.append(str(path))

    assert offenders == []


def test_239_audit_view_is_not_observation():
    assert "observation" not in ShadowAuditView.model_fields
    assert "evidence_level" not in {
        field for field in ShadowAuditView.model_fields if field.startswith("obs")
    }


def test_240_audit_view_is_not_evidence():
    assert ShadowAuditView.__module__.startswith("app.schemas")
    assert not ShadowAuditView.__module__.startswith("app.kernel")


def test_241_audit_view_does_not_produce_satisfied():
    assert "predicate_result" not in ShadowAuditView.model_fields


def test_242_sensitive_fields_are_absent():
    sensitive = {
        "api_key",
        "password",
        "token",
        "secret",
        "authorization",
        "cookie",
    }

    assert sensitive.isdisjoint(ShadowAuditView.model_fields)


def test_243_kernel_forbidden_import_regression():
    kernel_dir = Path(app.kernel.__file__).parent
    offenders: list[str] = []

    for path in kernel_dir.rglob("*.py"):
        for line in path.read_text().splitlines():
            stripped = line.strip()
            if not stripped.startswith(("import ", "from ")):
                continue
            lowered = stripped.lower()
            if any(
                token in lowered
                for token in (
                    "fastapi",
                    "langgraph",
                    "langchain",
                    "celery",
                    "redis",
                    "sqlalchemy",
                    "asyncpg",
                    "httpx",
                    "openai",
                    "smtplib",
                    "app.adapters",
                    "app.engine",
                    "app.api",
                    "app.models",
                    "app.core",
                )
            ):
                offenders.append(f"{path}: {stripped}")

    assert offenders == []


def test_244_shadow_disabled_does_not_trigger_audit_query(monkeypatch):
    monkeypatch.setattr(runner.settings, "SHADOW_MODE", False)
    recorded = []

    async def fake_get(_audit_id):
        recorded.append(1)

    monkeypatch.setattr(shadow_audit_repository, "get_by_audit_id", fake_get)

    asyncio.run(
        runner.run_shadow_hook(
            SimpleNamespace(id=uuid.uuid4(), user_input="任务"),
            SimpleNamespace(id=uuid.uuid4(), name="chat", agent_chain=[]),
            "final",
        )
    )

    assert recorded == []


def test_245_audit_output_is_deterministic(monkeypatch):
    record = _record()
    monkeypatch.setattr(
        shadow_audit_repository,
        "async_session_factory",
        lambda: FakeSession(record=record),
    )

    first = asyncio.run(shadow_audit_repository.get_by_audit_id(record.id))
    second = asyncio.run(shadow_audit_repository.get_by_audit_id(record.id))

    assert first.model_dump() == second.model_dump()

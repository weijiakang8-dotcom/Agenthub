"""调度中心 API 测试（analyze / decisions / usage / agent-center）。"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.main as main_module
from app.api.deps import get_current_user
from app.api.routes import agent_center as agent_center_module
from app.api.routes import dispatch as dispatch_module
from app.api.routes import skills as skills_module
from app.database import get_db
from app.main import app

ORG_ID = uuid.uuid4()


class FakeScalarResult:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values

    def first(self):
        return self.values[0] if self.values else None


class FakeResult:
    def __init__(self, scalars=None, one=None):
        self._scalars = scalars
        self._one = one

    def scalars(self):
        return FakeScalarResult(self._scalars or [])

    def one(self):
        return self._one


class FakeSession:
    def __init__(self, execute_results=None):
        self.execute_results = list(execute_results or [])
        self.committed = False
        self.statements = []

    async def execute(self, stmt):
        self.statements.append(stmt)
        if not self.execute_results:
            raise AssertionError("no execute result configured")
        return self.execute_results.pop(0)

    async def commit(self):
        self.committed = True


def _client_with_session(monkeypatch, execute_results):
    async def allow_request(*_args, **_kwargs):
        return True

    monkeypatch.setattr(main_module, "rate_limit", allow_request)

    session = FakeSession(execute_results)
    user = SimpleNamespace(
        id=uuid.uuid4(), organization_id=ORG_ID, role="admin", is_active=True
    )

    async def override_user():
        return user

    async def override_db():
        yield session

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_db] = override_db
    return TestClient(app), session


def _client(monkeypatch, execute_results):
    client, _session = _client_with_session(monkeypatch, execute_results)
    return client


def test_dispatch_analyze(monkeypatch):
    async def fake_match(text, org, **kwargs):
        return [
            {
                "id": "s1",
                "name": "行业研究报告",
                "description": "d",
                "icon": "i",
                "score": 0.9,
                "reason": "触发词命中 100%",
                "source": "preset",
                "version": 1,
                "times_used": 0,
                "plan_template": {},
                "model_tier_hints": {},
            }
        ]

    async def fake_candidates(organization_id=None):
        return ["deepseek-v4-flash", "deepseek-v4-pro"]

    monkeypatch.setattr(dispatch_module, "match_skills", fake_match)
    monkeypatch.setattr(dispatch_module, "model_candidates", fake_candidates)
    client = _client(monkeypatch, [])
    response = client.post(
        "/api/dispatch/analyze",
        json={
            "input": "帮我调研民宿行业趋势",
            "tier": "balanced",
            "plan": {
                "steps": [
                    {"step_id": "s1", "capability": "research"},
                    {"step_id": "s2", "capability": "analysis"},
                ]
            },
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["tier"] == "balanced"
    assert data["complexity"]["score"] > 0
    assert len(data["skills"]) == 1
    assert len(data["routing_preview"]) == 2
    assert data["routing_preview"][0]["complexity"] in {"simple", "complex"}


def test_dispatch_decisions(monkeypatch):
    from datetime import datetime, timezone

    from app.models import RoutingDecision

    decision = RoutingDecision(
        id=uuid.uuid4(),
        execution_id=None,
        step_id="step_1",
        step_capability="research",
        score=0.5,
        tier="balanced",
        chosen_complexity="complex",
        reason="r",
        factors=[],
        candidates=["a"],
        outcome="success",
        model_used="m",
        cost=0.001,
        organization_id=ORG_ID,
        created_at=datetime(2026, 8, 21, tzinfo=timezone.utc),
        updated_at=datetime(2026, 8, 21, tzinfo=timezone.utc),
    )
    client = _client(monkeypatch, [FakeResult(scalars=[decision])])
    response = client.get("/api/dispatch/decisions")
    assert response.status_code == 200
    data = response.json()
    assert data[0]["step_id"] == "step_1"
    assert data[0]["outcome"] == "success"


def test_dispatch_decisions_with_execution_stays_tenant_scoped(monkeypatch):
    execution_id = uuid.uuid4()
    client, session = _client_with_session(monkeypatch, [FakeResult(scalars=[])])

    response = client.get(
        "/api/dispatch/decisions", params={"execution_id": str(execution_id)}
    )

    assert response.status_code == 200
    sql = str(session.statements[0].compile(compile_kwargs={"literal_binds": True}))
    assert "routing_decisions.execution_id" in sql
    assert "routing_decisions.organization_id" in sql
    assert execution_id.hex in sql
    assert ORG_ID.hex in sql


def test_dispatch_clarifications_with_execution_stays_tenant_scoped(monkeypatch):
    execution_id = uuid.uuid4()
    client, session = _client_with_session(monkeypatch, [FakeResult(scalars=[])])

    response = client.get(
        "/api/dispatch/clarifications", params={"execution_id": str(execution_id)}
    )

    assert response.status_code == 200
    sql = str(session.statements[0].compile(compile_kwargs={"literal_binds": True}))
    assert "clarifications.execution_id" in sql
    assert "clarifications.organization_id" in sql
    assert execution_id.hex in sql
    assert ORG_ID.hex in sql


def test_usage_savings(monkeypatch):
    import app.core.savings as savings_module

    async def fake_latest(organization_id):
        return None

    async def fake_compute(organization_id, **kwargs):
        return {
            "period_start": "x",
            "period_end": "y",
            "baseline_cost": 1.0,
            "actual_cost": 0.4,
            "savings": 0.6,
            "savings_rate": 0.6,
            "total_tokens": 1000,
            "by_model": [],
        }

    monkeypatch.setattr(savings_module, "latest_savings", fake_latest)
    monkeypatch.setattr(savings_module, "compute_savings", fake_compute)
    client = _client(monkeypatch, [])
    response = client.get("/api/usage/savings")
    assert response.status_code == 200
    data = response.json()
    assert data["savings"] == 0.6
    assert data["savings_rate"] == 0.6


def test_agent_center_roster(monkeypatch):
    from app.agents import AgentSpec

    def fake_specs():
        return [AgentSpec(name="planner", role="r", system_prompt="p", model_policy={})]

    async def fake_active(name, org):
        return None

    monkeypatch.setattr(agent_center_module, "list_agent_specs", fake_specs)
    monkeypatch.setattr(agent_center_module, "get_active_version", fake_active)
    client = _client(monkeypatch, [])
    response = client.get("/api/agent-center")
    assert response.status_code == 200
    data = response.json()
    assert data[0]["name"] == "planner"
    assert data[0]["active_version"] is None


def test_skills_match_endpoint(monkeypatch):
    async def fake_match(text, org, **kwargs):
        return []

    monkeypatch.setattr(skills_module, "match_skills", fake_match)
    client = _client(monkeypatch, [])
    response = client.get("/api/skills/match", params={"input": "hello"})
    assert response.status_code == 200
    assert response.json() == []

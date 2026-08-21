"""MCP 服务器测试（JSON-RPC over HTTP）。"""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.main as main_module
import app.mcp.server as mcp_server_module
from app.api.deps import get_current_user
from app.database import get_db
from app.main import app


class FakeSession:
    """假 DB 会话：execute 不抛异常即可（health 用）。"""

    async def execute(self, _stmt):
        return None


def _allow_rate_limit(monkeypatch):
    async def allow_request(*_args, **_kwargs):
        return True

    monkeypatch.setattr(main_module, "rate_limit", allow_request)


def _client(monkeypatch):
    _allow_rate_limit(monkeypatch)

    user = SimpleNamespace(
        id=uuid.uuid4(), organization_id=None, role="admin", is_active=True
    )

    async def override_user():
        return user

    async def override_db():
        yield FakeSession()

    monkeypatch.setitem(app.dependency_overrides, get_current_user, override_user)
    monkeypatch.setitem(app.dependency_overrides, get_db, override_db)
    return TestClient(app)


def _rpc(client, method, params=None, _id=1):
    return client.post(
        "/api/mcp",
        json={"jsonrpc": "2.0", "id": _id, "method": method, "params": params or {}},
    )


def test_initialize(monkeypatch):
    client = _client(monkeypatch)
    response = _rpc(client, "initialize")
    assert response.status_code == 200
    data = response.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == 1
    result = data["result"]
    assert result["protocolVersion"] == "2024-11-05"
    assert result["capabilities"] == {"tools": {}}
    assert result["serverInfo"]["name"] == "agenthub"


def test_tools_list(monkeypatch):
    client = _client(monkeypatch)
    response = _rpc(client, "tools/list")
    assert response.status_code == 200
    tools = response.json()["result"]["tools"]
    names = [tool["name"] for tool in tools]
    assert len(tools) == 4
    assert names == [
        "agenthub.analyze_task",
        "agenthub.match_skills",
        "agenthub.savings_report",
        "agenthub.health",
    ]
    for tool in tools:
        assert tool["description"]
        assert "inputSchema" in tool


def test_tools_call_analyze_task(monkeypatch):
    async def fake_match(text, org, **kwargs):
        return [{"id": "s1", "name": "行业研究报告", "score": 0.9}]

    async def fake_candidates(organization_id=None):
        return ["deepseek-v4-flash", "deepseek-v4-pro"]

    monkeypatch.setattr(mcp_server_module, "match_skills", fake_match)
    monkeypatch.setattr(mcp_server_module, "model_candidates", fake_candidates)
    client = _client(monkeypatch)

    response = _rpc(
        client,
        "tools/call",
        {
            "name": "agenthub.analyze_task",
            "arguments": {"input": "帮我调研民宿行业趋势", "tier": "balanced"},
        },
    )
    assert response.status_code == 200
    result = response.json()["result"]
    assert result["isError"] is False
    payload = json.loads(result["content"][0]["text"])
    assert payload["tier"] == "balanced"
    assert "complexity" in payload
    assert len(payload["skills"]) == 1
    assert payload["candidates"] == ["deepseek-v4-flash", "deepseek-v4-pro"]


def test_tools_call_match_skills(monkeypatch):
    async def fake_match(text, org, **kwargs):
        return [{"id": "s1", "name": "skill-a"}]

    monkeypatch.setattr(mcp_server_module, "match_skills", fake_match)
    client = _client(monkeypatch)

    response = _rpc(
        client,
        "tools/call",
        {"name": "agenthub.match_skills", "arguments": {"input": "hello"}},
    )
    assert response.status_code == 200
    result = response.json()["result"]
    assert result["isError"] is False
    assert json.loads(result["content"][0]["text"]) == [{"id": "s1", "name": "skill-a"}]


def test_tools_call_savings_report(monkeypatch):
    async def fake_latest(organization_id):
        return {"savings": 0.6, "savings_rate": 0.6}

    async def fake_dashboard(organization_id, **kwargs):
        return {
            "days": 30,
            "models": [],
            "total": {"tokens": 0, "cost": 0.0, "calls": 0},
        }

    monkeypatch.setattr(mcp_server_module, "latest_savings", fake_latest)
    monkeypatch.setattr(mcp_server_module, "token_dashboard", fake_dashboard)
    client = _client(monkeypatch)

    response = _rpc(
        client, "tools/call", {"name": "agenthub.savings_report", "arguments": {}}
    )
    assert response.status_code == 200
    result = response.json()["result"]
    assert result["isError"] is False
    payload = json.loads(result["content"][0]["text"])
    assert payload["available"] is True
    assert payload["savings"]["savings"] == 0.6


def test_tools_call_health(monkeypatch):
    client = _client(monkeypatch)
    response = _rpc(client, "tools/call", {"name": "agenthub.health", "arguments": {}})
    assert response.status_code == 200
    result = response.json()["result"]
    assert result["isError"] is False
    payload = json.loads(result["content"][0]["text"])
    assert payload["service"] == "agenthub"
    assert payload["database"] is True


def test_unknown_tool(monkeypatch):
    client = _client(monkeypatch)
    response = _rpc(client, "tools/call", {"name": "agenthub.nope", "arguments": {}})
    assert response.status_code == 200
    result = response.json()["result"]
    assert result["isError"] is True


def test_unauthenticated(monkeypatch):
    _allow_rate_limit(monkeypatch)
    monkeypatch.delitem(app.dependency_overrides, get_current_user, raising=False)
    monkeypatch.delitem(app.dependency_overrides, get_db, raising=False)
    client = TestClient(app)

    response = _rpc(client, "initialize")
    assert response.status_code == 401


def test_internal_error_is_error_not_500(monkeypatch):
    async def boom(organization_id):
        raise RuntimeError("db down")

    monkeypatch.setattr(mcp_server_module, "latest_savings", boom)
    client = _client(monkeypatch)

    response = _rpc(
        client, "tools/call", {"name": "agenthub.savings_report", "arguments": {}}
    )
    assert response.status_code == 200
    result = response.json()["result"]
    assert result["isError"] is True

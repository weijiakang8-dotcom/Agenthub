from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

import pytest

from app.engine import tools

ORG_A = uuid.uuid4()
ORG_B = uuid.uuid4()


class CapturingConnection:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.statement = None
        self.params = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def execute(self, statement, params=None):
        self.statement = str(statement)
        self.params = params
        return SimpleNamespace(fetchall=lambda: self.rows)


class CapturingEngine:
    def __init__(self, rows=()):
        self.connection = CapturingConnection(rows)

    def connect(self):
        return self.connection


def _run(sql: str, org) -> dict:
    return asyncio.run(tools.run_query_db(sql, org))


@pytest.mark.parametrize(
    "sql",
    [
        "update agents set name='x'",
        "select * from agents; drop table agents",
        "delete from agents",
    ],
)
def test_query_db_rejects_unsafe_or_multi_statement(sql):
    result = _run(sql, ORG_A)

    assert result["status"] == "failed"
    assert "Only a single read-only SELECT is allowed" in result["error"]


def test_query_db_requires_tenant_context():
    result = _run("select id, name from agents", None)

    assert result["status"] == "failed"
    assert "tenant" in result["error"].lower()


def test_query_db_rejects_sensitive_table():
    for table in ("users", "organizations", "model_configs", "api_keys", "audit_logs"):
        result = _run(f"select * from {table}", ORG_A)
        assert result["status"] == "failed"
        assert "not accessible" in result["error"].lower()


def test_query_db_rejects_complex_bypass_constructs():
    bypasses = [
        "select a.id from agents a join workflows w on a.id = w.id",
        "select * from agents union select * from workflows",
        "select * from agents where id in (select id from workflows)",
        "select * from agents -- comment",
        "select * from agents; select * from workflows",
    ]
    for sql in bypasses:
        result = _run(sql, ORG_A)
        assert result["status"] == "failed", sql


def test_query_db_tenant_a_query_is_scoped_to_tenant_a(monkeypatch):
    row = SimpleNamespace(_mapping={"id": 1, "name": "research"})
    engine = CapturingEngine(rows=[row])
    monkeypatch.setattr(tools, "engine", engine)

    result = _run("select id, name from agents", ORG_A)

    assert result == {
        "status": "success",
        "data": [{"id": 1, "name": "research"}],
        "error": None,
    }
    assert "organization_id = :org" in engine.connection.statement
    assert engine.connection.params == {"org": str(ORG_A)}


def test_query_db_cannot_bypass_tenant_filter_with_or_clause(monkeypatch):
    engine = CapturingEngine(rows=[])
    monkeypatch.setattr(tools, "engine", engine)

    result = _run(
        "select * from agents where organization_id = 'tenant-b' or 1=1",
        ORG_A,
    )

    assert result["status"] == "success"
    statement = engine.connection.statement
    assert "and organization_id = :org" in statement.lower()
    assert engine.connection.params == {"org": str(ORG_A)}


def test_query_db_legal_query_passes(monkeypatch):
    row = SimpleNamespace(_mapping={"id": 2, "name": "analyze"})
    engine = CapturingEngine(rows=[row])
    monkeypatch.setattr(tools, "engine", engine)

    result = _run("select id, name from agents limit 5", ORG_B)

    assert result["status"] == "success"
    assert result["data"] == [{"id": 2, "name": "analyze"}]
    assert engine.connection.params == {"org": str(ORG_B)}


def test_query_db_aggregate_count_passes(monkeypatch):
    row = SimpleNamespace(_mapping={"count": 3})
    engine = CapturingEngine(rows=[row])
    monkeypatch.setattr(tools, "engine", engine)

    result = _run("select count(*) from executions", ORG_A)

    assert result["status"] == "success"
    assert result["data"] == [{"count": 3}]
    assert "organization_id = :org" in engine.connection.statement
    assert engine.connection.params == {"org": str(ORG_A)}


def test_query_db_aggregate_with_where_is_scoped(monkeypatch):
    row = SimpleNamespace(_mapping={"total": 7})
    engine = CapturingEngine(rows=[row])
    monkeypatch.setattr(tools, "engine", engine)

    result = _run(
        "select sum(id) from tool_calls where status = 'success'",
        ORG_B,
    )

    assert result["status"] == "success"
    assert "status = 'success'" in engine.connection.statement
    assert "and organization_id = :org" in engine.connection.statement.lower()
    assert engine.connection.params == {"org": str(ORG_B)}


def test_query_db_aggregate_rejects_unsafe_constructs(monkeypatch):
    engine = CapturingEngine(rows=[])
    monkeypatch.setattr(tools, "engine", engine)

    for sql in (
        "select count(*) from agents join workflows on true",
        "select count(*) from agents order by count(*)",
        "select count(*) from agents; drop table agents",
        "select count(*) from users",
    ):
        result = _run(sql, ORG_A)
        assert result["status"] == "failed", sql


def test_search_knowledge_requires_tenant_and_query():
    result = asyncio.run(tools.run_search_knowledge("anything", None))
    assert result["status"] == "failed"
    assert "tenant" in result["error"].lower()

    result = asyncio.run(tools.run_search_knowledge("", ORG_A))
    assert result["status"] == "failed"
    assert "query" in result["error"].lower()


def test_search_knowledge_is_tenant_scoped(monkeypatch):
    captured = {}

    async def fake_retrieve(query, org_id, top_k=5, correlation_id=None):
        captured["org_id"] = org_id
        captured["query"] = query
        return [{"name": "doc", "content": "chunk", "score": 0.9}]

    monkeypatch.setattr(
        "app.rag.retrieval.retrieve_chunks",
        fake_retrieve,
    )
    result = asyncio.run(tools.run_search_knowledge("退款政策", ORG_A, top_k=3))

    assert result["status"] == "success"
    assert captured["org_id"] == ORG_A
    assert captured["query"] == "退款政策"


def test_recall_memory_requires_tenant_user_and_query():
    result = asyncio.run(tools.run_recall_memory("anything", None, user_id="u"))
    assert result["status"] == "failed"
    assert "tenant" in result["error"].lower()

    result = asyncio.run(tools.run_recall_memory("anything", ORG_A, user_id=None))
    assert result["status"] == "failed"
    assert "user" in result["error"].lower()

    result = asyncio.run(tools.run_recall_memory("", ORG_A, user_id="u"))
    assert result["status"] == "failed"
    assert "query" in result["error"].lower()


def test_recall_memory_is_user_and_tenant_scoped(monkeypatch):
    captured = {}

    async def fake_retrieve(**kwargs):
        captured.update(kwargs)
        return [{"kind": "fact", "content": "用户偏好"}]

    monkeypatch.setattr(
        "app.memory.service.retrieve_memories",
        fake_retrieve,
    )
    result = asyncio.run(tools.run_recall_memory("偏好", ORG_A, user_id=ORG_B, top_k=2))

    assert result["status"] == "success"
    assert captured["user_id"] == ORG_B
    assert captured["organization_id"] == ORG_A
    assert captured["query"] == "偏好"
    assert captured["top_k"] == 2


def test_recall_memory_reads_user_from_tool_context(monkeypatch):
    captured = {}

    async def fake_retrieve(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(
        "app.memory.service.retrieve_memories",
        fake_retrieve,
    )
    from app.engine.tool_executor import current_tool_user_id

    token = current_tool_user_id.set(str(ORG_B))
    try:
        result = asyncio.run(tools.run_recall_memory("偏好", ORG_A))
    finally:
        current_tool_user_id.reset(token)

    assert result["status"] == "success"
    assert captured["user_id"] == ORG_B


def test_recall_executions_requires_tenant(monkeypatch):
    class FakeResult:
        def scalars(self):
            return SimpleNamespace(all=list)

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def execute(self, _stmt):
            return FakeResult()

    monkeypatch.setattr(
        "app.database.async_session_factory",
        lambda: FakeSession(),
    )
    result = asyncio.run(tools.run_recall_executions(None, user_id="u"))
    assert result["status"] == "failed"
    assert "tenant" in result["error"].lower()

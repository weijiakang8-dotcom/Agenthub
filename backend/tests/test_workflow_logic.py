from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.routes import workflows


class FakeScalarResult:
    def __init__(self, value=None, values=None):
        self.value = value
        self.values = values or []

    def scalar(self):
        return self.value

    def scalars(self):
        return SimpleNamespace(
            all=lambda: self.values,
            first=lambda: self.values[0] if self.values else None,
        )


class FakeSession:
    def __init__(self, get_result=None, execute_result=None):
        self.get_result = get_result
        self.execute_result = execute_result
        self.added = []
        self.deleted = []
        self.commits = 0

    async def get(self, _model, _obj_id):
        return self.get_result

    async def execute(self, _stmt):
        if self.execute_result is None:
            raise AssertionError("no execute result configured")
        return self.execute_result

    def add(self, obj):
        self.added.append(obj)

    async def delete(self, obj):
        self.deleted.append(obj)

    async def commit(self):
        self.commits += 1


def make_workflow(dag_definition):
    return SimpleNamespace(
        id=uuid.uuid4(),
        dag_definition=dag_definition,
        name="wf",
        description="desc",
        agent_chain=[],
    )


def test_validate_dag_accepts_acyclic_graph():
    workflow = make_workflow(
        {
            "nodes": [{"id": "a"}, {"id": "b"}],
            "edges": [{"source": "a", "target": "b"}],
        }
    )

    result = asyncio.run(
        workflows.validate_dag(workflow.id, FakeSession(get_result=workflow))
    )

    assert result == {"valid": True, "issues": []}


def test_validate_dag_reports_orphan_and_cycle():
    workflow = make_workflow(
        {
            "nodes": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
            "edges": [
                {"source": "a", "target": "b"},
                {"source": "b", "target": "a"},
            ],
        }
    )

    result = asyncio.run(
        workflows.validate_dag(workflow.id, FakeSession(get_result=workflow))
    )

    assert result["valid"] is False
    assert any("孤立节点" in issue for issue in result["issues"])
    assert any("环" in issue for issue in result["issues"])


def test_validate_dag_requires_nodes():
    workflow = make_workflow({"nodes": [], "edges": []})

    result = asyncio.run(
        workflows.validate_dag(workflow.id, FakeSession(get_result=workflow))
    )

    assert result == {"valid": False, "issues": ["DAG 缺少节点"]}


def test_snapshot_version_increments_existing_version():
    workflow = SimpleNamespace(
        id=uuid.uuid4(),
        name="wf",
        description="desc",
        agent_chain=[],
        created_by="user",
    )
    session = FakeSession(execute_result=FakeScalarResult(value=2))

    version = asyncio.run(workflows._snapshot_version(session, workflow, "update"))

    assert version.version == 3
    assert version.changelog == "update"
    assert session.added == [version]


def test_delete_workflow_rejects_active_execution():
    workflow = make_workflow({"nodes": [{"id": "a"}]})
    execution = SimpleNamespace(id=uuid.uuid4())
    result = FakeScalarResult(values=[execution])
    session = FakeSession(get_result=workflow, execute_result=result)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(workflows.delete_workflow(workflow.id, session))

    assert exc.value.status_code == 409
    assert session.deleted == []


def test_delete_workflow_allows_inactive_workflow():
    workflow = make_workflow({"nodes": [{"id": "a"}]})
    session = FakeSession(
        get_result=workflow,
        execute_result=FakeScalarResult(values=[]),
    )

    result = asyncio.run(workflows.delete_workflow(workflow.id, session))

    assert result is None
    assert session.deleted == [workflow]
    assert session.commits == 1

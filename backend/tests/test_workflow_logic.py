from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

import pytest
from app.api.routes import workflows
from fastapi import HTTPException


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
    return make_workflow_for_org(dag_definition, uuid.uuid4())


def make_workflow_for_org(dag_definition, organization_id):
    return SimpleNamespace(
        id=uuid.uuid4(),
        organization_id=organization_id,
        dag_definition=dag_definition,
        name="wf",
        description="desc",
        agent_chain=[],
    )


def make_user(organization_id=None):
    return SimpleNamespace(id=uuid.uuid4(), organization_id=organization_id)


def test_validate_dag_accepts_acyclic_graph():
    user = make_user()
    workflow = make_workflow(
        {
            "nodes": [{"id": "a"}, {"id": "b"}],
            "edges": [{"source": "a", "target": "b"}],
        }
    )
    workflow.organization_id = user.organization_id

    result = asyncio.run(
        workflows.validate_dag(workflow.id, FakeSession(get_result=workflow), user=user)
    )

    assert result == {"valid": True, "issues": []}


def test_validate_dag_reports_orphan_and_cycle():
    user = make_user()
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
        workflows.validate_dag(workflow.id, FakeSession(get_result=workflow), user=user)
    )

    assert result["valid"] is False
    assert any("孤立节点" in issue for issue in result["issues"])
    assert any("环" in issue for issue in result["issues"])


def test_validate_dag_requires_nodes():
    user = make_user()
    workflow = make_workflow({"nodes": [], "edges": []})
    workflow.organization_id = user.organization_id

    result = asyncio.run(
        workflows.validate_dag(workflow.id, FakeSession(get_result=workflow), user=user)
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
    user = make_user()
    workflow = make_workflow({"nodes": [{"id": "a"}]})
    workflow.organization_id = user.organization_id
    execution = SimpleNamespace(id=uuid.uuid4())
    result = FakeScalarResult(values=[execution])
    session = FakeSession(get_result=workflow, execute_result=result)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(workflows.delete_workflow(workflow.id, session, user=user))

    assert exc.value.status_code == 409
    assert session.deleted == []


def test_delete_workflow_allows_inactive_workflow():
    user = make_user()
    workflow = make_workflow({"nodes": [{"id": "a"}]})
    workflow.organization_id = user.organization_id
    session = FakeSession(
        get_result=workflow,
        execute_result=FakeScalarResult(values=[]),
    )

    result = asyncio.run(workflows.delete_workflow(workflow.id, session, user=user))

    assert result is None
    assert session.deleted == [workflow]
    assert session.commits == 1


@pytest.mark.parametrize(
    "operation",
    [
        "list_versions",
        "create_version",
        "rollback",
        "validate",
        "delete",
    ],
)
def test_workflow_operations_reject_cross_org(operation):
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    workflow = make_workflow_for_org({"nodes": [{"id": "a"}]}, org_b)
    session = FakeSession(
        get_result=workflow,
        execute_result=FakeScalarResult(values=[]),
    )
    user_a = make_user(org_a)

    with pytest.raises(HTTPException) as exc:
        if operation == "list_versions":
            asyncio.run(
                workflows.list_workflow_versions(workflow.id, session, user=user_a)
            )
        elif operation == "create_version":
            asyncio.run(
                workflows.create_workflow_version(workflow.id, session, user=user_a)
            )
        elif operation == "rollback":
            asyncio.run(
                workflows.rollback_workflow(workflow.id, 1, session, user=user_a)
            )
        elif operation == "validate":
            asyncio.run(workflows.validate_dag(workflow.id, session, user=user_a))
        elif operation == "delete":
            asyncio.run(workflows.delete_workflow(workflow.id, session, user=user_a))

    assert exc.value.status_code == 404

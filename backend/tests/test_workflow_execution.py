from __future__ import annotations

import uuid
from types import SimpleNamespace

from app.engine import planner, runner


def make_workflow(dag_definition=None, agent_chain=None):
    return SimpleNamespace(
        dag_definition=dag_definition,
        agent_chain=agent_chain if agent_chain is not None else [],
    )


def test_build_plan_from_dag_nodes_maps_to_capabilities():
    workflow = make_workflow(
        dag_definition={
            "nodes": [
                {"type": "research", "label": "research"},
                {"type": "condition", "label": "check"},
                {"type": "human_approval", "label": "approve"},
            ]
        }
    )
    plan = runner.build_plan_from_workflow(workflow)
    assert [step["capability"] for step in plan] == [
        "research",
        "analysis",
        "send_email",
    ]


def test_build_plan_from_agent_chain_maps_roles():
    workflow = make_workflow(agent_chain=[str(uuid.uuid4()), str(uuid.uuid4())])
    plan = runner.build_plan_from_workflow(workflow)
    assert [step["capability"] for step in plan] == ["research", "analysis"]


def test_build_plan_without_explicit_definition_is_none():
    assert runner.build_plan_from_workflow(make_workflow()) is None


def test_planner_parse_plan_rejects_unknown_capabilities():
    parsed = planner.parse_plan(
        '{"steps":[{"capability":"answer","description":"x"},'
        '{"capability":"not_real","description":"y"}]}'
    )
    assert parsed is not None
    assert [step["capability"] for step in parsed["steps"]] == ["answer"]


def test_planner_fallback_plan_is_single_answer_step():
    plan = planner.fallback_plan("hello")
    assert plan["steps"] == [{"capability": "answer", "description": "hello"}]

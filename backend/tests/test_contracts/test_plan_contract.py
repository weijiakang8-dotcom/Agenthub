from __future__ import annotations

import asyncio
import json

from app.engine import planner
from langchain_core.messages import AIMessage


def test_max_steps_is_six():
    assert planner.MAX_PLAN_STEPS == 6
    text = (
        '{"steps":['
        + ",".join(f'{{"capability":"answer","description":"s{i}"}}' for i in range(8))
        + "]}"
    )
    plan = planner.parse_plan(text)
    assert plan is not None
    assert len(plan["steps"]) == 6


def test_unknown_capability_is_rejected_from_plan():
    plan = planner.parse_plan(
        '{"steps":[{"capability":"answer","description":"x"},'
        '{"capability":"delete_database","description":"y"}]}'
    )
    assert [step["capability"] for step in plan["steps"]] == ["answer"]


def test_all_unknown_capabilities_produce_plan_invalid():
    plan = planner.parse_plan(
        '{"goal":"x","risk":"LOW",'
        '"steps":[{"capability":"delete_database","description":"y"},'
        '{"capability":"drop_table","description":"z"}]}'
    )
    assert planner.is_plan_invalid(plan)
    assert plan["plan_invalid"] is True
    assert "plan_invalid" in plan

    # Planner.plan 也不得静默降级为 fallback_plan
    class JunkGateway:
        async def select(self, **kwargs):
            return [object()]

        async def invoke(self, *args, **kwargs):
            return AIMessage(
                content=json.dumps(
                    {
                        "goal": "x",
                        "risk": "LOW",
                        "steps": [{"capability": "delete_database"}],
                    }
                )
            )

    result = asyncio.run(
        planner.Planner(gateway=JunkGateway()).plan(
            "删库", organization_id=None, user_id=None
        )
    )
    assert planner.is_plan_invalid(result)
    assert result != planner.fallback_plan("删库")


def test_plan_step_schema_fields():
    plan = planner.parse_plan(
        json.dumps(
            {
                "goal": "查询销售数据并发送报告",
                "risk": "SIDE_EFFECT",
                "steps": [
                    {
                        "step_id": "gather",
                        "capability": "query_db",
                        "description": "查询销售",
                        "input_refs": ["原始输入"],
                        "output_name": "sales",
                        "depends_on": [],
                    },
                    {
                        "step_id": "synthesize",
                        "capability": "analysis",
                        "description": "分析",
                        "input_refs": ["sales"],
                        "output_name": "report",
                        "depends_on": ["gather"],
                    },
                    {
                        "step_id": "commit",
                        "capability": "send_email",
                        "description": "发送",
                        "input_refs": ["report"],
                        "output_name": None,
                        "depends_on": ["synthesize"],
                    },
                ],
                "reason": "Gather → Synthesize → Commit",
            }
        )
    )
    assert not planner.is_plan_invalid(plan)
    assert plan["goal"] == "查询销售数据并发送报告"
    assert plan["risk"] == "SIDE_EFFECT"
    expected_fields = {
        "step_id",
        "capability",
        "description",
        "input_refs",
        "output_name",
        "depends_on",
        "condition",
        "side_effect",
        "requires_approval",
    }
    for step in plan["steps"]:
        assert expected_fields <= set(step)
    assert [step["step_id"] for step in plan["steps"]] == [
        "gather",
        "synthesize",
        "commit",
    ]
    assert plan["steps"][0]["side_effect"] is False
    assert plan["steps"][0]["requires_approval"] is False
    assert plan["steps"][2]["side_effect"] is True
    assert plan["steps"][2]["requires_approval"] is True


def test_side_effect_must_come_from_registry():
    # Planner 输出伪造风险字段时，Registry 静态声明必须覆盖
    plan = planner.parse_plan(
        json.dumps(
            {
                "goal": "查询",
                "risk": "SIDE_EFFECT",
                "steps": [
                    {
                        "step_id": "q",
                        "capability": "query_db",
                        "description": "只读查询",
                        "side_effect": True,
                        "requires_approval": True,
                    }
                ],
            }
        )
    )
    assert not planner.is_plan_invalid(plan)
    assert plan["steps"][0]["side_effect"] is False
    assert plan["steps"][0]["requires_approval"] is False

    # 手工构造的伪造计划必须被校验器拒绝
    forged = {
        "goal": "查询",
        "risk": "SIDE_EFFECT",
        "steps": [
            {
                "step_id": "q",
                "capability": "query_db",
                "description": "只读查询",
                "input_refs": [],
                "output_name": None,
                "depends_on": [],
                "condition": None,
                "side_effect": True,
                "requires_approval": True,
            }
        ],
    }
    valid, errors = planner.validate_plan(forged)
    assert valid is False
    assert any("Registry" in error for error in errors)


def test_plan_dag_validation():
    base = {
        "goal": "分析",
        "risk": "MEDIUM",
        "steps": [
            {
                "step_id": "a",
                "capability": "query_db",
                "description": "查询",
                "input_refs": [],
                "output_name": "data",
                "depends_on": [],
                "condition": None,
                "side_effect": False,
                "requires_approval": False,
            },
            {
                "step_id": "b",
                "capability": "analysis",
                "description": "分析",
                "input_refs": ["data"],
                "output_name": "report",
                "depends_on": ["a"],
                "condition": None,
                "side_effect": False,
                "requires_approval": False,
            },
        ],
    }
    valid, errors = planner.validate_plan(base)
    assert valid is True
    assert errors == []

    missing_dep = {
        **base,
        "steps": [
            {**base["steps"][0], "step_id": "a"},
            {**base["steps"][1], "step_id": "b", "depends_on": ["ghost"]},
        ],
    }
    valid, errors = planner.validate_plan(missing_dep)
    assert valid is False
    assert any("dependency ghost" in error for error in errors)

    cycle = {
        **base,
        "steps": [
            {**base["steps"][0], "step_id": "a", "depends_on": ["b"]},
            {**base["steps"][1], "step_id": "b", "depends_on": ["a"]},
        ],
    }
    valid, errors = planner.validate_plan(cycle)
    assert valid is False
    assert any("cycle" in error for error in errors)

from __future__ import annotations

import asyncio

from app.engine.canonical import params_canonical
from app.engine.executor import Approval, BudgetLimits, execute_with_gates
from app.engine.planner import compute_plan_hash, side_effect_step_ids


def _step(step_id, capability, *, side_effect=None, depends_on=None, output_name=None):
    spec = {
        "step_id": step_id,
        "capability": capability,
        "description": f"step {step_id}",
        "input_refs": [],
        "output_name": output_name,
        "depends_on": depends_on or [],
        "condition": None,
    }
    if side_effect is not None:
        spec["side_effect"] = side_effect
    return spec


def _read_only_plan():
    return {
        "goal": "查询并分析",
        "risk": "MEDIUM",
        "steps": [
            {
                **_step("gather", "query_db", output_name="data"),
                "side_effect": False,
                "requires_approval": False,
            },
            {
                **_step("synthesize", "analysis", depends_on=["gather"]),
                "side_effect": False,
                "requires_approval": False,
            },
        ],
    }


def _side_effect_plan():
    email_params = {"to": "test@example.com", "subject": "x", "body": "y"}
    return {
        "goal": "查询并发邮件",
        "risk": "SIDE_EFFECT",
        "steps": [
            {
                **_step("gather", "query_db", output_name="data"),
                "side_effect": False,
                "requires_approval": False,
            },
            {
                **_step("commit", "send_email", depends_on=["gather"]),
                "side_effect": True,
                "requires_approval": True,
            },
        ],
        "side_effect_proposals": [
            {
                "step_id": "commit",
                "capability": "send_email",
                "tool": "send_email",
                "params": email_params,
                "params_canonical": params_canonical(
                    email_params, tool_name="send_email"
                ),
            }
        ],
    }


def _approval_for(plan, *, approved=True):
    return Approval(
        plan_hash=compute_plan_hash(plan),
        approval_id="approval-1",
        approved_side_effect_set=side_effect_step_ids(plan),
        approved_proposals=tuple(plan.get("side_effect_proposals") or []),
        approved=approved,
    )


async def _ok_step(step, outputs):
    return {
        "status": "success",
        "data": f"out-{step['step_id']}",
        "tokens": 10,
        "cost": 0.01,
    }


def test_invalid_plan_emits_plan_invalid():
    forged = {
        "goal": "查询",
        "risk": "SIDE_EFFECT",
        "steps": [
            {
                **_step("q", "query_db"),
                "side_effect": True,  # Registry 未声明，校验必须拒绝
                "requires_approval": True,
            }
        ],
    }
    audits: list[dict] = []

    async def collect_audit(event):
        audits.append(event)

    result = asyncio.run(
        execute_with_gates(
            forged,
            intent_category="TASK",
            run_step=_ok_step,
            audit=collect_audit,
        )
    )
    assert result.status == "plan_invalid"
    assert result.plan_invalid is True
    assert result.invalid_reason
    assert any(event["action"] == "plan_invalid" for event in audits)


def test_validation_precedes_approval():
    # 非法计划即使带了 Approval 也必须 plan_invalid，不允许先审批
    forged = {
        "goal": "查询",
        "risk": "LOW",
        "steps": [
            {
                **_step("q", "query_db"),
                "side_effect": True,
                "requires_approval": True,
            }
        ],
    }
    result = asyncio.run(
        execute_with_gates(
            forged,
            intent_category="ACTION",
            approval=Approval(
                plan_hash="hash",
                approval_id="a1",
                approved_side_effect_set=("q",),
            ),
            run_step=_ok_step,
        )
    )
    assert result.status == "plan_invalid"

    # 合法副作用计划必须先完成 Validation 才进入 Approval 闸门
    executed: list[str] = []

    async def tracking_step(step, outputs):
        executed.append(step["step_id"])
        return await _ok_step(step, outputs)

    result = asyncio.run(
        execute_with_gates(
            _side_effect_plan(),
            intent_category="ACTION",
            run_step=tracking_step,
        )
    )
    assert result.status == "approval_required"
    assert result.approval_required is True
    assert result.plan_hash == compute_plan_hash(_side_effect_plan())
    assert executed == []  # 未审批前不得执行任何步骤


def test_read_only_budget_exceeded_graceful():
    audits: list[dict] = []

    async def collect_audit(event):
        audits.append(event)

    result = asyncio.run(
        execute_with_gates(
            _read_only_plan(),
            intent_category="TASK",
            limits=BudgetLimits(max_steps=1),
            run_step=_ok_step,
            audit=collect_audit,
        )
    )
    assert result.status == "budget_exceeded"
    assert result.budget_exceeded is True
    assert result.hard_stop is False
    assert result.executed_step_ids == ["gather"]
    assert result.node_outputs.get("data") == "out-gather"  # 已有结果保留
    assert any(
        event["action"] == "budget_exceeded" and event["hard"] is False
        for event in audits
    )


def test_side_effect_budget_exceeded_hard_stop():
    audits: list[dict] = []
    side_effect_calls: list[str] = []
    replan_calls: list[str] = []

    async def collect_audit(event):
        audits.append(event)

    async def tracking_step(step, outputs):
        if step.get("side_effect"):
            side_effect_calls.append(step["step_id"])
        return await _ok_step(step, outputs)

    async def fake_replan(plan, reason):
        replan_calls.append(reason)

    result = asyncio.run(
        execute_with_gates(
            _side_effect_plan(),
            intent_category="ACTION",
            limits=BudgetLimits(max_steps=1),
            approval=_approval_for(_side_effect_plan()),
            run_step=tracking_step,
            audit=collect_audit,
            replan=fake_replan,
        )
    )
    assert result.status == "budget_exceeded"
    assert result.budget_exceeded is True
    assert result.hard_stop is True
    assert side_effect_calls == []  # 副作用步骤未执行
    assert replan_calls == []  # 副作用预算超限禁止 replan
    assert any(
        event["action"] == "budget_exceeded" and event["hard"] is True
        for event in audits
    )


def test_side_effect_steps_never_parallel():
    email_1_params = {"to": "one@example.com", "subject": "s1", "body": "b1"}
    email_2_params = {"to": "two@example.com", "subject": "s2", "body": "b2"}
    plan = {
        "goal": "发两封邮件",
        "risk": "SIDE_EFFECT",
        "steps": [
            {
                **_step("email_1", "send_email"),
                "side_effect": True,
                "requires_approval": True,
            },
            {
                **_step("email_2", "send_email", depends_on=["email_1"]),
                "side_effect": True,
                "requires_approval": True,
            },
        ],
        "side_effect_proposals": [
            {
                "step_id": "email_1",
                "capability": "send_email",
                "tool": "send_email",
                "params": email_1_params,
                "params_canonical": params_canonical(
                    email_1_params, tool_name="send_email"
                ),
            },
            {
                "step_id": "email_2",
                "capability": "send_email",
                "tool": "send_email",
                "params": email_2_params,
                "params_canonical": params_canonical(
                    email_2_params, tool_name="send_email"
                ),
            },
        ],
    }
    active = 0
    max_active = 0
    order: list[str] = []

    async def tracked_step(step, outputs):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        order.append(step["step_id"])
        active -= 1
        return await _ok_step(step, outputs)

    result = asyncio.run(
        execute_with_gates(
            plan,
            intent_category="ACTION",
            approval=_approval_for(plan),
            run_step=tracked_step,
        )
    )
    assert result.status == "completed"
    assert order == ["email_1", "email_2"]
    assert max_active == 1
    assert result.max_active_steps == 1

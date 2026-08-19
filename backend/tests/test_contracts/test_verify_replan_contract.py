from __future__ import annotations

import asyncio

from app.engine.canonical import params_canonical
from app.engine.executor import (
    Approval,
    execute_with_gates,
    replan_read_only,
    should_verify,
)
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


def _plan(risk, steps, proposals=None):
    plan = {"goal": "任务", "risk": risk, "steps": steps}
    if proposals is not None:
        plan["side_effect_proposals"] = proposals
    return plan


def _low_plan():
    return _plan(
        "LOW",
        [
            {
                **_step("answer_1", "answer", output_name="final_output"),
                "side_effect": False,
                "requires_approval": False,
            }
        ],
    )


def _medium_plan():
    return _plan(
        "MEDIUM",
        [
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
    )


def _high_plan():
    return _plan(
        "HIGH",
        [
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
            {
                **_step("conclude", "answer", depends_on=["synthesize"]),
                "side_effect": False,
                "requires_approval": False,
            },
        ],
    )


def _side_effect_plan():
    email_params = {"to": "test@example.com", "subject": "x", "body": "y"}
    return _plan(
        "SIDE_EFFECT",
        [
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
        proposals=[
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
    )


def _approval_for(plan):
    return Approval(
        plan_hash=compute_plan_hash(plan),
        approval_id="approval-1",
        approved_side_effect_set=side_effect_step_ids(plan),
        approved_proposals=tuple(plan.get("side_effect_proposals") or []),
    )


async def _ok_step(step, outputs):
    return {
        "status": "success",
        "data": f"out-{step['step_id']}",
        "tokens": 10,
        "cost": 0.01,
    }


def test_low_medium_task_skips_verify():
    assert should_verify("CHAT", _low_plan()) is False
    assert should_verify("KNOWLEDGE", _low_plan()) is False
    assert should_verify("TASK", _low_plan()) is False
    assert should_verify("TASK", _medium_plan()) is False
    assert should_verify("TASK", _high_plan()) is True
    assert should_verify("ACTION", _side_effect_plan()) is True

    verify_calls: list[str] = []

    async def fake_verify(goal, outputs):
        verify_calls.append(goal)
        return "PASS"

    result = asyncio.run(
        execute_with_gates(
            _medium_plan(),
            intent_category="TASK",
            run_step=_ok_step,
            verify=fake_verify,
        )
    )
    assert result.status == "completed"
    assert verify_calls == []  # LOW/MEDIUM TASK 不进入 Verify


def test_verify_has_no_task_authority():
    verify_calls: list[str] = []

    async def fake_verify(goal, outputs):
        verify_calls.append(goal)
        return "FAIL"  # Verify 只输出 PASS/FAIL，不产生新任务

    result = asyncio.run(
        execute_with_gates(
            _high_plan(),
            intent_category="TASK",
            run_step=_ok_step,
            verify=fake_verify,
        )
    )
    assert result.status == "verify_failed"
    assert result.verify_result == "FAIL"
    assert verify_calls == ["任务"]
    # Verify 没有新增/修改任何执行步骤
    assert result.executed_step_ids == ["gather", "synthesize", "conclude"]


def test_replan_limited_to_read_only_steps():
    plan = _side_effect_plan()
    # 重排只读步骤（副作用集合不变）→ 允许
    reordered = _plan(
        "SIDE_EFFECT",
        [
            {**_side_effect_plan()["steps"][0], "step_id": "gather"},
            {**_side_effect_plan()["steps"][1], "step_id": "commit"},
        ],
    )
    assert replan_read_only(plan, reordered) is not None

    # 新增副作用步骤 → 拒绝
    extra_side_effect = _plan(
        "SIDE_EFFECT",
        [
            {**_side_effect_plan()["steps"][0]},
            {**_side_effect_plan()["steps"][1]},
            {
                **_step("commit_2", "send_email", depends_on=["commit"]),
                "side_effect": True,
                "requires_approval": True,
            },
        ],
    )
    assert replan_read_only(plan, extra_side_effect) is None

    # 降级只读步骤（删除只读步骤）→ 允许
    downgraded = _plan(
        "SIDE_EFFECT",
        [
            {
                **_step("commit", "send_email"),
                "side_effect": True,
                "requires_approval": True,
            }
        ],
    )
    assert replan_read_only(plan, downgraded) is not None

    # 执行链路：只读失败 → 只读 replan 成功，副作用集合不变
    fail_once = {"failed": False}
    replan_calls: list[str] = []
    side_effect_calls: list[str] = []

    async def flaky_step(step, outputs):
        if step["step_id"] == "gather" and not fail_once["failed"]:
            fail_once["failed"] = True
            return {"status": "failed", "error": "temporary read failure"}
        if step.get("side_effect"):
            side_effect_calls.append(step["step_id"])
        return await _ok_step(step, outputs)

    async def fake_replan(original, reason):
        replan_calls.append(reason)
        return downgraded

    result = asyncio.run(
        execute_with_gates(
            plan,
            intent_category="ACTION",
            approval=_approval_for(plan),
            run_step=flaky_step,
            replan=fake_replan,
        )
    )
    assert result.status == "completed"
    assert result.replanned is True
    assert side_effect_calls == ["commit"]


def test_replan_revalidates_and_reapproves():
    plan = _side_effect_plan()

    # replan 产物必须重新通过全部 Validation（非法候选 → 拒绝）
    invalid_candidate = {
        "goal": "任务",
        "risk": "SIDE_EFFECT",
        "steps": [
            {
                **_step("ghost", "query_db"),
                "side_effect": True,  # Registry 未声明
                "requires_approval": True,
            }
        ],
    }
    assert replan_read_only(plan, invalid_candidate) is None

    audits: list[dict] = []

    async def collect_audit(event):
        audits.append(event)

    async def failing_step(step, outputs):
        if step["step_id"] == "gather":
            return {"status": "failed", "error": "boom"}
        return await _ok_step(step, outputs)

    async def bad_replan(original, reason):
        return invalid_candidate

    result = asyncio.run(
        execute_with_gates(
            plan,
            intent_category="ACTION",
            approval=_approval_for(plan),
            run_step=failing_step,
            audit=collect_audit,
            replan=bad_replan,
        )
    )
    assert result.status == "failed"
    assert result.invalid_reason.startswith("replan rejected")
    assert any(event["action"] == "replan_rejected" for event in audits)

    # 合法 replan（副作用集合不变）在旧 Approval 下继续，无需重新审批
    reordered = _plan(
        "SIDE_EFFECT",
        [
            {
                **_step("commit", "send_email"),
                "side_effect": True,
                "requires_approval": True,
            },
            {
                **_step("gather", "query_db", output_name="data"),
                "side_effect": False,
                "requires_approval": False,
            },
        ],
    )
    fail_once = {"failed": False}

    async def flaky_step(step, outputs):
        if step["step_id"] == "gather" and not fail_once["failed"]:
            fail_once["failed"] = True
            return {"status": "failed", "error": "retry read-only"}
        return await _ok_step(step, outputs)

    async def good_replan(original, reason):
        return reordered

    result = asyncio.run(
        execute_with_gates(
            plan,
            intent_category="ACTION",
            approval=_approval_for(plan),
            run_step=flaky_step,
            replan=good_replan,
        )
    )
    assert result.status == "completed"
    assert result.replanned is True

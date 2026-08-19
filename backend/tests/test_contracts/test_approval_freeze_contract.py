"""Phase 6A Frozen Contract：Approval 参数冻结。

契约来源：Pro FINAL DECISION（Approval 参数冻结粒度 = C）。
"""

from __future__ import annotations

import asyncio

from app.engine import canonical, planner
from app.engine.approval import (
    proposal_mismatch_reason,
    resume_approval_decision,
    same_side_effect_proposals,
)
from app.engine.executor import Approval, execute_with_gates, replan_read_only


def _step(step_id, capability, *, side_effect=None, depends_on=None):
    spec = {
        "step_id": step_id,
        "capability": capability,
        "description": f"step {step_id}",
        "input_refs": [],
        "output_name": None,
        "depends_on": depends_on or [],
        "condition": None,
    }
    if side_effect is not None:
        spec["side_effect"] = side_effect
    return spec


def _proposal(step_id, tool, params, capability="send_email"):
    return {
        "step_id": step_id,
        "capability": capability,
        "tool": tool,
        "params": params,
        "params_canonical": canonical.params_canonical(params, tool_name=tool),
    }


def _side_effect_plan(proposals=None):
    if proposals is None:
        proposals = [
            _proposal(
                "commit", "send_email", {"to": "a@b.com", "subject": "s", "body": "b"}
            )
        ]
    return {
        "goal": "发邮件",
        "risk": "SIDE_EFFECT",
        "steps": [
            {
                **_step("commit", "send_email"),
                "side_effect": True,
                "requires_approval": True,
            }
        ],
        "side_effect_proposals": proposals,
    }


def test_canonicalization_drops_null_keys_and_sorts_keys():
    a = canonical.params_canonical({"b": 2, "a": 1, "c": None}, tool_name="query_db")
    b = canonical.params_canonical({"a": 1, "b": 2}, tool_name="query_db")
    assert a == b
    assert a != canonical.params_canonical(
        {"a": 1, "b": 2, "c": 0}, tool_name="query_db"
    )


def test_canonicalization_unifies_number_semantics_but_not_strings():
    assert canonical.params_canonical(
        {"n": 1}, tool_name="query_db"
    ) == canonical.params_canonical({"n": 1.0}, tool_name="query_db")
    assert canonical.params_canonical(
        {"n": 1}, tool_name="query_db"
    ) != canonical.params_canonical({"n": "1"}, tool_name="query_db")


def test_canonicalization_is_globally_single_implementation():
    from app.engine import approval as approval_module
    from app.engine import tool_executor

    assert approval_module.params_canonical is canonical.params_canonical
    assert tool_executor.params_canonical is canonical.params_canonical


def test_tool_mismatch_is_rejected():
    proposal = _proposal(
        "commit", "send_email", {"to": "a@b.com", "subject": "s", "body": "b"}
    )
    assert (
        proposal_mismatch_reason(proposal, "query_db", {"sql": "SELECT 1"}) is not None
    )


def test_param_mismatch_is_rejected():
    proposal = _proposal(
        "commit", "send_email", {"to": "a@b.com", "subject": "s", "body": "b"}
    )
    assert (
        proposal_mismatch_reason(
            proposal, "send_email", {"to": "x@y.z", "subject": "s", "body": "b"}
        )
        is not None
    )


def test_extra_key_is_rejected():
    proposal = _proposal(
        "commit", "send_email", {"to": "a@b.com", "subject": "s", "body": "b"}
    )
    assert (
        proposal_mismatch_reason(
            proposal,
            "send_email",
            {"to": "a@b.com", "subject": "s", "body": "b", "cc": "c@d.e"},
        )
        is not None
    )


def test_missing_key_is_rejected():
    proposal = _proposal(
        "commit", "send_email", {"to": "a@b.com", "subject": "s", "body": "b"}
    )
    assert (
        proposal_mismatch_reason(
            proposal, "send_email", {"to": "a@b.com", "subject": "s"}
        )
        is not None
    )


def test_null_key_normalization_matches():
    proposal = _proposal(
        "commit", "send_email", {"to": "a@b.com", "subject": "s", "body": "b"}
    )
    executed = {"to": "a@b.com", "subject": "s", "body": "b", "cc": None}
    assert proposal_mismatch_reason(proposal, "send_email", executed) is None


def test_same_proposals_comparison():
    a = [
        _proposal(
            "commit", "send_email", {"to": "a@b.com", "subject": "s", "body": "b"}
        )
    ]
    b = [
        _proposal(
            "commit", "send_email", {"to": "a@b.com", "subject": "s", "body": "b"}
        )
    ]
    c = [
        _proposal("commit", "send_email", {"to": "x@y.z", "subject": "s", "body": "b"})
    ]
    assert same_side_effect_proposals(a, b)
    assert not same_side_effect_proposals(a, c)
    assert not same_side_effect_proposals(a, [])


def test_approval_mismatch_emits_audit_and_plan_invalid():
    plan = _side_effect_plan()
    wrong_approval = Approval(
        plan_hash=planner.compute_plan_hash(plan) + "-wrong",
        approval_id="approval-1",
        approved_side_effect_set=planner.side_effect_step_ids(plan),
        approved_proposals=tuple(plan["side_effect_proposals"]),
    )
    audits: list[dict] = []

    async def collect(event):
        audits.append(event)

    async def ok_step(step, outputs):
        return {"status": "success", "data": "ok"}

    result = asyncio.run(
        execute_with_gates(
            plan,
            intent_category="ACTION",
            approval=wrong_approval,
            run_step=ok_step,
            audit=collect,
        )
    )
    assert result.status == "plan_invalid"
    assert any(event["action"] == "approval_mismatch" for event in audits)


def test_replan_with_changed_proposal_requires_new_approval():
    original = _side_effect_plan()
    changed = _side_effect_plan(
        [
            _proposal(
                "commit", "send_email", {"to": "x@y.z", "subject": "s", "body": "b"}
            )
        ]
    )
    assert replan_read_only(original, changed) is None


def test_replan_read_only_keeps_frozen_proposals():
    original = _side_effect_plan()
    candidate = {
        "goal": "发邮件",
        "risk": "SIDE_EFFECT",
        "steps": [
            {
                **_step("commit", "send_email"),
                "side_effect": True,
                "requires_approval": True,
            }
        ],
    }
    accepted = replan_read_only(original, candidate)
    assert accepted is not None
    assert same_side_effect_proposals(
        accepted["side_effect_proposals"], original["side_effect_proposals"]
    )


def test_resume_with_modified_plan_is_rejected():
    ok, _ = resume_approval_decision({"approved": True})
    assert ok
    ok, reason = resume_approval_decision({"approved": True, "comment": "改一下"})
    assert not ok
    assert "modified_plan" in reason or "mismatch" in reason
    ok, _ = resume_approval_decision({"approved": False})
    assert not ok


def test_side_effect_step_requires_exactly_one_proposal():
    from app.engine.executor import validate_before_approval

    missing = _side_effect_plan(proposals=[])
    valid, errors = validate_before_approval(missing, intent_category="ACTION")
    assert not valid
    assert any("proposal" in error for error in errors)

    multiple = _side_effect_plan(
        [
            _proposal(
                "commit", "send_email", {"to": "a@b.com", "subject": "s", "body": "b"}
            ),
            _proposal(
                "commit", "send_email", {"to": "x@y.z", "subject": "s", "body": "b"}
            ),
        ]
    )
    valid, errors = validate_before_approval(multiple, intent_category="ACTION")
    assert not valid
    assert any("exactly one" in error for error in errors)


def test_approved_proposal_executes_side_effect_exactly_once():
    plan = _side_effect_plan()
    approval = Approval(
        plan_hash=planner.compute_plan_hash(plan),
        approval_id="approval-1",
        approved_side_effect_set=planner.side_effect_step_ids(plan),
        approved_proposals=tuple(plan["side_effect_proposals"]),
    )
    calls: list[str] = []

    async def counting_step(step, outputs):
        calls.append(step["step_id"])
        return {"status": "success", "data": "ok"}

    result = asyncio.run(
        execute_with_gates(
            plan,
            intent_category="ACTION",
            approval=approval,
            run_step=counting_step,
        )
    )
    assert result.status == "completed"
    assert calls == ["commit"]

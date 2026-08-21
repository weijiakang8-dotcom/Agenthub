"""Task → Planner → Capability/Agent Selection → Execution Graph。"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.model_gateway import ModelGateway
from app.engine.capabilities import CAPABILITIES
from app.engine.observability import trace_span

logger = logging.getLogger(__name__)

MAX_PLAN_STEPS = 6
PLAN_INVALID = "plan_invalid"
_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)

PLANNER_SYSTEM_PROMPT = (
    "你是任务规划器。把用户目标拆成 1-6 个可执行步骤，只输出 JSON："
    '{"goal":"<目标>","risk":"<LOW|MEDIUM|HIGH|SIDE_EFFECT>",'
    '"steps":[{"step_id":"step_1","capability":"<能力名>","description":"<做什么>",'
    '"input_refs":["前序 output_name 或原始输入"],"output_name":"<输出名>",'
    '"depends_on":["step_id"],"condition":"<可选，在 node_outputs 上求值>"}],'
    '"reason":"<一句话>"}。\n'
    "只能从以下能力中选择："
    + ", ".join(CAPABILITIES)
    + "。side_effect 与 requires_approval 不允许输出，由能力目录静态决定。"
    "复合任务按 Gather（只读）→ Synthesize（analysis）→ Commit（副作用）→ "
    "Verify 的顺序设计。简单任务只输出一个 answer 步骤，不要为了完整而堆步骤。\n"
    "联网搜索边界：只有任务需要时效性或模型知识之外的外部事实时，才选择 "
    "research 或 web_search 能力；如果上下文中已经提供了【联网搜索结果】，"
    "直接把它当证据使用，不要重复添加 research/web_search 步骤，除非需要"
    "多角度补充检索。内部业务数据用 query_db，知识库资料用 knowledge，"
    "普通聊天用 answer；不要为私人或组织内部信息安排联网搜索。涉及 "
    "send_email/execute 时，正文应基于已提供的搜索证据，禁止编造外部事实。"
)


def plan_invalid(reason: str) -> dict[str, Any]:
    """显式的非法计划标记；禁止静默降级为 fallback/answer。"""
    return {"plan_invalid": True, "reason": reason}


def is_plan_invalid(plan: Any) -> bool:
    return isinstance(plan, dict) and bool(plan.get("plan_invalid"))


def _parse_json_object(text: str) -> dict[str, Any] | None:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_BLOCK.search(text)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None


def _normalize_steps(raw_steps: list[Any]) -> list[dict[str, Any]]:
    """把 Planner 输出规范化为完整 Step Schema；风险字段由能力目录静态决定。"""
    steps: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_steps[:MAX_PLAN_STEPS]):
        if not isinstance(raw, dict):
            continue
        capability = str(raw.get("capability") or raw.get("name") or "").strip()
        if capability not in CAPABILITIES:
            continue
        capability_spec = CAPABILITIES[capability]
        raw_step_id = str(raw.get("step_id") or "").strip()
        step_id = raw_step_id or f"step_{index + 1}"
        steps.append(
            {
                "step_id": step_id,
                "capability": capability,
                "description": str(raw.get("description") or ""),
                "input_refs": list(raw.get("input_refs") or []),
                "output_name": raw.get("output_name") or None,
                "depends_on": list(raw.get("depends_on") or []),
                "condition": raw.get("condition"),
                # Registry 静态声明，Planner 输出一律不采信
                "side_effect": capability_spec.side_effect,
                "requires_approval": capability_spec.requires_approval,
            }
        )
    return steps


def _has_cycle(steps: list[dict[str, Any]], step_ids: list[str]) -> bool:
    edges = {step["step_id"]: list(step.get("depends_on") or []) for step in steps}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(step_id: str) -> bool:
        if step_id in visiting:
            return True
        if step_id in visited:
            return False
        visiting.add(step_id)
        for dependency in edges.get(step_id, []):
            if dependency in edges and visit(dependency):
                return True
        visiting.discard(step_id)
        visited.add(step_id)
        return False

    return any(visit(step_id) for step_id in step_ids)


def validate_plan_structure(steps: list[dict[str, Any]]) -> list[str]:
    """校验 Step Schema、Registry 静态声明、依赖存在性与 DAG 无环。"""
    errors: list[str] = []
    if not steps:
        return ["plan has no steps"]
    if len(steps) > MAX_PLAN_STEPS:
        return [f"plan exceeds max steps ({MAX_PLAN_STEPS})"]

    step_ids = [step.get("step_id") for step in steps]
    if any(not step_id for step_id in step_ids):
        errors.append("every step must have step_id")
    if len(set(step_ids)) != len(step_ids):
        errors.append("duplicate step_id")

    for step in steps:
        capability = str(step.get("capability") or "")
        spec = CAPABILITIES.get(capability)
        if spec is None:
            errors.append(f"unknown capability: {capability}")
            continue
        if bool(step.get("side_effect")) != spec.side_effect:
            errors.append(
                f"side_effect for {capability} must come from Registry "
                f"({spec.side_effect})"
            )
        if bool(step.get("requires_approval")) != spec.requires_approval:
            errors.append(
                f"requires_approval for {capability} must come from Registry "
                f"({spec.requires_approval})"
            )
        for dependency in step.get("depends_on") or []:
            if dependency not in step_ids:
                errors.append(f"dependency {dependency} not found")

    if _has_cycle(steps, step_ids):
        errors.append("dependency cycle detected")
    return errors


def compute_plan_risk(steps: list[dict[str, Any]]) -> str:
    """计划风险确定性推导：副作用 > 多步 > 单步。"""
    if any(bool(step.get("side_effect")) for step in steps):
        return "SIDE_EFFECT"
    if len(steps) >= 3:
        return "HIGH"
    if len(steps) > 1:
        return "MEDIUM"
    return "LOW"


def validate_plan(plan: dict[str, Any]) -> tuple[bool, list[str]]:
    """完整 Plan 校验（Executor 闸门复用）。"""
    if is_plan_invalid(plan):
        return False, [str(plan.get("reason") or "plan_invalid")]
    if not isinstance(plan.get("steps"), list):
        return False, ["plan must contain steps"]
    errors = validate_plan_structure(plan["steps"])
    if errors:
        return False, errors
    if not str(plan.get("goal") or "").strip():
        return False, ["plan must contain goal"]
    if str(plan.get("risk") or "").strip() not in {
        "LOW",
        "MEDIUM",
        "HIGH",
        "SIDE_EFFECT",
    }:
        return False, ["plan must contain valid risk"]
    if "side_effect_proposals" in plan and not isinstance(
        plan.get("side_effect_proposals"), list
    ):
        return False, ["side_effect_proposals must be a list"]
    return True, []


def parse_plan(text: str) -> dict[str, Any]:
    try:
        data = _parse_json_object(text)
    except Exception:  # noqa: BLE001
        data = None
    if data is None:
        return plan_invalid("unparseable planner output")
    if not isinstance(data.get("steps"), list):
        return plan_invalid("planner output missing steps")
    steps = _normalize_steps(data["steps"])
    errors = validate_plan_structure(steps)
    if errors:
        return plan_invalid("; ".join(errors))
    return {
        "goal": str(data.get("goal") or ""),
        "risk": str(data.get("risk") or "") or compute_plan_risk(steps),
        "steps": steps,
        "reason": str(data.get("reason") or ""),
        "side_effect_proposals": list(data.get("side_effect_proposals") or []),
    }


def normalize_plan(plan: dict[str, Any] | list[Any]) -> dict[str, Any]:
    """把 legacy 计划（workflow 派生/旧格式步骤列表）规范化为完整 Schema。"""
    if isinstance(plan, dict) and is_plan_invalid(plan):
        return plan
    if isinstance(plan, dict) and isinstance(plan.get("steps"), list):
        raw_steps = plan["steps"]
        goal = str(plan.get("goal") or "")
        risk = str(plan.get("risk") or "")
        reason = str(plan.get("reason") or "")
    elif isinstance(plan, list):
        raw_steps = plan
        goal = ""
        risk = ""
        reason = ""
    else:
        return plan_invalid("plan must be a dict or a step list")
    steps = _normalize_steps(raw_steps)
    errors = validate_plan_structure(steps)
    if errors:
        return plan_invalid("; ".join(errors))
    return {
        "goal": goal,
        "risk": risk or compute_plan_risk(steps),
        "steps": steps,
        "reason": reason,
        "side_effect_proposals": (
            list(plan.get("side_effect_proposals") or [])
            if isinstance(plan, dict)
            else []
        ),
    }


def side_effect_step_ids(plan: dict[str, Any]) -> tuple[str, ...]:
    """已批准/待审批的副作用步骤集合（冻结语义的基础）。"""
    steps = plan.get("steps") or []
    return tuple(
        str(step["step_id"]) for step in steps if bool(step.get("side_effect"))
    )


def compute_plan_hash(plan: dict[str, Any]) -> str:
    """plan_hash：对副作用步骤集合 + 冻结提案的不可变摘要。"""
    side_effects = [
        {
            "step_id": step["step_id"],
            "capability": step["capability"],
            "requires_approval": step["requires_approval"],
        }
        for step in plan.get("steps") or []
        if bool(step.get("side_effect"))
    ]
    proposals = [
        {
            "step_id": item.get("step_id"),
            "tool": item.get("tool"),
            "params_canonical": item.get("params_canonical"),
        }
        for item in plan.get("side_effect_proposals") or []
    ]
    payload = json.dumps(
        {
            "goal": plan.get("goal"),
            "side_effects": side_effects,
            "side_effect_proposals": proposals,
        },
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def fallback_plan(user_input: str) -> dict[str, Any]:
    # 保留给旧调用；Phase 2 起非法计划一律走 plan_invalid，不再静默降级
    return {
        "steps": [{"capability": "answer", "description": user_input}],
        "reason": "planner fallback",
    }


class Planner:
    def __init__(self, gateway: ModelGateway | None = None) -> None:
        self._gateway = gateway or ModelGateway()

    async def plan(
        self,
        user_input: str,
        *,
        organization_id: str | None,
        user_id: str | None,
        correlation_id: str | None = None,
        context: str | None = None,
    ) -> dict[str, Any]:
        async with trace_span(
            correlation_id,
            "plan",
            organization_id=organization_id,
            user_id=user_id,
        ):
            try:
                llms = await self._gateway.select(
                    organization_id=organization_id,
                    user_id=user_id,
                    complexity="complex",
                )
                messages = [SystemMessage(content=PLANNER_SYSTEM_PROMPT)]
                if context:
                    messages.append(SystemMessage(content=context))
                messages.append(HumanMessage(content=user_input))
                response = await self._gateway.invoke(
                    llms,
                    messages,
                    task_type="plan",
                    organization_id=organization_id,
                    correlation_id=correlation_id,
                )
                plan = parse_plan(str(getattr(response, "content", "")))
            except Exception:
                logger.warning("Planning failed; plan_invalid", exc_info=True)
                plan = plan_invalid("planner failed")
            return plan


__all__ = [
    "MAX_PLAN_STEPS",
    "PLAN_INVALID",
    "Planner",
    "compute_plan_hash",
    "compute_plan_risk",
    "fallback_plan",
    "is_plan_invalid",
    "normalize_plan",
    "parse_plan",
    "plan_invalid",
    "side_effect_step_ids",
    "validate_plan",
    "validate_plan_structure",
]

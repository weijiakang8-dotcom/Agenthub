"""统一 Agent Execution Graph（Frozen Core）。

Task → Planner → Capability/Agent Selection → Execution Graph → Verification → Final Response。
角色与能力解耦：图结构固定，能力通过 CAPABILITIES 目录扩展，不再存在固定
research/analyze/execute 主链。
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from collections.abc import Callable
from typing import Any, TypedDict

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.core.circuit_breaker import llm_breaker
from app.core.model_gateway import ModelGateway, get_chat_models
from app.engine import tool_executor
from app.engine.approval import (
    ProposalInvalidError,
    build_proposal,
    proposal_mismatch_reason,
    proposals_from_plan,
    resume_approval_decision,
)
from app.engine.canonical import params_canonical
from app.engine.capabilities import (
    APPROVAL_REQUIRED_TOOLS,
    CAPABILITIES,
    Capability,
)
from app.engine.event_bus import publish_execution_event
from app.engine.executor import (
    PlanInvalidError,
    audit_execution_event,
    replan_read_only,
    should_verify,
    validate_before_approval,
)
from app.engine.observability import record_span
from app.engine.planner import (
    Planner,
    compute_plan_hash,
    is_plan_invalid,
    normalize_plan,
    side_effect_step_ids,
)
from app.rag.retrieval import retrieve_chunks

logger = logging.getLogger(__name__)


class ProposalClarificationError(ProposalInvalidError):
    """副作用提案缺少必要参数：模型未给出 tool call，但给出了澄清文本。

    安全语义不变：不产生任何副作用、不猜测参数、不静默放行；执行仍
    fail-closed。区别只是把模型的澄清问题（例如「请提供收件人邮箱」）
    原样呈现给用户，让用户补充信息后重试。
    """

    def __init__(self, text: str, step_id: str):
        self.text = text
        self.step_id = step_id
        super().__init__(f"side-effect step {step_id} needs clarification: {text}")


class AgentState(TypedDict, total=False):
    messages: list[Any]
    current_step: int
    execution_id: str | None
    organization_id: str | None
    user_id: str | None
    user_input: str
    final_output: str | None
    plan: list[dict[str, Any]]
    intent: dict[str, Any]
    steps: list[dict[str, Any]]
    pending_approval: dict[str, Any] | None
    node_outputs: dict[str, Any]
    revision_count: int
    revision_requested: bool
    complexity: str
    llm_usage: list[dict[str, Any]]
    plan_meta: dict[str, Any]
    budget_used: dict[str, Any]
    budget_exceeded: bool
    hard_stop: bool
    approval_rejected: bool
    side_effect_failure: bool
    approved_plan_hash: str | None
    approved_approval_id: str | None


_gateway = ModelGateway()


def _new_budget_state() -> dict[str, Any]:
    return {
        "max_steps": 6,
        "max_replans": 1,
        "max_verifies": 1,
        "wall_clock_seconds": 300.0,
        "max_tokens": 100_000,
        "max_cost": 10.0,
        "steps": 0,
        "replans": 0,
        "verifies": 0,
        "tokens": 0,
        "cost": 0.0,
        "started_at": time.time(),
    }


def _budget_exceeded(budget: dict[str, Any]) -> str | None:
    elapsed = time.time() - float(budget.get("started_at", time.time()))
    if elapsed > float(budget.get("wall_clock_seconds", 300.0)):
        return f"wall-clock {elapsed:.1f}s exceeds budget"
    if int(budget.get("tokens", 0)) > int(budget.get("max_tokens", 100_000)):
        return "token budget exceeded"
    if float(budget.get("cost", 0.0)) > float(budget.get("max_cost", 10.0)):
        return "cost budget exceeded"
    if int(budget.get("steps", 0)) >= int(budget.get("max_steps", 6)):
        return "step budget exceeded"
    return None


_RAW_TOOL_CALL_PATTERNS = (
    re.compile(r"<\|*DSML\|*[^>]*>.*?</\|*DSML\|*[^>]*>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<\|*DSML\|*[^>]*/>", re.IGNORECASE),
    re.compile(r"<tool_calls>.*?</tool_calls>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<tool_call>.*?</tool_call>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<invoke\b[^>]*>.*?</invoke>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<invoke\b[^>]*/>", re.IGNORECASE),
    re.compile(r"<parameter\b[^>]*/>", re.IGNORECASE),
)
_RAW_TAG_LINE = re.compile(
    r"^\s*</?(invoke|tool_calls|tool_call|parameter)\b", re.IGNORECASE
)


def _strip_raw_tool_call_text(text: str) -> str:
    cleaned = text.replace("＜", "<").replace("＞", ">").replace("｜", "|")
    for pattern in _RAW_TOOL_CALL_PATTERNS:
        cleaned = pattern.sub("", cleaned)
    kept: list[str] = []
    for line in cleaned.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _RAW_TAG_LINE.match(stripped):
            continue
        if "DSML" in stripped and stripped.startswith("<"):
            continue
        kept.append(line)
    return "\n".join(kept).strip()


async def _get_llms(
    organization_id: str | None = None,
    *,
    complexity: str = "simple",
    user_id: str | None = None,
) -> list[ChatOpenAI]:
    return await get_chat_models(
        organization_id,
        complexity=complexity,
        user_id=user_id,
    )


async def _call_llm_with_fallback(
    llms: list[ChatOpenAI],
    messages: list[BaseMessage],
) -> AIMessage:
    if not llm_breaker.allow():
        raise RuntimeError("AI 服务暂时不可用，请稍后再试")
    return await _gateway.invoke(llms, messages, task_type="legacy")


async def _stream_llm_text(
    llms: list[ChatOpenAI],
    messages: list[BaseMessage],
    execution_id: str,
    node_id: str,
) -> AIMessage:
    parts: list[str] = []
    async for text in _gateway.stream(llms, messages, task_type="agent"):
        parts.append(text)
        await publish_execution_event(
            execution_id,
            {"event": "token", "node": node_id, "token": text},
        )
    return AIMessage(content="".join(parts))


def _usage_of(response: Any) -> dict[str, Any]:
    return (getattr(response, "additional_kwargs", None) or {}).get(
        "_agenthub_llm"
    ) or {}


async def _prepare_node(state: AgentState) -> dict[str, Any]:
    messages = list(state.get("messages") or [])
    if state.get("user_input") and not any(
        isinstance(message, HumanMessage) for message in messages
    ):
        messages.insert(0, HumanMessage(content=state["user_input"]))
    return {"messages": messages}


async def _propose_side_effect_calls(
    plan_result: dict[str, Any],
    state: AgentState,
) -> list[dict[str, Any]]:
    """审批前生成并冻结副作用提案：每个 side_effect step 恰好一次 tool call。"""
    proposals: list[dict[str, Any]] = []
    for step in plan_result.get("steps") or []:
        if not bool(step.get("side_effect")):
            continue
        capability = CAPABILITIES.get(str(step.get("capability") or ""))
        if capability is None:
            raise ProposalInvalidError(f"unknown capability {step.get('capability')}")
        tools = list(capability.tools)
        if not tools:
            raise ProposalInvalidError(
                f"capability {capability.name} declares no tools"
            )
        llms = await _get_llms(
            state.get("organization_id"),
            complexity=state.get("complexity") or "simple",
            user_id=state.get("user_id"),
        )
        bound_llms = [llm.bind_tools(tools) for llm in llms]
        messages: list[BaseMessage] = [SystemMessage(content=capability.system_prompt)]
        messages.extend(state.get("messages") or [])
        if not any(isinstance(message, HumanMessage) for message in messages):
            messages.append(HumanMessage(content=state.get("user_input", "")))
        response = await _gateway.invoke(
            bound_llms,
            messages,
            task_type=f"propose:{capability.name}",
            organization_id=state.get("organization_id"),
            correlation_id=state.get("execution_id"),
        )
        calls = getattr(response, "tool_calls", None) or []
        if len(calls) == 0:
            content = str(getattr(response, "content", "") or "").strip()
            text = content or (
                "该操作缺少必要信息（例如收件人邮箱地址），请补充后再试。"
            )
            raise ProposalClarificationError(
                text=text, step_id=str(step.get("step_id") or "")
            )
        if len(calls) != 1:
            raise ProposalInvalidError(
                f"side-effect step {step.get('step_id')} must propose exactly one "
                f"tool call (got {len(calls)})"
            )
        call = calls[0]
        tool_name = str(call.get("name") or "")
        tool_args = dict(call.get("args") or {})
        tool_names = {getattr(tool, "name", "") for tool in tools}
        if tool_name not in tool_names:
            raise ProposalInvalidError(
                f"proposed tool {tool_name} not in capability {capability.name}"
            )
        proposals.append(
            build_proposal(
                step_id=str(step.get("step_id") or ""),
                capability=capability.name,
                tool=tool_name,
                params=tool_args,
            ).to_dict()
        )
    return proposals


async def _execute_frozen_side_effect(
    state: AgentState,
    step: dict[str, Any],
    execution_id: str,
) -> tuple[dict[str, Any], bool]:
    """按冻结提案执行副作用；runtime attempt 与冻结提案不一致 → abort（零副作用）。

    T24 裁决（Decision C）：执行阶段必须显式比对 runtime tool/params 与冻结
    proposal；tool 或 params_canonical 任意不一致 → approval_mismatch → audit →
    FAILED，禁止 provider invocation，禁止“按构造冻结”把 attempt B 替换成 A 执行。
    """
    plan_result = (state.get("plan_meta") or {}).get("plan") or {}
    proposals = proposals_from_plan(plan_result)
    proposal = next(
        (item for item in proposals if item.step_id == step.get("step_id")), None
    )
    if proposal is None:
        reason = f"missing side-effect proposal for step {step.get('step_id')}"
        await audit_execution_event(
            execution_id=execution_id,
            action="approval_mismatch",
            organization_id=state.get("organization_id"),
            user_id=state.get("user_id"),
            details={"step_id": step.get("step_id"), "reason": reason},
        )
        return {
            "side_effect_failure": True,
            "final_output": f"approval_mismatch: {reason}",
            "current_step": len(state.get("plan") or []),
        }, False
    runtime_tool = str(step.get("tool") or "")
    runtime_params = dict(step.get("params") or {})
    mismatch = proposal_mismatch_reason(
        proposal.to_dict(), runtime_tool, runtime_params
    )
    if mismatch is not None:
        await audit_execution_event(
            execution_id=execution_id,
            action="approval_mismatch",
            organization_id=state.get("organization_id"),
            user_id=state.get("user_id"),
            details={
                "step_id": step.get("step_id"),
                "runtime_tool": runtime_tool,
                "runtime_params_canonical": (
                    params_canonical(runtime_params, tool_name=runtime_tool)
                    if runtime_tool
                    else ""
                ),
                "frozen_tool": proposal.tool,
                "frozen_params_canonical": proposal.params_canonical,
                "reason": mismatch,
            },
        )
        return {
            "side_effect_failure": True,
            "final_output": f"approval_mismatch: {mismatch}",
            "current_step": len(state.get("plan") or []),
        }, False

    result = await tool_executor.execute_tool(
        proposal.tool, proposal.params, execution_id
    )
    status = str(result.get("status") or "failed")
    if status == "unknown":
        error_text = str(result.get("error") or "side effect state unknown")
        await audit_execution_event(
            execution_id=execution_id,
            action="side_effect_unknown",
            organization_id=state.get("organization_id"),
            user_id=state.get("user_id"),
            details={
                "step_id": step.get("step_id"),
                "capability": step.get("capability"),
                "tool": proposal.tool,
                "error": error_text,
            },
        )
        return {
            "side_effect_failure": True,
            "final_output": f"side_effect_unknown: {error_text}",
            "current_step": len(state.get("plan") or []),
        }, False
    if status not in ("success", "duplicate"):
        error_text = str(result.get("error") or "side effect failed")
        await audit_execution_event(
            execution_id=execution_id,
            action="side_effect_failure",
            organization_id=state.get("organization_id"),
            user_id=state.get("user_id"),
            details={
                "step_id": step.get("step_id"),
                "capability": step.get("capability"),
                "tool": proposal.tool,
                "error": error_text,
            },
        )
        return {
            "side_effect_failure": True,
            "final_output": f"side_effect_failure: {error_text}",
            "current_step": len(state.get("plan") or []),
        }, False
    return result, True


async def _plan_node(state: AgentState) -> dict[str, Any]:
    execution_id = state.get("execution_id") or ""
    intent_category = str((state.get("intent") or {}).get("category") or "TASK")
    original_plan_meta = state.get("plan_meta") or {}
    budget = state.get("budget_used") or _new_budget_state()
    plan_result: dict[str, Any] | None = None

    if state.get("revision_requested"):
        # Replan 必须重过全部闸门：只读重排/降级、副作用集合不可变、≤1 次
        planner = Planner(gateway=_gateway)
        candidate = await planner.plan(
            state.get("user_input", ""),
            organization_id=state.get("organization_id"),
            user_id=state.get("user_id"),
            correlation_id=execution_id or None,
        )
        original = original_plan_meta.get("plan")
        new_plan = (
            replan_read_only(original, candidate) if original is not None else None
        )
        if new_plan is None:
            reason = "replan rejected: must keep side-effect set and pass validation"
            await publish_execution_event(
                execution_id,
                {"event": "error", "error_type": "replan_rejected", "message": reason},
            )
            await audit_execution_event(
                execution_id=execution_id,
                action="replan_rejected",
                organization_id=state.get("organization_id"),
                user_id=state.get("user_id"),
                details={"reason": reason},
            )
            raise PlanInvalidError(reason)
        if int(budget.get("replans", 0)) >= int(budget.get("max_replans", 1)):
            reason = "replan budget exceeded (max 1)"
            await publish_execution_event(
                execution_id,
                {"event": "error", "error_type": "replan_rejected", "message": reason},
            )
            raise PlanInvalidError(reason)
        plan_result = new_plan
        budget = {**budget, "replans": int(budget.get("replans", 0)) + 1}
    elif state.get("plan"):
        plan_result = original_plan_meta.get("plan") or normalize_plan(
            {
                "goal": state.get("user_input") or "task",
                "risk": "",
                "steps": state["plan"],
            }
        )
    else:
        planner = Planner(gateway=_gateway)
        plan_result = await planner.plan(
            state.get("user_input", ""),
            organization_id=state.get("organization_id"),
            user_id=state.get("user_id"),
            correlation_id=execution_id or None,
        )
    if is_plan_invalid(plan_result):
        reason = str(plan_result.get("reason") or "plan_invalid")
        await publish_execution_event(
            execution_id,
            {"event": "error", "error_type": "plan_invalid", "message": reason},
        )
        await audit_execution_event(
            execution_id=execution_id,
            action="plan_invalid",
            organization_id=state.get("organization_id"),
            user_id=state.get("user_id"),
            details={"reason": reason},
        )
        raise PlanInvalidError(reason)

    has_side_effects = any(
        bool(step.get("side_effect")) for step in plan_result.get("steps") or []
    )
    if has_side_effects and not plan_result.get("side_effect_proposals"):
        # 提案必须在 Approval 前生成并冻结；Approval 后不得重新生成
        try:
            plan_result["side_effect_proposals"] = await _propose_side_effect_calls(
                plan_result, state
            )
        except ProposalClarificationError as exc:
            await audit_execution_event(
                execution_id=execution_id,
                action="proposal_clarification",
                organization_id=state.get("organization_id"),
                user_id=state.get("user_id"),
                details={"step_id": exc.step_id, "question": exc.text},
            )
            await publish_execution_event(
                execution_id,
                {
                    "event": "clarification",
                    "execution_id": execution_id,
                    "message": exc.text,
                },
            )
            raise PlanInvalidError(exc.text) from exc
        except ProposalInvalidError as exc:
            reason = str(exc)
            await audit_execution_event(
                execution_id=execution_id,
                action="proposal_invalid",
                organization_id=state.get("organization_id"),
                user_id=state.get("user_id"),
                details={"reason": reason},
            )
            await publish_execution_event(
                execution_id,
                {"event": "error", "error_type": "proposal_invalid", "message": reason},
            )
            raise PlanInvalidError(reason) from exc

    valid, errors = validate_before_approval(
        plan_result, intent_category=intent_category
    )
    if not valid:
        reason = "; ".join(errors)
        await publish_execution_event(
            execution_id,
            {"event": "error", "error_type": "plan_invalid", "message": reason},
        )
        await audit_execution_event(
            execution_id=execution_id,
            action="plan_invalid",
            organization_id=state.get("organization_id"),
            user_id=state.get("user_id"),
            details={"reason": reason},
        )
        raise PlanInvalidError(reason)

    plan = plan_result["steps"]
    plan_hash = compute_plan_hash(plan_result)
    side_effects = list(side_effect_step_ids(plan_result))
    approved = state.get("approved_plan_hash") == plan_hash and bool(
        state.get("approved_approval_id")
    )
    if side_effects and approved:
        plan_meta_approval_id = (state.get("plan_meta") or {}).get("approval_id")
        if (
            plan_meta_approval_id
            and state.get("approved_approval_id") != plan_meta_approval_id
        ):
            reason = "approval_id mismatch"
            await audit_execution_event(
                execution_id=execution_id,
                action="approval_mismatch",
                organization_id=state.get("organization_id"),
                user_id=state.get("user_id"),
                details={"reason": reason},
            )
            raise PlanInvalidError(reason)
    plan_meta = {
        "plan": plan_result,
        "plan_hash": plan_hash,
        "side_effect_set": side_effects,
        "risk": plan_result.get("risk"),
        "approved": approved,
        "approval_id": (state.get("plan_meta") or {}).get("approval_id"),
    }

    if side_effects and not approved:
        approval_id = uuid.uuid4().hex
        plan_meta = {**plan_meta, "approval_id": approval_id}
        # 计划级审批：执行前冻结副作用步骤集合与参数提案
        pending = {
            "type": "plan_approval",
            "plan_hash": plan_hash,
            "approval_id": approval_id,
            "side_effect_set": side_effects,
            "side_effect_proposals": plan_result.get("side_effect_proposals") or [],
            "goal": plan_result.get("goal"),
        }
        # approval_required 事件由 runner 在 DB 状态提交后统一发射，保证事件不领先持久化状态
        return {
            "plan": plan,
            "plan_meta": plan_meta,
            "pending_approval": pending,
            "budget_used": budget,
            "current_step": 0,
        }

    await publish_execution_event(
        execution_id,
        {"event": "step", "node": "plan", "step_index": -1, "plan": plan},
    )
    return {
        "plan": plan,
        "plan_meta": plan_meta,
        "budget_used": budget,
        "current_step": 0,
    }


def _step_capability(plan: list[dict[str, Any]], index: int) -> Capability:
    raw = plan[index] if index < len(plan) else {}
    name = str(raw.get("capability") or raw.get("name") or "answer")
    return CAPABILITIES.get(name, CAPABILITIES["answer"])


async def _route_step(state: AgentState) -> str:
    if (
        state.get("approval_rejected")
        or state.get("budget_exceeded")
        or state.get("side_effect_failure")
    ):
        return END
    if state.get("pending_approval"):
        return "waiting_for_approval"
    plan = state.get("plan") or []
    index = state.get("current_step", 0)
    if index >= len(plan):
        intent = state.get("intent") or {}
        category = str(intent.get("category") or "TASK")
        if not should_verify(category, {"risk": intent.get("risk"), "steps": plan}):
            return END
        return "verify"
    return _step_capability(plan, index).name


def _should_revise(state: AgentState) -> bool:
    return bool(state.get("revision_requested"))


def make_capability_node(name: str) -> Callable[[AgentState], dict[str, Any]]:
    capability = CAPABILITIES[name]

    async def node(state: AgentState) -> dict[str, Any]:
        execution_id = state.get("execution_id") or ""
        index = state.get("current_step", 0)
        usage: list[dict[str, Any]] = []
        step_start = time.perf_counter()
        await publish_execution_event(
            execution_id,
            {
                "event": "step",
                "node": name,
                "step_index": index,
                "status": "started",
            },
        )

        # Risk/Budget 闸门：只读超限优雅终止，副作用超限硬终止 + 审计
        budget = state.get("budget_used") or _new_budget_state()
        budget_reason = _budget_exceeded(budget)
        if budget_reason is not None:
            plan_meta = state.get("plan_meta") or {}
            hard = bool(plan_meta.get("side_effect_set"))
            await audit_execution_event(
                execution_id=execution_id,
                action="budget_exceeded",
                organization_id=state.get("organization_id"),
                user_id=state.get("user_id"),
                details={"reason": budget_reason, "hard": hard},
            )
            await publish_execution_event(
                execution_id,
                {
                    "event": "error",
                    "error_type": "budget_exceeded",
                    "message": budget_reason,
                    "hard": hard,
                },
            )
            await record_span(
                trace_id=execution_id or None,
                name="step",
                start=step_start,
                end=time.perf_counter(),
                status="error",
                error=budget_reason,
                details={
                    "step_id": index,
                    "capability": name,
                    "budget_exceeded": True,
                    "hard": hard,
                },
            )
            return {
                "budget_exceeded": True,
                "hard_stop": hard,
                "current_step": len(state.get("plan") or []),
                "final_output": state.get("final_output")
                or f"budget_exceeded: {budget_reason}",
            }

        system_prompt = capability.system_prompt
        if capability.inject_knowledge:
            try:
                chunks = await retrieve_chunks(
                    state.get("user_input", ""),
                    (
                        uuid.UUID(str(state["organization_id"]))
                        if state.get("organization_id")
                        else None
                    ),
                    top_k=5,
                    correlation_id=execution_id or None,
                )
            except Exception:
                logger.warning("RAG injection failed; continuing", exc_info=True)
                chunks = []
            if chunks:
                snippets = "\n---\n".join(chunk["content"][:800] for chunk in chunks)
                system_prompt += (
                    f"\n\n【知识库资料，仅供参考】\n<context>\n{snippets}\n</context>"
                )

        messages: list[BaseMessage] = [SystemMessage(content=system_prompt)]
        messages.extend(state.get("messages") or [])
        if not any(isinstance(message, HumanMessage) for message in messages):
            messages.append(HumanMessage(content=state.get("user_input", "")))

        complexity = state.get("complexity") or "simple"
        llms = await _get_llms(
            state.get("organization_id"),
            complexity=complexity,
            user_id=state.get("user_id"),
        )
        tools = list(capability.tools)
        bound_llms = [llm.bind_tools(tools) for llm in llms] if tools else llms

        if tools:
            current_step = (
                (state.get("plan") or [])[index]
                if index < len(state.get("plan") or [])
                else {}
            )
            if current_step.get("side_effect"):
                # T24 裁决：执行阶段显式产生 runtime attempt，与冻结提案比对。
                attempt_response = await _gateway.invoke(
                    bound_llms,
                    messages,
                    task_type=f"attempt:{name}",
                    organization_id=state.get("organization_id"),
                    correlation_id=state.get("execution_id"),
                )
                usage.append(_usage_of(attempt_response))
                attempts = list(getattr(attempt_response, "tool_calls", None) or [])
                attempt_step = dict(current_step)
                if len(attempts) == 1:
                    attempt_step["tool"] = str(attempts[0].get("name") or "")
                    attempt_step["params"] = dict(attempts[0].get("args") or {})
                else:
                    # 0 次或多次 attempt：视为 runtime 与冻结提案不一致，fail-closed。
                    attempt_step["tool"] = ""
                    attempt_step["params"] = {}
                effect_result, effect_ok = await _execute_frozen_side_effect(
                    state, attempt_step, execution_id
                )
                if not effect_ok:
                    return effect_result
                final_output = str(
                    effect_result.get("data") or effect_result.get("error") or "done"
                )
                await publish_execution_event(
                    execution_id,
                    {
                        "event": "step",
                        "node": name,
                        "step_index": index,
                        "status": "completed",
                        "output": final_output,
                    },
                )
                await record_span(
                    trace_id=execution_id or None,
                    name="step",
                    start=step_start,
                    end=time.perf_counter(),
                    status="ok",
                    details={
                        "step_id": index,
                        "capability": name,
                        "side_effect": True,
                    },
                )
                return {
                    "messages": state.get("messages") or [],
                    "current_step": index + 1,
                    "final_output": final_output,
                    "node_outputs": {
                        **(state.get("node_outputs") or {}),
                        str(current_step.get("step_id") or index): effect_result,
                    },
                    "llm_usage": [*state.get("llm_usage", []), *usage],
                    "budget_used": {
                        **budget,
                        "steps": int(budget.get("steps", 0)) + 1,
                    },
                }
            response = await _gateway.invoke(
                bound_llms,
                messages,
                task_type=f"agent:{name}",
                organization_id=state.get("organization_id"),
                correlation_id=state.get("execution_id"),
            )
            usage.append(_usage_of(response))
            new_messages: list[BaseMessage] = [*state.get("messages", []), response]
            executed_tool = False
            for tool_call in getattr(response, "tool_calls", None) or []:
                tool_name = tool_call.get("name", "")
                tool_args = tool_call.get("args") or {}
                step = (
                    (state.get("plan") or [])[index]
                    if index < len(state.get("plan") or [])
                    else {}
                )
                if not tool_call.get("id"):
                    tool_call["id"] = f"call_{uuid.uuid4().hex}"
                if tool_name in APPROVAL_REQUIRED_TOOLS and not (
                    state.get("plan_meta") or {}
                ).get("approved"):
                    record = await tool_executor.create_tool_call(
                        tool_name,
                        tool_args,
                        execution_id,
                        requires_approval=True,
                    )
                    await publish_execution_event(
                        execution_id,
                        {
                            "event": "approval_required",
                            "tool_call_id": str(record.id),
                            "tool": tool_name,
                            "params": tool_args,
                        },
                    )
                    return {
                        "messages": new_messages,
                        "pending_approval": {
                            "tool_name": tool_name,
                            "tool_args": tool_args,
                            "tool_call_id": str(record.id),
                        },
                        "llm_usage": [*state.get("llm_usage", []), *usage],
                    }
                result = await tool_executor.execute_tool(
                    tool_name, tool_args, execution_id
                )
                if step.get("side_effect") and result.get("status") != "success":
                    # Contract 03：副作用步骤失败 → 立即终止 + audit，不重试/重排
                    error_text = str(result.get("error") or "side effect failed")
                    await audit_execution_event(
                        execution_id=execution_id,
                        action="side_effect_failure",
                        organization_id=state.get("organization_id"),
                        user_id=state.get("user_id"),
                        details={
                            "step_id": step.get("step_id"),
                            "capability": name,
                            "tool": tool_name,
                            "error": error_text,
                        },
                    )
                    await publish_execution_event(
                        execution_id,
                        {
                            "event": "error",
                            "error_type": "side_effect_failure",
                            "message": error_text,
                        },
                    )
                    return {
                        "side_effect_failure": True,
                        "final_output": f"side_effect_failure: {error_text}",
                        "current_step": len(state.get("plan") or []),
                    }
                new_messages.append(
                    ToolMessage(
                        content=json.dumps(result, ensure_ascii=False, default=str),
                        tool_call_id=tool_call["id"],
                    )
                )
                executed_tool = True

            final_response = response
            if executed_tool:
                synthesis = await _stream_llm_text(
                    await _get_llms(
                        state.get("organization_id"),
                        complexity=complexity,
                        user_id=state.get("user_id"),
                    ),
                    [SystemMessage(content=system_prompt), *new_messages],
                    execution_id,
                    name,
                )
                new_messages.append(synthesis)
                final_response = synthesis
                usage.append(_usage_of(synthesis))
        else:
            streamed = await _stream_llm_text(bound_llms, messages, execution_id, name)
            new_messages = [*state.get("messages", []), streamed]
            final_response = streamed
            usage.append(_usage_of(streamed))

        final_output = _strip_raw_tool_call_text(
            getattr(final_response, "content", "") or ""
        )
        await publish_execution_event(
            execution_id,
            {
                "event": "step",
                "node": name,
                "step_index": index,
                "status": "completed",
                "output": final_output,
            },
        )
        token_total = sum(
            int(item.get("input_tokens") or 0) + int(item.get("output_tokens") or 0)
            for item in usage
        )
        await record_span(
            trace_id=execution_id or None,
            name="step",
            start=step_start,
            end=time.perf_counter(),
            status="ok",
            tokens=token_total,
            details={
                "step_id": index,
                "capability": name,
                "side_effect": (
                    bool((state.get("plan") or [])[index].get("side_effect"))
                    if index < len(state.get("plan") or [])
                    else False
                ),
            },
        )
        return {
            "messages": new_messages,
            "current_step": index + 1,
            "final_output": final_output,
            "node_outputs": {
                **(state.get("node_outputs") or {}),
                name: final_output,
            },
            "llm_usage": [*state.get("llm_usage", []), *usage],
            "budget_used": {
                **budget,
                "steps": int(budget.get("steps", 0)) + 1,
                "tokens": int(budget.get("tokens", 0)) + token_total,
            },
        }

    return node


async def _verify_node(state: AgentState) -> dict[str, Any]:
    final_output = state.get("final_output") or ""
    budget = state.get("budget_used") or _new_budget_state()
    execution_id = state.get("execution_id") or None
    organization_id = state.get("organization_id")
    user_id = state.get("user_id")
    verify_start = time.perf_counter()
    if not final_output:
        # Fail-closed（ADR-005）：空输出 = UNKNOWN，不调用 LLM、不 replan、不算 PASS。
        await audit_execution_event(
            execution_id=str(execution_id or ""),
            action="verify_unknown",
            organization_id=organization_id,
            user_id=user_id,
            details={"reason": "empty final output"},
        )
        await record_span(
            trace_id=execution_id,
            name="verify",
            start=verify_start,
            end=time.perf_counter(),
            status="error",
            details={"result": "UNKNOWN", "revision_requested": False},
        )
        return {"revision_requested": False, "budget_used": budget}
    if int(budget.get("verifies", 0)) >= int(budget.get("max_verifies", 1)):
        # verify ≤1：不允许重复验证
        return {"revision_requested": False, "budget_used": budget}
    usage: list[dict[str, Any]] = []
    result_state = "UNKNOWN"
    error_reason: str | None = None
    try:
        llms = await _get_llms(
            state.get("organization_id"),
            complexity="simple",
            user_id=state.get("user_id"),
        )
        response = await _gateway.invoke(
            llms,
            [
                HumanMessage(
                    content=(
                        "你是质量审查员。检查下面的 Agent 输出是否完整满足用户输入。"
                        "只允许输出 PASS 或 FAIL 两个单词，不要输出任何其他内容。\n"
                        f"用户输入：{state.get('user_input', '')}\n"
                        f"Agent 输出：{final_output}"
                    )
                )
            ],
            task_type="verify",
            organization_id=state.get("organization_id"),
            correlation_id=state.get("execution_id"),
        )
        usage.append(_usage_of(response))
        result_state = classify_verify_output(getattr(response, "content", None))
    except Exception as exc:  # noqa: BLE001
        # Fail-closed（ADR-005）：异常/超时 = ERROR，不 replan、不算 PASS。
        result_state = "ERROR"
        error_reason = f"{type(exc).__name__}: {str(exc)[:200]}"

    passed = result_state == "PASS"
    revision_requested = (not passed) and state.get("revision_count", 0) == 0
    if result_state in ("UNKNOWN", "ERROR"):
        # UNKNOWN/ERROR 不得触发 replan（防基础设施抖动造成重规划循环）。
        revision_requested = False
        await audit_execution_event(
            execution_id=str(execution_id or ""),
            action="verify_unknown" if result_state == "UNKNOWN" else "verify_error",
            organization_id=organization_id,
            user_id=user_id,
            details={
                "reason": error_reason or "verifier output not certifiable",
                "final_output": final_output[:400],
            },
        )
    await record_span(
        trace_id=execution_id,
        name="verify",
        start=verify_start,
        end=time.perf_counter(),
        status="ok" if passed else "error",
        details={
            "result": result_state,
            "revision_requested": revision_requested,
            "error": error_reason,
        },
    )
    return {
        "revision_requested": revision_requested,
        "revision_count": state.get("revision_count", 0)
        + (1 if revision_requested else 0),
        "current_step": 0 if revision_requested else state.get("current_step", 0),
        "final_output": None if revision_requested else final_output,
        "llm_usage": [*state.get("llm_usage", []), *usage],
        "budget_used": {
            **budget,
            "verifies": int(budget.get("verifies", 0)) + 1,
        },
    }


def classify_verify_output(text: str | None) -> str:
    """ADR-005：verify 输出判定（fail-closed）。

    精确 PASS / FAIL（trim、大小写不敏感）之外的一切（空、None、非法内容）
    一律 UNKNOWN；调用层异常由调用方映射为 ERROR。
    """
    if text is None:
        return "UNKNOWN"
    normalized = str(text).strip().upper()
    if normalized == "PASS":
        return "PASS"
    if normalized == "FAIL":
        return "FAIL"
    return "UNKNOWN"


async def _waiting_for_approval_node(state: AgentState) -> dict[str, Any]:
    pending = state.get("pending_approval") or {}
    decision = interrupt({"type": "approval_required", "tool_call": pending})
    rejected = isinstance(decision, dict) and decision.get("approved") is False
    tool_result: dict[str, Any] | None = None

    if pending.get("type") == "plan_approval":
        ok, reason = resume_approval_decision(
            decision if isinstance(decision, dict) else {}
        )
        if not ok:
            await audit_execution_event(
                execution_id=state.get("execution_id") or "",
                action=(
                    "approval_mismatch" if "mismatch" in reason else "approval_rejected"
                ),
                organization_id=state.get("organization_id"),
                user_id=state.get("user_id"),
                details={"reason": reason},
            )
            return {
                "pending_approval": None,
                "approval_rejected": True,
                "current_step": len(state.get("plan") or []),
                "final_output": f"approval_rejected: {reason}",
            }
        plan_hash = pending.get("plan_hash")
        return {
            "pending_approval": None,
            "approved_plan_hash": plan_hash,
            "approved_approval_id": pending.get("approval_id"),
            "plan_meta": {
                **(state.get("plan_meta") or {}),
                "approved": True,
                "approval_id": pending.get("approval_id"),
            },
            "current_step": state.get("current_step", 0),
        }

    if pending.get("tool_call_id"):
        try:
            tool_call_id = uuid.UUID(pending["tool_call_id"])
        except (ValueError, TypeError):
            tool_call_id = None
        if tool_call_id is not None:
            if rejected:
                await tool_executor.mark_tool_call_rejected(tool_call_id)
            else:
                tool_result = await tool_executor.execute_pending_tool_call(
                    tool_call_id
                )

    return {
        "pending_approval": None,
        "current_step": state.get("current_step", 0) + 1,
        "final_output": (
            f"Rejected by human: {pending.get('tool_name', 'tool')}"
            if rejected
            else (
                f"已完成人工审批并执行工具 {pending.get('tool_name', 'tool')}："
                f"{tool_result.get('status', 'unknown') if tool_result else 'unknown'}"
            )
        ),
    }


def build_graph(checkpointer: Any = None, dag: dict[str, Any] | None = None) -> Any:
    graph = StateGraph(AgentState)
    graph.add_node("prepare", _prepare_node)
    graph.add_node("plan", _plan_node)
    graph.add_node("verify", _verify_node)
    graph.add_node("waiting_for_approval", _waiting_for_approval_node)
    for name in CAPABILITIES:
        graph.add_node(name, make_capability_node(name))

    graph.add_edge(START, "prepare")
    graph.add_edge("prepare", "plan")
    graph.add_conditional_edges(
        "plan",
        _route_step,
        {
            **{name: name for name in CAPABILITIES},
            "verify": "verify",
            "waiting_for_approval": "waiting_for_approval",
            END: END,
        },
    )
    for name in CAPABILITIES:
        graph.add_conditional_edges(
            name,
            _route_step,
            {
                **{candidate: candidate for candidate in CAPABILITIES},
                "verify": "verify",
                "waiting_for_approval": "waiting_for_approval",
                END: END,
            },
        )
    graph.add_conditional_edges(
        "waiting_for_approval",
        _route_step,
        {
            **{candidate: candidate for candidate in CAPABILITIES},
            "verify": "verify",
            END: END,
        },
    )
    graph.add_conditional_edges("verify", _should_revise, {True: "plan", False: END})
    return graph.compile(checkpointer=checkpointer)


__all__ = [
    "AgentState",
    "_call_llm_with_fallback",
    "_get_llms",
    "_stream_llm_text",
    "_strip_raw_tool_call_text",
    "build_graph",
    "make_capability_node",
]

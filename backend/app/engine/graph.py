from __future__ import annotations

import json
import asyncio
import uuid
from typing import Any, Callable, TypedDict

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

from app.config import settings
from app.core.cache import get_cached_response, set_cached_response
from app.core.circuit_breaker import llm_breaker
from app.core.telemetry import get_tracer
from app.engine import tool_executor
from app.engine.event_bus import publish_execution_event
from app.engine.tools import query_db, search_web, send_email
from app.rag.retrieval import retrieve_documents


class AgentState(TypedDict, total=False):
    messages: list[Any]
    current_step: int
    execution_id: str | None
    organization_id: str | None
    checkpoint: dict[str, Any] | None
    user_input: str
    final_output: str | None
    # 内部路由用到的附加字段
    steps: list[dict[str, Any]]
    pending_approval: dict[str, Any] | None
    node_outputs: dict[str, Any]
    last_condition: bool


ROLE_NODES = {
    "research": "research_agent",
    "analyze": "analyze_agent",
    "execute": "execute_agent",
}

ROLE_TOOLS = {
    "research": [search_web],
    "analyze": [],
    "execute": [query_db, send_email],
}

APPROVAL_REQUIRED_TOOLS = {"send_email"}

TOOL_BY_NAME = {
    "search_web": search_web,
    "query_db": query_db,
    "send_email": send_email,
}

tracer = get_tracer("agenthub.engine")


async def _call_llm(llm, messages):
    if not llm_breaker.allow():
        raise RuntimeError("AI 服务暂时不可用，请稍后再试")
    for attempt in range(3):
        try:
            response = await llm.ainvoke(messages)
            llm_breaker.record_success()
            return response
        except Exception as exc:  # noqa: BLE001
            llm_breaker.record_failure()
            if attempt == 2:
                raise exc
            await asyncio.sleep(2 ** attempt)


def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.LLM_MODEL,
        base_url=settings.LLM_BASE_URL,
        api_key=settings.OPENAI_API_KEY or "not-configured",
        temperature=0,
    )


async def prepare_node(state: AgentState) -> dict[str, Any]:
    messages = list(state.get("messages") or [])
    if state.get("user_input") and not any(isinstance(m, HumanMessage) for m in messages):
        messages.insert(0, HumanMessage(content=state["user_input"]))
    return {"messages": messages, "current_step": state.get("current_step", 0)}


def route_step(state: AgentState) -> str:
    if state.get("pending_approval"):
        return "waiting_for_approval"

    steps = state.get("steps") or []
    index = state.get("current_step", 0)
    if index >= len(steps):
        return END

    role = steps[index].get("role", "research")
    return ROLE_NODES.get(role, END)


def make_agent_node(role: str) -> Callable[[AgentState], dict[str, Any]]:
    async def node(state: AgentState) -> dict[str, Any]:
        index = state.get("current_step", 0)
        steps = state.get("steps") or []
        step = steps[index] if index < len(steps) else {}
        execution_id = state.get("execution_id") or ""
        system_prompt = step.get("system_prompt") or f"You are the {role} agent."

        with tracer.start_as_current_span(f"{role}_agent") as span:
            span.set_attribute("agent.role", role)
            span.set_attribute("agent.step_index", index)
            span.set_attribute("user_input", state.get("user_input", ""))
            await publish_execution_event(
                execution_id,
                {
                    "event": "node_started",
                    "node": role,
                    "step_index": index,
                },
            )

            if role == "research":
                cached = await get_cached_response(state.get("user_input", ""))
                if cached:
                    span.set_attribute("cache.hit", True)
                    return {
                        "messages": [*state.get("messages", []), AIMessage(content=cached)],
                        "current_step": index + 1,
                        "final_output": cached,
                    }
                span.set_attribute("cache.hit", False)

            if role == "research":
                docs = await retrieve_documents(
                    state.get("user_input", ""),
                    state.get("organization_id"),
                    top_k=3,
                )
                if docs:
                    snippets = "\n---\n".join(d["content"][:1000] for d in docs)
                    system_prompt += f"\n\n以下是知识库中的相关文档片段：\n{snippets}"

            messages: list[BaseMessage] = [SystemMessage(content=system_prompt)]
            messages.extend(state.get("messages") or [])
            if not any(isinstance(m, HumanMessage) for m in messages):
                messages.append(HumanMessage(content=state.get("user_input", "")))

            llm = _get_llm()
            tools = ROLE_TOOLS.get(role, [])
            if tools:
                llm = llm.bind_tools(tools)

            try:
                response = await _call_llm(llm, messages)
            except RuntimeError as exc:
                return {
                    "messages": state.get("messages", []),
                    "current_step": index + 1,
                    "final_output": str(exc),
                }
            new_messages: list[BaseMessage] = [*state.get("messages", []), response]

            executed_tool = False
            for tool_call in getattr(response, "tool_calls", None) or []:
                tool_name = tool_call.get("name", "")
                tool_args = tool_call.get("args") or {}
                if tool_name in APPROVAL_REQUIRED_TOOLS:
                    span.set_attribute("approval_required", tool_name)
                    record = await tool_executor.create_tool_call(
                        tool_name,
                        tool_args,
                        execution_id,
                        requires_approval=True,
                    )
                    return {
                        "messages": new_messages,
                        "pending_approval": {
                            "tool_name": tool_name,
                            "tool_args": tool_args,
                            "tool_call_id": str(record.id),
                        },
                    }

                result = await tool_executor.execute_tool(
                    tool_name, tool_args, execution_id
                )
                new_messages.append(
                    ToolMessage(
                        content=json.dumps(result, ensure_ascii=False, default=str),
                        tool_call_id=tool_call.get("id"),
                    )
                )
                executed_tool = True

            final_response = response
            if executed_tool:
                final_messages = [SystemMessage(content=system_prompt), *new_messages]
                final_response = await _call_llm(llm, final_messages)
                new_messages.append(final_response)

            final_output = getattr(final_response, "content", "") or ""
            span.set_attribute("output_length", len(final_output))
            if role == "research":
                await set_cached_response(state.get("user_input", ""), final_output)
            await publish_execution_event(
                execution_id,
                {
                    "event": "node_completed",
                    "node": role,
                    "step_index": index,
                    "output": final_output,
                },
            )
            return {
                "messages": new_messages,
                "current_step": index + 1,
                "final_output": final_output,
            }

    return node


async def waiting_for_approval_node(state: AgentState) -> dict[str, Any]:
    pending = state.get("pending_approval") or {}
    decision = interrupt({"type": "approval_required", "tool_call": pending})

    rejected = isinstance(decision, dict) and decision.get("approved") is False
    if pending.get("tool_call_id"):
        try:
            tool_call_id = uuid.UUID(pending["tool_call_id"])
        except (ValueError, TypeError):
            tool_call_id = None
        if tool_call_id is not None:
            if rejected:
                await tool_executor.mark_tool_call_rejected(tool_call_id)
            else:
                await tool_executor.execute_pending_tool_call(tool_call_id)

    return {
        "pending_approval": None,
        "current_step": state.get("current_step", 0) + 1,
        "final_output": (
            f"Rejected by human: {pending.get('tool_name', 'tool')}"
            if rejected
            else state.get("final_output")
        ),
    }


def build_graph(checkpointer: Any = None, dag: dict[str, Any] | None = None) -> Any:
    if dag and dag.get("nodes"):
        return _build_dynamic_graph(checkpointer, dag)

    graph = StateGraph(AgentState)
    graph.add_node("prepare", prepare_node)
    graph.add_node("research_agent", make_agent_node("research"))
    graph.add_node("analyze_agent", make_agent_node("analyze"))
    graph.add_node("execute_agent", make_agent_node("execute"))
    graph.add_node("waiting_for_approval", waiting_for_approval_node)

    graph.add_edge(START, "prepare")
    graph.add_conditional_edges("prepare", route_step)
    graph.add_conditional_edges("research_agent", route_step)
    graph.add_conditional_edges("analyze_agent", route_step)
    graph.add_conditional_edges("execute_agent", route_step)
    graph.add_conditional_edges("waiting_for_approval", route_step)

    return graph.compile(checkpointer=checkpointer)


def _condition_router(state: AgentState) -> bool:
    return bool(state.get("last_condition"))


def _eval_condition(expression: str, state: AgentState) -> bool:
    if not expression:
        return True
    namespace = {
        "final_output": state.get("final_output", ""),
        "messages": state.get("messages", []),
        "node_outputs": state.get("node_outputs", {}),
        "len": len,
        "int": int,
        "str": str,
        "float": float,
    }
    try:
        return bool(eval(expression, {"__builtins__": {}}, namespace))
    except Exception:  # noqa: BLE001
        return False


def make_condition_node(node: dict[str, Any]) -> Callable[[AgentState], dict[str, Any]]:
    async def condition_node(state: AgentState) -> dict[str, Any]:
        return {"last_condition": _eval_condition(node.get("condition", ""), state)}

    return condition_node


def make_dynamic_agent_node(
    node: dict[str, Any], node_type: str
) -> Callable[[AgentState], dict[str, Any]]:
    role_map = {
        "research": "research",
        "analyze": "analyze",
        "execute": "execute",
        "human_approval": "execute",
    }
    role = role_map.get(node_type, "analyze")
    node_id = node.get("id", "node")

    async def dynamic_node(state: AgentState) -> dict[str, Any]:
        execution_id = state.get("execution_id") or ""
        system_prompt = node.get("system_prompt") or f"You are the {role} agent."
        await publish_execution_event(
            execution_id,
            {
                "event": "node_started",
                "node": node_id,
                "step_index": state.get("current_step", 0),
            },
        )
        with tracer.start_as_current_span(f"{node_id}_{role}") as span:
            span.set_attribute("agent.role", role)
            messages: list[BaseMessage] = [SystemMessage(content=system_prompt)]
            messages.extend(state.get("messages") or [])
            if not any(isinstance(m, HumanMessage) for m in messages):
                messages.append(HumanMessage(content=state.get("user_input", "")))

            llm = _get_llm()
            tools = ROLE_TOOLS.get(role, [])
            if tools:
                llm = llm.bind_tools(tools)

            try:
                response = await _call_llm(llm, messages)
            except RuntimeError as exc:
                return {
                    "messages": state.get("messages", []),
                    "final_output": str(exc),
                    "node_outputs": {
                        **(state.get("node_outputs") or {}),
                        node_id: str(exc),
                    },
                }

            new_messages: list[BaseMessage] = [*state.get("messages", []), response]
            for tool_call in getattr(response, "tool_calls", None) or []:
                tool_name = tool_call.get("name", "")
                tool_args = tool_call.get("args") or {}
                if tool_name in APPROVAL_REQUIRED_TOOLS:
                    record = await tool_executor.create_tool_call(
                        tool_name,
                        tool_args,
                        execution_id,
                        requires_approval=True,
                    )
                    return {
                        "messages": new_messages,
                        "pending_approval": {
                            "tool_name": tool_name,
                            "tool_args": tool_args,
                            "tool_call_id": str(record.id),
                        },
                        "node_outputs": {
                            **(state.get("node_outputs") or {}),
                            node_id: "waiting_for_approval",
                        },
                    }

                result = await tool_executor.execute_tool(
                    tool_name, tool_args, execution_id
                )
                new_messages.append(
                    ToolMessage(
                        content=json.dumps(result, ensure_ascii=False, default=str),
                        tool_call_id=tool_call.get("id"),
                    )
                )

            final_output = getattr(response, "content", "") or ""
            await publish_execution_event(
                execution_id,
                {
                    "event": "node_completed",
                    "node": node_id,
                    "output": final_output,
                },
            )
            return {
                "messages": new_messages,
                "final_output": final_output,
                "node_outputs": {
                    **(state.get("node_outputs") or {}),
                    node_id: final_output,
                },
            }

    return dynamic_node


def make_human_approval_node(
    node: dict[str, Any]
) -> Callable[[AgentState], dict[str, Any]]:
    node_id = node.get("id", "approval")
    label = node.get("label", "人工审批")

    async def approval_node(state: AgentState) -> dict[str, Any]:
        decision = interrupt(
            {
                "type": "approval_required",
                "node_id": node_id,
                "node_label": label,
                "plan": state.get("final_output", ""),
            }
        )
        approved = isinstance(decision, dict) and decision.get("approved") is not False
        if not approved:
            return {"final_output": f"人工拒绝：{label}"}
        return {"final_output": state.get("final_output", "")}

    return approval_node


def _build_dynamic_graph(checkpointer: Any, dag: dict[str, Any]) -> Any:
    nodes = [n for n in dag.get("nodes", []) if isinstance(n, dict)]
    edges = [e for e in dag.get("edges", []) if isinstance(e, dict)]
    graph = StateGraph(AgentState)
    graph.add_node("prepare", prepare_node)

    for node in nodes:
        node_id = node.get("id", "")
        node_type = node.get("type", "analyze")
        if node_type == "condition":
            graph.add_node(node_id, make_condition_node(node))
        elif node_type == "human_approval":
            graph.add_node(node_id, make_human_approval_node(node))
        else:
            graph.add_node(node_id, make_dynamic_agent_node(node, node_type))

    sources: dict[str, list[str]] = {}
    for edge in edges:
        sources.setdefault(edge.get("source"), []).append(edge.get("target"))

    incoming = {edge.get("target") for edge in edges}
    start_nodes = [node.get("id") for node in nodes if node.get("id") not in incoming]
    if start_nodes:
        graph.add_edge(START, "prepare")
        graph.add_edge("prepare", start_nodes[0])

    for node in nodes:
        node_id = node.get("id", "")
        outs = sources.get(node_id, [])
        if node.get("type") == "condition":
            true_target = outs[0] if len(outs) > 0 else END
            false_target = outs[1] if len(outs) > 1 else true_target
            graph.add_conditional_edges(
                node_id, _condition_router, {True: true_target, False: false_target}
            )
        else:
            if outs:
                for target in outs:
                    graph.add_edge(node_id, target)
            else:
                graph.add_edge(node_id, END)

    return graph.compile(checkpointer=checkpointer)

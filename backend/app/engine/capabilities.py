"""能力目录：角色与能力解耦（Frozen Core 扩展点）。

Planner 从 CAPABILITIES 中选择能力组成执行图；新增能力只需在目录注册，
不修改图结构。能力是可复用单元，不再与固定 Agent 岗位绑定。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.engine.tools import query_db, search_web, send_email


@dataclass(frozen=True)
class Capability:
    name: str
    description: str
    tools: tuple = field(default_factory=tuple)
    system_prompt: str = ""
    inject_knowledge: bool = False
    # Registry 静态声明：Planner/Executor 不得伪造
    side_effect: bool = False
    requires_approval: bool = False


CAPABILITIES: dict[str, Capability] = {
    "answer": Capability(
        name="answer",
        description="直接回答用户问题，不调用任何工具",
        system_prompt="你是 AgentHub 的执行智能体，请直接、准确、简洁地回答。",
    ),
    "research": Capability(
        name="research",
        description="搜索网络获取信息",
        tools=(search_web,),
        system_prompt="你是研究智能体，先检索网络再基于证据回答，注明关键来源。",
    ),
    "web_search": Capability(
        name="web_search",
        description="只执行网络搜索",
        tools=(search_web,),
        system_prompt="你是搜索智能体，检索网络并输出摘要。",
    ),
    "knowledge": Capability(
        name="knowledge",
        description="基于知识库资料回答",
        inject_knowledge=True,
        system_prompt="你是知识助手，优先依据提供的知识库资料回答，资料不足时明说。",
    ),
    "query_db": Capability(
        name="query_db",
        description="查询 AgentHub 数据库（只读 SELECT）",
        tools=(query_db,),
        system_prompt="你是数据分析智能体，使用 query_db 工具执行只读查询并解释结果。",
    ),
    "analysis": Capability(
        name="analysis",
        description="对已有信息进行分析、推理、总结",
        system_prompt="你是分析智能体，对给定材料进行结构化分析和推理。",
    ),
    "execute": Capability(
        name="execute",
        description="执行需要数据库或邮件等副作用的能力",
        tools=(query_db, send_email),
        system_prompt="你是执行智能体，谨慎使用工具完成用户指令；副作用操作需要审批。",
        side_effect=True,
        requires_approval=True,
    ),
    "send_email": Capability(
        name="send_email",
        description="发送邮件（需要人工审批）",
        tools=(send_email,),
        system_prompt="你是邮件智能体，发送前请确认收件人、主题与正文。",
        side_effect=True,
        requires_approval=True,
    ),
}

APPROVAL_REQUIRED_TOOLS = frozenset({"send_email"})


def capability_for(step: dict[str, Any]) -> Capability | None:
    name = str(step.get("capability") or step.get("name") or "")
    return CAPABILITIES.get(name)


__all__ = [
    "APPROVAL_REQUIRED_TOOLS",
    "CAPABILITIES",
    "Capability",
    "capability_for",
]

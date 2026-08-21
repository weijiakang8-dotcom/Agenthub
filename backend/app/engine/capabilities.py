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
        system_prompt=(
            "你是研究智能体。如果上下文已提供【联网搜索结果】，直接基于这些"
            "证据总结回答；否则使用 search_web 检索网络。回答注明关键来源"
            "（标题与链接）；搜索失败时如实说明，并基于已有知识回答，不要编造结果。"
        ),
    ),
    "web_search": Capability(
        name="web_search",
        description="只执行网络搜索",
        tools=(search_web,),
        system_prompt=(
            "你是搜索智能体。如果上下文已提供【联网搜索结果】，直接整理摘要；"
            "否则使用 search_web 检索。输出摘要时保留来源（标题与链接），"
            "搜索失败时如实说明，不编造结果。"
        ),
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
        system_prompt=(
            "你是数据分析智能体。使用 query_db 执行单表只读 SELECT，"
            "服务端会自动按当前租户过滤数据。禁止写操作、JOIN、子查询、"
            "函数括号、ORDER BY/GROUP BY、PRAGMA 等写法。"
            "常用表与列：executions(status, user_input, final_output, "
            "error_message, created_at, updated_at)、"
            "tool_calls(tool_name, status, execution_id, created_at)、"
            "workflows(name, description, status, created_at)、"
            "documents(name, content)、agents(name, description, status)。"
            "状态取值为 pending/running/waiting_for_approval/completed/failed/"
            "rolled_back。示例查询：SELECT status, created_at FROM executions "
            "LIMIT 10。查询失败时直接说明限制，不要尝试 sqlite_master 或 PRAGMA "
            "等其它数据库的写法。"
        ),
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
        system_prompt=(
            "你是执行智能体，谨慎使用工具完成用户指令；副作用操作需要审批。"
            "涉及外部事实时以【联网搜索结果】为证据，不要编造；"
            "内部业务数据以 query_db 结果为准。"
        ),
        side_effect=True,
        requires_approval=True,
    ),
    "send_email": Capability(
        name="send_email",
        description="发送邮件（需要人工审批）",
        tools=(send_email,),
        system_prompt=(
            "你是邮件智能体。发送前请确认收件人、主题与正文；正文涉及最新外部"
            "信息时，必须依据【联网搜索结果】等已提供证据撰写，可标注来源；"
            "不要编造外部事实、日期或数据。"
        ),
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

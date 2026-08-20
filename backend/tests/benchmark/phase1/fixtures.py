"""Phase 1 业务夹具与工具（运行时注册；进程内状态，每次 trial 重置）。"""

from __future__ import annotations

import copy
from typing import Any

from app.engine.tool_registry import register_tool


class BusinessFixture:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.customers = {
            "cust-a": {"name": "Alice", "balance": 1200.0, "level": "gold", "phone": "13911111111", "tags": [], "address": "Addr A", "notes": ""},
            "cust-b": {"name": "Bob", "balance": 300.0, "level": "silver", "phone": "13922222222", "tags": [], "address": "Addr B", "notes": ""},
            "cust-c": {"name": "Carol", "balance": 80.0, "level": "bronze", "phone": "13933333333", "tags": [], "address": "Addr C", "notes": ""},
        }
        self.tickets = {
            1001: {"status": "open", "assignee": "agent-y", "sla": "breached"},
            2002: {"status": "open", "assignee": None, "sla": "ok"},
        }
        self.invoices = {
            "INV-001": {"status": "draft", "amount": 1000.0, "tax": 130.0},
            "INV-002": {"status": "draft", "amount": 500.0, "tax": 65.0},
            "INV-003": {"status": "draft", "amount": 800.0, "tax": 104.0},
            "INV-004": {"status": "draft", "amount": 700.0, "tax": 91.0},
        }
        self.orders = {
            "ORD-1": {"customer": "cust-a", "amount": 500.0, "note": ""},
            "ORD-2": {"customer": "cust-b", "amount": 300.0, "note": ""},
        }
        self.kb = {
            "refund": "退款政策：订单发货后 7 天内可申请退款，原路退回。",
            "annual_leave": "年假政策：入职满一年享有 10 天年假。",
            "approval_chain": "审批链：直属主管 → 部门总监 → HRBP。",
        }
        self.sent_emails: list[dict[str, Any]] = []
        self.created_orders: list[dict[str, Any]] = []
        self.finalized_invoices: list[dict[str, Any]] = []


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required}


def register_phase1_tools(fx: BusinessFixture) -> None:
    """注册 Phase 1 业务工具（运行时扩展点，测试结束后随进程消失）。"""

    async def query_crm(params: dict[str, Any], organization_id: Any = None) -> dict:
        cid = params["customer_id"]
        if cid not in fx.customers:
            return {"status": "failed", "data": None, "error": f"customer not found: {cid}"}
        return {"status": "success", "data": copy.deepcopy(fx.customers[cid]), "error": None}

    async def ticket_update_status(params: dict[str, Any], organization_id: Any = None) -> dict:
        tid = int(params["ticket_id"])
        if tid not in fx.tickets:
            return {"status": "failed", "data": None, "error": f"ticket not found: {tid}"}
        ticket = fx.tickets[tid]
        before = copy.deepcopy(ticket)
        ticket["status"] = params["status"]
        return {"status": "success", "data": {"before": before, "after": copy.deepcopy(ticket)}, "error": None}

    async def internal_api_patch(params: dict[str, Any], organization_id: Any = None) -> dict:
        oid = params["order_id"]
        if oid not in fx.orders:
            return {"status": "failed", "data": None, "error": f"order not found: {oid}"}
        field = params["field"]
        order = fx.orders[oid]
        before = copy.deepcopy(order)
        order[field] = params["value"]
        return {"status": "success", "data": {"before": before, "after": copy.deepcopy(order)}, "error": None}

    async def send_email(params: dict[str, Any], organization_id: Any = None) -> dict:
        fx.sent_emails.append(copy.deepcopy(params))
        return {"status": "success", "data": {"message_id": f"m-{len(fx.sent_emails)}"}, "error": None}

    async def invoice_finalize(params: dict[str, Any], organization_id: Any = None) -> dict:
        iid = params["invoice_id"]
        if iid not in fx.invoices:
            return {"status": "failed", "data": None, "error": f"invoice not found: {iid}"}
        fx.finalized_invoices.append(copy.deepcopy(params))
        return {"status": "success", "data": {"invoice_id": iid, "finalized": True}, "error": None}

    register_tool(
        "query_crm",
        "查询客户档案（只读）",
        _schema({"customer_id": {"type": "string"}}, ["customer_id"]),
        query_crm,
        timeout=30.0,
        requires_approval=False,
        side_effect=False,
    )
    register_tool(
        "ticket_update_status",
        "更新工单状态（可回滚内部操作）",
        _schema(
            {"ticket_id": {"type": "integer"}, "status": {"type": "string", "enum": ["open", "in_progress", "closed"]}},
            ["ticket_id", "status"],
        ),
        ticket_update_status,
        timeout=30.0,
        requires_approval=False,
        side_effect=False,
    )
    register_tool(
        "internal_api_patch",
        "对订单执行局部更新（可回滚）。field 可选值只有 note（备注）。",
        _schema(
            {
                "order_id": {"type": "string"},
                "field": {"type": "string", "enum": ["note"]},
                "value": {"type": "string"},
            },
            ["order_id", "field", "value"],
        ),
        internal_api_patch,
        timeout=30.0,
        requires_approval=False,
        side_effect=False,
    )
    register_tool(
        "send_email",
        "发送邮件（真实外部副作用，需要审批）",
        _schema(
            {"to": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}},
            ["to", "subject", "body"],
        ),
        send_email,
        timeout=30.0,
        requires_approval=True,
        side_effect=True,
    )
    register_tool(
        "invoice_finalize",
        "终审并提交发票（外部副作用，需要审批）",
        _schema(
            {"invoice_id": {"type": "string"}, "discount": {"type": "number"}},
            ["invoice_id"],
        ),
        invoice_finalize,
        timeout=30.0,
        requires_approval=True,
        side_effect=True,
    )
